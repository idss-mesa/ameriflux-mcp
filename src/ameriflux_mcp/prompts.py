"""MCP prompts: three task recipes that steer an agent through the tools (build step 8).

``find_flux_sites`` goes from a question to candidate towers, ``plan_site_analysis``
from chosen sites to previewed, cited data (with the download plan shown to the user
before anything is sent), and ``cite_flux_data`` to the citations and obligations a
paper needs. Arguments are validated here; the recipes name only tools that exist.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from mcp import types as t

from ameriflux_mcp.ameriflux.products import normalize_product
from ameriflux_mcp.errors import ToolError
from ameriflux_mcp.tools._common import parse_year_range


@dataclass(frozen=True)
class _Arg:
    name: str
    description: str
    required: bool = False


@dataclass(frozen=True)
class _Prompt:
    name: str
    title: str
    description: str
    arguments: tuple[_Arg, ...]


PROMPTS: tuple[_Prompt, ...] = (
    _Prompt(
        "cite_flux_data",
        "Cite AmeriFlux or FLUXNET data",
        "Citations, acknowledgments and data-policy obligations for the sites a paper used.",
        (
            _Arg("sites", "Comma-separated site IDs, NEON codes or names (up to 50).", True),
            _Arg("product", "BASE-BADM (default), BIF, FLUXNET or FLUXNET2015."),
        ),
    ),
    _Prompt(
        "find_flux_sites",
        "Find flux tower sites for a question",
        "Go from a research question to candidate AmeriFlux and FLUXNET towers with their "
        "years, products and data policy.",
        (
            _Arg("question", "The research question in plain language.", True),
            _Arg("region", "Country, US state, place or bounding box to focus on."),
            _Arg("ecosystem", "IGBP class or ecosystem words (DBF, grassland, wetland …)."),
            _Arg("years", "Years of interest, e.g. 2010-2020."),
            _Arg("variables", "Measured variables or gases, e.g. CH4, SWC, LE."),
        ),
    ),
    _Prompt(
        "plan_site_analysis",
        "Plan an analysis of one or more sites",
        "Availability, variable meanings, a download plan the user approves, previews and "
        "citations for chosen sites.",
        (
            _Arg("sites", "Comma-separated site IDs, NEON codes or names (up to 20).", True),
            _Arg("product", "BASE-BADM, FLUXNET (default) or FLUXNET2015."),
            _Arg("variables", "Comma-separated variable names, e.g. NEE_VUT_REF,LE_F_MDS."),
            _Arg("years", "Years of interest, e.g. 2012-2018."),
        ),
    ),
)

_SITE_LIMITS = {"cite_flux_data": 50, "plan_site_analysis": 20}
_TOKEN = re.compile(r"^[A-Za-z0-9 ._'()/-]{1,80}$")


def list_prompts() -> list[t.Prompt]:
    return [
        t.Prompt(
            name=p.name,
            title=p.title,
            description=p.description,
            arguments=[
                t.PromptArgument(name=a.name, description=a.description, required=a.required)
                for a in p.arguments
            ],
        )
        for p in PROMPTS
    ]


def _split(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


def _validate(prompt: _Prompt, arguments: Mapping[str, str]) -> dict[str, str]:
    known = {a.name for a in prompt.arguments}
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise ToolError(
            "invalid_argument",
            f"Unknown argument(s) for {prompt.name}: {', '.join(unknown)}.",
            details={"valid": sorted(known)},
        )
    values = {k: str(v).strip() for k, v in arguments.items() if v is not None and str(v).strip()}
    missing = [a.name for a in prompt.arguments if a.required and a.name not in values]
    if missing:
        raise ToolError(
            "invalid_argument",
            f"Missing required argument(s) for {prompt.name}: {', '.join(missing)}.",
        )
    if "sites" in values:
        sites = _split(values["sites"])
        limit = _SITE_LIMITS[prompt.name]
        if not sites or len(sites) > limit:
            raise ToolError("invalid_argument", f"sites takes 1 to {limit} comma-separated sites.")
        if any(not _TOKEN.match(s) for s in sites):
            raise ToolError("invalid_argument", "sites holds an unexpected character.")
        values["sites"] = ", ".join(sites)
    if "product" in values:
        values["product"] = normalize_product(values["product"])
        allowed = (
            ("BASE-BADM", "BIF", "FLUXNET", "FLUXNET2015")
            if prompt.name == "cite_flux_data"
            else ("BASE-BADM", "FLUXNET", "FLUXNET2015")
        )
        if values["product"] not in allowed:
            raise ToolError(
                "invalid_argument",
                f"product must be one of {', '.join(allowed)} for {prompt.name}.",
            )
    if "years" in values:
        bounds = parse_year_range(values["years"])
        if bounds:
            first, last = bounds
            values["years"] = str(first) if first == last else f"{first}-{last}"
    if "variables" in values:
        values["variables"] = ", ".join(_split(values["variables"])[:20])
    return values


def _list_literal(text: str) -> str:
    return "[" + ", ".join(repr(s) for s in _split(text)) + "]"


def _find(v: Mapping[str, str]) -> str:
    extra = "".join(
        f"\n- {label}: {v[key]}"
        for key, label in (
            ("region", "Region"),
            ("ecosystem", "Ecosystem"),
            ("years", "Years"),
            ("variables", "Variables"),
        )
        if key in v
    )
    return (
        f"Research question: {v['question']}{extra}\n\n"
        "Use the ameriflux-mcp tools to find eddy-covariance towers that can answer it:\n"
        "1. amf_search_sites with the filters the question implies: igbp (e.g. ['DBF']), "
        "country or state, bbox or near, min_years or years, product, base_variable or gas, "
        "and collection='all' to include FLUXNET2015 and FLUXNET-CH4. Read the facets; follow "
        "page.nextOffset before concluding a list is complete.\n"
        "2. amf_get_site for the 3-5 best candidates: location, ecosystem, climate, data "
        "policy, DOIs and links to NEON (neonSiteCode) or LTER.\n"
        "3. amf_get_availability(sites=[...]) for the years per product and the policy the "
        "selection must follow; explain sites listed in emptySites.\n"
        "4. Finish with a table of site, ecosystem, years per product and policy (CC-BY-4.0, "
        "Legacy, Tier Two), and the caveats from the results' notes. Suggest the "
        "plan_site_analysis prompt for the next step. Do not download anything."
    )


def _plan(v: Mapping[str, str]) -> str:
    sites = _list_literal(v["sites"])
    product = v.get("product", "FLUXNET")
    years = f", years={v['years']!r}" if "years" in v else ""
    names = _list_literal(v["variables"]) if "variables" in v else None
    resolution = "DD" if product in ("FLUXNET", "FLUXNET2015") else "HH"
    describe = (
        f"amf_describe_variables(names={names}, resolution={resolution!r}, site=<one of the sites>)"
        if names
        else f"amf_search_variables(query=<what the analysis needs>, resolution={resolution!r})"
    )
    if product == "FLUXNET2015":
        fetch = (
            "4. FLUXNET2015 files come from fluxnet.org, which needs the user's own login: read "
            "ameriflux://guide/fluxnet2015-access and ask the user to download the zips and add "
            "their folder to local.roots. Never use unofficial copies."
        )
    else:
        fetch = (
            "4. Call amf_list_files(site=...) first: if current files are already on disk, use "
            "them. Otherwise call amf_download_data(sites=" + sites + f", product={product!r}) "
            "WITHOUT confirm. Show the user the plan's disclosure (what AmeriFlux sends to the "
            "site PIs), the eligible sites and the policy obligations, and ask whether to "
            "proceed. Only if the user explicitly agrees, call it again with "
            "accept_data_policy=<the plan's policy.code> and confirm=true. If the plan has "
            "blockers, ask the user to configure the identity (ameriflux://guide/identity); "
            "never write the intended use or description for them. If amf_download_data is not "
            "listed, downloads are off (the default; the user enables them with "
            "AMERIFLUX_MCP_DOWNLOADS__ENABLED=true) or the server is remote: point the user to "
            "the AmeriFlux website and read their files with amf_list_files afterwards."
        )
    return (
        f"Plan an analysis of {product} data for sites {v['sites']}"
        + (f", years {v['years']}" if "years" in v else "")
        + ".\n"
        f"1. amf_get_availability(sites={sites}, products=[{product!r}]{years}): which sites "
        "have data, which years, and the policy the selection must follow.\n"
        f"2. {describe}: units at that resolution, QC meaning and sign conventions.\n"
        "3. amf_get_badm(site=...) for each site's ecosystem, instruments and measurement "
        "heights where they matter.\n"
        f"{fetch}\n"
        "5. amf_preview_data(site=..., product=..., resolution='DD', columns=[...]) for a "
        "summary (missing values, ranges, outOfRange counts); use qc_min_fraction or qc_max "
        "to see the effect of QC filtering, and to_utc=true when comparing sites across time "
        "zones.\n"
        f"6. amf_get_citation(sites={sites}, product={product!r}) and list every citation, "
        "acknowledgment and required obligation the analysis must carry."
    )


def _cite(v: Mapping[str, str]) -> str:
    sites = _list_literal(v["sites"])
    product = v.get("product", "BASE-BADM")
    return (
        f"Cite the {product} data of sites {v['sites']}. Call amf_get_citation(sites={sites}, "
        f"product={product!r}, include_bibtex=true).\n"
        "Present, in this order: every citation exactly as returned (one per site, for the "
        "reference list, not supplementary material); the acknowledgments verbatim; for Legacy "
        "sites, each site's funding; the data-availability sentence with today's date; the "
        "processing references; and the effective policy with its required obligations first "
        "and recommended ones after. If the selection mixes CC-BY-4.0 and Legacy (or Tier One "
        "and Tier Two), say that the stricter policy applies to all. Report any site without a "
        "citation and why."
    )


_RENDER = {"cite_flux_data": _cite, "find_flux_sites": _find, "plan_site_analysis": _plan}


def get_prompt(name: str, arguments: Mapping[str, str] | None = None) -> t.GetPromptResult:
    prompt = next((p for p in PROMPTS if p.name == name), None)
    if prompt is None:
        raise ToolError(
            "not_found",
            f"Unknown prompt {name!r}.",
            details={"name": name, "available": [p.name for p in PROMPTS]},
        )
    values = _validate(prompt, arguments or {})
    return t.GetPromptResult(
        description=prompt.description,
        messages=[
            t.PromptMessage(
                role="user", content=t.TextContent(type="text", text=_RENDER[name](values))
            )
        ],
    )


__all__ = ["PROMPTS", "get_prompt", "list_prompts"]
