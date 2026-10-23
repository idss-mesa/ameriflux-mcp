from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest

from ameriflux_mcp.ameriflux.client import AmeriFluxClient, endpoint_label, user_agent
from ameriflux_mcp.ameriflux.endpoints import DOI, FP_VAR, SITE_INFO
from ameriflux_mcp.config import CacheConfig, UpstreamConfig
from ameriflux_mcp.context import UpstreamStats
from ameriflux_mcp.errors import AmeriFluxApiError, ToolError, map_api_error
from tests.fixture_router import FixtureRouter, Reply

FP_KEY = "GET amfcdn.lbl.gov/api/v1/fp_var?limits=True"


@dataclass
class FakeTime:
    now: float = 1000.0
    wall: float = 1_800_000_000.0
    sleeps: list[float] = field(default_factory=list)

    def clock(self) -> float:
        return self.now

    def wall_clock(self) -> float:
        return self.wall

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        self.wall += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds
        self.wall += seconds


@pytest.fixture
def fake() -> FakeTime:
    return FakeTime()


def make_client(
    router: FixtureRouter, fake: FakeTime, disk: Path | None, **upstream: object
) -> AmeriFluxClient:
    return AmeriFluxClient(
        UpstreamConfig(**upstream),  # type: ignore[arg-type]
        CacheConfig(),
        disk_dir=disk,
        http_transport=router.transport,
        clock=fake.clock,
        wall_clock=fake.wall_clock,
        sleep=fake.sleep,
    )


@pytest.fixture
async def client(
    router: FixtureRouter, fake: FakeTime, tmp_path: Path
) -> AsyncIterator[AmeriFluxClient]:
    c = make_client(router, fake, tmp_path / "cache")
    yield c
    await c.aclose()


def test_user_agent_and_labels() -> None:
    assert user_agent() == "ameriflux-mcp/0.1.0 (+https://github.com/idss-mesa/ameriflux-mcp)"
    assert user_agent("ci").endswith(" ci")
    assert (
        endpoint_label("GET", "https://AMFCDN.lbl.gov/api/v1/fp_var?limits=True#x")
        == "GET amfcdn.lbl.gov/api/v1/fp_var"
    )


async def test_get_json_records_stats(client: AmeriFluxClient, router: FixtureRouter) -> None:
    stats = UpstreamStats()
    body = await client.get_json("v1/fp_var", params={"limits": "True"}, stats=stats)
    assert len(body) == 145
    assert stats.requests == 1 and stats.backend == "amfcdn"
    assert stats.endpoints == ["GET amfcdn.lbl.gov/api/v1/fp_var"]
    headers = router.calls[0].headers
    assert headers["accept"] == "application/json"
    assert headers["user-agent"].startswith("ameriflux-mcp/0.1.0")


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", "https://amfcdn.lbl.gov/api/v1/data_download"),
        ("PUT", "https://amfcdn.lbl.gov/api/v1/fp_var"),
        ("GET", "http://amfcdn.lbl.gov/api/v1/fp_var"),
        ("GET", "https://example.org/api/v1/fp_var"),
        ("GET", "https://amfcdn.lbl.gov/create"),
        ("GET", "https://ftp.fluxdata.org/.fluxnet_downloads_67934/paper_test/FLX_US-Ha1.zip"),
        ("GET", "https://ftp.fluxdata.org/.fluxnet_downloads_67934/webdoc/../paper_test/x.zip"),
        ("GET", "https://ftp.fluxdata.org/.fluxnet_downloads_67934/FLUXNET2015/x.zip"),
        ("GET", "https://ameriflux.lbl.gov/data/data-download-log/"),
        ("GET", "https://fluxnet.org/data/download-historical-data/"),
        ("GET", "https://raw.githubusercontent.com/someone/else/main/x.csv"),
    ],
)
def test_allow_list_refuses(client: AmeriFluxClient, method: str, url: str) -> None:
    with pytest.raises(ToolError) as exc:
        client.check_request(method, url)
    assert exc.value.code == "download_denied"


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", "https://amfcdn.lbl.gov/api/v2/site_info_display/AmeriFlux"),
        ("HEAD", "https://ftp.fluxdata.org/.ameriflux_downloads/FLUXNET/AMF_AR-Bal.zip"),
        ("GET", "https://ftp.fluxdata.org/.fluxnet_downloads_67934/webdoc/variable_codes.csv"),
        ("GET", "https://ameriflux.lbl.gov/data/measurement-height/"),
        (
            "GET",
            "https://raw.githubusercontent.com/chuhousen/amerifluxr/master/data-summary/x.csv",
        ),
        ("GET", "https://api.datacite.org/dois/10.17190/AMF/1246059"),
    ],
)
def test_allow_list_admits(client: AmeriFluxClient, method: str, url: str) -> None:
    client.check_request(method, url)


async def test_refused_requests_open_no_connection(
    client: AmeriFluxClient, router: FixtureRouter
) -> None:
    with pytest.raises(ToolError):
        await client.request(
            "GET",
            "https://ftp.fluxdata.org/.fluxnet_downloads_67934/paper_test/x.zip",
            stats=UpstreamStats(),
        )
    assert router.calls == []


async def test_fetch_unwraps_and_caches(client: AmeriFluxClient, router: FixtureRouter) -> None:
    first = UpstreamStats()
    rows = await client.fetch(SITE_INFO, stats=first)
    assert {r["site_id"] for r in rows} >= {"US-Ha1", "CA-Let", "US-xSR"}
    assert first.requests == 1 and first.cache_hits == 0
    second = UpstreamStats()
    again = await client.fetch(SITE_INFO, stats=second)
    assert again is rows
    assert second.requests == 0 and second.cache_hits == 1 and second.backend == "amfcdn"
    assert second.endpoints == ["GET amfcdn.lbl.gov/api/v2/site_info_display/AmeriFlux"]
    assert len(router.calls) == 1


async def test_disk_cache_survives_a_restart_without_emails(
    router: FixtureRouter, fake: FakeTime, tmp_path: Path
) -> None:
    disk = tmp_path / "cache"
    first = make_client(router, fake, disk)
    rows = await first.fetch(SITE_INFO, stats=UpstreamStats())
    await first.aclose()
    assert any("team_member_email" in m for r in rows for m in r["grp_team_member"])
    stored = "".join(p.read_text() for p in disk.rglob("*.json"))
    assert "team_member_email" not in stored and "@" not in stored

    second = make_client(router, fake, disk)
    stats = UpstreamStats()
    again = await second.fetch(SITE_INFO, stats=stats)
    await second.aclose()
    assert len(router.calls) == 1  # served from disk
    assert stats.cache_hits == 1 and len(again) == len(rows)
    assert second.cache_stats().disk_hits == 1


async def test_disk_entries_expire(router: FixtureRouter, fake: FakeTime, tmp_path: Path) -> None:
    disk = tmp_path / "cache"
    first = make_client(router, fake, disk)
    await first.fetch(SITE_INFO, stats=UpstreamStats())
    await first.aclose()
    fake.advance(21600 + 1)
    second = make_client(router, fake, disk)
    await second.fetch(SITE_INFO, stats=UpstreamStats())
    await second.aclose()
    assert len(router.calls) == 2


async def test_citations_never_reach_disk(client: AmeriFluxClient, tmp_path: Path) -> None:
    record = await client.fetch(DOI, stats=UpstreamStats(), site="US-Ha1", product="AmeriFlux")
    assert record["DOI_INFO"]["DOI"] == "10.17190/AMF/1246059"
    assert not (tmp_path / "cache" / "citations").exists()


@pytest.mark.parametrize("product", ["BASE", "BIF"])
async def test_doi_without_a_doi_is_none(client: AmeriFluxClient, product: str) -> None:
    assert await client.fetch(DOI, stats=UpstreamStats(), site="US-Ha1", product=product) is None


async def test_drift_is_reported(client: AmeriFluxClient, router: FixtureRouter) -> None:
    router.add(FP_KEY, Reply.json([{"Name": "FC", "Type": "GASES"}]))
    with pytest.raises(AmeriFluxApiError) as exc:
        await client.fetch(FP_VAR, stats=UpstreamStats(), use_cache=False)
    assert exc.value.kind == "drift" and "Units" in exc.value.missing
    mapped = map_api_error(exc.value)
    assert mapped.code == "upstream_error"
    assert mapped.details["drift"]["endpoint"] == "GET amfcdn.lbl.gov/api/v1/fp_var"


async def test_retries_5xx_with_backoff(
    client: AmeriFluxClient, router: FixtureRouter, fake: FakeTime
) -> None:
    router.inject(Reply(503, b"busy", "text/plain"), times=2)
    stats = UpstreamStats()
    rows = await client.fetch(FP_VAR, stats=stats, use_cache=False)
    assert len(rows) == 145 and stats.requests == 3
    backoffs = [s for s in fake.sleeps if s >= 0.5]
    assert len(backoffs) == 2 and backoffs[0] < 0.8


async def test_cloudflare_errors_exhaust_to_upstream_unavailable(
    client: AmeriFluxClient, router: FixtureRouter
) -> None:
    router.inject(Reply(521, b"origin down", "text/html"), times=3)
    with pytest.raises(AmeriFluxApiError) as exc:
        await client.fetch(FP_VAR, stats=UpstreamStats(), use_cache=False)
    assert exc.value.status == 521
    assert map_api_error(exc.value).code == "upstream_unavailable"


async def test_429_honours_retry_after(
    client: AmeriFluxClient, router: FixtureRouter, fake: FakeTime
) -> None:
    router.inject(Reply(429, b"slow down", "text/plain", {"retry-after": "2"}))
    await client.fetch(FP_VAR, stats=UpstreamStats(), use_cache=False)
    assert 2.0 in fake.sleeps


async def test_transport_failures_after_retries(
    client: AmeriFluxClient, router: FixtureRouter
) -> None:
    router.inject(httpx.ConnectError, times=3)
    with pytest.raises(AmeriFluxApiError) as exc:
        await client.fetch(FP_VAR, stats=UpstreamStats(), use_cache=False)
    assert exc.value.kind == "transport" and exc.value.status == 0
    assert len(router.calls) == 3


async def test_redirects_are_errors(client: AmeriFluxClient, router: FixtureRouter) -> None:
    router.inject(Reply(302, b"", "text/html", {"location": "https://example.org/"}))
    with pytest.raises(AmeriFluxApiError) as exc:
        await client.fetch(FP_VAR, stats=UpstreamStats(), use_cache=False)
    assert exc.value.status == 302 and exc.value.detail == "redirect not followed"
    assert len(router.calls) == 1


async def test_recorded_error_bodies(client: AmeriFluxClient) -> None:
    with pytest.raises(AmeriFluxApiError) as missing:
        await client.get_json("v1/does_not_exist", stats=UpstreamStats())
    assert missing.value.status == 404 and "Not Found" in missing.value.detail
    with pytest.raises(AmeriFluxApiError) as invalid:
        await client.get_json(
            "v1/data_availability/FLUXNET/FLUXNET2015/Tier2", stats=UpstreamStats()
        )
    mapped = map_api_error(invalid.value)
    assert mapped.code == "invalid_argument" and "Must be one of: TIER2, CCBY4.0." in mapped.message


async def test_unvalidated_ameriflux_enum_returns_empty_rows(client: AmeriFluxClient) -> None:
    rows = await client.get_json(
        "v1/data_availability/AmeriFlux/BASE-BADM/Tier2", stats=UpstreamStats()
    )
    assert rows and all(r["publish_years"] == [] for r in rows)  # why D6 validates locally


async def test_byte_cap(router: FixtureRouter, fake: FakeTime) -> None:
    small = make_client(router, fake, None, max_response_bytes=2048)
    with pytest.raises(AmeriFluxApiError) as exc:
        await small.fetch(FP_VAR, stats=UpstreamStats(), use_cache=False)
    await small.aclose()
    assert exc.value.kind == "decode" and "cap" in exc.value.detail


async def test_stale_if_error(
    client: AmeriFluxClient, router: FixtureRouter, fake: FakeTime
) -> None:
    rows = await client.fetch(FP_VAR, stats=UpstreamStats())
    fake.advance(86400 + 5)
    router.inject(Reply(500, b"boom", "text/plain"), times=3)
    stats = UpstreamStats()
    again = await client.fetch(FP_VAR, stats=stats)
    assert again == rows and stats.cache_hits == 1
    assert client.cache_stats().stale_served == 1


async def test_error_text_never_carries_emails(
    client: AmeriFluxClient, router: FixtureRouter
) -> None:
    router.inject(Reply(400, b"bad request from someone@example.edu", "text/plain"))
    with pytest.raises(AmeriFluxApiError) as exc:
        await client.get_json("v1/fp_var", stats=UpstreamStats())
    assert "someone@example.edu" not in exc.value.detail
    assert "[email]" in json.dumps(exc.value.detail)
