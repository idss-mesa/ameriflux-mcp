# ameriflux-mcp — verified research

Facts below carry the date they were verified. Re-verify anything that contradicts
observed behaviour. Every network observation was a GET or HEAD request; nothing here
came from a POST (DESIGN.md D28). The raw evidence trail, five research reports each
re-checked by an independent verifier, is `research/2026-10-22-dossier.md`; the approved
build plan is `research/2026-10-22-plan.md`. "UNVERIFIED" marks claims inferred from
client source code or documentation that nobody has observed on the wire.

## 0. Evidence index (verified 2026-10-22)

DESIGN.md cites these as `[E#]`.

| # | Evidence |
|---|---|
| E1 | `/home/tswetnam/github/idss-mesa/ameriflux-mcp` was empty and not a git repo before step 1. |
| E2 | edi-mcp/DESIGN.md: "Template: `idss-mesa/neon-mcp` at `main` (a5949d2); its D-register applies wherever this file is silent." |
| E3 | edi-mcp/pyproject.toml runtime dependencies: mcp>=2.0,<3; httpx>=0.28,<1; defusedxml>=0.7; pydantic>=2.7; pyyaml>=6; structlog>=24; anyio>=4; starlette>=0.40; uvicorn>=0.30. Built with hatchling. |
| E4 | edi registry.py: `NAME_RE ^edi_[a-z_]+$`, `MAX_DESCRIPTION_CHARS = 600`, a "Next:" sentence regex, the `invoke()` pipeline, `fit_to_budget`, `SURFACES`. |
| E5 | edi models/common.py: `ToolResultBase{resolved, notes, nextSteps, source}`, `Page`, inputs `extra='forbid'`, camelCase outputs, `Backend` Literal. |
| E6 | edi config.py: LimitsConfig 50 000 / 200 000 / 25 / 200 / 300 / 4000 / 60 000, `preview_max_bytes` 256 KiB; `__` env nesting; secrets are SecretStr; no `.env` autoload. |
| E7 | edi errors.py: 16 ErrorCodes; `map_api_error` caps redacted upstream detail at 500 characters. |
| E8 | neon resolve.py thresholds 0.75 / 1.15 / 0.45 / 8, didYouMean top 3. |
| E9 | neon downloads.py: realpath confinement, basename regex, host allow-list checked on every redirect hop, caps of 50 files and 2 GiB, `.part` files, skip/error; registered `requires_token=True, token_check="handler"`, stdio only. |
| E10 | edi record_fixtures.py: 40 KiB per fixture, 3 MiB total, secret-shape checks. edi scripts/probe_auth.py POSTs (lines 135, 154), so it is not reused. |
| E11 | edi ci.yml jobs: test, macos, spec-conformance, live (cron `17 7 * * *`); docs.yml checks drift. neon release.yml and Dockerfile use `uv sync --frozen --no-dev --extra pdf`, uid 10001. |
| E12 | `GET https://amfcdn.lbl.gov/api/v1/` → 404 `{"detail":{},"message":"Not Found"}`. No OpenAPI, Swagger or docs path exists on v1 or v2. |
| E13 | `GET v2/site_info_display/AmeriFlux` → `{"values":[856 sites]}`, 1 708 401 B (~248 KB gzipped), 22 keys. Policies CCBY4.0 687 / LEGACY 169; 610 sites have BASE years, 407 FLUXNET years. Team records carry emails (2 703). US-Ha1 `doi` is `{AmeriFlux: 10.17190/AMF/1246059, FLUXNET: 10.17190/AMF/1871137}`. |
| E14 | v1 and v2 are asymmetric: `v2/site_display`, `v2/site_availability` and `v1/site_info_display` all return 404. `v1/site_display/AmeriFlux/US-xSR` ignores the trailing ID and returns the full list. |
| E15 | `GET v1/data_availability/{net}/{prod}/{pol}` returns every site, empty or not. Non-empty: BASE-BADM CCBY4.0 533, LEGACY 610; FLUXNET CCBY4.0 407, LEGACY 0. `AmeriFlux/FOO/BAR` → 200 with 856 empty rows. `FLUXNET/FLUXNET2015/Tier2` → 422 `Must be one of: TIER2, CCBY4.0.`. CC-BY ⊂ LEGACY. |
| E16 | `GET v1/site_availability` → nested `{network:{product:{policy:[[SITE_ID, SITE_NAME]]}}}`. BIF lists 674 sites under CCBY4.0 and 843 under LEGACY. |
| E17 | `GET v1/fp_var?limits=True` → 145 variables in 13 types, with Min and Max. |
| E18 | `GET v1/site_display/FLUXNET/FLUXNET2015` → 212 sites, sparse fields. Site-years 1 493 CC-BY, 1 532 TIER2. Six sites are TIER2-only: RU-Sam, RU-SkP, RU-Tks, RU-Vrk, SE-St1, ZA-Kru. |
| E19 | `GET v1/DOI/US-Ha1/AmeriFlux` → keys `DOI_CONTRIBUTOR, DOI_CONTRIBUTOR_ORGANIZATION, DOI_INFO, DOI_SPONSOR_ORGANIZATION, REFERENCES`; `DATA_POLICY` CCBY4.0; `DOI_CITATION` "J. William Munger, … (2026), AmeriFlux BASE US-Ha1 Harvard Forest EMS Tower (HFR1), Ver. 28-5, AmeriFlux AMP, (Dataset). https://doi.org/10.17190/AMF/1246059". `…/FLUXNET` → "… AmeriFlux FLUXNET-1F US-Ha1 … Ver. v1.3_r1 (1991-2025) … https://doi.org/10.17190/AMF/1871137". `…/BASE` → 200 `{"status":"No valid DOI for BASE"}`. |
| E20 | `DOI/CA-Let/AmeriFlux` → LEGACY, "Ver. 1-5". `DOI/US-Ha1/FLUXNET2015` → `DOI_CITATION: null`. `DOI/US-Ha1/BASE-BADM` → `{}`. `DOI/XX-Zzz/AmeriFlux` → `{"status":"No valid DOI for AmeriFlux"}`. All 200. Contributor records include `DOI_CONTRIBUTOR_EMAIL`. |
| E21 | GET on `v1/data_download`, `v1\|v2/citations/*`, `v1/variable_availability` and the v2 shuttle endpoints → 405 `{"detail":{},"message":"Method Not Allowed"}`. The `data_download` request body (user_id, user_email, site_ids, data_product, data_variant, data_policy, intended_use, description, is_test) comes from the website's datadownload.js and amerifluxr. **The response shape (data_urls, manifest, pi_contact_emails) is UNVERIFIED**, inferred from client code only. |
| E22 | The website sends `user_id='friendlyfluxnetwork'` when not logged in and forces CCBY4.0; the Shuttle sends `fluxnetshuttle` with Referer `local_shuttle`; the website sends `is_test=false` only when served from ameriflux.lbl.gov. amerifluxr requires `@` in the email, appends ` [amerifluxr download]` to the description and sends `is_test` as the string `"true"`/`""`. |
| E23 | `HEAD ftp.fluxdata.org/.ameriflux_downloads/FLUXNET/AMF_US-Ha1_FLUXNET_1991-2025_v1.3_r1.zip`, with or without `?=fluxnetshuttle`: 200, 163 629 147 B, same ETag, `accept-ranges: bytes`, `cache-control: public, max-age=14400`. Directory listing → 403. No signature or expiry in the URL. |
| E24 | ameriflux.lbl.gov/data/data-policy/: the intended use "is sent to the site Principal Investigators (PIs) and posted to the AmeriFlux Data Download Log". The log redirects to `/login/` (login-gated, not public). Mixing CC-BY and Legacy data means Legacy applies. ONEFlux processes CC-BY data only. |
| E25 | Data-policy text, verbatim: CC-BY "Funding for the AmeriFlux data service was provided by the U.S. Department of Energy Office of Science."; Legacy "Funding for the AmeriFlux data portal was provided by the U.S. Department of Energy Office of Science."; FLUXNET add-on "FLUXNET data products were produced and harmonized by eddy covariance regional networks and data processing centers, including AmeriFlux, ChinaFlux, European Fluxes Database, ICOS, JapanFlux, KoFlux, OzFlux, SAEON, and TERN. These products also include a modified version of ERA5 hourly data provided by the Copernicus Climate Change Service."; "Chu, H., Christianson, D.S., Cheah, YW. et al. AmeriFlux BASE data pipeline to support network growth and data sharing. Sci Data 10, 614 (2023). https://doi.org/10.1038/s41597-023-02531-2"; Pastorello et al., Sci Data 7, 225 (2020), https://doi.org/10.1038/s41597-020-0534-3; data-availability sentence "The AmeriFlux [DATA PRODUCT] were accessed from [SOURCE] on XX Month YYYY", where [SOURCE] may be "the AmeriFlux data portal, AmeriFlux APIs, FLUXNET User Interface for the Shuttle, or the FLUXNET Shuttle code". |
| E26 | fluxnet.org labels FLUXNET2015 "outdated" and points to the FLUXNET Shuttle; `/data/download-historical-data/` redirects to `/login/`. Mixing tiers means Tier Two; Tier Two gives providers at least 3 weeks after the first draft. |
| E27 | `ftp.fluxdata.org/.fluxnet_downloads_67934/paper_test/` is an open Apache index of every FLUXNET2015 zip plus whole-dataset bundles. It is not linked from any official page. **Never used** (D15). |
| E28 | webdoc `variable_codes_FULLSET_20200504.csv` (68 347 B, ETag `"10afb-5a4e12f9d7b40"`) and `variable_codes_SUBSET_20200504.csv` (18 685 B, ETag `"48fd-5a4e12bcceb40"`), both served over HTTPS. They contain section rows (TIMEKEEPING, …), per-resolution rows, "not available"/"not defined", two-letter names (PA, WS, WD, RH) and many blank Units cells. FULLSET ≈ 232 variables, SUBSET ≈ 72. |
| E29 | ONEFlux `var_info_definitions_{hh,dd,ww,mm,yy}.txt` are `\|\|`-delimited (Variable, Units, Description, Members) and store µ as U+FFFD. The YY NEE_VUT_REF entry is mislabelled "(CUT)". No CH4 variables. |
| E30 | `BASE_MeasurementHeight_20260908.csv`: 2 254 621 B, 8 columns (Site_ID, Variable, Start_Date, Height, Instrument_Model, Instrument_Model2, Comment, BASE_Version); Start_Date empty in 30 472 of 40 306 rows; 1 159 rows hold a YYYYMM-like value in Comment. Linked from `/data/measurement-height/`; the FTP listing times out. |
| E31 | amerifluxr data-summary CSVs (`AMF_AA-Flx_BASE_VARIABLE-AVAILABILITY_LATEST.csv` 6.5 MB, `…VARIABLE-SUMMARY_LATEST.csv` 6.2 MB) start `create_date:2025-10-20`, year columns Y1990–Y2025; last commit 2025-11-03. |
| E32 | Range read of `AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip` (22 077 723 B): FLUXMET, ERA5 and BIFVARINFO files at HH/DD/WW/MM/YY, a `_BIF_` CSV, README.txt and DATA_POLICY_LICENSE_AND_INSTRUCTIONS.txt; no FULLSET/SUBSET token in any name. FLUXMET_HH starts with the header row (no `#` lines), 152 columns. Range read of `AMF_US-Ha1_BASE-BADM_28-5.zip` (28 443 441 B): `AMF_US-Ha1_BASE_HR_28-5.csv` (229 MB) and `AMF_US-Ha1_BIF_20260908.xlsx`. |
| E33 | amerifluxr's US-CRT BASE sample starts `# Site: US-CRT,,,,` and `# Version: 2-5,,,,`; missing value -9999. Its BIF xlsx has 5 columns (SITE_ID, GROUP_ID, VARIABLE_GROUP, VARIABLE, DATAVALUE) and includes GRP_UTC_OFFSET, GRP_DOI and GRP_ACKNOWLEDGEMENT. |
| E34 | Shuttle filename regex (`shuttle.py:68`, applied with IGNORECASE): `^([A-Z]{2,10})_([A-Z]{2}-[A-Za-z0-9]{3})_FLUXNET_(\d{4})-(\d{4})_(v\d+(?:\.\d+)?)_(r\d+)\.zip$`. Shuttle is BSD-3 and not on PyPI (v0.3.8, 2026-04-30); amerifluxr BSD-3 (v1.0.0); ONEFlux LBNL BSD-3; icoscp GPLv3+. |
| E35 | 47 AmeriFlux sites carry the NEON network tag; they equal the NEON DP4.00200.001 site list, with the NEON code in parentheses in `site_name` (e.g. "NEON Santa Rita Experimental Range (SRER)"). Only 18 sites carry the LTER tag; US-Seg, US-Ses, US-Wjs and US-Mpj are missing it. |
| E36 | FLUXNET2015 known issues: DK-ZaF, DK-ZaH and DK-NuF became GL-*; NO-Adv and NO-Blv became SJ-*. 11 sites are HR (AU-Tum, BR-Sa1, SJ-Blv, US-Cop, US-Ha1, US-MMS, US-Ne1, US-Ne2, US-Ne3, US-PFa, US-UMB). Largest CSV: FI-Hyy FULLSET_HH at 516 MB. |
| E37 | The API sends no Cache-Control, ETag, Last-Modified or rate-limit headers (`cf-cache-status: DYNAMIC`, `Access-Control-Allow-Origin: *`). 20 sequential GETs all returned 200 in 0.17–0.24 s. ameriflux.lbl.gov robots.txt: `Crawl-delay: 15`. |
| E38 | The `fluxnet` R package reads AMERIFLUX_USER_NAME, AMERIFLUX_USER_EMAIL, AMERIFLUX_INTENDED_USE and AMERIFLUX_DESCRIPTION; there is no AMERIFLUX_USER_ID precedent. |
| E39 | The MCP registry returns 0 results for "ameriflux" and for "fluxnet"; GitHub flux-net/FLUXNET-MCP is empty. |
| E40 | edi `tests/test_resources.py:52` asserts instructions are ≤1 200 characters. No sibling ships a server.json. |
| E41 | `DOI/US-CRT/AmeriFlux` → CCBY4.0, "Jiquan Chen, Housen Chu (2021), AmeriFlux BASE US-CRT …, Ver. 5-5". `DOI/US-Ha1/BIF` → `{}`. `DOI/US-Ha1/FLUXNET-CH4` → `{"status":"No valid DOI for FLUXNET-CH4"}`. |
| E42 | `v1/data_availability/AmeriFlux/BASE-BADM/Tier2` → 200, 856 rows, 0 non-empty: only the FLUXNET network validates the policy segment. |
| E43 | `v1/site_display/FLUXNET/FLUXNET2015` → 212; `…/FLUXNET/FLUXNET-CH4` → 81; `v1/data_availability/FLUXNET/FLUXNET-CH4/CCBY4.0` → 81 rows, 79 non-empty. |
| E44 | amerifluxr `R/amf_download_bif.R:79-83` calls `amf_download_base(site_id = ifelse(site_w_data, "AA-Flx", "AA-Net"), data_product = "BASE-BADM")`; `amf_download_base.R:223` checks agree_policy, `:258-259` sends is_test as `"true"`/`""`, `:293` drops `FLUXNET-BIF` links. |
| E45 | ameriflux.lbl.gov `datadownload.js:148-149` reads `sitesIndex['BIF'][CCBY4.0\|LEGACY]`; `:264, :303-307` read AA-Flx/AA-Net URLs from the response (`aa_urls`); AA-Net is skipped for FLUXNET. |
| E46 | The data-policy page (tags stripped) contains every E25 string. |
| E47 | modelcontextprotocol/registry `docs/modelcontextprotocol-io/package-types.mdx:80`: the registry verifies PyPI ownership by finding `mcp-name: $SERVER_NAME` in the package README. |

Step 1 probe results (`scripts/probe_api.py`, 2026-10-22; sections 1, 4 and 9 below):

| # | Evidence |
|---|---|
| E48 | P1 reproduced E12–E18 and E42–E43 exactly (status, envelope, row and non-empty counts; table in section 1). |
| E49 | Availability keys differ by path. `site_display/FLUXNET/FLUXNET2015` rows carry `CCBY4_0` (206) and `Tier2` (212) plus `CH4_CCBY4.0` (24) / `CH4_TIER2` (26); `site_display/FLUXNET/FLUXNET-CH4` rows carry `CCBY4_0` (79) / `Tier2` (81) plus `2015_CCBY4.0` / `2015_TIER2`; `site_display/FLUXNET` rows (267) carry `2015_*` and `CH4_*`. FLUXNET-CH4 site-years: 293 CC-BY, 297 TIER2. |
| E50 | DOI key sets vary: Legacy (CA-Let) and Tier-2-only or some FLUXNET2015 records (RU-Sam, DE-Tha) omit `DOI_SPONSOR_ORGANIZATION` and `DOI_CONTRIBUTOR_ORGANIZATION`. Present in all 14 non-empty responses (of 20 pairs probed): `DOI_INFO`, `DOI_CONTRIBUTOR`, `REFERENCES`. `DOI_INFO` has `amf_site_page` for AmeriFlux products and `flx_site_page` for FLUXNET2015 / FLUXNET-CH4. `REFERENCES` rows carry `REFERENCE_PAPER`, `REFERENCE_USAGE` and `REFERENCE_DOI` or `REFERENCE_COMMENT`. |
| E51 | `DOI_CITATION` is `null` for every FLUXNET2015 (US-Ha1, BR-Sa1, RU-Sam, DE-Tha) and FLUXNET-CH4 (US-Myb) record sampled; the DOI itself is present (FLUXNET2015 `10.18140/FLX/1440071`, `…/1440032`, `…/1440185`, `…/1440152`; FLUXNET-CH4 US-Myb `10.18140/FLX/1669685`). The product segment is case-sensitive (`fluxnet2015` → `{}`). |
| E52 | Current AmeriFlux citations: US-xSR BASE "NEON (National Ecological Observatory Network) (2025), … Ver. 10-5" (DOI 10.17190/AMF/1579543) and FLUXNET-1F "Ver. v1.3_r1 (2019-2024)" (10.17190/AMF/1985453); US-Seg BASE Ver. 30-5 (10.17190/AMF/1246124); US-Myb BASE Ver. 17-5 (10.17190/AMF/1246139); AR-Bal FLUXNET-1F Ver. v1.3_r1 (2012-2013) (10.17190/AMF/2571144); CA-Let Legacy Ver. 1-5 (10.17190/AMF/1436318). |
| E53 | A GET of `v1/fp_var` with `If-Modified-Since` returns 200 with the full body; amfcdn never answers 304. API responses carry only `Content-Type`, `Access-Control-Allow-Origin: *` and `cf-cache-status: DYNAMIC`. |
| E54 | P7: in `v2/site_info_display`, `base_variables` is `list[str]` (610 non-empty, up to 65 names, FP base names such as `CO2`, `FC_SSITC_TEST`, `FETCH_90`); `dom_dist_mgmt` is `list[str]` (554 non-empty, up to 6; e.g. "Agriculture", "Grazing", "Undisturbed", "Drought", "Fire", "Temperature extreme"); `flux_measurements_variables` is `list[str]` on all 856 (gas species such as `CO2`, `H2O`, `CH4`, `Isotopes`, with repeated "Other"). |
| E55 | P8: `/data/measurement-height/` links exactly one file, `BASE_MeasurementHeight_20260908.csv`; HEAD → 200, `text/csv`, 2 254 621 B, ETag `"22671d-65affa8c88ad7"`, Last-Modified Tue, 08 Sep 2026 21:45:55 GMT, `cache-control: public, max-age=14400`. |

Build steps 4 and 5 (2026-10-24; GET only):

| # | Evidence |
|---|---|
| E56 | The site-search page (`ameriflux.lbl.gov/sites/site-search/`) embeds AmeriFlux's own descriptions as JSON string literals `igbpText` (17 IGBP classes) and `climText` (Köppen codes); its `Bsh` text reads "Steppe: very cold winter" and `Bsk` "Steppe: warm winter", the reverse of standard Köppen-Geiger (step 4). |
| E57 | Webdoc dictionaries re-fetched (ETags unchanged from E28): a section row, then a variable row with blank Units, then one row per resolution label (`HH`, `DD`, `WW`, `MM`, `YY`, `WW-YY`, `WW-MM`, `DD-YY`, `DD-MM`, `HH-DD`, `HH-YY`). Every resolution row has units unless its description is "not available"/"not defined"; µ is stored as UTF-8. FULLSET has 232 names, SUBSET 72, SUBSET ⊂ FULLSET; placeholders `XX` (percentiles) and `#` (soil layer) appear in 24 FULLSET names. |
| E58 | ONEFlux `var_info_definitions_{hh,dd,ww,mm,yy}.txt` at commit `d4ecebe` (2025-12-09, v1.3.0-rc, last change to the files) define 230 names, all in FULLSET; FULLSET also has `RECO_SR` and `RECO_SR_N`, which ONEFlux v1.3 does not. Units agree with FULLSET at every name and resolution; only the timestamps differ (FULLSET gives none per resolution, ONEFlux YYYYMMDDHHMM/YYYYMMDD/YYYYMM/YYYY). So E29's "many blank Units cells" are the variable rows only; units come from FULLSET (D35). |
| E59 | The AmeriFlux data-policy page lists the processing references verbatim: "Chu, H., Christianson, D.S., Cheah, YW. et al. AmeriFlux BASE data pipeline to support network growth and data sharing. Sci Data 10, 614 (2023). https://doi.org/10.1038/s41597-023-02531-2" and "Pastorello, G., Trotta, C., Canfora, E. et al. The FLUXNET2015 dataset and the ONEFlux processing pipeline for eddy covariance data. Sci Data 7, 225 (2020). https://doi.org/10.1038/s41597-020-0534-3"; the Data Availability sentence is "The AmeriFlux [DATA PRODUCT] were accessed from [SOURCE] on XX Month YYYY" with [SOURCE] = AmeriFlux data portal, AmeriFlux APIs, FLUXNET User Interface for the Shuttle, or the FLUXNET Shuttle code. |
| E60 | `doi.org/10.18140/FLX/1440071` redirects to `fluxnet.org/doi/FLUXNET2015/US-Ha1`, whose template renders the citation as `{{author.name}} , ({{doiObject.tier2}}) {{dataProduct}} {{siteId}} {{doiObject.siteName}}, Dataset. https://doi.org/{{doiObject.DOI}}` from the same DOI API record: authors, the Tier Two year range, title, "Dataset", DOI. |
| E61 | fluxnet.org/data/data-policy/ (FLUXNET2015): CC-BY-4.0 asks to cite Pastorello et al. 2020 and list each site by FLUXNET ID and/or per-site DOI (informing providers recommended); Tier Two asks to contact the providers "when you begin research that could lead to a publication", to give them at least three weeks after the first draft, and to list sites in a table; "In case of a synthesis using both CC-BY-4.0 and Tier Two data, all data should be treated as Tier Two." |
| E62 | The measurement-height CSV of 2026-09-08 covers 587 sites (US-Ha1 138 rows, US-Myb 278, RU-Sam none); the amerifluxr coverage snapshot is unchanged since commit `7319e63` (2025-11-03, `create_date:2025-10-20`, 561 sites, years Y1990–Y2025). DataCite still records US-Ha1's BASE DOI without a version (2016, Harvard University). `fp_var` `HeightDirection` is `pos` for 125 names, `neg` for 7 (soil and water: SWC, TS, WTD …), null for 13. |
| E63 | amerifluxr `inst/extdata` (2026-10-24): `AMF_US-CRT_BASE-BADM_2-5.zip` (22 226 B) holds `AMF_US-CRT_BASE_HH_2-5.csv` (28 098 B, 96 rows, 36 columns, `# Site:`/`# Version:` lines) and `AMF_US-CRT_BIF_20201005.xlsx` (12 172 B); `AMF_AA-Flx_BIF_CCBY4_20201218.xlsx` (27 839 B) covers US-CRT, US-Oho and US-WPT. The workbooks have one sheet, shared strings, numeric GROUP_IDs and the five BIF columns. They carry personal data: TEAM_MEMBER_EMAIL, TEAM_MEMBER_ADDRESS, DOI_CONTRIBUTOR_EMAIL, SHIPPING_ADDRESS and a private LAND_OWNER. GRP_UTC_OFFSET has UTC_OFFSET only. The BIF's DOI_CITATION uses the older form "Authors (2011-2013) AmeriFlux US-CRT …, Dataset. https://doi.org/…". One GRP_REFERENCE_PAPER entry is spam ("Bank Instrument (2020) …"), passed on as written. |
| E64 | ONEFlux README (version 20260106): FLUXMET, BIFVARINFO and ERA5 files per resolution and one BIF file, named `[N]_[CC-###]_FLUXNET_<KIND>_[T]_[YS]-[YE]_[V]_[R].csv`; "comma delimited, with first row as header", missing -9999, local standard time without DST; BIF and BIFVARINFO follow the BIF standard (Pastorello et al. 2020, Table SM8). |
| E65 | fluxnet.org FULLSET and SUBSET pages: AUXMETEO holds ERA-Interim downscaling results for TA, PA, VPD, WS, P, SW_IN, LW_IN, LW_IN_JSB (ERA_SLOPE, ERA_INTERCEPT, ERA_RMSE, ERA_CORRELATION); AUXNEE holds USTAR results (USTAR_MP_METHOD, USTAR_CP_METHOD, NEE_USTAR50_[UT], NEE_[UT]_REF …). The column layout is not documented, so both are read as plain tables (D31). |
| E66 | Preview throughput (stdio, one core): a 95 MB BASE HH file (64 columns, 210 240 rows) summarizes 2 columns in 0.73 s and all 64 in 4.3 s; a one-month window stops after reading 84 MB (0.52 s). |

## 1. The amfcdn.lbl.gov API (verified 2026-10-22)

Public, unauthenticated, CORS-open JSON behind Cloudflare. No published contract (E12),
so `ameriflux/endpoints.py` records version and envelope per endpoint (D4) and the
upstream models check required keys (D8). v1 returns bare arrays with UPPERCASE keys and
all-string values (used by amerifluxr and the website); v2 returns `{"values": [...]}`
with snake_case keys and typed values (used by the FLUXNET Shuttle).

| Endpoint (base `https://amfcdn.lbl.gov/api/`) | Status | Envelope | Rows | Notes |
|---|---|---|---|---|
| `v1/site_display/AmeriFlux` | 200 | bare | 856 | 303 516 B. SITE_ID, SITE_NAME, COUNTRY, STATE (806), GRP_LOCATION{LOCATION_LAT, LOCATION_LONG, LOCATION_ELEV}, IGBP, GRP_CLIM_AVG{CLIMATE_KOEPPEN, MAT, MAP}, TOWER_BEGAN (848), TOWER_END (299), URL_AMERIFLUX. Path and query suffixes ignored. |
| `v1/site_display/FLUXNET` | 200 | bare | 267 | FLUXNET2015 ∪ FLUXNET-CH4 sites, with `2015_*` and `CH4_*` year ranges (E49). |
| `v1/site_display/FLUXNET/FLUXNET2015` | 200 | bare | 212 | `CCBY4_0`, `Tier2` year ranges; sparse ELEV (175), MAT/MAP (163), TOWER_BEGAN (145), STATE (72), TOWER_END (52). |
| `v1/site_display/FLUXNET/FLUXNET-CH4` | 200 | bare | 81 | `CCBY4_0` (79), `Tier2` (81). |
| `v2/site_info_display/AmeriFlux` | 200 | values | 856 | 1.7 MB. The catalog: site_id, site_name, site_desc, country, state, status, grp_location, grp_igbp{igbp}, grp_clim_avg, grp_network[], grp_team_member[{team_member_name, team_member_role, team_member_institution, team_member_email}], url, url_ameriflux, url_fluxnet, dom_dist_mgmt[], flux_measurements_variables[], base_variables[], publish_ameriflux_policy, doi{AmeriFlux?, FLUXNET?}, grp_publish_base[int], grp_publish_fluxnet[int], tower_dates{tower_start, tower_end}. `v2/site_info_display/FLUXNET` → `{"values":[]}`. |
| `v1/site_availability[/{net}[/{prod}/{pol}]]` | 200 | object | — | 152 510 B tree; counts AmeriFlux BASE-BADM 533/610, BIF 674/843, FLUXNET 407; FLUXNET2015 206/212; FLUXNET-CH4 79/81. v2 → 404. |
| `v1/data_availability/{net}/{prod}/{pol}` | 200 / 422 | bare | all sites | `[{SITE_ID, URL, publish_years:[int]}]`; v2 identical inside `values` with lowercase keys. `…/{net}/{prod}` (no policy) → 404. |
| `v1/fp_var[?limits=True]` | 200 | bare | 145 | Name, Type, Units, Description, Sequence, ModelType, HeightDirection (+ Min, Max). v2 lowercase, no limits. `?name=` ignored; `fp_var/NEE` → 404. |
| `v1/DOI/{SITE}/{AmeriFlux\|FLUXNET\|FLUXNET2015\|FLUXNET-CH4}` | 200 | object | — | See section 4. |
| `v1/` and unknown paths | 404 | object | — | `{"detail":{},"message":"Not Found"}` (36 B). |
| `v1/data_download`, `v1/citations/*`, `v1/variable_availability`, v2 `amf_shuttle_data_files_and_manifest`, `log_shuttle_data_request` | 405 on GET | object | — | `{"detail":{},"message":"Method Not Allowed"}`. POST-only; never called by this project except `data_download` from the consented download tool (D11). |

**Network statistics** (v2 catalog): status Active 562 / Inactive 294; IGBP CRO 215,
WET 135, GRA 119, ENF 114, DBF 60, OSH 57; countries USA 695, Canada 93, Brazil 23,
Mexico 16; secondary networks Phenocam 196, NEON 47, LTAR 41, Fluxnet-Canada 30, LTER 18,
NY State Mesonet 18, MexFlux 16, UFLUX 16, LBA 8; team roles PI, FluxContact,
DataManager, AncContact, Technician, Affiliate, BADMContact. DataCite prefix 10.17190
holds 1 020 DOIs against 1 017 in the catalog (609 BASE + 408 FLUXNET).

**Politeness.** No rate-limit headers and no 429s seen (E37); conditional GETs are
ignored (E53), so freshness is ours to manage (D22). The site-search page embeds the same
catalog (2.5 MB HTML) with `CC-BY-4.0`/`Legacy` spellings, which is one reason policy
strings need normalizing (D6).

## 2. Exact error bodies (verified 2026-10-22)

| Request | Response |
|---|---|
| unknown path | `404 {"detail":{},"message":"Not Found"}` |
| `FLUXNET/FLUXNET2015/Tier2` | `422 {"detail":{"path":{"availability":["Must be one of: TIER2, CCBY4.0."]}},"message":"Validation error"}` |
| `AmeriFlux/FOO/BAR`, `AmeriFlux/BASE-BADM/Tier2` | `200`, 856 rows, all `publish_years: []` (no validation on the AmeriFlux network) |
| GET on a POST-only path | `405 {"detail":{},"message":"Method Not Allowed"}` |
| `DOI/{site}/BASE`, `DOI/{site}/FLUXNET-CH4` (AmeriFlux site), `DOI/XX-Zzz/AmeriFlux` | `200 {"status":"No valid DOI for <PRODUCT>"}` |
| `DOI/{site}/BASE-BADM`, `DOI/{site}/BIF`, `DOI/{site}/fluxnet2015` | `200 {}` |

## 3. Products, policies and availability semantics (verified 2026-10-22)

- **Valid matrix** (D6): AmeriFlux{BASE-BADM:{CCBY4.0, LEGACY}, BIF:{CCBY4.0, LEGACY},
  FLUXNET:{CCBY4.0}}; FLUXNET{FLUXNET2015:{CCBY4.0, TIER2}, FLUXNET-CH4:{CCBY4.0, TIER2}}.
- **LEGACY is a superset.** All 533 CC-BY BASE sites appear in the 610 LEGACY list (77
  Legacy-only sites): LEGACY means "everything usable under Legacy terms". BIF CC-BY ⊂
  LEGACY too. FLUXNET/LEGACY is empty because ONEFlux processes CC-BY data only (E24).
- **BIF availability** exists only in `site_availability` (membership, no years);
  `data_availability/AmeriFlux/BIF/*` rows are always empty (D7).
- **FLUXNET2015 tiers** are effectively per site, although the README says per
  site-year: the CC-BY and TIER2 lists differ only by the six TIER2-only sites (39
  site-years), and the CC-BY and Tier 2 zips are byte-identical.
- **Overlap.** 86 FLUXNET2015 sites are in the AmeriFlux registry (64 US, 20 CA, 2 BR);
  74 of them have the newer AmeriFlux FLUXNET (FLUXNET-1F) product, which uses the same
  SUBSET/FULLSET variable definitions. AR-SLu, AR-Vir, GF-Guy, PA-SPn and PA-SPs are
  in the Americas but not in the AmeriFlux registry.
- **Processing order** (flux-data-products page): Format QA/QC → Data QA/QC → BASE
  Publish (FP Standard, BADM, DOI) → ONEFlux → FLUXNET Publish (DOI). ONEFlux needs CO2,
  FC, H, LE, WS, USTAR, TA, RH, PA and SW_IN (or PPFD_IN).

## 4. DOIs and citations (verified 2026-10-22)

`GET v1/DOI/{SITE}/{PRODUCT}` is the citation source (D9). `DOI_INFO` holds `DOI`,
`DATA_POLICY` (`CCBY4.0`, `LEGACY` or `TIER2`), `DOI_CITATION`, `title`,
`doi_description`, `country` and `amf_site_page` or `flx_site_page`. Required keys are
`DOI_INFO`, `DOI_CONTRIBUTOR`, `REFERENCES`; the two organization keys are optional
(E50). `DOI_CONTRIBUTOR` rows include `DOI_CONTRIBUTOR_EMAIL`, so DOI responses are
cached in memory only (D19, D22).

| Product segment | Citation | Source |
|---|---|---|
| `AmeriFlux` (BASE-BADM, and BIF by D9) | `DOI_CITATION` verbatim, with "Ver. X-Y" | E19, E41, E52 |
| `FLUXNET` (FLUXNET-1F) | `DOI_CITATION` verbatim, with "Ver. v1.3_r1 (YYYY-YYYY)" | E19, E52 |
| `FLUXNET2015` | `DOI_CITATION` is null: construct it as the FLUXNET DOI page does (authors, Tier Two years, title, "Dataset", DOI; E60), plus Pastorello et al. 2020 | E20, E51, E60 |
| `FLUXNET-CH4` | `DOI_CITATION` is null; DOI present. Reference paper for the product is UNVERIFIED (Q8; v0.2) | E51 |

DataCite also knows these DOIs (CSL-JSON by content negotiation; Crossref does not) but
its metadata has no version and a different year and publisher (US-Ha1: 2016 and 2022,
"Harvard University"), so it is a last resort with a `versionMissing` warning. The POST
`citations/*` endpoint returns base64 text in v1 (website JS) and is never called. Each
FLUXNET2015 site also has a DataCite DOI under 10.18140/FLX (212 in total).

## 5. Downloads (UNVERIFIED on the wire; from client code, 2026-10-22)

- **Route.** `POST https://amfcdn.lbl.gov/api/v1/data_download`, JSON body: `user_id`,
  `user_email`, `site_ids[]` (or `AA-Net` = all sites' BIF, `AA-Flx` = sites with data),
  `data_product` (`BASE-BADM` or `FLUXNET`; BIF bulk is `BASE-BADM` with AA-Flx/AA-Net,
  E44), `data_variant` (`FULLSET`; the website hard-codes it, amerifluxr defaults to
  `SUBSET`), `data_policy` (`CCBY4.0` or `LEGACY`), `intended_use`, `description`,
  `is_test`.
- **Intended use** (verbose strings, as the website and amerifluxr send them): 1
  "Research - Multi-site synthesis", 2 "Research - Land model/Earth system model", 3
  "Research - Remote sensing", 4 "Research - Other", 5 "Education (Teacher or Student)",
  6 "Other". (Codes follow the Shuttle GUI's `<option value>` order.)
- **Response** (datadownload.js; UNVERIFIED): `data_urls[{site_id, url, data_product,
  download_size}]`, `manifest{download_timestamp, number_of_sites_downloaded,
  data_files[{site_id, filename, start_year, end_year, version, file_type, timestamp}]}`,
  `pi_contact_emails[]`; for AA-* requests, `aa_urls`. amerifluxr drops `FLUXNET-BIF`
  links (E44).
- **Files** are static objects on `ftp.fluxdata.org/.ameriflux_downloads/{BASE-BADM,
  FLUXNET}/…` with ETags, Last-Modified and Range support; `?=<user_id>` is only a tag
  (E23). We never construct these URLs (D11, D15).
- **Identity.** There is no API key: identity is self-declared. The website sends
  `friendlyfluxnetwork` when not logged in; LEGACY is offered only to logged-in
  accounts. Server-side validation of `user_id` is UNVERIFIED (Q2). The Shuttle's v2 path
  hard-codes `user_id='fluxnetshuttle'` with optional user fields but always POSTs a
  download log with a Referer header.
- **FLUXNET2015** downloads go through a login-gated WordPress form on fluxnet.org that
  emails the intended use to the site PIs; there is no documented API (E26).

## 6. Files (verified 2026-10-22 unless marked)

| Family | Name pattern | Contents |
|---|---|---|
| BASE-BADM zip | `AMF_<SITE>_BASE-BADM_<X-Y>.zip` | `AMF_<SITE>_BASE_(HH\|HR)_<X-Y>.csv` + `AMF_<SITE>_BIF_<YYYYMMDD>.xlsx` (E32). README/licence files in current zips: UNVERIFIED (P6). |
| BIF bulk | `AMF_(AA-Flx\|AA-Net)_BIF_(CCBY4\|LEGACY)_<YYYYMMDD>.xlsx` | CCBY4 form seen in an amerifluxr sample; LEGACY form inferred. BIF changes do not bump the zip version. |
| FLUXNET v1.3+ zip | `<NET>_<SITE>_FLUXNET_<YS>-<YE>_v<maj[.min]>_r<N>.zip` | `…_FLUXNET_FLUXMET_<T>_…csv`, `…_ERA5_<T>_1981-2025_…csv`, `…_BIFVARINFO_<T>_…csv` for T in HH/DD/WW/MM/YY, `…_FLUXNET_BIF_<YS>-<YE>_…csv`, README.txt, DATA_POLICY_LICENSE_AND_INSTRUCTIONS.txt (E32). `HH` means the finest step, hourly or half-hourly. |
| FLUXNET2015 zip | `FLX_<SITE>_FLUXNET2015_(FULLSET\|SUBSET)_<YS>-<YE>_<n-n>.zip` | FULLSET: FULLSET_{HH\|HR,DD,WW,MM,YY}, ERAI_{same}_1989-2014, AUXMETEO, AUXNEE (12 files). SUBSET: SUBSET_{…}, AUXMETEO, AUXNEE (7). Versions 1-4 (346 zips) and 2-4 (78). |
| FLUXNET-CH4 | `FLX_<SITE>_FLUXNET-CH4_(HH\|HR\|DD)_<YS>-<YE>_<n-n>.csv` | V1.0, 81 sites; recognized only in v0.1. |
| ICOS mirrors | `FLX_…_FLUXNET2015_FULLSET_…_beta-3.zip` | Drought-2018 / Warm Winter 2020 releases, no Americas sites; the `beta-<n>` version form must parse. |

**CSV conventions.** Missing value `-9999` (defensively also `-9999.0`, `-9999.9`).
HH/HR/WW files use `TIMESTAMP_START`/`TIMESTAMP_END`; DD/MM/YY use one `TIMESTAMP`
(YYYYMMDD, YYYYMM, YYYY); hours 00–23; END can roll into the next year. Local standard
time, no DST; the offset is BADM `GRP_UTC_OFFSET` (`UTC_OFFSET`, `UTC_OFFSET_DATE_START`,
multiple entries allowed). No anonymous API exposes the offset, so readers take it from
the BIF in the user's download. Column order is not guaranteed; select by name. BASE
starts with two comma-padded `#` lines; FLUXMET does not.

**Sizes.** US-Ha1 FLUXNET zip 163 MB; BASE_HR CSV 229 MB; FLUXNET2015 FULLSET zips
9.8–181 MB (13.6 GB total), largest CSV 516 MB (FI-Hyy).

## 7. Variables (verified 2026-10-22)

- **FP Standard registry** (`fp_var`): 145 base names in 13 types (MET_RAD 45, GASES 28,
  MET_WIND 11, QC_FLAG 9, HEAT 8, AQUATIC 7, MET_ATM 7, MET_PRECIP 7, BIOLOGICAL 6,
  MET_SOIL 6, FOOTPRINT 5, PRODUCTS 3, TIMEKEEPING 3). Units examples: FC µmolCO2 m-2
  s-1; FCH4 nmolCH4 m-2 s-1; H, LE, G, NETRAD W m-2; TA, TS deg C; RH, SWC % (0–100);
  VPD hPa; PA kPa; USTAR m s-1; WTD m (positive above surface).
- **Qualifier grammar** (data-variables page §3): general qualifiers `_PI`, `_QC`, `_F`,
  `_IU` in that order, then position `_H_V_R` or aggregation `_H_V_A`, `_#`, `_SD`, `_N`.
  V=1 is the highest sensor or shallowest depth; indices are relative and may be
  renumbered in released products. Uploads may use only `_F`. Specials: `FETCH_70/80/90`
  are not positional; `<FLUX>_SSITC_TEST` (FC, FCH4, FN2O, FNO, FNO2, FO3, H, LE, TAU) is
  Foken 0/1/2; `FETCH_FILTER` is 0 (discard) / 1 (keep).
- **FLUXNET suffixes**: `_F_MDS`, `_ERA`, `_F` (consolidated), `_JSB`; `_VUT`/`_CUT`
  with `_REF`, `_USTAR50`, `_MEAN`, `_SE`, `_XX` (05, 16, 25, 50, 75, 84, 95);
  partitioning `_NT`, `_DT`, `_SR`; `_RANDUNC`, `_JOINTUNC`; `_CORR`, `_CORR_25`,
  `_CORR_75`; `_DAY`/`_NIGHT`; `TS/SWC_F_MDS_#`. SUBSET is VUT-only with no `_ERA`/`_MDS`
  met split.
- **QC**: at HH, `*_F_MDS_QC` 0 measured / 1 good / 2 medium / 3 poor; consolidated
  `*_F_QC` 2 = ERA-downscaled; `PA_F_QC`, `P_F_QC`, `WS_F_QC` 0/2. At DD and coarser, QC
  is a 0–1 fraction of measured + good gapfill, except `USTAR_QC` and `NETRAD_QC`, which
  are the fraction of measured data only. `NIGHT` 0 day / 1 night.
- **Units change with resolution**: NEE/GPP/RECO µmolCO2 m-2 s-1 (HH), gC m-2 d-1
  (DD–MM), gC m-2 y-1 (YY, sum of daily); P mm per interval (HH), mm d-1, mm y-1.
- **Signs**: negative NEE is uptake; GPP and RECO positive; NEE = RECO − GPP.
- **Dictionary sources**: descriptions, units per resolution and SUBSET membership from
  the webdoc CSVs (E28, E57); timestamp formats and the resolutions the AmeriFlux FLUXNET
  product defines from ONEFlux var_info (E29, E58, µ restored). The two agree on every
  unit.
- **Quick-start defaults** (fluxnet.org guide): NEE_VUT_REF, GPP_NT_VUT_REF and
  GPP_DT_VUT_REF (their difference as uncertainty), RECO_*, NEE_VUT_XX, LE_F_MDS,
  H_F_MDS, LE_CORR, H_CORR.

## 8. Data policy (verified 2026-10-22)

- **AmeriFlux CC-BY-4.0 (revised December 2025)**: per-site citation with DOI in the
  reference list (not supplementary material); the DOE "data service" acknowledgment;
  the data-availability sentence when the paper has one; for FLUXNET, the
  multi-network/ERA5 text; recommended processing references Chu et al. 2023 (BASE) and
  Pastorello et al. 2020 (FLUXNET). Informing providers is recommended, not required.
- **AmeriFlux Legacy**: contact data contributors at the start of in-depth analysis;
  cite the DOI; acknowledge site funding (`DOI_SPONSOR_ORGANIZATION` or BIF
  `GRP_ACKNOWLEDGEMENT`); the DOE "data portal" acknowledgment; inform providers before
  publication; presentations use the AmeriFlux logo or link. CC-BY + Legacy → Legacy.
- **FLUXNET2015**: Tier One became CC-BY-4.0 on 2020-02-06; Tier Two adds RU-Sam,
  RU-SkP, RU-Tks, RU-Vrk, SE-St1, ZA-Kru for scientific and educational use, gives
  providers at least three weeks after the first draft, and Tier-Two-only sites are not
  in Pastorello 2020. Mixed tiers → Tier Two. FLUXNET-CH4 V1 uses the same two tiers.
- **FLUXNET Shuttle licence (document 20251226)**: per-site PID/DOI citation, a global
  acknowledgment, network add-ons keyed by the source-network code, and "The FLUXNET
  data products used in this work were downloaded from [SOURCE] on XX Month YYYY" (note
  the different wording from AmeriFlux's sentence).
- **Disclosure**: the AmeriFlux intended use goes to the site PIs and the login-gated
  Download Log (E24); the FLUXNET2015 statement is emailed to the data producers.

## 9. Supporting data (verified 2026-10-22)

- **Measurement heights**: one dated CSV linked from `/data/measurement-height/` (E30,
  E55, E62). The page documents a `Historical_Information` column the file lacks; parsers
  follow the file. Monthly cadence is UNVERIFIED.
- **Variable coverage**: only amerifluxr's GitHub snapshots (E31); stale by at least one
  release (BASE years reach 2026). `POST variable_availability` exists but is not used.
- **Catalog fields** (E54): `base_variables` lists FP base names per site, usable as a
  search filter; `dom_dist_mgmt` is a short disturbance/management vocabulary;
  `flux_measurements_variables` lists gas species with repeated "Other".

## 10. Ecosystem and prior art (verified 2026-10-22)

- **No prior MCP server** (E39). Clients: amerifluxr (R, BSD-3, v1.0.0; endpoint map in
  `R/zzz.R`; `amf_download_fluxnet` hard-codes `is_test <- TRUE` on master); FLUXNET
  Shuttle (Python, BSD-3, not on PyPI; plugins for AmeriFlux v2, ICOS SPARQL
  `meta.icos-cp.eu/sparql`, TERN THREDDS); the `fluxnet` R package wraps the Shuttle;
  ONEFlux (fluxnet/ONEFlux, latest v1.3.7-rc, 2026-09-06; tags mix `v` and no `v`).
- **FLUXNET Shuttle** (data.fluxnet.org, GUI launched 2026-05-14): 782 products
  (AmeriFlux 381, ICOS hub 350, TERN 51); the ICOS hub aggregates EUF 138, ICOS 82, JPF 54,
  CNF 32, KOF 21, FLX 18, SAEON 5. FLUXNET2015 is not served through it.
- **Mirrors**: no official anonymous FLUXNET2015 mirror on AWS Open Data, the Google
  Earth Engine catalog root, Zenodo (derived datasets only) or ICOS (European releases
  only).
- **Licences for dependencies**: icoscp is GPLv3+, so ICOS access in v0.2 goes through
  SPARQL directly. amerifluxr, the Shuttle and ONEFlux are BSD-style and may be ported
  with attribution (NOTICE).
- **NEON**: the 47 NEON-tagged AmeriFlux sites map 1:1 to DP4.00200.001 (E35), so
  `amf_get_site` can hand off to neon-mcp.

## 11. Sibling template (verified 2026-10-22)

edi-mcp HEAD `bfc666a9241a1b2cf3465e4c00205c9700fc594c` (core, 7 042 lines of src);
neon-mcp HEAD `a5949d2525e0909decb1c0dda41112b76570bc82` (downloads, ratelimit, resolve,
prompts, Docker, release; 11 793 lines). After masking the prefix renames, edi's
`transport/stdio.py` is identical to neon's and the rest of the core differs by tens of
lines, so the core ports almost verbatim (DESIGN.md D2). Neither sibling has a
server.json; edi has no Dockerfile or release workflow; the umbrella installer in
`idss-mesa/docs` registers neither data-source server.

## 12. Still unverified

- The `data_download` response shape and error bodies; whether returned URLs expire;
  what `is_test` does server-side; whether `user_id` is validated; how LEGACY is gated
  (Q1, Q2, Q4).
- Whether `data_product='BIF'` is accepted literally, and whether SUBSET is accepted for
  FLUXNET v1.3 (Q3).
- Whether `data_download` accepts FLUXNET2015; whether `paper_test/` is sanctioned (Q6).
- `If-Match` support on ftp.fluxdata.org (D16).
- BIF CSV columns and the UTC offset location inside FLUXNET zips (P5; the README says
  BIF standard, E64); README/licence files inside current BASE-BADM zips (P6);
  AUXMETEO/AUXNEE column layout (E65). The readers were tested on amerifluxr's real
  BASE-BADM sample (E63) and on synthetic archives, not yet on a current download.
- Measurement Height release cadence.
- The FLUXNET-CH4 reference paper for citations (Q8).
- The comma in the FLUXNET DOI page template (`{{author.name}} , (…)`) is presumably the
  author-list separator; ameriflux-mcp writes "A, B (1991-2012) FLUXNET2015 …" (E60).
