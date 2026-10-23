"""The one upstream HTTP client (build step 2: the minimal GET path).

Every request to AmeriFlux goes through :class:`AmeriFluxClient`. In this step
it can only GET JSON from the configured AmeriFlux API host, which is all
``amf_ping(check_api=true)`` needs. Build step 3 adds the per-endpoint
version and envelope table (D4), rate limiting and concurrency (D21), retries,
the response cache (D22) and the full host/path allow-list (D15, D21).

Rules that hold from the start: GET only, no redirects followed, no request
body, a descriptive User-Agent, a byte cap on responses, and endpoint labels
(``GET host/path``, never a query string) for ``source.endpoints``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from ameriflux_mcp import __version__
from ameriflux_mcp.errors import AmeriFluxApiError

if TYPE_CHECKING:
    from ameriflux_mcp.config import UpstreamConfig
    from ameriflux_mcp.context import UpstreamStats

REPO_URL = "https://github.com/idss-mesa/ameriflux-mcp"


def user_agent(suffix: str | None = None) -> str:
    agent = f"ameriflux-mcp/{__version__} (+{REPO_URL})"
    return f"{agent} {suffix}" if suffix else agent


def endpoint_label(method: str, url: str) -> str:
    """``GET host/path``: what ``source.endpoints`` shows (no scheme, query or fragment)."""
    parts = urlsplit(url)
    return f"{method} {parts.hostname}{parts.path}"


class AmeriFluxClient:
    """Async client for the AmeriFlux API (``upstream.api_base_url``)."""

    def __init__(
        self,
        upstream: UpstreamConfig,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = upstream
        self.base_url = upstream.api_base_url.rstrip("/")
        base = urlsplit(self.base_url)
        self.api_host = (base.hostname or "").lower()
        self._api_path = base.path.rstrip("/") + "/"
        self._http = httpx.AsyncClient(
            transport=http_transport,
            timeout=httpx.Timeout(upstream.read_timeout_s, connect=upstream.connect_timeout_s),
            headers={
                "User-Agent": user_agent(upstream.user_agent_suffix),
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            },
            follow_redirects=False,
        )

    def url(self, path: str) -> str:
        """Absolute URL of an API path such as ``v1/fp_var``."""
        return f"{self.base_url}/{path.lstrip('/')}"

    def _check(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme != "https" and parts.hostname not in ("127.0.0.1", "localhost"):
            raise ValueError(f"refusing a non-https upstream URL: {url}")
        if (parts.hostname or "").lower() != self.api_host or not parts.path.startswith(
            self._api_path
        ):
            raise ValueError(f"refusing a request outside the AmeriFlux API: {url}")

    async def get_json(
        self, path: str, *, params: dict[str, str] | None = None, stats: UpstreamStats
    ) -> Any:
        """GET one API path and decode its JSON body."""
        url = self.url(path)
        self._check(url)
        label = endpoint_label("GET", url)
        stats.record_endpoint(label)
        stats.requests += 1
        stats.backend = "amfcdn"
        try:
            response = await self._http.get(url, params=params)
        except httpx.TransportError as exc:
            raise AmeriFluxApiError(0, type(exc).__name__, label, kind="transport") from None
        content_type = response.headers.get("content-type")
        if 300 <= response.status_code < 400:
            # Redirects are never followed: they could lead off the allow-listed host.
            raise AmeriFluxApiError(
                response.status_code,
                "redirect not followed",
                label,
                content_type=content_type,
            )
        if response.status_code >= 400:
            retry_after = response.headers.get("retry-after")
            raise AmeriFluxApiError(
                response.status_code,
                response.text[:500],
                label,
                retry_after_s=float(retry_after) if retry_after and retry_after.isdigit() else None,
                content_type=content_type,
            )
        if len(response.content) > self.config.max_response_bytes:
            raise AmeriFluxApiError(
                response.status_code,
                f"response of {len(response.content)} bytes exceeds the "
                f"{self.config.max_response_bytes}-byte cap",
                label,
                kind="decode",
                content_type=content_type,
            )
        try:
            return response.json()
        except ValueError:
            raise AmeriFluxApiError(
                response.status_code, "not JSON", label, kind="decode", content_type=content_type
            ) from None

    async def aclose(self) -> None:
        await self._http.aclose()


__all__ = ["REPO_URL", "AmeriFluxClient", "endpoint_label", "user_agent"]
