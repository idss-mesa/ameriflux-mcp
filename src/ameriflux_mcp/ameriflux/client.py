"""The one upstream HTTP client.

Every request to AmeriFlux, its file server, the amerifluxr snapshots and DataCite
goes through :class:`AmeriFluxClient`. Rules (DESIGN.md D15, D21, D22, D24):

* **Allow-list.** Each request's host and path prefix is checked against
  :data:`ALLOWED` before any socket opens; ``/.fluxnet_downloads_67934/paper_test/``
  is denied outright (E27). https only.
* **Methods.** GET and HEAD. (The one consented ``data_download`` POST arrives with
  the download tool in build step 7.) No request body, ever.
* **Redirects are never followed**: a 3xx is an error, so a redirect cannot lead
  off the allow-list.
* **Politeness.** A per-host token bucket and one semaphore
  (:class:`~ameriflux_mcp.ameriflux.ratelimit.RateLimiter`); retries with backoff
  on network errors, 5xx (including Cloudflare's 520–527) and 429 (honouring
  ``Retry-After``).
* **Limits and hygiene.** Bodies are read with a byte cap; error text is cut and
  scrubbed of registered secrets and email addresses; endpoint labels
  (``GET host/path``) never carry a query string.
* **Caching.** :meth:`AmeriFluxClient.fetch` unwraps an endpoint's envelope, checks
  its required keys (drift) and caches the result per family, in memory and on
  disk.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx
import structlog

from ameriflux_mcp import __version__
from ameriflux_mcp.ameriflux.cache import CacheStats, TTLCache, cache_key
from ameriflux_mcp.ameriflux.endpoints import Endpoint, unwrap
from ameriflux_mcp.ameriflux.privacy import EMAIL_RE
from ameriflux_mcp.ameriflux.ratelimit import RateLimiter
from ameriflux_mcp.config import CacheConfig
from ameriflux_mcp.errors import AmeriFluxApiError, ToolError, redact
from ameriflux_mcp.logging import registered_secrets

if TYPE_CHECKING:
    from ameriflux_mcp.config import UpstreamConfig
    from ameriflux_mcp.context import BackendName, UpstreamStats

REPO_URL = "https://github.com/idss-mesa/ameriflux-mcp"
log = structlog.get_logger("ameriflux_mcp.http")

#: host -> allowed path prefixes (DESIGN.md D15, D21). The API host is added from config.
ALLOWED: dict[str, tuple[str, ...]] = {
    "amfcdn.lbl.gov": ("/api/",),
    "ftp.fluxdata.org": ("/.ameriflux_downloads/", "/.fluxnet_downloads_67934/webdoc/"),
    "ameriflux.lbl.gov": ("/data/measurement-height/",),
    "raw.githubusercontent.com": ("/chuhousen/amerifluxr/master/data-summary/",),
    "api.datacite.org": ("/dois/",),
}
#: Path fragments refused on every host (the unofficial FLUXNET2015 index, E27).
DENIED_FRAGMENTS: tuple[str, ...] = ("/paper_test/",)
ALLOWED_METHODS = frozenset({"GET", "HEAD"})
SERVICES: dict[str, str] = {
    "amfcdn.lbl.gov": "The AmeriFlux API",
    "ftp.fluxdata.org": "The AmeriFlux file server",
    "ameriflux.lbl.gov": "The AmeriFlux website",
    "raw.githubusercontent.com": "The amerifluxr snapshot repository",
    "api.datacite.org": "DataCite",
}
BACKENDS: dict[str, BackendName] = {
    "amfcdn.lbl.gov": "amfcdn",
    "ftp.fluxdata.org": "fluxdata",
    "raw.githubusercontent.com": "amerifluxr",
    "api.datacite.org": "datacite",
}
_ERROR_BODY_BYTES = 64 * 1024


def user_agent(suffix: str | None = None) -> str:
    agent = f"ameriflux-mcp/{__version__} (+{REPO_URL})"
    return f"{agent} {suffix}" if suffix else agent


def endpoint_label(method: str, url: str) -> str:
    """``GET host/path``: what ``source.endpoints`` shows (no scheme, query or fragment)."""
    parts = urlsplit(url)
    return f"{method} {(parts.hostname or '').lower()}{parts.path}"


@dataclass
class Fetched:
    """One upstream response body (never cached at this level)."""

    body: bytes
    status: int
    content_type: str | None
    endpoint: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


class AmeriFluxClient:
    """Async client for the AmeriFlux API and the few other allow-listed sources."""

    def __init__(
        self,
        upstream: UpstreamConfig,
        cache_config: CacheConfig | None = None,
        *,
        disk_dir: Path | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = upstream
        self.base_url = upstream.api_base_url.rstrip("/")
        base = urlsplit(self.base_url)
        self.api_host = (base.hostname or "").lower()
        self.allowed: dict[str, tuple[str, ...]] = dict(ALLOWED)
        api_prefix = base.path.rstrip("/") + "/"
        self.allowed[self.api_host] = tuple(
            sorted({*self.allowed.get(self.api_host, ()), api_prefix})
        )
        self._clock = clock
        self._sleep = sleep
        self.cache = TTLCache(
            cache_config or CacheConfig(), disk_dir=disk_dir, clock=clock, wall_clock=wall_clock
        )
        self.limiter = RateLimiter(
            requests_per_second=upstream.requests_per_second,
            max_concurrency=upstream.max_concurrency,
            clock=clock,
            sleep=sleep,
        )
        self._http = httpx.AsyncClient(
            transport=http_transport,
            timeout=httpx.Timeout(
                connect=upstream.connect_timeout_s,
                read=upstream.read_timeout_s,
                write=10.0,
                pool=10.0,
            ),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            headers={
                "User-Agent": user_agent(upstream.user_agent_suffix),
                "Accept-Encoding": "gzip",
            },
            follow_redirects=False,
        )

    # ------------------------------------------------------------------ rules

    def url(self, path: str) -> str:
        """Absolute URL of an API path such as ``v1/fp_var``."""
        return f"{self.base_url}/{path.lstrip('/')}"

    def service(self, url: str) -> str:
        host = (urlsplit(url).hostname or "").lower()
        return SERVICES.get(host, "The AmeriFlux API" if host == self.api_host else host)

    def check_request(self, method: str, url: str) -> None:
        """Refuse methods, schemes, hosts and paths outside the allow-list (no I/O)."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        details: dict[str, Any] = {"method": method, "host": host, "path": parts.path}
        if method.upper() not in ALLOWED_METHODS:
            raise ToolError(
                "download_denied", f"Method {method} is not allowed upstream.", details=details
            )
        if parts.scheme != "https" and host not in ("127.0.0.1", "localhost"):
            raise ToolError("download_denied", "Only https URLs are fetched.", details=details)
        segments = parts.path.split("/")
        if ".." in segments or any(frag in parts.path for frag in DENIED_FRAGMENTS):
            raise ToolError(
                "download_denied", "This path is never fetched (DESIGN.md D15).", details=details
            )
        prefixes = self.allowed.get(host)
        if prefixes is None or not any(parts.path.startswith(p) for p in prefixes):
            raise ToolError(
                "download_denied",
                f"{host}{parts.path} is outside ameriflux-mcp's upstream allow-list.",
                details=details,
            )

    # ------------------------------------------------------------------ sending

    async def _backoff(self, attempt: int) -> None:
        retries = self.config.retries
        delay = min(retries.backoff_base_s * (2 ** (attempt - 1)), retries.backoff_max_s)
        await self._sleep(delay + random.uniform(0, 0.25))  # noqa: S311 - jitter, not crypto

    def _retry_after(self, headers: Mapping[str, str]) -> float:
        value = headers.get("retry-after")
        if value is not None:
            try:
                return max(float(value), 0.0)
            except ValueError:
                pass
        return self.config.retries.retry_after_default_s

    def _error(self, status: int, detail: str, url: str, **kw: Any) -> AmeriFluxApiError:
        clean = EMAIL_RE.sub("[email]", redact(detail, registered_secrets()))
        return AmeriFluxApiError(
            status,
            clean.strip()[:300] or "no detail",
            endpoint_label("GET", url),
            service=self.service(url),
            **kw,
        )

    async def _send(
        self,
        method: str,
        url: str,
        params: Mapping[str, str] | None,
        *,
        accept: str | None,
        stats: UpstreamStats,
        read_timeout_s: float | None = None,
    ) -> httpx.Response:
        """One request with pacing and retries; returns an open (streamed) response."""
        self.check_request(method, url)
        host = (urlsplit(url).hostname or "").lower()
        attempts = self.config.retries.max_attempts
        attempt = 0
        while True:
            attempt += 1
            started = self._clock()
            try:
                async with self.limiter.slot(host):
                    request = self._http.build_request(
                        method,
                        url,
                        params=dict(params) if params else None,
                        headers={"Accept": accept} if accept else None,
                    )
                    if read_timeout_s:
                        request.extensions["timeout"] = httpx.Timeout(
                            connect=self.config.connect_timeout_s,
                            read=read_timeout_s,
                            write=10.0,
                            pool=10.0,
                        ).as_dict()
                    response = await self._http.send(request, stream=True)
            except httpx.HTTPError as exc:
                if attempt < attempts:
                    await self._backoff(attempt)
                    continue
                raise self._error(0, type(exc).__name__, url, kind="transport") from None
            stats.requests += 1
            backend = BACKENDS.get(host, "amfcdn" if host == self.api_host else None)
            if backend is not None:
                stats.backend = backend
            log.debug(
                "upstream.http",
                endpoint=endpoint_label(method, url),
                status=response.status_code,
                ms=round((self._clock() - started) * 1000, 1),
                attempt=attempt,
            )
            status = response.status_code
            if status == 429 and attempt < attempts:
                await response.aclose()
                wait = self._retry_after(response.headers)
                self.limiter.penalize(host, wait)
                await self._sleep(wait)
                continue
            if status >= 500 and attempt < attempts:
                await response.aclose()
                await self._backoff(attempt)
                continue
            return response

    async def _read(self, response: httpx.Response, url: str, max_bytes: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        try:
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise self._error(
                        response.status_code,
                        f"response larger than the {max_bytes}-byte cap",
                        url,
                        kind="decode",
                        content_type=_content_type(response),
                    )
                chunks.append(chunk)
        finally:
            await response.aclose()
        return b"".join(chunks)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        accept: str | None = None,
        stats: UpstreamStats,
        max_bytes: int | None = None,
    ) -> Fetched:
        """GET or HEAD ``url``; raises :class:`AmeriFluxApiError` for anything but 2xx."""
        label = endpoint_label(method, url)
        stats.record_endpoint(label)
        response = await self._send(method, url, params, accept=accept, stats=stats)
        status = response.status_code
        content_type = _content_type(response)
        if 300 <= status < 400:
            await response.aclose()
            raise self._error(status, "redirect not followed", url, content_type=content_type)
        if status >= 400:
            body = await self._read(response, url, _ERROR_BODY_BYTES)
            raise self._error(
                status,
                body.decode("utf-8", "replace"),
                url,
                content_type=content_type,
                retry_after_s=self._retry_after(response.headers) if status == 429 else None,
            )
        headers = {k.lower(): v for k, v in response.headers.items()}
        if method.upper() == "HEAD":
            await response.aclose()
            return Fetched(b"", status, content_type, label, headers)
        body = await self._read(response, url, max_bytes or self.config.max_response_bytes)
        return Fetched(body, status, content_type, label, headers)

    # ------------------------------------------------------------------ the API

    async def get_json(
        self, path: str, *, params: Mapping[str, str] | None = None, stats: UpstreamStats
    ) -> Any:
        """GET one API path and decode its JSON body (uncached)."""
        url = self.url(path)
        fetched = await self.request(
            "GET", url, params=params, accept="application/json", stats=stats
        )
        try:
            return json.loads(fetched.body)
        except ValueError:
            raise self._error(
                fetched.status, "not JSON", url, kind="decode", content_type=fetched.content_type
            ) from None

    async def fetch(
        self,
        endpoint: Endpoint,
        *,
        stats: UpstreamStats,
        use_cache: bool = True,
        **params: str,
    ) -> Any:
        """An endpoint's unwrapped rows (or object, or ``None`` for "no DOI"), cached."""
        path = endpoint.path(**params)
        url = self.url(path)
        query = dict(endpoint.query)
        label = endpoint_label("GET", url)

        async def load() -> Any:
            payload = await self.get_json(path, params=query or None, stats=stats)
            return unwrap(endpoint, payload, label)

        if not use_cache:
            return await load()
        stats.record_endpoint(label)
        value, hit = await self.cache.get_or_fetch(
            endpoint.family_for(**params), cache_key("GET", url, query), load
        )
        if hit in ("hit", "stale", "disk"):
            stats.cache_hits += 1
            stats.backend = stats.backend or "amfcdn"
        return value

    def cache_stats(self) -> CacheStats:
        return self.cache.stats()

    async def aclose(self) -> None:
        await self._http.aclose()


def _content_type(response: httpx.Response) -> str | None:
    return (response.headers.get("content-type") or "").split(";")[0].strip() or None


__all__ = [
    "ALLOWED",
    "BACKENDS",
    "DENIED_FRAGMENTS",
    "REPO_URL",
    "AmeriFluxClient",
    "Fetched",
    "endpoint_label",
    "user_agent",
]
