"""Static reference data: vocabularies and the curated LTER crosswalk.

``resources_static/vocabularies.json`` is built by ``scripts/build_site_vocabularies.py``
from AmeriFlux's own IGBP and Köppen descriptions (E56); ``lter-crosswalk.json`` is
curated (status draft, D20). Lookups are case-insensitive because catalog codes vary
in case (``Bsk``, ``BSk``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

STATIC_DIR = Path(__file__).resolve().parent.parent / "resources_static"


@lru_cache(maxsize=1)
def vocabularies() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((STATIC_DIR / "vocabularies.json").read_text("utf-8"))
    return data


@lru_cache(maxsize=1)
def lter_crosswalk() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((STATIC_DIR / "lter-crosswalk.json").read_text("utf-8"))
    return data


def _lookup(table: dict[str, str], code: str | None) -> str | None:
    if not code:
        return None
    folded = {k.casefold(): v for k, v in table.items()}
    return folded.get(code.strip().casefold())


def igbp_label(code: str | None) -> str | None:
    """``DBF`` -> ``Deciduous Broadleaf Forests: …`` (AmeriFlux's wording)."""
    return _lookup(vocabularies()["igbp"], code)


def koeppen_label(code: str | None) -> str | None:
    return _lookup(vocabularies()["koeppen"], code)


def koeppen_caveat(code: str | None) -> str | None:
    return _lookup(vocabularies().get("koeppenCaveats", {}), code)


def lter_link(site_id: str) -> dict[str, Any] | None:
    """The curated LTER row for a site, or ``None``."""
    for row in lter_crosswalk()["rows"]:
        if row["siteId"] == site_id:
            return dict(row)
    return None


__all__ = [
    "igbp_label",
    "koeppen_caveat",
    "koeppen_label",
    "lter_crosswalk",
    "lter_link",
    "vocabularies",
]
