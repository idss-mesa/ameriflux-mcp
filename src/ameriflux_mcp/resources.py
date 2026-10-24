"""MCP resources: static guides and references, derived references and the site template.

* Static (``resources_static/``, ``cacheScope: public``): the identity guide, the
  vocabularies (built from AmeriFlux's own IGBP and Köppen text) and the curated LTER
  crosswalk (draft).
* Derived from the site catalog (``public``: nothing depends on the caller): the NEON
  crosswalk and the ``ameriflux://site/{site_id}`` card (the ``amf_get_site`` payload).
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import unquote

from mcp import types as t

from ameriflux_mcp.errors import AmeriFluxApiError, ToolError, map_api_error
from ameriflux_mcp.logging import registered_secrets

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


@dataclass(frozen=True)
class _Derived:
    uri: str
    mime_type: str
    title: str
    description: str


@dataclass(frozen=True)
class _Template:
    uri_template: str
    pattern: re.Pattern[str]
    name: str
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
    _Static(
        "ameriflux://reference/vocabularies",
        "vocabularies.json",
        "application/json",
        "Vocabularies",
        "IGBP ecosystem classes and Köppen climates in AmeriFlux's wording (with caveats), the "
        "product x policy matrix, policies, intended-use codes and member networks.",
    ),
    _Static(
        "ameriflux://reference/lter-crosswalk",
        "lter-crosswalk.json",
        "application/json",
        "LTER crosswalk (draft)",
        "AmeriFlux sites linked to LTER sites and their EDI scopes, with the basis of each link; "
        "curated, status draft.",
    ),
)
DERIVED: tuple[_Derived, ...] = (
    _Derived(
        "ameriflux://reference/neon-crosswalk",
        "application/json",
        "NEON crosswalk",
        "NEON site codes and their AmeriFlux site IDs (e.g. SRER -> US-xSR), from the live "
        "catalog; NEON's flux product for these towers is DP4.00200.001.",
    ),
)
TEMPLATES: tuple[_Template, ...] = (
    _Template(
        "ameriflux://site/{site_id}",
        re.compile(r"^ameriflux://site/([^/?#]+)$"),
        "site",
        "application/json",
        "AmeriFlux or FLUXNET site",
        "One site's card (the amf_get_site payload). site_id is a site ID such as US-Ha1; NEON "
        "codes and FLUXNET2015 old IDs also resolve.",
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
    ] + [
        t.Resource(
            name=d.uri.rsplit("/", 1)[-1],
            uri=d.uri,
            title=d.title,
            description=d.description,
            mime_type=d.mime_type,
            meta={META_RESOURCE_KIND: "derived"},
        )
        for d in DERIVED
    ]
    return sorted(out, key=lambda r: str(r.uri))


def list_resource_templates() -> list[t.ResourceTemplate]:
    return [
        t.ResourceTemplate(
            name=tpl.name,
            uri_template=tpl.uri_template,
            title=tpl.title,
            description=tpl.description,
            mime_type=tpl.mime_type,
        )
        for tpl in TEMPLATES
    ]


@lru_cache(maxsize=16)
def _static_text(file: str) -> str:
    return (STATIC_DIR / file).read_text(encoding="utf-8")


def known_uris() -> list[str]:
    return [s.uri for s in STATIC] + [d.uri for d in DERIVED] + [t.uri_template for t in TEMPLATES]


def _compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


async def _neon_crosswalk(ctx: ToolContext) -> str:
    from ameriflux_mcp.ameriflux.crosswalk import neon_crosswalk
    from ameriflux_mcp.tools.sites import NEON_FLUX_PRODUCT, site_index

    try:
        index = await site_index(ctx)
    except AmeriFluxApiError as exc:
        raise map_api_error(exc, secrets=registered_secrets()) from None
    rows = neon_crosswalk(index)
    return _compact({"neonDataProduct": NEON_FLUX_PRODUCT, "count": len(rows), "sites": rows})


async def _site_card(site_id: str, ctx: ToolContext) -> str:
    from ameriflux_mcp.registry import get_tool, invoke

    return _compact(await invoke(get_tool("amf_get_site"), {"site": site_id}, ctx))


async def read_resource(uri: str, ctx: ToolContext, *, server: Any = None) -> ResourceContent:
    """Read one ``ameriflux://`` resource; ``ToolError(not_found)`` with ``didYouMean`` otherwise."""
    del server
    for s in STATIC:
        if s.uri == uri:
            return ResourceContent(_static_text(s.file), s.mime_type, STATIC_TTL_MS, "static")
    for d in DERIVED:
        if d.uri == uri:
            return ResourceContent(
                await _neon_crosswalk(ctx), d.mime_type, DERIVED_TTL_MS, "derived"
            )
    for tpl in TEMPLATES:
        match = tpl.pattern.match(uri)
        if match is not None:
            text = await _site_card(unquote(match.group(1)), ctx)
            return ResourceContent(text, tpl.mime_type, DERIVED_TTL_MS, "derived")
    raise ToolError(
        "not_found",
        f"Unknown resource {uri!r}.",
        details={
            "uri": uri,
            "didYouMean": difflib.get_close_matches(uri, known_uris(), n=3, cutoff=0.4),
        },
    )
