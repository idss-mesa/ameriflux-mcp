---
title: "Prompts, resources and status"
description: "The three ameriflux-mcp prompts, the guide and reference resources agents read, the site card template, and the amf_ping status report."
type: Guide
tags:
  - tools
  - prompts
  - resources
  - agents
generated:
  by: "claude/opus-5.5"
  at: "2026-10-24T00:00:00Z"
sources:
  - id: mcp-prompts
    resource: "https://modelcontextprotocol.io/specification/2026-07-28/server/prompts"
    title: "MCP specification: prompts"
    author: "team:modelcontextprotocol"
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design"
    author: "team:idss-mesa"
status: draft
stale_after: "2027-04-24T00:00:00Z"
---

# Prompts, resources and status

Besides its tools, ameriflux-mcp offers **prompts** (task recipes a client can show as
commands[^mcp-prompts]) and **resources** (guides and reference tables an agent reads on
demand). Both work over stdio and HTTP and need no account.

## Prompts

| Prompt | Arguments | What it asks the agent to do |
| --- | --- | --- |
| `find_flux_sites` | `question` (required), `region`, `ecosystem`, `years`, `variables` | Search towers with the filters the question implies, read the best candidates, check their years and policy, and end with a table. It downloads nothing. |
| `plan_site_analysis` | `sites` (required, up to 20), `product`, `variables`, `years` | Availability, variable meanings and BADM; then local files first, or a download **plan** shown to the user, confirmed only after they agree; a preview; citations. For FLUXNET2015 it explains the fluxnet.org route instead. |
| `cite_flux_data` | `sites` (required, up to 50), `product` | Every citation as returned, the acknowledgments verbatim, Legacy site funding, the data-availability sentence, the processing references and the obligations. |

Arguments are checked before a recipe is returned: site lists are capped, products are
normalized (`FLUXNET-1F` → `FLUXNET`), and years must read as `2012` or `2010-2015`. A
recipe names only tools and resources the server has.

## Guides

| URI | Read it for |
| --- | --- |
| `ameriflux://guide/agent-workflow` | The seven-call path from a question to previewed, cited data; inputs and errors |
| `ameriflux://guide/products` | BASE-BADM, BIF, FLUXNET, FLUXNET2015 and FLUXNET-CH4: which to use, FULLSET vs SUBSET, bulk BADM, versions |
| `ameriflux://guide/data-policy` | CC-BY-4.0, Legacy, Tier One and Tier Two, and why mixing escalates |
| `ameriflux://guide/variable-grammar` | How BASE and FLUXNET variable names are built |
| `ameriflux://guide/identity` | What a download discloses, how the user configures it, the download flow |
| `ameriflux://guide/file-formats` | File names and contents, timestamps, UTC offsets, previews, safety rules |
| `ameriflux://guide/fluxnet2015-access` | Getting FLUXNET2015 zips from fluxnet.org yourself |

## Reference tables

| URI | Content |
| --- | --- |
| `ameriflux://reference/vocabularies` | IGBP classes and Köppen climates in AmeriFlux's wording, the product × policy matrix, intended-use codes, networks |
| `ameriflux://reference/fp-variables` | The FP Standard variables with units and QA/QC ranges (live, or the bundled snapshot) |
| `ameriflux://reference/fluxnet-variables` | FLUXNET FULLSET/SUBSET and ONEFlux variables with units per resolution |
| `ameriflux://reference/acknowledgments` | The verbatim acknowledgment and data-availability texts, with the date checked |
| `ameriflux://reference/neon-crosswalk` | NEON site codes and their AmeriFlux IDs, from the live catalog |
| `ameriflux://reference/lter-crosswalk` | AmeriFlux sites linked to LTER sites and EDI scopes (draft) |

The template `ameriflux://site/{site_id}` returns one site's card, the same payload as
`amf_get_site`; NEON codes and FLUXNET2015 old IDs resolve too.

## amf_ping

`amf_ping` reports the server version, the protocol (`2026-07-28`) and transport, which
download-identity fields are configured (booleans and profile names only, never values),
whether downloads are enabled and where they go, the local roots, cache statistics and,
with `check_api=true`, whether one small AmeriFlux API request answers and how fast. Call
it first when a tool is missing or a download refuses. `ameriflux-mcp --check` runs the
same report offline from the command line.

[^mcp-prompts]: MCP specification: prompts. <https://modelcontextprotocol.io/specification/2026-07-28/server/prompts>
