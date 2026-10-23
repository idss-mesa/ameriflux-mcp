"""Response cache: in-memory TTL with single-flight and stale-if-error, plus a disk layer.

Ported from edi-mcp (families follow ``cache.ttl_s``; DESIGN.md D22):

* Concurrent misses on one key perform a single fetch.
* An expired entry is served (reported as ``stale``) for up to
  ``cache.stale_if_error_s`` when its refresh fails.
* On stdio a disk layer (``cache.disk_dir``) keeps JSON values across restarts,
  so a restarted server need not refetch the 1.7 MB site catalog. Values pass
  through :func:`~ameriflux_mcp.ameriflux.privacy.strip_emails` before they are
  written, and the ``citations`` family (DOI records list contributor emails) is
  never written to disk.

The AmeriFlux API sends no cache headers and never answers 304 (RESEARCH.md E37,
E53), so freshness is TTL-only.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import tempfile
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeVar
from urllib.parse import urlencode

import structlog

from ameriflux_mcp.ameriflux.privacy import strip_emails
from ameriflux_mcp.config import CacheConfig

T = TypeVar("T")

CacheFamily = Literal[
    "catalog",
    "availability",
    "fluxnet2015",
    "variables",
    "citations",
    "dictionaries",
    "heights",
    "coverage",
]
CacheHit = Literal["hit", "miss", "stale", "disk", "bypass"]

FAMILY_CAPS: dict[str, int] = {
    "catalog": 4,
    "availability": 64,
    "fluxnet2015": 16,
    "variables": 8,
    "citations": 512,
    "dictionaries": 16,
    "heights": 4,
    "coverage": 8,
}
#: Families never written to disk (DOI records carry contributor emails).
MEMORY_ONLY: frozenset[str] = frozenset({"citations"})
DISK_FORMAT = 1

log = structlog.get_logger("ameriflux_mcp.cache")


@dataclass
class _Entry:
    value: Any
    expires_at: float


@dataclass
class CacheStats:
    entries: int
    hits: int
    misses: int
    stale_served: int
    disk_hits: int
    disk_dir: str | None
    families: dict[str, int] = field(default_factory=dict)


def cache_key(method: str, url: str, params: Mapping[str, Any] | None = None) -> str:
    """Canonical key: method, URL without query, sorted params."""
    items = sorted((k, str(v)) for k, v in (params or {}).items() if v is not None)
    return f"{method.upper()} {url}?{urlencode(items)}"


class DiskCache:
    """JSON files under ``<dir>/<family>/<sha256>.json`` with wall-clock expiry."""

    def __init__(self, directory: Path, *, wall_clock: Callable[[], float] = time.time) -> None:
        self.directory = directory
        self._wall = wall_clock

    def _path(self, family: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.directory / family / f"{digest}.json"

    def read(self, family: str, key: str) -> tuple[Any, float] | None:
        """``(value, expires_at)`` or ``None`` (missing, unreadable, other key or format)."""
        path = self._path(family, key)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if (
            not isinstance(record, dict)
            or record.get("format") != DISK_FORMAT
            or record.get("key") != key
            or not isinstance(record.get("expiresAt"), (int, float))
        ):
            return None
        return record.get("value"), float(record["expiresAt"])

    def write(self, family: str, key: str, value: Any, ttl_s: float) -> None:
        if family in MEMORY_ONLY:
            return
        path = self._path(family, key)
        record = {
            "format": DISK_FORMAT,
            "key": key,
            "storedAt": self._wall(),
            "expiresAt": self._wall() + ttl_s,
            "value": strip_emails(value),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(record, fh, separators=(",", ":"), ensure_ascii=False)
            os.replace(tmp, path)
        except OSError as exc:  # a read-only or full disk must never fail a tool call
            log.warning("cache.disk_write_failed", family=family, error=type(exc).__name__)
            with contextlib.suppress(OSError, UnboundLocalError):
                os.unlink(tmp)

    def clear(self, family: str | None = None) -> int:
        removed = 0
        families = [family] if family else [p.name for p in self.directory.glob("*") if p.is_dir()]
        for fam in families:
            for path in (self.directory / fam).glob("*.json"):
                with contextlib.suppress(OSError):
                    path.unlink()
                    removed += 1
        return removed


class TTLCache:
    def __init__(
        self,
        cfg: CacheConfig,
        *,
        disk_dir: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._cfg = cfg
        self._clock = clock
        self._wall = wall_clock
        self.disk = DiskCache(disk_dir, wall_clock=wall_clock) if disk_dir else None
        self._data: dict[str, OrderedDict[str, _Entry]] = {f: OrderedDict() for f in FAMILY_CAPS}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self.hits = 0
        self.misses = 0
        self.stale_served = 0
        self.disk_hits = 0

    def ttl_for(self, family: CacheFamily) -> float:
        return float(getattr(self._cfg.ttl_s, family))

    def _from_disk(self, family: CacheFamily, key: str) -> tuple[Any, float] | None:
        """A disk value and its remaining lifetime in seconds (negative when expired)."""
        if self.disk is None or family in MEMORY_ONLY:
            return None
        found = self.disk.read(family, key)
        if found is None:
            return None
        value, expires_at = found
        return value, expires_at - self._wall()

    async def get_or_fetch(
        self,
        family: CacheFamily,
        key: str,
        fetch: Callable[[], Awaitable[T]],
        *,
        ttl_s: float | None = None,
    ) -> tuple[T, CacheHit]:
        ttl = self.ttl_for(family) if ttl_s is None else float(ttl_s)
        if not self._cfg.enabled or ttl <= 0:
            return await fetch(), "bypass"

        entry = self._data[family].get(key)
        if entry is not None and self._clock() < entry.expires_at:
            self.hits += 1
            self._data[family].move_to_end(key)
            return entry.value, "hit"

        lock = self._locks.setdefault((family, key), asyncio.Lock())
        try:
            async with lock:
                entry = self._data[family].get(key)
                now = self._clock()
                if entry is not None and now < entry.expires_at:
                    self.hits += 1
                    return entry.value, "hit"
                disk = self._from_disk(family, key)
                if disk is not None and disk[1] > 0:
                    self.disk_hits += 1
                    self._remember(family, key, disk[0], disk[1])
                    return disk[0], "disk"
                self.misses += 1
                try:
                    value = await fetch()
                except Exception:
                    stale = self._stale(family, entry, disk, now)
                    if stale is not None:
                        return stale, "stale"
                    raise
                self.put(family, key, value, ttl_s=ttl)
                return value, "miss"
        finally:
            if not lock.locked():
                self._locks.pop((family, key), None)

    def _stale(
        self,
        family: CacheFamily,
        entry: _Entry | None,
        disk: tuple[Any, float] | None,
        now: float,
    ) -> Any:
        window = self._cfg.stale_if_error_s
        if entry is not None and now - entry.expires_at <= window:
            age = now - entry.expires_at
            value = entry.value
        elif disk is not None and -disk[1] <= window:
            age = -disk[1]
            value = disk[0]
        else:
            return None
        self.stale_served += 1
        log.warning("cache.stale_served", family=family, age_s=round(age, 1))
        return value

    def _remember(self, family: CacheFamily, key: str, value: Any, ttl_s: float) -> None:
        bucket = self._data[family]
        bucket[key] = _Entry(value=value, expires_at=self._clock() + ttl_s)
        bucket.move_to_end(key)
        while len(bucket) > FAMILY_CAPS[family]:
            bucket.popitem(last=False)
        while sum(len(b) for b in self._data.values()) > self._cfg.max_entries:
            max(self._data.values(), key=len).popitem(last=False)

    def put(self, family: CacheFamily, key: str, value: Any, *, ttl_s: float) -> None:
        if not self._cfg.enabled or ttl_s <= 0:
            return
        self._remember(family, key, value, ttl_s)
        if self.disk is not None:
            self.disk.write(family, key, value, ttl_s)

    def invalidate(self, family: CacheFamily | None = None) -> int:
        removed = 0
        for fam in [family] if family else list(self._data):
            removed += len(self._data[fam])
            self._data[fam].clear()
        if self.disk is not None:
            removed += self.disk.clear(family)
        return removed

    def stats(self) -> CacheStats:
        families = {name: len(bucket) for name, bucket in self._data.items() if bucket}
        return CacheStats(
            entries=sum(families.values()),
            hits=self.hits,
            misses=self.misses,
            stale_served=self.stale_served,
            disk_hits=self.disk_hits,
            disk_dir=str(self.disk.directory) if self.disk else None,
            families=families,
        )


__all__ = [
    "MEMORY_ONLY",
    "CacheFamily",
    "CacheHit",
    "CacheStats",
    "DiskCache",
    "TTLCache",
    "cache_key",
]
