#!/usr/bin/env python3
"""Build the variable dictionaries in ``src/ameriflux_mcp/resources_static/`` (maintainer tool).

    uv run python scripts/build_variable_dictionaries.py            # GET the sources, write both
    uv run python scripts/build_variable_dictionaries.py --from DIR # build from saved copies
    uv run python scripts/build_variable_dictionaries.py --check    # offline: committed files parse

Two files come out (DESIGN.md D35):

* ``fluxnet-variables.json``: the FLUXNET variables, one entry per name with its units
  and notes per resolution (HH, DD, WW, MM, YY), FULLSET and SUBSET membership and the
  resolutions ONEFlux defines it at. Descriptions, units and SUBSET membership come from
  the FLUXNET2015 webdoc dictionaries (``variable_codes_{FULLSET,SUBSET}_20200504.csv``,
  RESEARCH.md E28, E57); timestamp formats and per-resolution presence from ONEFlux's
  ``var_info_definitions_{hh,dd,ww,mm,yy}.txt`` at a pinned commit (E29, E58), with the
  micro sign restored from U+FFFD. The webdoc files state no licence, so only this
  derived table is committed, with each source's URL, ETag and fetch date (NOTICE, Q7).
* ``fp-variables.json``: a snapshot of the FP Standard list (``v1/fp_var?limits=True``,
  E17), the fallback when the live list cannot be fetched.

Every request is a GET with a descriptive User-Agent; nothing else is stored.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ameriflux_mcp.ameriflux.client import user_agent  # noqa: E402

STATIC = ROOT / "src" / "ameriflux_mcp" / "resources_static"
FLUXNET_TARGET = STATIC / "fluxnet-variables.json"
FP_TARGET = STATIC / "fp-variables.json"
WEBDOC = "https://ftp.fluxdata.org/.fluxnet_downloads_67934/webdoc/"
WEBDOC_FILES = {
    "fullset": "variable_codes_FULLSET_20200504.csv",
    "subset": "variable_codes_SUBSET_20200504.csv",
}
#: fluxnet/ONEFlux commit that last changed the var_info files (2025-12-09, v1.3.0-rc).
ONEFLUX_COMMIT = "d4ecebef96b83b33c82c8c0449aad308adf604cd"
ONEFLUX_RAW = (
    f"https://raw.githubusercontent.com/fluxnet/ONEFlux/{ONEFLUX_COMMIT}/oneflux/metadata/"
)
FP_VAR = "https://amfcdn.lbl.gov/api/v1/fp_var?limits=True"
RESOLUTIONS = ("HH", "DD", "WW", "MM", "YY")
_RES_LABEL = re.compile(r"^(HH|DD|WW|MM|YY)(?:-(HH|DD|WW|MM|YY))?$")
_UNAVAILABLE = {"not available", "not defined", "not produced"}
_DIMENSIONLESS = {"adimensional", "nondimensional", "dimensionless"}


def fix_units(units: str | None) -> str | None:
    """Restore µ (ONEFlux stores it as U+FFFD) and spell dimensionless one way."""
    if units is None:
        return None
    text = units.replace("�", "µ").strip()
    if text.lower() in _DIMENSIONLESS:
        return "nondimensional"
    return text or None


def expand(label: str) -> list[str]:
    """``WW-YY`` -> ``['WW', 'MM', 'YY']``; ``DD`` -> ``['DD']``."""
    match = _RES_LABEL.match(label)
    if not match:
        return []
    first, last = match.group(1), match.group(2) or match.group(1)
    return list(RESOLUTIONS[RESOLUTIONS.index(first) : RESOLUTIONS.index(last) + 1])


def parse_webdoc(text: str) -> dict[str, dict[str, Any]]:
    """A webdoc CSV -> {name: {section, description, units{res}, notes{res}}} in file order.

    Layout (E57): a section row (``MICROMETEOROLOGICAL,,``), a variable row
    (``TA_F_MDS,,description``), then one row per resolution label (``HH,deg C,``,
    ``WW-YY,deg C,average from daily data``); blank rows separate sections.
    """
    out: dict[str, dict[str, Any]] = {}
    section: str | None = None
    current: dict[str, Any] | None = None
    for row in csv.reader(io.StringIO(text)):
        name, units, description = ([*row, "", "", ""])[:3]
        name, units, description = name.strip(), units.strip(), description.strip()
        if name == "Variable" and units == "Units":
            continue
        if not name:
            current = None
            continue
        resolutions = expand(name)
        if resolutions and current is not None:
            for res in resolutions:
                if description.lower() in _UNAVAILABLE:
                    current["units"][res] = None
                    current["notes"][res] = "not available"
                else:
                    current["units"][res] = fix_units(units)
                    if description:
                        current["notes"][res] = description
            continue
        if not units and not description:
            section = name
            current = None
            continue
        current = {
            "section": section,
            "description": description,
            "headerUnits": fix_units(units),
            "units": {},
            "notes": {},
        }
        out[name] = current
    return out


def parse_var_info(text: str) -> dict[str, dict[str, str | None]]:
    """``Variable||Units||Description||Members`` -> {name: {units, description, members}}."""
    out: dict[str, dict[str, str | None]] = {}
    for line in text.splitlines()[1:]:
        parts = line.split("||")
        if len(parts) < 3 or not parts[0].strip():
            continue
        out[parts[0].strip()] = {
            "units": fix_units(parts[1]),
            "description": parts[2].replace("�", "µ").strip() or None,
            "members": parts[3].strip() if len(parts) > 3 and parts[3].strip() else None,
        }
    return out


def build_fluxnet(
    fullset: str,
    subset: str,
    var_info: dict[str, str],
    sources: dict[str, Any],
) -> dict[str, Any]:
    full = parse_webdoc(fullset)
    sub = parse_webdoc(subset)
    oneflux = {res: parse_var_info(var_info[res.lower()]) for res in RESOLUTIONS}
    names = list(full)
    for res in RESOLUTIONS:
        names.extend(n for n in oneflux[res] if n not in names)
    variables: list[dict[str, Any]] = []
    for name in names:
        entry = full.get(name) or sub.get(name) or {}
        units = {res: entry.get("units", {}).get(res) for res in RESOLUTIONS}
        notes = {res: note for res, note in entry.get("notes", {}).items() if note}
        defined = [res for res in RESOLUTIONS if name in oneflux[res]]
        for res in defined:  # timestamps (and any gap) take ONEFlux's per-resolution units
            if units[res] is None and res not in notes:
                units[res] = oneflux[res][name]["units"]
        if not any(units.values()) and entry.get("headerUnits"):
            units = {res: entry["headerUnits"] for res in RESOLUTIONS}
        description = entry.get("description") or next(
            (
                oneflux[res][name]["description"]
                for res in defined
                if oneflux[res][name]["description"]
            ),
            None,
        )
        members = next(
            (oneflux[res][name]["members"] for res in defined if oneflux[res][name]["members"]),
            None,
        )
        variables.append(
            {
                "name": name,
                "section": entry.get("section"),
                "description": description,
                "units": units,
                "notes": notes,
                "fullset": name in full,
                "subset": name in sub,
                "oneflux": defined,
                "members": members,
            }
        )
    return {
        "sources": sources,
        "resolutions": list(RESOLUTIONS),
        "placeholders": {
            "XX": ["05", "16", "25", "50", "75", "84", "95"],
            "#": "soil layer index, 1 = shallowest",
        },
        "count": len(variables),
        "variables": variables,
    }


def build_fp(rows: list[dict[str, Any]], fetched: str) -> dict[str, Any]:
    variables = [
        {
            "name": r["Name"],
            "type": r.get("Type"),
            "units": r.get("Units"),
            "description": r.get("Description"),
            "min": r.get("Min"),
            "max": r.get("Max"),
            "heightDirection": r.get("HeightDirection"),
            "modelType": r.get("ModelType"),
        }
        for r in sorted(
            rows, key=lambda r: (r.get("Type") or "", r.get("Sequence") or 0, r["Name"])
        )
    ]
    return {"source": FP_VAR, "fetched": fetched, "count": len(variables), "variables": variables}


# ---------------------------------------------------------------------- I/O


def _get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def fetch_all() -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]], dict[str, Any]]:
    webdoc: dict[str, str] = {}
    var_info: dict[str, str] = {}
    meta: dict[str, Any] = {}
    today = datetime.date.today().isoformat()
    with httpx.Client(
        headers={"User-Agent": user_agent("dictionary-builder")}, timeout=60, follow_redirects=False
    ) as client:
        for key, name in WEBDOC_FILES.items():
            response = _get(client, WEBDOC + name)
            webdoc[key] = response.content.decode("utf-8")
            meta[key] = {
                "url": WEBDOC + name,
                "etag": response.headers.get("etag"),
                "lastModified": response.headers.get("last-modified"),
                "fetched": today,
            }
        for res in RESOLUTIONS:
            name = f"var_info_definitions_{res.lower()}.txt"
            var_info[res.lower()] = _get(client, ONEFLUX_RAW + name).content.decode(
                "utf-8", "replace"
            )
        meta["oneflux"] = {
            "repository": "https://github.com/fluxnet/ONEFlux",
            "commit": ONEFLUX_COMMIT,
            "files": "oneflux/metadata/var_info_definitions_{hh,dd,ww,mm,yy}.txt",
            "fetched": today,
        }
        fp_rows = _get(client, FP_VAR).json()
    return webdoc, var_info, fp_rows, meta


def load_dir(
    directory: Path,
) -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]], dict[str, Any]]:
    """Saved copies: FULLSET.csv, SUBSET.csv, var_info_{hh..yy}.txt, fp_var.json."""
    today = datetime.date.today().isoformat()
    webdoc = {
        key: (directory / f"{key.upper()}.csv").read_text(encoding="utf-8") for key in WEBDOC_FILES
    }
    var_info = {
        res.lower(): (directory / f"var_info_{res.lower()}.txt")
        .read_bytes()
        .decode("utf-8", "replace")
        for res in RESOLUTIONS
    }
    fp_rows = json.loads((directory / "fp_var.json").read_text(encoding="utf-8"))
    meta: dict[str, Any] = {
        key: {"url": WEBDOC + name, "etag": None, "lastModified": None, "fetched": today}
        for key, name in WEBDOC_FILES.items()
    }
    meta["oneflux"] = {
        "repository": "https://github.com/fluxnet/ONEFlux",
        "commit": ONEFLUX_COMMIT,
        "files": "oneflux/metadata/var_info_definitions_{hh,dd,ww,mm,yy}.txt",
        "fetched": today,
    }
    return webdoc, var_info, fp_rows, meta


def check() -> int:
    fluxnet = json.loads(FLUXNET_TARGET.read_text(encoding="utf-8"))
    fp = json.loads(FP_TARGET.read_text(encoding="utf-8"))
    names = {v["name"] for v in fluxnet["variables"]}
    assert {"NEE_VUT_REF", "GPP_NT_VUT_REF", "TA_F_MDS_QC", "TIMESTAMP"} <= names, "core names"
    assert all(set(v["units"]) == set(RESOLUTIONS) for v in fluxnet["variables"])
    assert "�" not in FLUXNET_TARGET.read_text(encoding="utf-8"), "U+FFFD left in units"
    assert fluxnet["count"] == len(fluxnet["variables"]) and fp["count"] == len(fp["variables"])
    subset = sum(v["subset"] for v in fluxnet["variables"])
    print(f"{FLUXNET_TARGET.name}: {len(names)} variables ({subset} in SUBSET)")
    print(f"{FP_TARGET.name}: {fp['count']} FP Standard variables (fetched {fp['fetched']})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="validate the committed files")
    group.add_argument("--from", dest="source_dir", type=Path, help="build from saved copies")
    args = parser.parse_args()
    if args.check:
        return check()
    webdoc, var_info, fp_rows, meta = load_dir(args.source_dir) if args.source_dir else fetch_all()
    fluxnet = build_fluxnet(webdoc["fullset"], webdoc["subset"], var_info, meta)
    fp = build_fp(fp_rows, meta["fullset"]["fetched"])
    for target, data in ((FLUXNET_TARGET, fluxnet), (FP_TARGET, fp)):
        target.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)} ({data['count']} variables)")
    return check()


if __name__ == "__main__":
    sys.exit(main())
