"""Server instructions returned by ``server/discover`` (kept under 1 200 characters)."""

from __future__ import annotations

SERVER_INSTRUCTIONS = (
    "ameriflux-mcp exposes AmeriFlux and FLUXNET eddy-covariance flux tower data: AmeriFlux BASE "
    "and BADM, the AmeriFlux FLUXNET product and FLUXNET2015. Sites are IDs such as US-Ha1 "
    "(country-code, three characters). Typical flow: amf_search_sites -> amf_get_availability "
    "-> amf_describe_variables -> amf_download_data (stdio only, off by default; it first returns a plan showing "
    "exactly what AmeriFlux will send to the site PIs; only confirm=true sends it) -> "
    "amf_preview_data -> amf_get_citation. Discovery, availability, variables and citations need "
    "no account. Downloads need the user's own download identity from the server's environment; "
    "never invent or write intended-use text for the user, and without it the download tool "
    "returns auth_required. Cite every site's DOI and follow its data policy (CC-BY-4.0, "
    "AmeriFlux Legacy or FLUXNET2015 Tier 2; mixing escalates to the stricter one). Results are "
    "compact and paginated (page.nextOffset), carry notes, and end with nextSteps. Call amf_ping "
    "to see which tools this build offers and whether downloads are set up. Read "
    "ameriflux://guide/agent-workflow for worked examples and ameriflux://guide/identity "
    "before any download."
)
