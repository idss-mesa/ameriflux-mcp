"""Probe the public AmeriFlux API shapes the server will depend on (plan Step 1).

The amfcdn.lbl.gov JSON API has no published contract, so this script records what it
actually returns before any client code is written:

  P1  status, envelope (bare list, ``{"values": [...]}`` or object), row counts and key
      sets of every discovery endpoint, plus the error bodies for unknown paths,
      unvalidated enums and read-only methods;
  P4  ``v1/DOI/{SITE}/{PRODUCT}`` for 20 site/product pairs (CC-BY, Legacy, Tier 2, BIF,
      FLUXNET-CH4 and unknown sites);
  P7  the shape of ``base_variables`` and ``dom_dist_mgmt`` in ``v2/site_info_display``;
  P8  the Measurement Height CSV linked from ameriflux.lbl.gov (one page fetch).

Read-only by construction: ``http()`` sends GET and HEAD only, to an allow-list of hosts
and paths, never with a request body, and refuses everything else before any socket is
opened. It never touches data zips: AmeriFlux logs downloads and tells the site PIs, and
fetching files outside that route would bypass it (DESIGN.md D11, D15). Responses can
hold team and contributor emails; the script keeps key names and counts, never those
values, and scrubs anything email-shaped from what it prints or writes.

Usage:
    python3 scripts/probe_api.py [--only P1,P4,P7,P8] [--json probe.json]
    python3 scripts/probe_api.py --selftest   # offline checks of the guards

Stdlib only, so it runs before ``uv sync``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from typing import Any

UA = "ameriflux-mcp-probe/0.1 (+https://github.com/idss-mesa/ameriflux-mcp)"
TIMEOUT = 60
API = "https://amfcdn.lbl.gov/api"

ALLOWED_METHODS = frozenset({"GET", "HEAD"})
# host -> allowed path prefixes ("" allows the whole host)
ALLOWED_PATHS: dict[str, tuple[str, ...]] = {
    "amfcdn.lbl.gov": ("/api/",),
    "ameriflux.lbl.gov": ("/data/measurement-height/",),
    "ftp.fluxdata.org": (
        "/.ameriflux_downloads/measurement_height/",
        "/.fluxnet_downloads_67934/webdoc/",
    ),
}
DENIED_FRAGMENTS = ("/paper_test/",)
# Politeness (D21): 2 req/s to amfcdn; ameriflux.lbl.gov robots.txt asks for 15 s.
MIN_INTERVAL = {"amfcdn.lbl.gov": 0.5, "ameriflux.lbl.gov": 15.0, "ftp.fluxdata.org": 0.5}

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_last_call: dict[str, float] = {}


class ProbeRefused(Exception):
    """Raised before any network I/O when a request breaks the read-only rules."""


def scrub(text: str) -> str:
    """Replace anything email-shaped with ``<email>``."""
    return _EMAIL.sub("<email>", text)


def check_request(method: str, url: str) -> None:
    """Refuse methods, schemes, hosts and paths outside the allow-list."""
    if method.upper() not in ALLOWED_METHODS:
        raise ProbeRefused(f"method {method!r} is not allowed (GET and HEAD only)")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise ProbeRefused(f"scheme {parts.scheme!r} is not allowed (https only)")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_PATHS:
        raise ProbeRefused(f"host {host!r} is not on the allow-list")
    if ".." in parts.path.split("/") or any(f in parts.path for f in DENIED_FRAGMENTS):
        raise ProbeRefused(f"path {parts.path!r} is explicitly denied")
    if not any(parts.path.startswith(prefix) for prefix in ALLOWED_PATHS[host]):
        raise ProbeRefused(f"path {parts.path!r} is not allowed on {host}")


def http(method: str, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Send one GET or HEAD request; returns status, headers, timing and the decoded body."""
    check_request(method, url)
    host = urllib.parse.urlsplit(url).hostname or ""
    wait = MIN_INTERVAL.get(host, 1.0) - (time.monotonic() - _last_call.get(host, -1e9))
    if wait > 0:
        time.sleep(wait)
    hdrs = {"User-Agent": UA, "Accept-Encoding": "gzip", **(headers or {})}
    req = urllib.request.Request(url, headers=hdrs, method=method.upper())  # noqa: S310
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
            status, resp_headers, raw = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        status, resp_headers, raw = exc.code, dict(exc.headers or {}), exc.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        _last_call[host] = time.monotonic()
        return {"status": None, "error": scrub(str(exc)), "url": url}
    _last_call[host] = time.monotonic()
    wire_bytes = len(raw)
    if resp_headers.get("Content-Encoding", "").lower() == "gzip" and raw:
        raw = gzip.decompress(raw)
    body = raw.decode("utf-8", errors="replace")
    keep = (
        "Content-Type",
        "Content-Length",
        "Cache-Control",
        "ETag",
        "Last-Modified",
        "Access-Control-Allow-Origin",
        "Retry-After",
        "cf-cache-status",
    )
    lower = {k.lower(): v for k, v in resp_headers.items()}
    return {
        "status": status,
        "url": url,
        "ms": round((time.monotonic() - started) * 1000),
        "bytes": len(raw),
        "wireBytes": wire_bytes,
        "headers": {k: lower[k.lower()] for k in keep if k.lower() in lower},
        "_body": body,
    }


def _json(result: dict[str, Any]) -> Any:
    try:
        return json.loads(result.get("_body") or "")
    except ValueError:
        return None


def envelope(payload: Any) -> tuple[str, list[Any] | None]:
    """Classify a response body and return its row list when it has one."""
    if isinstance(payload, list):
        return "bare", payload
    if isinstance(payload, dict) and isinstance(payload.get("values"), list):
        return "values", payload["values"]
    if isinstance(payload, dict):
        return "object", None
    return "other", None


def key_counts(rows: list[Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        if isinstance(row, dict):
            counts.update(row.keys())
    return dict(sorted(counts.items()))


# --- P1: endpoint shapes ----------------------------------------------------------------

P1_ENDPOINTS: list[str] = [
    "v1/",
    "v1/site_display/AmeriFlux",
    "v1/site_display/FLUXNET",
    "v1/site_display/FLUXNET/FLUXNET2015",
    "v1/site_display/FLUXNET/FLUXNET-CH4",
    "v2/site_display/AmeriFlux",
    "v2/site_info_display/AmeriFlux",
    "v1/site_info_display/AmeriFlux",
    "v1/site_availability",
    "v2/site_availability",
    "v1/data_availability/AmeriFlux/BASE-BADM/CCBY4.0",
    "v1/data_availability/AmeriFlux/BASE-BADM/LEGACY",
    "v1/data_availability/AmeriFlux/BASE-BADM/Tier2",
    "v1/data_availability/AmeriFlux/BIF/CCBY4.0",
    "v1/data_availability/AmeriFlux/FLUXNET/CCBY4.0",
    "v1/data_availability/AmeriFlux/FLUXNET/LEGACY",
    "v1/data_availability/AmeriFlux/FOO/BAR",
    "v1/data_availability/FLUXNET/FLUXNET2015/CCBY4.0",
    "v1/data_availability/FLUXNET/FLUXNET2015/TIER2",
    "v1/data_availability/FLUXNET/FLUXNET2015/Tier2",
    "v1/data_availability/FLUXNET/FLUXNET-CH4/CCBY4.0",
    "v1/data_availability/FLUXNET/FLUXNET-CH4/TIER2",
    "v2/data_availability/AmeriFlux/BASE-BADM/CCBY4.0",
    "v1/fp_var?limits=True",
    "v2/fp_var",
    "v1/data_download",
    "v1/citations/AmeriFlux",
    "v1/variable_availability",
]


def probe_p1() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in P1_ENDPOINTS:
        res = http("GET", f"{API}/{path}")
        payload = _json(res)
        kind, rows = envelope(payload)
        row: dict[str, Any] = {k: res.get(k) for k in ("status", "ms", "bytes", "wireBytes")}
        row["headers"] = res.get("headers", {})
        row["envelope"] = kind
        if rows is not None:
            row["rows"] = len(rows)
            row["keys"] = key_counts(rows)
            with_years = [r for r in rows if isinstance(r, dict) and "publish_years" in r]
            if with_years:
                row["nonEmpty"] = sum(1 for r in with_years if r["publish_years"])
                row["siteYears"] = sum(len(r["publish_years"]) for r in with_years)
        elif kind == "object" and isinstance(payload, dict):
            if path == "v1/site_availability":
                row["tree"] = {
                    net: {
                        prod: {pol: len(sites) for pol, sites in pols.items()}
                        for prod, pols in prods.items()
                    }
                    for net, prods in payload.items()
                    if isinstance(prods, dict)
                }
            else:
                row["body"] = scrub(json.dumps(payload))[:300]
        elif res.get("_body") is not None:
            row["body"] = scrub(res["_body"])[:300]
        if res.get("error"):
            row["error"] = res["error"]
        out[path] = row
    # The API sends no ETag or Last-Modified (E37); check whether a conditional GET does anything.
    cond = http("GET", f"{API}/v1/fp_var", {"If-Modified-Since": "Wed, 01 Jan 2025 00:00:00 GMT"})
    out["conditional:v1/fp_var"] = {"status": cond.get("status"), "headers": cond.get("headers")}
    return out


# --- P4: DOI citations ------------------------------------------------------------------

P4_PAIRS: list[tuple[str, str]] = [
    ("US-Ha1", "AmeriFlux"),
    ("US-Ha1", "FLUXNET"),
    ("US-Ha1", "FLUXNET2015"),
    ("US-Ha1", "BASE"),
    ("US-Ha1", "BASE-BADM"),
    ("US-Ha1", "BIF"),
    ("US-Ha1", "FLUXNET-CH4"),
    ("US-Ha1", "fluxnet2015"),
    ("CA-Let", "AmeriFlux"),
    ("US-CRT", "AmeriFlux"),
    ("AR-Bal", "FLUXNET"),
    ("US-xSR", "AmeriFlux"),
    ("US-xSR", "FLUXNET"),
    ("US-Seg", "AmeriFlux"),
    ("BR-Sa1", "FLUXNET2015"),
    ("RU-Sam", "FLUXNET2015"),
    ("DE-Tha", "FLUXNET2015"),
    ("US-Myb", "FLUXNET-CH4"),
    ("US-Myb", "AmeriFlux"),
    ("XX-Zzz", "AmeriFlux"),
]


def _doi_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__}
    summary: dict[str, Any] = {"keys": sorted(payload)}
    if "status" in payload:
        summary["statusText"] = scrub(str(payload["status"]))
    info = payload.get("DOI_INFO")
    if isinstance(info, dict):
        summary["infoKeys"] = sorted(info)
        for key in ("DOI", "DATA_POLICY", "DOI_CITATION"):
            if key in info:
                summary[key] = scrub(str(info[key])) if info[key] is not None else None
    for key in (
        "DOI_CONTRIBUTOR",
        "DOI_CONTRIBUTOR_ORGANIZATION",
        "DOI_SPONSOR_ORGANIZATION",
        "REFERENCES",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            summary[f"{key}.count"] = len(value)
            summary[f"{key}.keys"] = sorted(key_counts(value))
    return summary


def probe_p4() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for site, product in P4_PAIRS:
        res = http("GET", f"{API}/v1/DOI/{site}/{product}")
        out[f"{site}/{product}"] = {"status": res.get("status"), **_doi_summary(_json(res))}
    return out


# --- P7: base_variables and dom_dist_mgmt -----------------------------------------------

P7_SITES = ("US-Ha1", "US-xSR", "CA-Let", "AR-Bal", "US-Seg")


def _shape(value: Any) -> str:
    if isinstance(value, list):
        inner = sorted({_shape(v) for v in value[:50]})
        return f"list[{'|'.join(inner) or 'empty'}]"
    if isinstance(value, dict):
        return "dict{" + ",".join(sorted(value)) + "}"
    return type(value).__name__


def probe_p7() -> dict[str, Any]:
    res = http("GET", f"{API}/v2/site_info_display/AmeriFlux")
    _, rows = envelope(_json(res))
    if not rows:
        return {"status": res.get("status"), "error": "no rows"}
    out: dict[str, Any] = {"status": res.get("status"), "sites": len(rows)}
    for field in ("base_variables", "dom_dist_mgmt", "flux_measurements_variables"):
        values = [r.get(field) for r in rows if isinstance(r, dict)]
        lengths = [len(v) for v in values if isinstance(v, list)]
        out[field] = {
            "shapes": dict(Counter(_shape(v) for v in values)),
            "nonEmpty": sum(1 for n in lengths if n),
            "maxLength": max(lengths, default=0),
            "samples": {
                r["site_id"]: scrub(json.dumps(r.get(field)))[:400]
                for r in rows
                if isinstance(r, dict) and r.get("site_id") in P7_SITES
            },
        }
    return out


# --- P8: Measurement Height CSV ---------------------------------------------------------

_HEIGHT_HREF = re.compile(
    r"https://ftp\.fluxdata\.org/\.ameriflux_downloads/measurement_height/"
    r"BASE_MeasurementHeight_(\d{8})\.csv"
)


def probe_p8() -> dict[str, Any]:
    page = http("GET", "https://ameriflux.lbl.gov/data/measurement-height/")
    hrefs = sorted(set(_HEIGHT_HREF.findall(page.get("_body") or "")))
    out: dict[str, Any] = {"pageStatus": page.get("status"), "linkedDates": hrefs}
    if hrefs:
        url = (
            "https://ftp.fluxdata.org/.ameriflux_downloads/measurement_height/"
            f"BASE_MeasurementHeight_{hrefs[-1]}.csv"
        )
        head = http("HEAD", url)
        out["latest"] = {"url": url, "status": head.get("status"), "headers": head.get("headers")}
    return out


PROBES = {"P1": probe_p1, "P4": probe_p4, "P7": probe_p7, "P8": probe_p8}


def selftest() -> int:
    """Offline checks that the guards refuse what they must, without opening a socket."""
    refused = [
        ("PUT", f"{API}/v1/fp_var"),
        ("DELETE", f"{API}/v1/fp_var"),
        ("PATCH", f"{API}/v1/fp_var"),
        ("GET", "http://amfcdn.lbl.gov/api/v1/fp_var"),
        ("GET", "https://example.org/api/v1/fp_var"),
        ("GET", "https://ftp.fluxdata.org/.fluxnet_downloads_67934/paper_test/x.zip"),
        ("HEAD", "https://ftp.fluxdata.org/.ameriflux_downloads/FLUXNET/x.zip"),
        ("GET", "https://ameriflux.lbl.gov/data/data-download-log/"),
    ]
    failures = 0
    for method, url in refused:
        try:
            check_request(method, url)
        except ProbeRefused:
            continue
        print(f"selftest FAILED: {method} {url} was not refused", file=sys.stderr)
        failures += 1
    for method, url in (("GET", f"{API}/v1/fp_var"), ("HEAD", f"{API}/v2/site_info_display/x")):
        try:
            check_request(method, url)
        except ProbeRefused as exc:
            print(f"selftest FAILED: {method} {url} refused: {exc}", file=sys.stderr)
            failures += 1
    if scrub("pi a.b+c@example.edu, x@example.org") != "pi <email>, <email>":
        print("selftest FAILED: scrub", file=sys.stderr)
        failures += 1
    print("selftest ok" if not failures else f"selftest: {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--only", default="P1,P4,P7,P8", help="comma-separated probes to run")
    ap.add_argument("--json", help="write results to this JSON file")
    ap.add_argument("--selftest", action="store_true", help="offline guard checks only")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    wanted = [p.strip().upper() for p in args.only.split(",") if p.strip()]
    unknown = [p for p in wanted if p not in PROBES]
    if unknown:
        ap.error(f"unknown probe(s): {', '.join(unknown)}")
    results: dict[str, Any] = {"date": date.today().isoformat(), "userAgent": UA}
    for name in wanted:
        print(f"running {name} ...", file=sys.stderr)
        results[name] = PROBES[name]()

    out = scrub(json.dumps(results, indent=2, ensure_ascii=False))
    if "@" in out:  # belt and braces: nothing email-shaped may survive
        print("refusing to write results: an '@' survived scrubbing", file=sys.stderr)
        return 1
    print(out)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
