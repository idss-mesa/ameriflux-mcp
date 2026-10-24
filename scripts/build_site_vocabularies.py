#!/usr/bin/env python3
"""Build ``src/ameriflux_mcp/resources_static/vocabularies.json`` (maintainer tool).

    uv run python scripts/build_site_vocabularies.py           # one GET of the site-search page
    uv run python scripts/build_site_vocabularies.py --check   # offline: the committed file parses

The AmeriFlux site-search page embeds the descriptions AmeriFlux itself uses for IGBP
ecosystem classes (``igbpText``) and Köppen climate codes (``climText``) as JSON string
literals (RESEARCH.md E53). This script fetches that one page (GET, descriptive
User-Agent), extracts both dictionaries and writes them, with the product × policy
matrix, the intended-use codes and the secondary networks, to the static resource
served as ``ameriflux://reference/vocabularies``. The output records its source and
fetch date; nothing else in the page is stored.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ameriflux_mcp.ameriflux.client import user_agent  # noqa: E402
from ameriflux_mcp.ameriflux.products import MATRIX  # noqa: E402
from ameriflux_mcp.config import INTENDED_USE_CODES, INTENDED_USE_LABELS  # noqa: E402

SOURCE = "https://ameriflux.lbl.gov/sites/site-search/"
TARGET = ROOT / "src" / "ameriflux_mcp" / "resources_static" / "vocabularies.json"
#: Secondary networks tagged in the catalog (grp_network), with counts on 2026-10-24.
NETWORKS: dict[str, int] = {
    "Phenocam": 196,
    "NEON": 47,
    "LTAR": 41,
    "Fluxnet-Canada": 30,
    "LTER": 18,
    "New York State Mesonet": 18,
    "MexFlux": 16,
    "UFLUX": 16,
    "LBA": 8,
    "USCCC": 4,
    "CZNet": 2,
    "Urban Flux Network": 1,
}


#: Where AmeriFlux's wording departs from the standard Köppen-Geiger definitions. The text
#: above is kept verbatim (it is what AmeriFlux shows); these notes travel with it.
KOEPPEN_CAVEATS: dict[str, str] = {
    "Bsh": "Standard Köppen-Geiger BSh is hot semi-arid (steppe); AmeriFlux's text reads "
    "'very cold winter', which matches BSk. The two descriptions appear swapped upstream.",
    "Bsk": "Standard Köppen-Geiger BSk is cold semi-arid (steppe); AmeriFlux's text reads "
    "'warm winter', which matches BSh. The two descriptions appear swapped upstream.",
}


def extract(page: str, name: str) -> dict[str, str]:
    """``name = '{\\"KEY\\":{\\"description\\":…,\\"sequence\\":10},…}';`` -> {KEY: description}."""
    match = re.search(name + r"\s*=\s*'(.*?)';", page, re.S)
    if not match:
        raise SystemExit(f"{name} not found in {SOURCE}; the page changed")
    raw: dict[str, dict[str, Any]] = json.loads(match.group(1).replace('\\"', '"'))
    ordered = sorted(raw.items(), key=lambda kv: (kv[1].get("sequence", 0), kv[0]))
    return {code: str(entry.get("description", "")).strip() for code, entry in ordered}


def build(page: str, fetched: str) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "fetched": fetched,
        "igbp": extract(page, "igbpText"),
        "koeppen": extract(page, "climText"),
        "koeppenCaveats": KOEPPEN_CAVEATS,
        "products": {
            product: {
                "network": info.network,
                "policies": list(info.policies),
                "collection": info.collection,
                "doiSegment": info.doi_segment,
                "label": info.label,
            }
            for product, info in MATRIX.items()
        },
        "policies": {
            "CCBY4.0": "CC-BY-4.0 license (AmeriFlux) or FLUXNET Tier One",
            "LEGACY": "AmeriFlux Legacy Data Policy (more restrictive; mixing with CC-BY means "
            "Legacy applies)",
            "TIER2": "FLUXNET Tier Two (scientific and educational use; mixing tiers means "
            "Tier Two applies)",
        },
        "intendedUse": [
            {"code": int(code), "key": key, "label": INTENDED_USE_LABELS[key]}
            for code, key in INTENDED_USE_CODES.items()
        ],
        "networks": NETWORKS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate the committed file")
    args = parser.parse_args()
    if args.check:
        data = json.loads(TARGET.read_text(encoding="utf-8"))
        assert {"igbp", "koeppen", "products", "policies", "intendedUse"} <= set(data)
        print(f"{TARGET.name}: {len(data['igbp'])} IGBP classes, {len(data['koeppen'])} climates")
        return 0
    response = httpx.get(
        SOURCE, headers={"User-Agent": user_agent("vocabulary-builder")}, timeout=60
    )
    response.raise_for_status()
    fetched = datetime.date.today().isoformat()
    data = build(response.text, fetched)
    TARGET.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote {TARGET.relative_to(ROOT)} ({len(data['igbp'])} IGBP, {len(data['koeppen'])} Köppen)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
