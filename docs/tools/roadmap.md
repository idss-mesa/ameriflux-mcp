---
title: "Roadmap"
description: "The twelve planned ameriflux-mcp tools, the build step that delivers each, and which work over HTTP or need a download identity."
type: Reference
tags:
  - tools
  - roadmap
  - planning
generated:
  by: "claude/opus-5.5"
  at: "2026-10-24T00:00:00Z"
sources:
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design (tool surface and build order)"
    author: "team:idss-mesa"
  - id: research
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md"
    title: "ameriflux-mcp verified research"
    author: "team:idss-mesa"
status: draft
stale_after: "2027-01-23T00:00:00Z"
---

# Roadmap

ameriflux-mcp is built in eight steps, one pull request each[^design]. This page lists
what each step delivers. Once tools exist, a generated tool reference replaces the
descriptions here.

## Build steps

| Step | Delivers | Status |
| --- | --- | --- |
| 1 | Design, verified API research, a read-only API probe | done |
| 2 | The MCP core ported from edi-mcp, configuration, identity settings, `amf_ping`, CI | done |
| 3 | AmeriFlux API client, rate limiting, cache, site catalog and name resolution, policy engine, recorded test fixtures | done |
| 4 | Site discovery and availability tools | done |
| 5 | Variable, citation and BADM tools | done |
| 6 | Local file readers and previews | done |
| 7 | The download tool (merged only after AmeriFlux confirms third-party use) | next |
| 8 | Prompts, resources, full documentation, Docker image, PyPI release v0.1.0 | planned |

The [tool reference](reference.md) is generated from the server's registry and lists
exactly the tools the current build offers.

## Planned tools

| Tool | Step | HTTP | What it does |
| --- | --- | --- | --- |
| `amf_ping` | 2 | yes | Version, protocol, transport; which identity fields are configured (booleans only); whether the AmeriFlux API answers. |
| `amf_search_sites` | 4 | yes | Find AmeriFlux (856 sites), FLUXNET2015 (212) and FLUXNET-CH4 (81) towers[^research] by name, place, bounding box, IGBP ecosystem class, Köppen climate, years, product, data policy and measured variables. |
| `amf_get_site` | 4 | yes | One site by ID, name, NEON code or FLUXNET2015 alias: location, ecosystem, climate, data policy, DOIs, years per product, team (no emails by default) and links to NEON and EDI. |
| `amf_get_availability` | 4 | yes | Published years per site, product and policy, with the sites that have no data listed separately and the effective policy of the selection. |
| `amf_search_variables` | 5 | yes | Search the FP Standard (145 base names) and FLUXNET FULLSET/SUBSET dictionaries, with units per time resolution. |
| `amf_describe_variables` | 5 | yes | Parse names such as `TA_F_1_1_1` or `GPP_NT_VUT_REF`: qualifiers, gap-filling and partitioning method, QC scheme, units by resolution, sign convention, measurement heights. |
| `amf_get_citation` | 5 | yes | The versioned citation AmeriFlux recommends per site, required acknowledgments, the obligations of the CC-BY-4.0, Legacy or Tier 2 policy, and a data-availability sentence. |
| `amf_get_badm` | 5 | yes | Site metadata (BADM) the API exposes: location, IGBP, climate, team, disturbance and management, funding, reference papers, instruments and measurement heights. |
| `amf_download_data` | 7 | no | BASE-BADM, AmeriFlux FLUXNET and bulk BADM through AmeriFlux's logged download route: a plan first, then `confirm=true`; checksummed files. Needs a [download identity](../getting-started/identity.md). |
| `amf_list_files` | 6 | no | Classify downloaded zips and CSVs by product, site, resolution, years and version. |
| `amf_preview_data` | 6 | no | Column summaries and row windows from local BASE, FLUXNET and FLUXNET2015 files, with time windows, QC filtering, missing values as nulls and a SUBSET view. |
| `amf_read_bif` | 6 | no | Read BADM Interchange Format files (xlsx or CSV), including UTC offsets and the site's DOI citation. |

## Data products covered

| Product | Discover | Availability | Cite | Download | Read locally |
| --- | --- | --- | --- | --- | --- |
| AmeriFlux BASE (BASE-BADM) | yes | yes | yes | yes | yes |
| AmeriFlux BADM / BIF | yes | yes (membership) | yes (BASE DOI) | yes (bulk) | yes |
| AmeriFlux FLUXNET (FLUXNET-1F) | yes | yes | yes | yes | yes |
| FLUXNET2015 FULLSET / SUBSET | yes | yes | yes | no (login-protected form) | yes |
| FLUXNET-CH4 | yes | yes | v0.2 | no | v0.2 |

## After v0.1.0

Version 0.2 focuses on analysis: server-side summaries by year, month or hour with QC
handling, Parquet export with a hand-off to the CyVerse Data Store and mesa-ducklake,
DuckDB as an optional extra, FLUXNET-CH4 readers and citations, and possibly the
European and Australian networks served through the FLUXNET Shuttle.

[^design]: ameriflux-mcp design. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md>
[^research]: ameriflux-mcp verified research. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md>
