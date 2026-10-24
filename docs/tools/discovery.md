---
title: "Discovery and availability"
description: "Find flux tower sites with amf_search_sites, read one with amf_get_site, and check which years exist per product and policy with amf_get_availability."
type: Guide
tags:
  - tools
  - discovery
  - availability
  - data-policy
generated:
  by: "claude/opus-5.5"
  at: "2026-10-24T00:00:00Z"
sources:
  - id: research
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md"
    title: "ameriflux-mcp verified research (sections 1 and 3)"
    author: "team:idss-mesa"
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design (D6, D7, D10, D20, D34)"
    author: "team:idss-mesa"
  - id: amf-sites
    resource: "https://ameriflux.lbl.gov/sites/site-search/"
    title: "AmeriFlux site search"
    author: "team:ameriflux"
status: stable
stale_after: "2027-04-24T00:00:00Z"
---

# Discovery and availability

Three tools answer "which towers, and what data do they have?" They read the AmeriFlux
site catalog and availability lists, which need no account, and work over stdio and
HTTP alike. Inputs and result fields are in the [Tool reference](reference.md).

## One catalog for three collections

ameriflux-mcp merges three lists into one catalog[^research], the same data the
[AmeriFlux site search](https://ameriflux.lbl.gov/sites/site-search/){target=_blank}[^amf-sites]
shows:

| Collection | Sites | What it is |
| --- | --- | --- |
| `ameriflux` | about 856 | AmeriFlux sites across the Americas, with BASE and FLUXNET (FLUXNET-1F) years, data policy, DOIs, team, networks and measured variables |
| `fluxnet2015` | 212 | The frozen FLUXNET2015 release, worldwide, with Tier One (CC-BY-4.0) and Tier Two year ranges |
| `fluxnet_ch4` | 81 | The FLUXNET-CH4 Community Product V1.0 |

A tower in several lists is one site (US-Ha1 is in `ameriflux` and `fluxnet2015`). Sites
only in a FLUXNET list, such as DE-Tha, carry the sparser FLUXNET fields. The catalog is
cached for six hours, and on stdio also on disk, so a restarted server does not reload
it[^design].

## Naming a site

Every `site` or `sites` argument accepts:

- a site ID in any case: `US-Ha1`, `us-ha1`;
- a NEON site code: `SRER` is `US-xSR`;
- a FLUXNET2015 ID renamed after the release: `DK-ZaF` is `GL-ZaF` (with a note);
- a site name: `Santa Rita`, `Mayberry Wetland`.

Each interpretation is echoed in `resolved`. A name that fits several sites fails with
`ambiguous_input` and lists them (`Harvard Forest` gives US-Ha1, US-Ha2, US-Ha3, …): pick
one and call again.

## amf_search_sites

Filters combine (every filter must hold): words in the ID, name, place, NEON code or
networks (prefixes count: `harv`); `collection`; `product` and `policy`; IGBP class;
Köppen climate (prefixes: `B` is every dry climate); country (code as in site IDs, or
name); state or province; tower status; member network (`NEON`, `LTER`, `Phenocam`, …);
a bounding box or `near` a point; data years overlapping a window, or at least
`min_years`; measured BASE variables (`FCH4`); flux gas species (`CH4`).

Each site comes with its years per product, its policy and its member networks;
`facets` count every match by collection, IGBP, country, policy and status, so you can
see the shape of a large result before paging through it.

```json
{"tool": "amf_search_sites", "arguments": {"network": ["NEON"], "igbp": ["GRA"]}}
{"tool": "amf_search_sites", "arguments": {"near": {"latitude": 34.36, "longitude": -106.7, "radius_km": 60}}}
{"tool": "amf_search_sites", "arguments": {"collection": "fluxnet2015", "policy": "TIER2"}}
```

## amf_get_site

One site, with the ecosystem and climate described in AmeriFlux's own words (from the
[vocabularies](#resources)), the policy and what it asks of you, DOIs, years per
product, team (names, roles, institutions), measured BASE variables and links to other
networks:

- **NEON**: for NEON towers, the NEON site code and NEON's own flux product,
  DP4.00200.001, with a next step for the NEON MCP server.
- **LTER**: for sites in the [LTER crosswalk](#resources), the LTER site and its EDI
  scope, with a next step for the EDI MCP server. The crosswalk is curated and marked
  draft; each link says whether it comes from the upstream LTER tag or the site name.

Team emails are withheld unless you ask for contacts **and** the server's operator
enabled `privacy.allow_contact_emails` ([Configuration](../getting-started/configuration.md)).

!!! note "AmeriFlux's Köppen wording"

    AmeriFlux describes `Bsh` as "Steppe: very cold winter" and `Bsk` as "Steppe: warm
    winter", the reverse of standard Köppen-Geiger (BSh hot, BSk cold semi-arid). The
    text is passed on as AmeriFlux shows it, with a `koeppenNote` flagging the swap.

## amf_get_availability

The years each site has per product, from AmeriFlux's availability lists:

| Product | Policies | Rows |
| --- | --- | --- |
| `BASE-BADM` | CCBY4.0, LEGACY | years |
| `FLUXNET` (FLUXNET-1F) | CCBY4.0 only | years |
| `FLUXNET2015` | CCBY4.0, TIER2 | years |
| `FLUXNET-CH4` | CCBY4.0, TIER2 | years |
| `BIF` (BADM) | CCBY4.0, LEGACY | membership only: AmeriFlux publishes no BADM years |

Without a `policy`, every row is labelled with the policy its data are actually shared
under. LEGACY and TIER2 lists are supersets of the CC-BY lists (a CC-BY site may also
be used under the stricter terms), so asking for `policy="LEGACY"` returns every site,
while the default labels US-Ha1 `CCBY4.0` and CA-Let `LEGACY`.

For the sites you name, the result also lists:

- **`emptySites`**: requested sites without data for a product, and why (a Legacy site
  has no FLUXNET product; RU-Sam has no Tier One years; no data in your year window);
- **`policyVerdict`**: the policy the selection must follow per product, with its
  obligations: mixing CC-BY and Legacy sites means Legacy, mixing tiers means Tier Two;
- **`combinedObligations`**: every obligation once, across collections.

An impossible product and policy pair (FLUXNET under LEGACY, BASE-BADM under TIER2)
fails with `invalid_argument` before any request: the AmeriFlux API would answer it
with empty rows rather than an error.

## Resources

| URI | Content |
| --- | --- |
| `ameriflux://site/{site_id}` | One site's card (the `amf_get_site` result) |
| `ameriflux://reference/vocabularies` | IGBP classes and Köppen climates in AmeriFlux's wording, the product × policy matrix, intended-use codes, member networks |
| `ameriflux://reference/neon-crosswalk` | NEON site codes and their AmeriFlux sites, from the live catalog |
| `ameriflux://reference/lter-crosswalk` | AmeriFlux sites linked to LTER sites and EDI scopes (draft) |

[^research]: ameriflux-mcp verified research. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md>
[^design]: ameriflux-mcp design. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md>
[^amf-sites]: AmeriFlux site search. <https://ameriflux.lbl.gov/sites/site-search/>
