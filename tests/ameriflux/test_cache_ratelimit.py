from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from ameriflux_mcp.ameriflux.cache import DiskCache, TTLCache, cache_key
from ameriflux_mcp.ameriflux.ratelimit import MAX_WAIT_S, RateLimiter
from ameriflux_mcp.config import CacheConfig
from ameriflux_mcp.errors import ToolError
from tests.ameriflux.test_client import FakeTime


def make_cache(fake: FakeTime, disk: Path | None = None, **cfg: object) -> TTLCache:
    return TTLCache(
        CacheConfig.model_validate(cfg),
        disk_dir=disk,
        clock=fake.clock,
        wall_clock=fake.wall_clock,
    )


def test_cache_key_is_canonical() -> None:
    assert cache_key("get", "https://x/a", {"b": 2, "a": 1, "c": None}) == "GET https://x/a?a=1&b=2"


async def test_hit_miss_expiry() -> None:
    fake = FakeTime()
    cache = make_cache(fake)
    calls = 0

    async def fetch() -> list[int]:
        nonlocal calls
        calls += 1
        return [calls]

    assert await cache.get_or_fetch("variables", "k", fetch) == ([1], "miss")
    assert await cache.get_or_fetch("variables", "k", fetch) == ([1], "hit")
    fake.advance(86401)
    assert await cache.get_or_fetch("variables", "k", fetch) == ([2], "miss")
    assert cache.stats().hits == 1 and cache.stats().misses == 2


async def test_single_flight() -> None:
    cache = make_cache(FakeTime())
    calls = 0

    async def fetch() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "v"

    results = await asyncio.gather(*(cache.get_or_fetch("catalog", "k", fetch) for _ in range(5)))
    assert calls == 1 and {r[0] for r in results} == {"v"}


async def test_disabled_cache_bypasses() -> None:
    cache = make_cache(FakeTime(), enabled=False)

    async def fetch() -> int:
        return 1

    assert await cache.get_or_fetch("catalog", "k", fetch) == (1, "bypass")
    assert cache.stats().entries == 0


async def test_stale_window_is_bounded() -> None:
    fake = FakeTime()
    cache = make_cache(fake, stale_if_error_s=60)

    async def good() -> str:
        return "v"

    async def bad() -> str:
        raise RuntimeError("down")

    await cache.get_or_fetch("variables", "k", good)
    fake.advance(86400 + 30)
    assert await cache.get_or_fetch("variables", "k", bad) == ("v", "stale")
    fake.advance(120)
    with pytest.raises(RuntimeError):
        await cache.get_or_fetch("variables", "k", bad)


async def test_disk_layer_round_trip_and_privacy(tmp_path: Path) -> None:
    fake = FakeTime()
    first = make_cache(fake, tmp_path)

    async def fetch() -> dict[str, object]:
        return {"team": [{"name": "A", "team_member_email": "a@x.org"}], "n": 1}

    await first.get_or_fetch("catalog", "k", fetch)
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 1 and "@" not in files[0].read_text()
    second = make_cache(fake, tmp_path)

    async def never() -> dict[str, object]:
        raise AssertionError("should come from disk")

    value, hit = await second.get_or_fetch("catalog", "k", never)
    assert hit == "disk" and value == {"team": [{"name": "A"}], "n": 1}


async def test_disk_stale_if_error_across_restarts(tmp_path: Path) -> None:
    fake = FakeTime()

    async def fetch() -> str:
        return "v"

    async def bad() -> str:
        raise RuntimeError("down")

    await make_cache(fake, tmp_path).get_or_fetch("catalog", "k", fetch)
    fake.advance(21600 + 100)
    assert await make_cache(fake, tmp_path).get_or_fetch("catalog", "k", bad) == ("v", "stale")


async def test_memory_only_family_never_hits_disk(tmp_path: Path) -> None:
    cache = make_cache(FakeTime(), tmp_path)

    async def fetch() -> dict[str, str]:
        return {"DOI_CONTRIBUTOR_EMAIL": "a@x.org"}

    await cache.get_or_fetch("citations", "k", fetch)
    assert list(tmp_path.rglob("*.json")) == []


def test_disk_cache_tolerates_damage(tmp_path: Path) -> None:
    disk = DiskCache(tmp_path)
    disk.write("catalog", "k", [1, 2], 60)
    path = next(tmp_path.rglob("*.json"))
    path.write_text("{not json")
    assert disk.read("catalog", "k") is None
    path.write_text(json.dumps({"format": 1, "key": "other", "expiresAt": 0, "value": 1}))
    assert disk.read("catalog", "k") is None
    assert disk.clear() == 1


def test_disk_write_failure_is_not_fatal(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    disk = DiskCache(blocker)  # a file, not a directory: every write fails
    disk.write("catalog", "k", [1], 60)
    assert disk.read("catalog", "k") is None


async def test_rate_limiter_paces_after_the_burst() -> None:
    fake = FakeTime()
    limiter = RateLimiter(
        requests_per_second=2.0, max_concurrency=4, clock=fake.clock, sleep=fake.sleep
    )
    for _ in range(4):
        async with limiter.slot("amfcdn.lbl.gov"):
            pass
    assert fake.sleeps == []
    async with limiter.slot("amfcdn.lbl.gov"):
        pass
    assert fake.sleeps == [pytest.approx(0.5)]


async def test_website_is_paced_at_one_request_per_15s() -> None:
    fake = FakeTime()
    limiter = RateLimiter(
        requests_per_second=2.0, max_concurrency=4, clock=fake.clock, sleep=fake.sleep
    )
    async with limiter.slot("ameriflux.lbl.gov"):
        pass
    async with limiter.slot("ameriflux.lbl.gov"):
        pass
    assert fake.sleeps == [pytest.approx(15.0)]


async def test_penalty_and_fail_fast() -> None:
    fake = FakeTime()
    limiter = RateLimiter(
        requests_per_second=2.0, max_concurrency=4, clock=fake.clock, sleep=fake.sleep
    )
    limiter.penalize("amfcdn.lbl.gov", 3.0)
    async with limiter.slot("amfcdn.lbl.gov"):
        pass
    assert fake.sleeps == [pytest.approx(3.0)]
    limiter.penalize("amfcdn.lbl.gov", MAX_WAIT_S + 10)
    with pytest.raises(ToolError) as exc:
        async with limiter.slot("amfcdn.lbl.gov"):
            pass
    assert exc.value.code == "rate_limited" and exc.value.details["host"] == "amfcdn.lbl.gov"
