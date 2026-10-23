"""Cross-links to other networks: NEON site codes and LTER membership (DESIGN.md D20).

The 47 AmeriFlux sites tagged ``NEON`` carry the NEON site code in parentheses at the
end of their name ("NEON Santa Rita Experimental Range (SRER)") and match the NEON
DP4.00200.001 site list (RESEARCH.md E35). LTER tagging is incomplete upstream
(US-Seg, US-Ses, US-Wjs and US-Mpj lack it), so LTER links stay a curated draft
(build step 4).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ameriflux_mcp.ameriflux.catalog import SiteIndex

NEON_CODE_RE = re.compile(r"\(([A-Z]{4})\)\s*$")


def neon_code(name: str, networks: Iterable[str]) -> str | None:
    """The NEON site code of a NEON-tagged AmeriFlux site, from its name."""
    if "NEON" not in set(networks):
        return None
    match = NEON_CODE_RE.search(name)
    return match.group(1) if match else None


def neon_crosswalk(index: SiteIndex) -> list[dict[str, str]]:
    """``[{neonSiteCode, siteId, siteName}]`` sorted by NEON code."""
    rows = [
        {"neonSiteCode": rec.neon_code, "siteId": rec.site_id, "siteName": rec.name}
        for rec in index.records.values()
        if rec.neon_code
    ]
    return sorted(rows, key=lambda r: r["neonSiteCode"])


__all__ = ["NEON_CODE_RE", "neon_code", "neon_crosswalk"]
