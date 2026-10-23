#!/usr/bin/env python3
"""Generate llms.txt and llms-full.txt from the ameriflux-mcp docs/ OKF bundle.

llms.txt      — linked outline of the site (llmstxt.org convention): every
                concept page with its frontmatter description, grouped by
                section, with absolute URLs derived from site_url.
llms-full.txt — the entire corpus concatenated as Markdown, frontmatter
                included, so an agent can ingest the whole bundle in one file.

Both are written into docs/ so the static build ships them at the site root
(https://idss-mesa.github.io/ameriflux-mcp/llms.txt). They are committed; CI fails
when they drift from the sources (`git diff --exit-code`).

Sections that do not exist yet are skipped silently, so the script works on
the phase-1 scaffold as well as on the full site. Needs only PyYAML.

Usage: python scripts/gen_llms_txt.py      (from the repository root)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

SECTION_ORDER = ["getting-started", "tools", "mcp", "deploy", "develop", "about"]


def site_url() -> str:
    text = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    m = re.search(r'^site_url\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return (m.group(1) if m else "/").rstrip("/") + "/"


def frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    return (data if isinstance(data, dict) else {}), text[m.end() :]


def page_url(base: str, rel: Path) -> str:
    # use_directory_urls-style pretty URLs
    if rel.name == "index.md":
        tail = str(rel.parent) + "/" if str(rel.parent) != "." else ""
    else:
        tail = str(rel.with_suffix("")) + "/"
    return base + tail.replace("\\", "/")


def section_heading(section_dir: Path) -> str:
    idx = section_dir / "index.md"
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return section_dir.name.replace("-", " ").title()


def main():
    base = site_url()
    lines = [
        "# ameriflux-mcp documentation",
        "",
        "> ameriflux-mcp is a Model Context Protocol (MCP 2026-07-28) server for "
        "AmeriFlux (https://ameriflux.lbl.gov) and FLUXNET (https://fluxnet.org) "
        "eddy-covariance data: find flux tower sites, check product and year "
        "availability, describe FLUXNET variables and QC flags, cite data under "
        "the CC-BY-4.0, Legacy or Tier 2 policies, download through AmeriFlux's "
        "logged route with the user's consent, and preview BASE, BADM, AmeriFlux "
        "FLUXNET and FLUXNET2015 files. This documentation covers installation "
        "on macOS, Linux and Windows, client setup, the download identity, "
        "configuration and the planned tools. The source repository is an Open "
        "Knowledge Format (OKF v0.2) bundle: every page carries YAML frontmatter "
        "with type, provenance (generated/sources), and lifecycle "
        "(status/stale_after) fields.",
        "",
        f"Full corpus for ingestion: {base}llms-full.txt",
        "",
        "Every page's Markdown source (OKF frontmatter included) is served at "
        "its URL plus `index.md` — for example "
        f"{base}getting-started/install/index.md. Agent guide: "
        f"{base}about/ai-agents/",
        "",
        "If you want AmeriFlux or FLUXNET data rather than documentation, "
        "connect to the ameriflux-mcp server itself (stdio or Streamable HTTP) "
        "and call its tools; the agent guide explains how.",
        "",
    ]
    full = [
        "# ameriflux-mcp documentation — full corpus",
        "",
        "Each page below begins with its canonical URL followed by its "
        "original Markdown, OKF frontmatter included.",
        "",
    ]

    n = 0
    for section in SECTION_ORDER:
        sdir = DOCS / section
        if not sdir.is_dir():
            continue
        pages = [p for p in sorted(sdir.glob("*.md")) if p.name != "index.md"]
        if not pages:
            continue
        lines += [f"## {section_heading(sdir)}", ""]
        for path in pages:
            fm, _ = frontmatter(path)
            rel = path.relative_to(DOCS)
            url = page_url(base, rel)
            title = fm.get("title") or path.stem.replace("-", " ").title()
            desc = str(fm.get("description", "")).strip()
            suffix = ""
            if fm.get("status") == "deprecated":
                suffix = " (deprecated; kept for history)"
            elif fm.get("status") == "draft":
                suffix = " (draft)"
            lines.append(f"- [{title}]({url}): {desc}{suffix}")
            full += [f"---8<--- {url}", "", path.read_text(encoding="utf-8").rstrip(), ""]
            n += 1
        lines.append("")

    # Root pages
    lines += [
        "## Meta",
        "",
        f"- [Documentation update log]({base}log/): dated history of changes to this bundle.",
        "",
    ]
    log = DOCS / "log.md"
    if log.exists():
        full += [f"---8<--- {base}log/", "", log.read_text(encoding="utf-8").rstrip(), ""]

    (DOCS / "llms.txt").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    (DOCS / "llms-full.txt").write_text("\n".join(full).rstrip() + "\n", encoding="utf-8")
    print(
        f"llms.txt: {n} pages indexed; llms-full.txt: "
        f"{(DOCS / 'llms-full.txt').stat().st_size // 1024} KB"
    )


if __name__ == "__main__":
    sys.exit(main())
