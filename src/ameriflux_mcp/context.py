"""Per-call context handed to every tool handler.

Handlers take ``(args, ctx)``. :class:`ToolContext` carries the process-wide
config, the call's resolved download identity (stdio only, never logged;
DESIGN.md D12, D25), the caller's MRTR capability, the upstream client and an
:class:`UpstreamStats` accumulator that feeds the ``io.ameriflux-mcp/upstream``
result ``_meta``.

HTTP-scoped values (request id) reach the MCP adapter through the context
variables below, set by
:class:`ameriflux_mcp.transport.streamable_http.RequestContextMiddleware`.
Request headers are recorded for routing only; no header is ever read as an
identity.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import structlog

if TYPE_CHECKING:
    from ameriflux_mcp.ameriflux.client import AmeriFluxClient
    from ameriflux_mcp.ameriflux.identity import Identity
    from ameriflux_mcp.config import Config

TransportName = Literal["stdio", "http"]
BackendName = Literal["amfcdn", "fluxdata", "amerifluxr", "datacite"]

current_transport: ContextVar[TransportName | None] = ContextVar(
    "ameriflux_mcp_transport", default=None
)
current_request_headers: ContextVar[Mapping[str, str] | None] = ContextVar(
    "ameriflux_mcp_request_headers", default=None
)
current_request_id: ContextVar[str | None] = ContextVar("ameriflux_mcp_request_id", default=None)


@dataclass
class UpstreamStats:
    """What one tool call cost upstream (reported in result ``_meta``)."""

    requests: int = 0
    cache_hits: int = 0
    backend: BackendName | None = None
    identity_sent: bool = False
    endpoints: list[str] = field(default_factory=list)

    def record_endpoint(self, endpoint: str) -> None:
        if endpoint not in self.endpoints:
            self.endpoints.append(endpoint)

    def as_meta(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "cacheHits": self.cache_hits,
            "backend": self.backend,
            "identitySent": self.identity_sent,
        }


@dataclass(frozen=True)
class Elicited:
    """An MRTR follow-up: the user's answers plus the decoded continuation."""

    responses: Mapping[str, Any]
    state: Mapping[str, Any]


@dataclass(frozen=True)
class ToolContext:
    config: Config
    transport: TransportName
    tool_name: str
    identity: Identity | None
    client_capabilities: Mapping[str, Any]
    elicitation_supported: bool
    elicited: Elicited | None
    request_id: str | None
    stats: UpstreamStats
    log: Any
    #: The process-wide upstream client (``None`` only in bare unit tests).
    client: AmeriFluxClient | None = None


def build_tool_context(
    *,
    config: Config,
    transport: TransportName,
    tool_name: str,
    client_capabilities: Mapping[str, Any] | None = None,
    elicited: Elicited | None = None,
    request_id: str | None = None,
    stats: UpstreamStats | None = None,
    client: AmeriFluxClient | None = None,
) -> ToolContext:
    """Resolve the call's identity and assemble a :class:`ToolContext`."""
    from ameriflux_mcp.ameriflux.identity import resolve_identity

    caps = dict(client_capabilities or {})
    return ToolContext(
        config=config,
        transport=transport,
        tool_name=tool_name,
        identity=resolve_identity(config, transport=transport),
        client_capabilities=caps,
        elicitation_supported="elicitation" in caps,
        elicited=elicited,
        request_id=request_id,
        stats=stats if stats is not None else UpstreamStats(),
        log=structlog.get_logger("ameriflux_mcp.tool").bind(tool=tool_name, request_id=request_id),
        client=client,
    )
