---
title: "Tool reference"
description: "Every ameriflux-mcp tool with its inputs, result fields, upstream endpoints and annotations, generated from the tool registry."
type: MCP Tool Reference
tags:
  - tools
  - reference
  - generated
generated:
  by: "process:gen_tools_reference"
  at: "2026-10-24T00:00:00Z"
sources:
  - id: registry
    resource: "https://github.com/idss-mesa/ameriflux-mcp/tree/main/src/ameriflux_mcp/tools"
    title: "ameriflux-mcp tool registry"
    author: "team:idss-mesa"
status: stable
---

# Tool reference

Generated from the tool registry by `scripts/gen_tools_reference.py`; do not edit by hand. 4 tools are registered. Inputs are snake_case and outputs camelCase. Every result also carries `resolved`, `notes`, `nextSteps` and `source` (whose `backend` says what answered: the AmeriFlux API, its file server, or nothing upstream), and failures return `structuredContent.error` with a stable `code`. Tools still to come are on the [roadmap](roadmap.md).

| Tool | Title | Family | Download identity |
| --- | --- | --- | --- |
| [`amf_get_availability`](#amf_get_availability) | Get data availability per site and product | [availability](discovery.md) | no |
| [`amf_get_site`](#amf_get_site) | Get one AmeriFlux or FLUXNET site | [discovery](discovery.md) | no |
| [`amf_ping`](#amf_ping) | Check ameriflux-mcp status | [core](roadmap.md) | no |
| [`amf_search_sites`](#amf_search_sites) | Search AmeriFlux and FLUXNET sites | [discovery](discovery.md) | no |

## amf_get_availability

**Get data availability per site and product.** Published years per site for AmeriFlux BASE-BADM and FLUXNET (FLUXNET-1F), FLUXNET2015 and FLUXNET-CH4, and BADM (BIF) membership, each labelled with the data policy it is shared under (CC-BY-4.0, Legacy, Tier Two). Lists requested sites without data and why, and the policy the selection must follow with its obligations. Invalid product/policy pairs fail before any request. Next: call amf_get_citation for these sites.

| | |
| --- | --- |
| Surface | `availability` |
| Download identity | not needed |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET amfcdn.lbl.gov/api/v1/data_availability/{network}/{product}/{policy}`<br>`GET amfcdn.lbl.gov/api/v1/site_availability`<br>`GET amfcdn.lbl.gov/api/v2/site_info_display/AmeriFlux` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `sites` | array of string \\| null |  | null | Site IDs, NEON codes or names (up to 50). Omit for every site with data. (max items 50) |
| `products` | array of string \\| null |  | null | BASE-BADM, BIF, FLUXNET, FLUXNET2015, FLUXNET-CH4. Default: the products of each site's collections (BASE-BADM and FLUXNET for AmeriFlux sites), or BASE-BADM when no sites are given. (max items 5) |
| `policy` | string \\| null |  | null | CCBY4.0, LEGACY or TIER2: only data usable under that policy. Default: every row labelled with its own policy. |
| `years` | string \\| null |  | null | Only years in this window: '2015' or '2010-2015'. |
| `limit` | integer |  | `50` | >= 1; <= 200 |
| `offset` | integer |  | `0` | >= 0 |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `rows` | array of AvailabilityRow |  |
| `emptySites` | array of EmptySite | Requested sites without data for a product, and why. |
| `policyVerdict` | array of PolicyVerdict | The policy the requested sites must follow, per product, with obligations. |
| `combinedObligations` | array of ObligationOut | Every obligation once, across all collections. |
| `summary` | AvailabilitySummary |  |
| `page` | Page |  |

## amf_get_site

**Get one AmeriFlux or FLUXNET site.** One site by ID (any case), NEON code, FLUXNET2015 old ID or name: location, IGBP and Köppen with AmeriFlux's descriptions, data policy and what it means, DOIs, years per product (BASE, FLUXNET, FLUXNET2015, FLUXNET-CH4), member networks, links to NEON and to LTER data in EDI, team (no emails by default), measured BASE variables. Next: call amf_get_availability for exact years or amf_get_citation to cite it.

| | |
| --- | --- |
| Surface | `discovery` |
| Download identity | not needed |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET amfcdn.lbl.gov/api/v2/site_info_display/AmeriFlux`<br>`GET amfcdn.lbl.gov/api/v1/site_display/FLUXNET/FLUXNET2015`<br>`GET amfcdn.lbl.gov/api/v1/site_display/FLUXNET/FLUXNET-CH4` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `site` | string | yes |  | Site ID (US-Ha1, any case), NEON code (SRER), FLUXNET2015 old ID (DK-ZaF) or site name. (max length 200) |
| `include` | array of `description` \\| `team` \\| `variables` \\| `disturbance` \\| null |  | null | Optional sections; default all: description, team, variables, disturbance. |
| `include_contacts` | boolean |  | false | Include team emails, if the server allows it (privacy.allow_contact_emails). |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `siteId` | string |  |
| `name` | string |  |
| `collections` | array of string |  |
| `status` | string \\| null |  |
| `tower` | Tower |  |
| `location` | Location |  |
| `ecosystem` | Ecosystem |  |
| `policy` | PolicyInfo |  |
| `dois` | Dois |  |
| `products` | SiteProducts |  |
| `networks` | array of string |  |
| `crosslinks` | Crosslinks |  |
| `gasSpecies` | array of string |  |
| `description` | string \\| null |  |
| `disturbance` | array of string \\| null |  |
| `team` | array of TeamEntry \\| null |  |
| `teamTotal` | integer \\| null |  |
| `baseVariables` | array of string \\| null | FP Standard base names in the site's BASE data (up to 60). |
| `baseVariablesTotal` | integer \\| null |  |

## amf_ping

**Check ameriflux-mcp status.** Liveness and capability report: server version, protocol and transport; whether a download identity is configured (booleans and profile names only, never the values) and which tools need it; whether downloads are enabled and where files go. With check_api=true it also makes one small request to the AmeriFlux API to confirm connectivity. Next: read ameriflux://guide/identity to set up downloads.

| | |
| --- | --- |
| Surface | `core` |
| Download identity | not needed |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET amfcdn.lbl.gov/api/v1/fp_var` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `check_api` | boolean |  | false | Also make one small request to the AmeriFlux API (the FP Standard variable list) to confirm connectivity. |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `pong` | `ok` |  |
| `version` | string |  |
| `protocolVersion` | string |  |
| `transport` | `stdio` \\| `http` |  |
| `identity` | IdentityReport |  |
| `identityRequiredTools` | array of string | Registered tools that need the download identity (auth_required without it). |
| `downloadsEnabled` | boolean |  |
| `downloadDir` | string \\| null |  |
| `localRoots` | array of string \\| null | Directories the local file tools may read (stdio only). |
| `endpoints` | Endpoints |  |
| `cache` | CacheReport |  |
| `upstream` | UpstreamCheck \\| null | Present when check_api was requested. |

## amf_search_sites

**Search AmeriFlux and FLUXNET sites.** Find flux tower sites in the AmeriFlux (856), FLUXNET2015 (212) and FLUXNET-CH4 (81) catalogs by words, place (bbox or near a point), IGBP ecosystem, Köppen climate, country/state, status, member network (NEON, LTER, ...), data product and policy, years with data, measured variables or gas species. Returns compact site summaries with years per product, facets over all matches, and paging. Next: call amf_get_site for one site or amf_get_availability for exact years.

| | |
| --- | --- |
| Surface | `discovery` |
| Download identity | not needed |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET amfcdn.lbl.gov/api/v2/site_info_display/AmeriFlux`<br>`GET amfcdn.lbl.gov/api/v1/site_display/FLUXNET/FLUXNET2015`<br>`GET amfcdn.lbl.gov/api/v1/site_display/FLUXNET/FLUXNET-CH4` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `query` | string \\| null |  | null | Words matched against site ID, name, state, country, NEON code and networks (every word must match; prefixes count, e.g. 'harv'). (max length 200) |
| `collection` | `ameriflux` \\| `fluxnet2015` \\| `fluxnet_ch4` \\| `all` |  | `"all"` | ameriflux (856 sites), fluxnet2015 (212), fluxnet_ch4 (81) or all. |
| `product` | string \\| null |  | null | Only sites with data in BASE-BADM, FLUXNET (FLUXNET-1F), FLUXNET2015 or FLUXNET-CH4. |
| `policy` | string \\| null |  | null | CCBY4.0, LEGACY (AmeriFlux) or TIER2 (Tier-Two-only FLUXNET2015/CH4 sites). CC-BY-4.0, Legacy and Tier2 spellings are accepted. |
| `igbp` | array of string \\| null |  | null | IGBP classes, e.g. ['DBF', 'ENF'] (see the vocabulary). (max items 17) |
| `koeppen` | array of string \\| null |  | null | Köppen codes or prefixes, e.g. ['Dfb'] or ['B']. (max items 30) |
| `country` | array of string \\| null |  | null | Country codes as in site IDs ('US', 'CA', 'BR') or names ('Canada'). (max items 50) |
| `state` | array of string \\| null |  | null | US state or province codes, e.g. ['NM', 'AZ']. (max items 60) |
| `status` | `active` \\| `inactive` \\| `any` |  | `"any"` | AmeriFlux tower status. |
| `network` | array of string \\| null |  | null | Member networks besides AmeriFlux, e.g. ['NEON'], ['LTER'], ['Phenocam']. (max items 12) |
| `bbox` | array of number \\| null |  | null | [west, south, east, north] in decimal degrees (no antimeridian crossing). (min items 4; max items 4) |
| `near` | Near \\| null |  | null | Sites within radius_km of a point. |
| `years` | string \\| null |  | null | Data overlapping a year or range ('2015', '2010-2015') in the chosen product (default: BASE for AmeriFlux sites, the FLUXNET tier range otherwise). |
| `min_years` | integer \\| null |  | null | At least this many data years. (>= 1; <= 100) |
| `base_variable` | array of string \\| null |  | null | FP Standard base names every site must measure, e.g. ['FCH4', 'SWC']. (max items 20) |
| `gas` | array of string \\| null |  | null | Flux gas species, e.g. ['CH4'] or ['CO2', 'H2O']. (max items 6) |
| `sort` | `site_id` \\| `name` \\| `years` \\| `distance` \\| null |  | null | Default: distance with near, relevance with query, else site_id. |
| `limit` | integer |  | `25` | >= 1; <= 200 |
| `offset` | integer |  | `0` | >= 0 |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `sites` | array of SiteSummary |  |
| `facets` | Facets | Counts over every match, not just this page. |
| `page` | Page |  |
