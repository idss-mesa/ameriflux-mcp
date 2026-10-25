"""``amf_ping``: liveness and capability report."""

from __future__ import annotations

import time
from typing import Any, Literal

from mcp.types import LATEST_PROTOCOL_VERSION
from pydantic import Field

from ameriflux_mcp import __version__
from ameriflux_mcp.ameriflux.endpoints import FP_VAR
from ameriflux_mcp.ameriflux.identity import identity_status
from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.errors import (
    ACCOUNT_PAGE_URL,
    IDENTITY_GUIDE,
    AmeriFluxApiError,
    ToolError,
    map_api_error,
)
from ameriflux_mcp.logging import registered_secrets
from ameriflux_mcp.models.common import AmfInput, AmfOutput, Source, ToolResultBase
from ameriflux_mcp.registry import get_registered_tools, register_tool


class PingIn(AmfInput):
    """``amf_ping`` arguments."""

    check_api: bool = Field(
        False,
        description="Also make one small request to the AmeriFlux API (the FP Standard variable "
        "list) to confirm connectivity.",
    )


class IdentityReport(AmfOutput):
    """The download identity as booleans and profile names, never the values."""

    available: bool = Field(
        description="True when this server may act with an identity (stdio, user ID and email set)."
    )
    reason: Literal["ok", "http", "incomplete"] = Field(
        description="ok; http (a hosted server never uses an identity); incomplete (user ID or "
        "email missing)."
    )
    user_id_configured: bool
    email_configured: bool
    name_configured: bool
    profiles: list[str] = Field(description="Configured profile names (e.g. default).")
    complete_profiles: list[str] = Field(
        description="Profiles with both an intended use and a description."
    )
    is_test_set: bool = Field(
        description="False until is_test is set; downloads refuse until then."
    )
    is_test: bool | None = None


class UpstreamCheck(AmfOutput):
    ok: bool = Field(description="True when the AmeriFlux API answered with the expected shape.")
    endpoint: str
    latency_ms: float
    variables: int | None = Field(None, description="FP Standard variables returned.")
    error: dict[str, Any] | None = Field(
        None, description="The error code and message when the check failed."
    )


class Endpoints(AmfOutput):
    api: str = Field(description="AmeriFlux API base URL.")


class CacheReport(AmfOutput):
    enabled: bool
    disk_dir: str | None = Field(None, description="On-disk cache directory (stdio only).")
    entries: int = Field(description="Entries held in memory.")
    hits: int
    misses: int
    disk_hits: int
    stale_served: int = Field(description="Expired entries served because a refresh failed.")
    catalog_sites: int | None = Field(
        None, description="Sites in the loaded catalog (absent until a tool has loaded it)."
    )


class PingResult(ToolResultBase):
    pong: Literal["ok"] = "ok"
    version: str
    protocol_version: str
    transport: Literal["stdio", "http"]
    identity: IdentityReport
    identity_required_tools: list[str] = Field(
        description="Registered tools that need the download identity (auth_required without it)."
    )
    downloads_enabled: bool
    download_dir: str | None = None
    local_roots: list[str] | None = Field(
        None, description="Directories the local file tools may read (stdio only)."
    )
    endpoints: Endpoints
    cache: CacheReport
    upstream: UpstreamCheck | None = Field(
        None, description="Present when check_api was requested."
    )


async def _check_api(ctx: ToolContext) -> UpstreamCheck:
    if ctx.client is None:  # pragma: no cover - every server builds a client
        raise ToolError("internal_error", "No upstream client is configured.")
    started = time.monotonic()
    error: dict[str, Any] | None = None
    variables: int | None = None
    try:
        # Uncached on purpose: the point is to reach the API now. The FP_VAR endpoint
        # definition also checks the response's shape (drift, DESIGN.md D8).
        rows = await ctx.client.fetch(FP_VAR, stats=ctx.stats, use_cache=False)
        variables = len(rows)
    except AmeriFluxApiError as exc:
        err = map_api_error(exc, secrets=registered_secrets())
        error = {"code": err.code, "message": err.message}
    return UpstreamCheck(
        ok=error is None,
        endpoint=ctx.stats.endpoints[-1] if ctx.stats.endpoints else FP_VAR.path(),
        latency_ms=round((time.monotonic() - started) * 1000, 1),
        variables=variables,
        error=error,
    )


def _cache_report(ctx: ToolContext) -> CacheReport:
    stats = ctx.client.cache_stats() if ctx.client is not None else None
    index = ctx.catalog.peek() if ctx.catalog is not None else None
    return CacheReport(
        enabled=ctx.config.cache.enabled,
        disk_dir=stats.disk_dir if stats else None,
        entries=stats.entries if stats else 0,
        hits=stats.hits if stats else 0,
        misses=stats.misses if stats else 0,
        disk_hits=stats.disk_hits if stats else 0,
        stale_served=stats.stale_served if stats else 0,
        catalog_sites=len(index) if index is not None else None,
    )


@register_tool(
    "amf_ping",
    title="Check ameriflux-mcp status",
    description=(
        "Liveness and capability report: server version, protocol and transport; whether a "
        "download identity is configured (booleans and profile names only, never the values) and "
        "which tools need it; whether downloads are enabled and where files go. With "
        "check_api=true it also makes one small request to the AmeriFlux API to confirm "
        "connectivity. Next: read ameriflux://guide/identity to set up downloads."
    ),
    input_model=PingIn,
    output_model=PingResult,
    surface="core",
    endpoints=["GET amfcdn.lbl.gov/api/v1/fp_var"],
)
async def amf_ping(args: PingIn, ctx: ToolContext) -> PingResult:
    cfg = ctx.config
    upstream = await _check_api(ctx) if args.check_api else None
    downloads = cfg.effective_downloads_enabled(ctx.transport)
    status = identity_status(cfg, transport=ctx.transport)
    identity_tools = sorted(
        s.name
        for s in get_registered_tools(transport=ctx.transport, downloads_enabled=downloads)
        if s.requires_key
    )
    notes: list[str] = []
    steps: list[str] = []
    if ctx.transport == "http":
        notes.append(
            "Hosted (HTTP) server: discovery, variables and citations only. Downloads and local "
            "files need a local (stdio) ameriflux-mcp, and no identity is accepted over HTTP."
        )
    elif not status.available:
        notes.append(
            "No download identity: everything except downloads works. AmeriFlux sends the user "
            "ID, email, intended use and description of every download to the site PIs."
        )
        steps.append(f"Read {IDENTITY_GUIDE} to set up downloads (account: {ACCOUNT_PAGE_URL})")
    elif not status.is_test_set:
        notes.append(
            "AMERIFLUX_MCP_IDENTITY__IS_TEST is unset; downloads refuse until it is true or false."
        )
    if ctx.transport == "stdio" and not downloads:
        notes.append(
            "Downloads are off (the default until AmeriFlux confirms third-party use of its "
            "download request): amf_download_data is not listed. The user turns it on with "
            "AMERIFLUX_MCP_DOWNLOADS__ENABLED=true or --downloads; local files can always be read."
        )
    if upstream is None:
        steps.append("amf_ping(check_api=true) to confirm the AmeriFlux API answers")
    return PingResult(
        version=__version__,
        protocol_version=LATEST_PROTOCOL_VERSION,
        transport=ctx.transport,
        identity=IdentityReport(
            available=status.available,
            reason=status.reason,
            user_id_configured=status.user_id_configured,
            email_configured=status.email_configured,
            name_configured=status.name_configured,
            profiles=status.profiles,
            complete_profiles=status.complete_profiles,
            is_test_set=status.is_test_set,
            is_test=status.is_test,
        ),
        identity_required_tools=identity_tools,
        downloads_enabled=downloads,
        download_dir=str(cfg.downloads.directory) if downloads else None,
        local_roots=[str(p) for p in cfg.local_roots()] if ctx.transport == "stdio" else None,
        endpoints=Endpoints(api=cfg.upstream.api_base_url),
        cache=_cache_report(ctx),
        upstream=upstream,
        notes=notes,
        next_steps=steps,
        source=Source(
            endpoints=list(ctx.stats.endpoints),
            backend="amfcdn" if upstream is not None else "local",
            cached=False,
        ),
    )
