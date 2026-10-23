"""Client-side politeness (DESIGN.md D21): one token bucket per host and one semaphore.

AmeriFlux publishes no rate limits (RESEARCH.md E37), so these are local policy:
``upstream.requests_per_second`` (default 2) with a small burst for the API and the
file server, and one request per 15 s to ameriflux.lbl.gov, whose robots.txt asks
for ``Crawl-delay: 15``. A 429 blocks the host for its ``Retry-After``. Waits longer
than ``MAX_WAIT_S`` fail fast with ``rate_limited`` instead of stalling a tool call.
Adapted from neon-mcp's limiter (no per-identity buckets: every API read is
anonymous).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from ameriflux_mcp.errors import ToolError

#: Hosts with a fixed, slower budget: (requests per second, burst).
SLOW_HOSTS: dict[str, tuple[float, float]] = {"ameriflux.lbl.gov": (1 / 15, 1.0)}
MAX_WAIT_S = 30.0


@dataclass
class _Bucket:
    capacity: float
    rate: float
    tokens: float
    updated: float
    blocked_until: float = 0.0


class RateLimiter:
    def __init__(
        self,
        *,
        requests_per_second: float,
        max_concurrency: int,
        burst: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._rate = requests_per_second
        self._burst = burst if burst is not None else float(max(1, max_concurrency))
        self._clock = clock
        self._sleep = sleep
        self._buckets: dict[str, _Bucket] = {}
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def _bucket(self, host: str) -> _Bucket:
        bucket = self._buckets.get(host)
        if bucket is None:
            rate, cap = SLOW_HOSTS.get(host, (self._rate, self._burst))
            bucket = _Bucket(capacity=cap, rate=rate, tokens=cap, updated=self._clock())
            self._buckets[host] = bucket
        return bucket

    @staticmethod
    def _refill(bucket: _Bucket, now: float) -> None:
        bucket.tokens = min(bucket.capacity, bucket.tokens + (now - bucket.updated) * bucket.rate)
        bucket.updated = now

    @asynccontextmanager
    async def slot(self, host: str) -> AsyncIterator[None]:
        """Wait for concurrency and rate headroom on ``host``, then allow one request."""
        async with self._semaphore:
            await self._acquire(host)
            yield

    async def _acquire(self, host: str) -> None:
        bucket = self._bucket(host)
        now = self._clock()
        wait = max(0.0, bucket.blocked_until - now)
        self._refill(bucket, now)
        if bucket.tokens < 1.0:
            wait = max(wait, (1.0 - bucket.tokens) / bucket.rate)
        if wait > MAX_WAIT_S:
            raise ToolError(
                "rate_limited",
                f"ameriflux-mcp is pacing requests to {host}; wait before retrying.",
                details={"retryAfterSeconds": round(wait, 2), "host": host},
            )
        if wait > 0:
            await self._sleep(wait)
            self._refill(bucket, self._clock())
        bucket.tokens -= 1.0

    def penalize(self, host: str, retry_after_s: float) -> None:
        """After a 429, block ``host`` until ``now + retry_after_s``."""
        bucket = self._bucket(host)
        bucket.blocked_until = max(bucket.blocked_until, self._clock() + max(retry_after_s, 0.0))


__all__ = ["MAX_WAIT_S", "SLOW_HOSTS", "RateLimiter"]
