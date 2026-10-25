---
title: "Quickstart"
description: "A first session with ameriflux-mcp: register it with Claude Code, check it with amf_ping, find a tower, check its data and get a citation."
type: Tutorial
tags:
  - getting-started
  - quickstart
  - tutorial
generated:
  by: "claude/opus-5.5"
  at: "2026-10-24T00:00:00Z"
sources:
  - id: claude-code-mcp
    resource: "https://docs.claude.com/en/docs/claude-code/mcp"
    title: "Claude Code — MCP"
    author: "team:anthropic"
  - id: amf-products
    resource: "https://ameriflux.lbl.gov/data/flux-data-products/"
    title: "AmeriFlux flux data products"
    author: "team:ameriflux"
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design (tool surface)"
    author: "team:idss-mesa"
status: draft
stale_after: "2027-04-23T00:00:00Z"
---

# Quickstart

This walks through a first session in Claude Code[^claude-code-mcp]; other clients work
the same way once connected ([Clients](clients.md)).

!!! note "Results abbreviated"

    The results below are shortened; the [tool reference](../tools/reference.md) lists
    every field, following the design[^design]. Step 6 needs downloads turned on
    (`AMERIFLUX_MCP_DOWNLOADS__ENABLED=true`; they are off by default) and a
    [download identity](identity.md) before `confirm=true` sends anything. The
    `plan_site_analysis` prompt runs the same sequence for chosen sites.

## 1. Register the server

```bash
claude mcp add ameriflux -s user -- ameriflux-mcp --transport stdio
```

No account is needed for this walkthrough. Downloads (step 6 below) need a
[download identity](identity.md).

## 2. Check it

Ask the agent to "call amf_ping with check_api=true". The result shows the version,
protocol `2026-07-28`, the transport, which download-identity fields are configured (as
booleans), whether downloads are enabled, and under `upstream` whether one small request
to the AmeriFlux API succeeded.

## 3. Find towers

```json
{"tool": "amf_search_sites", "arguments": {"igbp": ["DBF"], "state": ["MA"], "product": "FLUXNET", "min_years": 10}}
```

→ deciduous broadleaf forest sites in Massachusetts with at least ten years of
AmeriFlux FLUXNET data, each with `siteId` (such as `US-Ha1`, Harvard Forest), name,
location, IGBP class, data policy and the years per product. Sites also resolve by name
or NEON code: `amf_get_site(site="SRER")` finds `US-xSR`, the NEON Santa Rita tower, and
points to the matching NEON data product.

## 4. Check what data exist

```json
{"tool": "amf_get_availability", "arguments": {"sites": ["US-Ha1", "CA-Let"], "products": ["BASE-BADM", "FLUXNET"]}}
```

→ the published years per site and product[^amf-products]. `CA-Let` shares its data
under the Legacy policy, so it has BASE years but appears in `emptySites` for FLUXNET,
with a note that the FLUXNET product exists only for CC-BY sites.

## 5. Understand the variables

```json
{"tool": "amf_describe_variables", "arguments": {"names": ["GPP_NT_VUT_REF", "TA_F_MDS_QC"], "resolution": "DD"}}
```

→ `GPP_NT_VUT_REF` is gross primary production from nighttime partitioning with a
variable USTAR threshold, reference realization, in gC m-2 d-1 at daily resolution;
`TA_F_MDS_QC` is the fraction (0–1) of measured or good-quality gap-filled air
temperature in each day.

## 6. Plan a download

```json
{"tool": "amf_download_data", "arguments": {"sites": ["US-Ha1"], "product": "FLUXNET"}}
```

→ a **plan**, not a download: the exact user ID (masked), email (masked), intended use
and description that would be sent to the US-Ha1 PIs, the data policy (`CCBY4.0`) and
what it asks of you. Only `confirm=true` with `accept_data_policy="CCBY4.0"` sends the
request; the files land in `~/ameriflux-downloads/FLUXNET/` with a checksum record
(see [Downloads](../tools/downloads.md)). Then
`amf_preview_data(site="US-Ha1", product="FLUXNET", resolution="DD")` summarizes the
daily file without loading it all.

## 7. Cite it

```json
{"tool": "amf_get_citation", "arguments": {"sites": ["US-Ha1"], "product": "FLUXNET"}}
```

→ the versioned citation AmeriFlux recommends ("… AmeriFlux FLUXNET-1F US-Ha1 Harvard
Forest EMS Tower (HFR1), Ver. v1.3_r1 (1991-2025), AmeriFlux AMP, (Dataset).
https://doi.org/10.17190/AMF/1871137"), the required acknowledgments, the processing
reference and a data-availability sentence. See
[Citing AmeriFlux and FLUXNET data](../about/citing-ameriflux.md).

Every result also carries `notes` (caveats) and `nextSteps` (concrete follow-up calls),
so agents normally chain these on their own.

[^claude-code-mcp]: Claude Code — MCP. <https://docs.claude.com/en/docs/claude-code/mcp>
[^amf-products]: AmeriFlux flux data products. <https://ameriflux.lbl.gov/data/flux-data-products/>
[^design]: ameriflux-mcp design. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md>
