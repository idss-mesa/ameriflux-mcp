#!/usr/bin/env python3
"""Maintainer tool for the hermetic fixtures in ``tests/fixtures/``.

    uv run python scripts/record_fixtures.py check     # CI: the rules below
    uv run python scripts/record_fixtures.py record    # re-record everything live (GET only)

``record`` sends real GET requests to the AmeriFlux API through a recording
transport and stores the responses tests replay (``tests/fixture_router.py``). The
API is anonymous, so no credential is involved; the request list is fixed
(:data:`SCENARIOS`) and checked against the client's allow-list before sending.
Before anything is written, each response is transformed:

* catalog, FLUXNET site lists and availability responses are filtered to the fixture
  site set (``tests.fixture_router.FIXTURE_SITES``), so fixtures stay small and tests
  never assert network-wide counts;
* every email address becomes ``<hash>@example.org`` (DESIGN.md D19);
* long free text (``site_desc``) is cut, and long reference lists are shortened.

Each manifest entry records the transform applied. Recordings land in
``tests/fixtures/_raw/`` (gitignored) and replace the committed set only if ``check``
passes on them.

Rules checked: every manifest file present and referenced; no file without a manifest
entry; each fixture <= 40 KiB and all <= 3 MiB; no ``@`` outside ``example.org``;
every manifest key on the client's allow-list and never under ``paper_test/``; GET only.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ameriflux_mcp.ameriflux.client import ALLOWED, DENIED_FRAGMENTS  # noqa: E402
from tests.fixture_router import FIXTURE_SITES, canonical_key  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
RAW = FIXTURES / "_raw"
API = "https://amfcdn.lbl.gov/api"
MAX_FIXTURE_BYTES = 40 * 1024
MAX_TOTAL_BYTES = 3 * 1024 * 1024
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
DESC_CHARS = 280
MAX_REFERENCES = 4
SITES = frozenset(FIXTURE_SITES)

#: (path, query) of every recorded request. Invalid combinations are recorded on purpose:
#: they pin the API's error bodies (RESEARCH.md section 2).
SCENARIOS: list[tuple[str, dict[str, str]]] = [
    ("v2/site_info_display/AmeriFlux", {}),
    ("v1/site_display/FLUXNET/FLUXNET2015", {}),
    ("v1/site_display/FLUXNET/FLUXNET-CH4", {}),
    ("v1/site_availability", {}),
    ("v1/data_availability/AmeriFlux/BASE-BADM/CCBY4.0", {}),
    ("v1/data_availability/AmeriFlux/BASE-BADM/LEGACY", {}),
    ("v1/data_availability/AmeriFlux/FLUXNET/CCBY4.0", {}),
    ("v1/data_availability/FLUXNET/FLUXNET2015/CCBY4.0", {}),
    ("v1/data_availability/FLUXNET/FLUXNET2015/TIER2", {}),
    ("v1/data_availability/FLUXNET/FLUXNET-CH4/CCBY4.0", {}),
    ("v1/data_availability/FLUXNET/FLUXNET-CH4/TIER2", {}),
    ("v1/data_availability/FLUXNET/FLUXNET2015/Tier2", {}),  # 422
    ("v1/data_availability/AmeriFlux/BASE-BADM/Tier2", {}),  # 200, all rows empty
    ("v1/fp_var", {"limits": "True"}),
    ("v1/does_not_exist", {}),  # 404
    *(
        (f"v1/DOI/{site}/{product}", {})
        for site, product in (
            ("US-Ha1", "AmeriFlux"),
            ("US-Ha1", "FLUXNET"),
            ("US-Ha1", "FLUXNET2015"),
            ("US-Ha1", "BASE"),
            ("US-Ha1", "BIF"),
            ("CA-Let", "AmeriFlux"),
            ("US-CRT", "AmeriFlux"),
            ("AR-Bal", "FLUXNET"),
            ("US-xSR", "AmeriFlux"),
            ("US-xSR", "FLUXNET"),
            ("RU-Sam", "FLUXNET2015"),
            ("BR-Sa1", "FLUXNET2015"),
            ("US-Myb", "FLUXNET-CH4"),
            ("XX-Zzz", "AmeriFlux"),
        )
    ),
]


# ---------------------------------------------------------------------- transforms


def fake_email(match: re.Match[str]) -> str:
    digest = hashlib.sha1(match.group(0).lower().encode(), usedforsecurity=False).hexdigest()
    return f"person-{digest[:8]}@example.org"


def scrub_emails(text: str) -> str:
    return EMAIL_RE.sub(fake_email, text)


def _site_filter(rows: Any, key: str) -> Any:
    return [r for r in rows if isinstance(r, dict) and r.get(key) in SITES]


def transform(path: str, payload: Any) -> tuple[Any, str | None]:
    """Shrink one response to the fixture site set; returns (payload, description)."""
    if path == "v2/site_info_display/AmeriFlux":
        rows = _site_filter(payload.get("values", []), "site_id")
        for row in rows:
            desc = row.get("site_desc")
            if isinstance(desc, str) and len(desc) > DESC_CHARS:
                row["site_desc"] = desc[:DESC_CHARS].rstrip() + "…"
        return {"values": rows}, (
            f"filtered to the fixture sites; site_desc cut to {DESC_CHARS} characters"
        )
    if path.startswith(("v1/site_display/FLUXNET/", "v1/data_availability/")) and isinstance(
        payload, list
    ):
        return _site_filter(payload, "SITE_ID"), "filtered to the fixture sites"
    if path == "v1/site_availability" and isinstance(payload, dict):
        out: dict[str, Any] = {}
        for network, products in payload.items():
            out[network] = {
                product: {
                    policy: [pair for pair in sites if pair and pair[0] in SITES]
                    for policy, sites in policies.items()
                }
                for product, policies in products.items()
            }
        return out, "filtered to the fixture sites"
    if path.startswith("v1/DOI/") and isinstance(payload, dict):
        refs = payload.get("REFERENCES")
        if isinstance(refs, list) and len(refs) > MAX_REFERENCES:
            payload["REFERENCES"] = refs[:MAX_REFERENCES]
            return payload, f"REFERENCES cut to {MAX_REFERENCES} of {len(refs)}"
    return payload, None


# ---------------------------------------------------------------------- check


def _allowed(key: str) -> bool:
    method, _, rest = key.partition(" ")
    host, _, path = rest.partition("/")
    path = "/" + path.split("?", 1)[0]
    if method != "GET" or any(f in path for f in DENIED_FRAGMENTS):
        return False
    return any(path.startswith(p) for p in ALLOWED.get(host, ()))


def check(directory: Path = FIXTURES) -> list[str]:
    problems: list[str] = []
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return [f"{manifest_path.name}: missing"]
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    referenced: set[str] = set()
    for entry in entries:
        if not _allowed(entry["key"]):
            problems.append(f"manifest: not an allow-listed GET: {entry['key'][:80]}")
        if entry.get("file"):
            referenced.add(entry["file"])
            if not (directory / entry["file"]).exists():
                problems.append(f"manifest: {entry['file']} is missing")
    total = 0
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        rel = path.relative_to(directory)
        if "_raw" in rel.parts and directory == FIXTURES:
            continue
        size = path.stat().st_size
        total += size
        name = str(rel)
        if size > MAX_FIXTURE_BYTES:
            problems.append(f"{name}: {size} bytes > {MAX_FIXTURE_BYTES}")
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in EMAIL_RE.finditer(text):
            if match.group(1).lower() != "example.org":
                problems.append(f"{name}: an email outside example.org")
                break
        if path.name != "manifest.json" and name not in referenced:
            problems.append(f"{name}: not referenced by the manifest")
    if total > MAX_TOTAL_BYTES:
        problems.append(f"fixtures total {total} bytes > {MAX_TOTAL_BYTES}")
    return problems


# ---------------------------------------------------------------------- recording


def fixture_name(key: str, status: int) -> str:
    """``<api version or host>/<readable slug>_<status>_<hash>.json``."""
    rest = key.split(" ", 1)[1]
    path = rest.split("/", 1)[1].split("?", 1)[0] if "/" in rest else ""
    path = path.removeprefix("api/")
    folder, _, tail = path.partition("/")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", tail).strip("_")[-60:] or "root"
    digest = hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{folder or 'other'}/{slug}_{status}_{digest}.json"


async def _record(out: Path) -> dict[str, dict[str, Any]]:
    from ameriflux_mcp.ameriflux.client import user_agent

    entries: dict[str, dict[str, Any]] = {}
    async with httpx.AsyncClient(
        headers={"User-Agent": user_agent("fixture-recorder"), "Accept": "application/json"},
        timeout=httpx.Timeout(120.0, connect=15.0),
        follow_redirects=False,
    ) as client:
        for path, query in SCENARIOS:
            request = client.build_request("GET", f"{API}/{path}", params=query or None)
            key = canonical_key("GET", request.url)
            if not _allowed(key):
                raise SystemExit(f"refusing to record a non-allow-listed request: {key}")
            response = await client.send(request)
            await asyncio.sleep(0.5)  # D21: 2 requests per second
            content_type = (response.headers.get("content-type") or "").split(";")[0] or None
            entry: dict[str, Any] = {
                "key": key,
                "status": response.status_code,
                "contentType": content_type,
            }
            text = response.text
            note: str | None = None
            try:
                payload, note = transform(path, json.loads(text))
                text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            except ValueError:
                pass  # error bodies that are not JSON are stored as they came
            if note:
                entry["transform"] = note
            if text:
                name = fixture_name(key, response.status_code)
                target = out / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(scrub_emails(text), encoding="utf-8")
                entry["file"] = name
            entries[key] = entry
            print(f"  {response.status_code} {key}")
    return entries


def record() -> int:
    if RAW.exists():
        shutil.rmtree(RAW)
    RAW.mkdir(parents=True)
    print("recording (GET only):")
    entries = asyncio.run(_record(RAW))
    (RAW / "manifest.json").write_text(
        json.dumps([entries[k] for k in sorted(entries)], indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    problems = check(RAW)
    if problems:
        for problem in problems:
            print("FIXTURE:", problem)
        print(f"{len(problems)} problem(s); recordings left in {RAW} and NOT promoted")
        return 1
    for child in FIXTURES.iterdir():
        if child.name != "_raw":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    for child in RAW.iterdir():
        shutil.move(str(child), FIXTURES / child.name)
    RAW.rmdir()
    print(f"promoted {len(entries)} recordings to {FIXTURES}")
    return 0


COMMANDS: dict[str, Callable[[], int]] = {"record": record}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "check":
        problems = check()
        for problem in problems:
            print("FIXTURE:", problem)
        print(f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if argv[0] in COMMANDS:
        return COMMANDS[argv[0]]()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
