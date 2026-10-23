"""Site identifiers: syntax, case-insensitive canonicalization and FLUXNET2015 renames.

AmeriFlux and FLUXNET site IDs are ``CC-SSS``: a two-letter country code and three
characters whose case is significant to the reader but not unique (``US-xSR``,
``US-Ha1``). Lookups are therefore case-insensitive and always return the canonical
spelling. FLUXNET2015 renamed five sites to ISO country codes after release
(RESEARCH.md E36); the old IDs resolve to the new ones with a note (D20).
"""

from __future__ import annotations

import re

SITE_ID_RE = re.compile(r"^[A-Za-z]{2}-[A-Za-z0-9]{3}$")

#: FLUXNET2015 known issues: old ID -> current ID.
RENAMES: dict[str, str] = {
    "DK-ZaF": "GL-ZaF",
    "DK-ZaH": "GL-ZaH",
    "DK-NuF": "GL-NuF",
    "NO-Adv": "SJ-Adv",
    "NO-Blv": "SJ-Blv",
}
_RENAMES_FOLDED = {old.casefold(): new for old, new in RENAMES.items()}


def is_site_id(text: str) -> bool:
    return bool(SITE_ID_RE.match(text.strip()))


def renamed(text: str) -> str | None:
    """The current ID for a renamed FLUXNET2015 site, else ``None``."""
    return _RENAMES_FOLDED.get(text.strip().casefold())


def rename_note(old: str, new: str) -> str:
    return (
        f"{old} was renamed {new} after the FLUXNET2015 release (ISO country code); "
        f"results use {new}."
    )


__all__ = ["RENAMES", "SITE_ID_RE", "is_site_id", "rename_note", "renamed"]
