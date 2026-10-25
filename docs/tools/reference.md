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

Generated from the tool registry by `scripts/gen_tools_reference.py`; do not edit by hand. 11 tools are registered; `amf_list_files`, `amf_preview_data`, `amf_read_bif` are offered only over stdio. Inputs are snake_case and outputs camelCase. Every result also carries `resolved`, `notes`, `nextSteps` and `source` (whose `backend` says what answered: the AmeriFlux API, its file server, or nothing upstream), and failures return `structuredContent.error` with a stable `code`. Tools still to come are on the [roadmap](roadmap.md).

| Tool | Title | Family | Download identity |
| --- | --- | --- | --- |
| [`amf_describe_variables`](#amf_describe_variables) | Describe variable names: grammar, units, QC and sites | [variables](variables.md) | no |
| [`amf_get_availability`](#amf_get_availability) | Get data availability per site and product | [availability](discovery.md) | no |
| [`amf_get_badm`](#amf_get_badm) | Get a site's BADM metadata | [metadata](citation.md) | no |
| [`amf_get_citation`](#amf_get_citation) | Get citations and acknowledgments for sites | [citation](citation.md) | no |
| [`amf_get_site`](#amf_get_site) | Get one AmeriFlux or FLUXNET site | [discovery](discovery.md) | no |
| [`amf_list_files`](#amf_list_files) | List local AmeriFlux and FLUXNET files | [local](local-files.md) | no |
| [`amf_ping`](#amf_ping) | Check ameriflux-mcp status | [core](roadmap.md) | no |
| [`amf_preview_data`](#amf_preview_data) | Preview a local AmeriFlux or FLUXNET data file | [local](local-files.md) | no |
| [`amf_read_bif`](#amf_read_bif) | Read a local BADM (BIF) file | [local](local-files.md) | no |
| [`amf_search_sites`](#amf_search_sites) | Search AmeriFlux and FLUXNET sites | [discovery](discovery.md) | no |
| [`amf_search_variables`](#amf_search_variables) | Search the FP Standard and FLUXNET variable dictionaries | [variables](variables.md) | no |

## amf_describe_variables

**Describe variable names: grammar, units, QC and sites.** Decode up to 20 variable names from BASE or FLUXNET files: base name and FP Standard definition with QA/QC range, qualifiers (_PI, _QC, _F, _IU), position (_H_V_R, _H_V_A, _#), FLUXNET processing tokens (MDS, VUT/CUT, NT/DT, REF, percentiles), units and QC meaning per resolution, sign conventions. With site: whether the site measures it, sensor heights and instruments, yearly coverage. Next: call amf_get_availability for the site's years.

| | |
| --- | --- |
| Surface | `variables` |
| Download identity | not needed |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET amfcdn.lbl.gov/api/v1/fp_var` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `names` | array of string | yes |  | Variable names as in file headers: TA_F_1_1_1, FC_PI_F_1_1_A, GPP_NT_VUT_REF, NEE_VUT_05, TS_F_MDS_2_QC … (min items 1; max items 20) |
| `resolution` | string \\| null |  | null | HH (also HR), DD, WW, MM or YY: units and QC meaning at this resolution (FLUXNET). Default: all resolutions. |
| `site` | string \\| null |  | null | A site (ID, NEON code or name): adds whether it measures the variable, its measurement heights and instruments, and yearly coverage. (max length 200) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `variables` | array of VariableDescription |  |
| `page` | Page |  |

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

## amf_get_badm

**Get a site's BADM metadata.** A site's Biological, Ancillary, Disturbance and Metadata as the API exposes it, by group: location, IGBP and climate, tower dates, team (no emails by default), disturbance and management, funding sponsors and organizations (needed to acknowledge Legacy sites), reference papers, and instruments with measurement heights. The full BADM ships as the BIF file in BASE-BADM downloads. Next: call amf_get_citation to cite the site.

| | |
| --- | --- |
| Surface | `metadata` |
| Download identity | not needed |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET amfcdn.lbl.gov/api/v2/site_info_display/AmeriFlux`<br>`GET amfcdn.lbl.gov/api/v1/site_display/FLUXNET/FLUXNET2015`<br>`GET amfcdn.lbl.gov/api/v1/site_display/FLUXNET/FLUXNET-CH4`<br>`GET amfcdn.lbl.gov/api/v1/DOI/{site}/{product}` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `site` | string | yes |  | Site ID (any case), NEON code, FLUXNET2015 old ID or name. (max length 200) |
| `include` | array of `site` \\| `team` \\| `disturbance` \\| `funding` \\| `references` \\| `instruments` \\| null |  | null | Sections; default all: site, team, disturbance, funding, references, instruments. |
| `variables` | array of string \\| null |  | null | Instruments: only these base names or exact variables (e.g. ['TA', 'SWC_1_1_1']). (max items 20) |
| `references_limit` | integer |  | `20` | Reference papers per page. (>= 1; <= 200) |
| `references_offset` | integer |  | `0` | >= 0 |
| `include_contacts` | boolean |  | false | Team emails, if the server allows it (privacy.allow_contact_emails). |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `siteId` | string |  |
| `name` | string |  |
| `policy` | string \\| null |  |
| `site` | SiteGroup \\| null |  |
| `team` | array of TeamEntry \\| null |  |
| `disturbance` | array of string \\| null | Dominant disturbance and management (catalog summary of GRP_DM). |
| `fluxMeasurements` | array of string \\| null | Flux gas species measured. |
| `funding` | FundingGroup \\| null |  |
| `references` | ReferencesGroup \\| null |  |
| `instruments` | InstrumentsGroup \\| null |  |

## amf_get_citation

**Get citations and acknowledgments for sites.** Citations for up to 50 sites and one product (BASE-BADM, BIF, FLUXNET, FLUXNET2015): AmeriFlux's own versioned text per site DOI (e.g. 'Ver. 28-5'), the policy the selection must follow with its obligations (mixing CC-BY and Legacy means Legacy; mixing tiers means Tier Two), verbatim acknowledgments, Legacy site funding, the data-availability sentence and processing papers. Optional BibTeX. Next: cite every site in the reference list and follow the obligations.

| | |
| --- | --- |
| Surface | `citation` |
| Download identity | not needed |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET amfcdn.lbl.gov/api/v1/DOI/{site}/{product}` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `sites` | array of string | yes |  | Site IDs (any case), NEON codes, FLUXNET2015 old IDs or names. (min items 1; max items 50) |
| `product` | string |  | `"BASE-BADM"` | BASE-BADM, BIF (cited with the BASE DOI), FLUXNET (FLUXNET-1F) or FLUXNET2015. FLUXNET-CH4 citations arrive in v0.2. |
| `include_bibtex` | boolean |  | false | Add a BibTeX @misc entry per citation. |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `product` | string |  |
| `citations` | array of CitationOut |  |
| `missing` | array of MissingCitation | Requested sites without a citation, and why. |
| `effectivePolicy` | EffectivePolicyOut |  |
| `acknowledgments` | array of AcknowledgmentOut |  |
| `siteFunding` | array of SiteFunding | Legacy policy: acknowledge each site's funding (DOI record sponsors). |
| `dataAvailability` | DataAvailabilityOut \\| null |  |
| `processingReferences` | array of ReferenceOut |  |
| `bibtexElided` | boolean \\| null |  |
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

## amf_list_files

**List local AmeriFlux and FLUXNET files.** Find the AmeriFlux and FLUXNET files already on this computer, in the download directory and configured local roots: BASE and BASE-BADM zips, BIF files, AmeriFlux FLUXNET (ONEFlux) and FLUXNET2015 archives, with each archive's members classified by kind (data, ERA, BIFVARINFO, BIF, aux tables), site, resolution, years and version. Unsafe members are flagged. stdio only. Next: call amf_preview_data(file=...) on one.

| | |
| --- | --- |
| Surface | `local` |
| Download identity | not needed |
| Transports | stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=false |
| Upstream endpoints | none |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `path` | string \\| null |  | null | A folder or archive inside the download directory or a local root; default: every root. (max length 1000) |
| `family` | array of `base` \\| `bif` \\| `fluxnet` \\| `fluxnet2015` \\| `fluxnet_ch4` \\| null |  | null | Only these families. |
| `site` | string \\| null |  | null | Only this site ID (any case). (max length 20) |
| `include_members` | boolean |  | true | Classify the members of each archive. |
| `limit` | integer |  | `50` | >= 1; <= 200 |
| `offset` | integer |  | `0` | >= 0 |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `roots` | array of string |  |
| `files` | array of FileEntry |  |
| `facets` | ListFacets |  |
| `unrecognized` | integer | Files skipped because their names are not ours. |
| `membersElided` | boolean \\| null |  |
| `page` | Page |  |

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

## amf_preview_data

**Preview a local AmeriFlux or FLUXNET data file.** Summarize or page through a local BASE, AmeriFlux FLUXNET or FLUXNET2015 CSV, in place or inside its zip: time step and range, per-column count, missing (-9999), min, max, mean and out-of-range counts, units per resolution, a time window, a QC filter, UTC timestamps from the site's BIF, a SUBSET column view, and aux tables. Stops within a byte and time budget. stdio only. Next: call amf_describe_variables on columns to decode.

| | |
| --- | --- |
| Surface | `local` |
| Download identity | not needed |
| Transports | stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=false |
| Upstream endpoints | none |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `file` | string \\| null |  | null | A file or 'archive.zip::member.csv', relative to a local root (see amf_list_files). Or give site and product instead. (max length 1000) |
| `site` | string \\| null |  | null | Newest local file of this site. (max length 20) |
| `product` | string \\| null |  | null | With site: BASE-BADM (default), FLUXNET or FLUXNET2015. |
| `resolution` | `HH` \\| `HR` \\| `DD` \\| `WW` \\| `MM` \\| `YY` \\| null |  | null | Member of an archive to read (default HH; HR sites match HH). |
| `columns` | array of string \\| null |  | null | Columns by name (default: up to 80 in summaries). (max items 60) |
| `start` | string \\| null |  | null | First time, e.g. 2012, 2012-06, 2012-06-01T12:00. |
| `end` | string \\| null |  | null | Last time (inclusive): end='2012' keeps all of 2012. |
| `mode` | `summary` \\| `rows` |  | `"summary"` | summary: per-column statistics; rows: a window of rows. |
| `max_rows` | integer |  | `100` | Rows per page (capped by the server). (>= 1; <= 5000) |
| `offset` | integer |  | `0` | Rows to skip within the time window. (>= 0) |
| `qc_max` | integer \\| null |  | null | HH/HR FLUXNET: keep values whose _QC flag is at most this. (>= 0; <= 3) |
| `qc_min_fraction` | number \\| null |  | null | DD and coarser FLUXNET: keep values whose _QC fraction is at least this. (>= 0; <= 1) |
| `to_utc` | boolean |  | false | Add UTC timestamps (offset from the site's BIF). |
| `view` | `full` \\| `subset` |  | `"full"` | subset: only FLUXNET2015 SUBSET variables (AmeriFlux FLUXNET files). |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `fileInfo` | FileInfo |  |
| `columns` | array of ColumnSummary |  |
| `rowColumns` | array of string \\| null |  |
| `rows` | array of array of number \\| string \\| null \\| null |  |
| `scan` | ScanInfo |  |
| `page` | Page \\| null |  |

## amf_read_bif

**Read a local BADM (BIF) file.** Read a local BADM Interchange Format file, the site metadata shipped in BASE-BADM (xlsx) and AmeriFlux FLUXNET (CSV) downloads, also from inside the zip: entries by group (location, IGBP, team, instruments, disturbance …), UTC offsets with their start dates, the DOI and citation recorded for that version, and funding acknowledgments. Emails and addresses are withheld by default. stdio only. Next: call amf_get_citation for the current citation.

| | |
| --- | --- |
| Surface | `local` |
| Download identity | not needed |
| Transports | stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=false |
| Upstream endpoints | none |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `file` | string \\| null |  | null | A BIF xlsx or CSV, or an archive holding one (BASE-BADM, FLUXNET), relative to a local root. Or give site. (max length 1000) |
| `site` | string \\| null |  | null | The newest local BIF of this site. (max length 20) |
| `groups` | array of string \\| null |  | null | Only these groups, e.g. ['GRP_UTC_OFFSET', 'GRP_DOI']. (max items 40) |
| `site_id` | string \\| null |  | null | In a bulk file (AA-Flx, AA-Net): only this site. (max length 20) |
| `include_contacts` | boolean |  | false | Emails and addresses, if the server allows it (privacy settings). |
| `limit` | integer |  | `100` | >= 1; <= 500 |
| `offset` | integer |  | `0` | >= 0 |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `fileInfo` | BifFileInfo |  |
| `entries` | array of BifEntryOut |  |
| `utcOffsets` | array of UtcOffsetOut |  |
| `citations` | array of BifCitation |  |
| `acknowledgments` | array of BifAcknowledgment |  |
| `withheld` | integer | Personal values withheld (emails, addresses, land owners). |
| `page` | Page |  |

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

## amf_search_variables

**Search the FP Standard and FLUXNET variable dictionaries.** Find variable names in the FP Standard list (AmeriFlux BASE, live, with QA/QC ranges) and the FLUXNET dictionaries (AmeriFlux FLUXNET from ONEFlux v1.3; FLUXNET2015 FULLSET and SUBSET), by words, category or resolution. FLUXNET units change with resolution (NEE is umol m-2 s-1 at HH, gC m-2 d-1 at DD), so each result lists units per resolution and SUBSET membership. Next: call amf_describe_variables on the names.

| | |
| --- | --- |
| Surface | `variables` |
| Download identity | not needed |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET amfcdn.lbl.gov/api/v1/fp_var` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `query` | string \\| null |  | null | Words matched against name, description and units (prefixes count: 'soil temp', 'GPP', 'methane'). (max length 200) |
| `dictionary` | `fp` \\| `fluxnet` \\| `fluxnet_fullset` \\| `fluxnet_subset` \\| `all` |  | `"all"` | fp (FP Standard, BASE), fluxnet (AmeriFlux FLUXNET, ONEFlux v1.3), fluxnet_fullset / fluxnet_subset (FLUXNET2015), or all. |
| `category` | string \\| null |  | null | FP type (GASES, MET_RAD, MET_SOIL, …) or FLUXNET section (PARTITIONING, NET ECOSYSTEM EXCHANGE, …); prefixes count. (max length 60) |
| `resolution` | string \\| null |  | null | HH (also HR), DD, WW, MM or YY: FLUXNET variables available at it, with its units. |
| `limit` | integer |  | `25` | >= 1; <= 200 |
| `offset` | integer |  | `0` | >= 0 |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `variables` | array of VariableSummary |  |
| `facets` | VariableFacets |  |
| `page` | Page |  |
