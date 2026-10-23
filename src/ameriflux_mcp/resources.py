"""MCP resources: static guides (more guides, references and the site template arrive with
the tools that use them).

Static guides are the same for everyone (``cacheScope: public``).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from mcp import types as t

from ameriflux_mcp.errors import ToolError

if TYPE_CHECKING:
    from ameriflux_mcp.context import ToolContext

STATIC_DIR = Path(__file__).parent / "resources_static"
META_RESOURCE_KIND = "io.ameriflux-mcp/kind"
STATIC_TTL_MS = 86_400_000
DERIVED_TTL_MS = 3_600_000


@dataclass(frozen=True)
class ResourceContent:
    text: str
    mime_type: str
    ttl_ms: int
    kind: Literal["static", "derived"]
    cache_scope: Literal["public", "private"] = "public"


@dataclass(frozen=True)
class _Static:
    uri: str
    file: str
    mime_type: str
    title: str
    description: str


STATIC: tuple[_Static, ...] = (
    _Static(
        "ameriflux://guide/identity",
        "identity.md",
        "text/markdown",
        "Download identity",
        "Why AmeriFlux downloads disclose the user's ID, email and intended use to site PIs, how "
        "the user configures it, and the auth_required errors without it.",
    ),
)


def list_resources() -> list[t.Resource]:
    out = [
        t.Resource(
            name=s.uri.rsplit("/", 1)[-1],
            uri=s.uri,
            title=s.title,
            description=s.description,
            mime_type=s.mime_type,
            meta={META_RESOURCE_KIND: "static"},
        )
        for s in STATIC
    ]
    return sorted(out, key=lambda r: str(r.uri))


def list_resource_templates() -> list[t.ResourceTemplate]:
    """``ameriflux://site/{site_id}`` arrives with the site tools (build step 4)."""
    return []


@lru_cache(maxsize=16)
def _static_text(file: str) -> str:
    return (STATIC_DIR / file).read_text(encoding="utf-8")


def known_uris() -> list[str]:
    return [s.uri for s in STATIC]


async def read_resource(uri: str, ctx: ToolContext, *, server: Any = None) -> ResourceContent:
    """Read one ``ameriflux://`` resource; ``ToolError(not_found)`` with ``didYouMean`` otherwise."""
    del ctx, server
    for s in STATIC:
        if s.uri == uri:
            return ResourceContent(_static_text(s.file), s.mime_type, STATIC_TTL_MS, "static")
    raise ToolError(
        "not_found",
        f"Unknown resource {uri!r}.",
        details={
            "uri": uri,
            "didYouMean": difflib.get_close_matches(uri, known_uris(), n=3, cutoff=0.4),
        },
    )
