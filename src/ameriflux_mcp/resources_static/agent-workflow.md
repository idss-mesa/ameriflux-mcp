# ameriflux-mcp agent workflow

From a question to previewed, cited flux data. Every result is compact JSON with
`resolved`, `notes`, `nextSteps` and `source`; lists carry `page` (follow
`page.nextOffset` before concluding a list is complete).

1. **Find towers** — `amf_search_sites(igbp=['DBF'], state=['MA'], product='FLUXNET',
   min_years=10)`. Filters: `query`, `collection` (`ameriflux`, `fluxnet2015`,
   `fluxnet_ch4`, `all`), `product`, `policy`, `igbp`, `koeppen`, `country`, `state`,
   `bbox` or `near`, `years`/`min_years`, `base_variable`, `gas`. `facets` summarize the
   matches.
2. **Read one** — `amf_get_site(site='US-Ha1')`: location, ecosystem, climate, policy,
   DOIs, years per product, team (no emails by default), NEON and LTER links.
3. **Check years** — `amf_get_availability(sites=[...], products=['FLUXNET'])`: years per
   site and product, `emptySites` with the reason, and `policyVerdict` with the
   obligations the selection must follow.
4. **Understand variables** — `amf_search_variables(query='latent heat')`,
   `amf_describe_variables(names=['GPP_NT_VUT_REF','TA_F_MDS_QC'], resolution='DD')`:
   units at that resolution, QC meaning, sign convention, heights at a site.
5. **Get the data (stdio)** — first `amf_list_files(site=...)`: files already on disk are
   read in place. `amf_download_data` is off by default (listed only when the user sets
   `AMERIFLUX_MCP_DOWNLOADS__ENABLED=true`); without it, the user downloads from the
   AmeriFlux website into the download directory. When it is listed,
   `amf_download_data(sites=[...], product='FLUXNET')` returns a
   **plan** and sends nothing. Show the user `disclosure` (what AmeriFlux sends to the site
   PIs), `ineligible` and `policy.obligations`, and ask. Only after an explicit yes call
   again with `accept_data_policy=<policy.code>` and `confirm=true`. If `blockers` is not
   empty, the user configures the identity (`ameriflux://guide/identity`); never write the
   intended use or description for them. FLUXNET2015 zips come from fluxnet.org
   (`ameriflux://guide/fluxnet2015-access`).
6. **Preview** — `amf_preview_data(site='US-Ha1', product='FLUXNET', resolution='DD',
   columns=['NEE_VUT_REF'])`: count, missing, min, max, mean, outOfRange per column;
   `mode='rows'` with `start`/`end` for a window; `qc_min_fraction`/`qc_max`; `to_utc`.
   `amf_read_bif(file=...)` gives the site metadata and UTC offsets.
7. **Cite** — `amf_get_citation(sites=[...], product='FLUXNET')`: one citation per site,
   verbatim acknowledgments, the data-availability sentence and the obligations.

## Inputs

- Sites: IDs in any case (`us-ha1`), NEON codes (`SRER` → US-xSR), FLUXNET2015 old IDs
  (`DK-ZaF` → GL-ZaF) or names. A confident match is echoed in `resolved`; otherwise
  `ambiguous_input` lists candidates: retry with one of their IDs.
- Products: `BASE-BADM`, `BIF`, `FLUXNET` (also `FLUXNET-1F`), `FLUXNET2015`,
  `FLUXNET-CH4`. Policies: `CCBY4.0` (`CC-BY-4.0`), `LEGACY`, `TIER2`. Invalid pairs fail
  before any request (`ameriflux://guide/products`).

## Errors (`structuredContent.error.code`)

| Code | Meaning | What to do |
| --- | --- | --- |
| `ambiguous_input` | Several sites match | Pick one of `details.candidates` |
| `not_found` | Unknown site, or no DOI for that product | Use `didYouMean` or another product |
| `invalid_argument` | Bad value or product × policy pair | Read `details.reason` and `hint` |
| `auth_required` | No usable download identity | `ameriflux://guide/identity` |
| `feature_unavailable` | FLUXNET2015/CH4 downloads, CH4 reading | Local files or v0.2 |
| `upstream_unavailable` | AmeriFlux unreachable | Retry; `amf_ping(check_api=true)` |
| `upstream_error` | Changed upstream shape (`details.drift`) | Report it |

## Policy in one paragraph

CC-BY-4.0 and AmeriFlux Legacy apply to AmeriFlux sites; mixing them means Legacy for
all. FLUXNET2015 has Tier One (CC-BY-4.0) and Tier Two; mixing means Tier Two. Every
site's DOI goes in the reference list. `ameriflux://guide/data-policy` has the details.
