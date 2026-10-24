# ameriflux-mcp — design

Status: **build step 4 (discovery tools), 2026-10-24.** Target: MCP **2026-07-28** (stateless core) on the
Python `mcp` SDK 2.x (`mcp>=2.0,<3`), Python 3.11+. Repo
`https://github.com/idss-mesa/ameriflux-mcp`, package `ameriflux_mcp`, console script
`ameriflux-mcp`, tool prefix `amf_`, MIT (Regents of UNM). Templates:
`idss-mesa/edi-mcp` at `main` (bfc666a) for the core and `idss-mesa/neon-mcp` at `main`
(a5949d2) for downloads, rate limiting, resolve, prompts, Docker and release; their
D-registers apply wherever this file is silent. Evidence `[E#]` is in RESEARCH.md §0;
the approved plan is `research/2026-10-22-plan.md`.

User decisions (2026-10-22): prefix `amf_`; downloads are built in v0.1 but merge only
after AmeriFlux support answers Q1 and Q4 (otherwise v0.1.0 ships read-only);
FLUXNET-CH4 discovery and availability in v0.1, readers/downloads/citations in v0.2;
v0.2 focuses on analysis (`amf_summarize_data`, Parquet export, CyVerse/mesa-ducklake
hand-off, optional DuckDB extra).

## Decisions register

| # | Question | Decision | Why |
|---|---|---|---|
| D1 | Names | Package `ameriflux_mcp`, script `ameriflux-mcp`, tool prefix `amf_` (`NAME_RE ^amf_[a-z_]+$`), URI scheme `ameriflux://`, `_meta` key `io.ameriflux-mcp/requiresIdentity`, env `AMERIFLUX_MCP_<SECTION>__<FIELD>`. Registry kwargs keep edi's names `requires_key`/`key_check`, documented as meaning "identity". FLUXNET2015 and FLUXNET-CH4 are `collection`/`product` arguments, not a second prefix. | `AMF` is upstream's own code [E23]; short names keep tools/list small [E6]; unchanged kwargs keep diffs against edi small. |
| D2 | Template | Port edi's core nearly verbatim; port neon's `ratelimit`, `resolve`, `downloads`, `prompts`, Dockerfile and release.yml. | edi is the newest port of neon [E2]; edi has no Dockerfile or release workflow [E11]. |
| D3 | Dependencies | Same as edi [E3]. Parse with stdlib `csv`/`zipfile`; read BIF xlsx through defusedxml. Core has no pandas, pyarrow, duckdb or openpyxl (DuckDB becomes an optional extra in v0.2). | Small install; xlsx is untrusted XML. |
| D4 | API versions | `ameriflux/endpoints.py` records version and envelope (`bare`/`values`/`object`) per endpoint; there is no global version switch. | v1 and v2 are asymmetric [E14]. |
| D5 | Source field | `source.backend: Literal['amfcdn','fluxdata','amerifluxr','datacite','local','mixed']`. | edi precedent [E5]. |
| D6 | Product matrix | Validate network × product × policy on the client before any call: AmeriFlux{BASE-BADM:{CCBY4.0,LEGACY}, BIF:{CCBY4.0,LEGACY}, FLUXNET:{CCBY4.0}}, FLUXNET{FLUXNET2015:{CCBY4.0,TIER2}, FLUXNET-CH4:{CCBY4.0,TIER2}}. Normalize `CC-BY-4.0`, `Legacy`, `Tier2` first. | The AmeriFlux network answers typos with 200 and empty rows [E15, E42]; only FLUXNET validates (422). |
| D7 | "Available" | `publish_years` non-empty, never row count. LEGACY is the superset of everything usable under Legacy. FLUXNET has no LEGACY rows. BIF availability comes from `site_availability` (membership, no years). | [E15, E16]. |
| D8 | Upstream drift | Upstream pydantic models use `extra='allow'` plus a required-key set per endpoint; a missing key or changed envelope raises `upstream_error` with `details.drift={endpoint, missing}`. DOI required keys are `DOI_INFO`, `DOI_CONTRIBUTOR`, `REFERENCES`; the organization keys are optional. | No published contract [E12]; Legacy and Tier-2 DOI records omit the organization keys [E50]. |
| D9 | Citations | `GET v1/DOI/{SITE}/{AmeriFlux\|FLUXNET\|FLUXNET2015}`; BASE-BADM → `AmeriFlux`; **BIF → the BASE DOI, with a note**. `{}` or `{"status":"No valid DOI…"}` → `not_found`. FLUXNET2015 (and FLUXNET-CH4 in v0.2) `DOI_CITATION` is null, so the citation is constructed from DOI, title and contributors plus the product paper (`source:'constructed'`). DataCite is a last resort with a `versionMissing` warning. Never the citations POST, never siteinfo scraping. | [E19, E20, E41, E51]; DataCite lacks the version and differs in year and publisher. |
| D10 | Policy engine | `policy.py`: Legacy if any selected site or the request is Legacy; TIER2 if any FLUXNET2015/CH4 site is TIER2-only; FLUXNET + LEGACY → `invalid_argument` (`fluxnet_requires_ccby`). Selections across collections return the union of obligations, one block per collection, each tagged `required\|recommended`: CC-BY inform providers (recommended); Legacy contact PIs early, credit site funding, inform before publication, logo or link in presentations, "data portal" wording; Tier Two 3-week window, Tier-Two-only sites not in Pastorello 2020. | [E24–E26, E46]. |
| D11 | Download route | Only `POST v1/data_download` with the user's configured identity. Tool `product='BIF'` is sent as `data_product='BASE-BADM'` with `site_ids=['AA-Flx'\|'AA-Net']`; `FLUXNET-BIF` links come back as `skipped`. Never build `ftp.fluxdata.org` URLs; never send `friendlyfluxnetwork`, `fluxnetshuttle` or `local_shuttle`; never call the v2 shuttle endpoints. | Keeps PI notification and the download log intact [E22–E24, E44, E45]. |
| D12 | Disclosed text | `intended_use` and `description` come only from config the user wrote (named `identity.profiles`), never from tool arguments. The server appends ` [ameriflux-mcp]`. The 20–1000 character bound is local policy, not upstream. | That text reaches the PIs [E24]; the model must not write it. amerifluxr tags its requests the same way [E22]. |
| D13 | Consent | One tool, two phases: `confirm=false` (default) returns a plan showing the exact disclosure and makes no request; `confirm=true` also requires `accept_data_policy` equal to the policy the server computed. No elicitation. | Works on every client; the plan is the consent record. |
| D14 | Download annotations | `amf_download_data`: readOnly=false, destructive=false, **idempotent=false**, openWorld=true; `key_check='handler'`, `transports=('stdio',)`, `needs_downloads=True`. | Every confirmed request notifies the PIs again [E24]. |
| D15 | URL provenance | Fetch only URLs held in an in-process ledger of `data_download` responses (`?=` tag stripped, no identity stored). Allowed: `ftp.fluxdata.org` under `/.ameriflux_downloads/` and `/.fluxnet_downloads_67934/webdoc/`; `/.fluxnet_downloads_67934/paper_test/` explicitly denied. No Range or HEAD previews of data zips before a logged download. | [E23, E27]. |
| D16 | Integrity | Compare the GET response's ETag and Content-Length with HEAD; send `If-Match` only as a hint; then `zipfile.testzip()`; record sha256 in a `<file>.amf.json` sidecar with no identity. | No published checksums; static files carry ETags [E23, E55]; If-Match support is unverified. |
| D17 | `is_test` | `identity.is_test` has **no default**; unset → `confirm=true` gives `auth_required` (`reason: is_test_unset`). Sent as a JSON boolean. | Semantics unverified; the website and amerifluxr disagree [E22]. |
| D18 | Kill switch | `downloads.enabled=false` removes `amf_download_data`. | Ships read-only if AmeriFlux declines third-party use. |
| D19 | Personal data | Team, contributor and PI emails are stripped unless `include_contacts=true` **and** `privacy.allow_contact_emails=true` (default false on every transport). Never written to disk cache, logs, sidecars, manifests, the ledger or fixtures. | 2 703 emails in the catalog [E13]; contributor emails in the DOI API [E20]. |
| D20 | Site resolution | Exact ID; NEON code via the 47-row crosswalk (`SRER` → US-xSR); FLUXNET2015 rename alias (DK-ZaF → GL-ZaF …) echoed in `resolved` with a note; fuzzy name with neon thresholds. Never elicits. | [E8, E35, E36]. |
| D21 | Politeness and hosts | 2 req/s, concurrency 4 to amfcdn (local policy; upstream publishes no limits). Allowed hosts: `amfcdn.lbl.gov`; `ftp.fluxdata.org` (paths per D15); `ameriflux.lbl.gov` (`/data/measurement-height/` only, plus `/data/data-policy/` in live tests; 15 s spacing); `raw.githubusercontent.com` (`/chuhousen/amerifluxr/master/data-summary/` only); `api.datacite.org`. gzip on; UA `ameriflux-mcp/<ver> (+repo URL)`; backoff on transport errors, 5xx and 520–527; honour Retry-After on 429. | [E37]. |
| D22 | Cache | Port edi's TTL / single-flight / stale-if-error cache plus a disk layer under `cache.disk_dir` (default `~/.cache/ameriflux-mcp`), personal fields stripped before writing; disk layer off on HTTP unless a volume is configured. amfcdn freshness is TTL-only; conditional requests are used only for static files on ftp.fluxdata.org. DOI responses stay in memory. | 1.7 MB catalog, stdio restarts, no cache headers and no 304s on amfcdn [E13, E37, E53]. |
| D23 | Budgets | edi limits verbatim [E6]. tools/list bound starts at 48 000 B and is tightened in step 8. `preview_max_rows=500`, `preview_scan_max_bytes=256 MiB`, `preview_time_budget_s=20`, `zip_member_max_bytes=1 GiB`. | CSVs reach 516 MB [E36]. |
| D24 | Errors | edi's 16 codes, no new ones; specifics in `details.reason`. | Envelope contract [E7]. |
| D25 | HTTP transport | Stateless Streamable HTTP at `/mcp` with `/healthz`, `/readyz`. No identity headers; identity-bearing and local-file tools are stdio only. | No HTTP tool needs a credential. |
| D26 | Surfaces | `('core','discovery','availability','variables','citation','metadata','data','local')`. | Each server defines its own tuple [E4]. |
| D27 | Licence and NOTICE | MIT, (c) 2026 The Regents of the University of New Mexico. NOTICE credits the BSD-3 code ported from amerifluxr (`amf_parse_basename`) and the Shuttle filename regex; carries the ONEFlux LICENSE text for var_info-derived units; records source URL, date and ETag for derived webdoc dictionaries (licence unstated, so derived tables only, Q7); describes the vendored US-CRT sample as AmeriFlux CC-BY-4.0 data (DOI 10.17190/AMF/1246156, Ver. 2-5; current is 5-5). | [E34, E41]. |
| D28 | Probe script | `scripts/probe_api.py` is stdlib-only, GET/HEAD only, allow-listed hosts and paths, scrubs emails; `tests/test_probe_no_post.py` guards it. edi's `probe_auth.py` is not copied. | edi's probe POSTs [E10]; here a POST is a disclosure. |
| D29 | Release | `server.json` (`io.github.idss-mesa/ameriflux-mcp`); README carries `<!-- mcp-name: io.github.idss-mesa/ameriflux-mcp -->`; Dockerfile from neon with a pinned uv image, no `--extra pdf`, uid 10001; release.yml with a `pypi` environment. | [E40, E47]. |
| D30 | SUBSET (FLUXNET v1.x) | A local column view (`view='subset'`) taken from the SUBSET dictionary; the download variant is fixed at FULLSET until Q3 is answered. | v1.3 zips carry no SUBSET/FULLSET token [E32]. |
| D31 | Auxiliary tables | FLUXNET2015 AUXMETEO/AUXNEE are `aux_table` files read without the timestamp requirement; ERAI spans 1989–2014 regardless of the site's flux years. | RESEARCH.md §6. |
| D34 | Discovery tools (step 4) | `amf_search_sites` defaults to `collection="all"` and reports each site's collections; query words match ID, name, place, NEON code and networks by prefix (or 0.85 similarity for 4+ letters). `amf_get_availability` without a policy reads both lists and labels each row with the policy its data are shared under (LEGACY/TIER2 lists are supersets, E15); BIF rows are membership only (D7); with defaulted products, "not part of this collection" gaps are not reported as empty sites. Vocabularies keep AmeriFlux's own IGBP/Köppen wording, with a caveat where it departs from the standard (AmeriFlux swaps Bsh/Bsk). The LTER crosswalk is curated (draft) and every row records its basis (upstream tag, site name, untagged); EDI scopes were checked against EDI's scope list. The NEON crosswalk and the site template are derived from the catalog and public (nothing depends on the caller). | Agents get the whole picture by default without noise, never a mislabelled CC-BY site, and never a silently "corrected" upstream vocabulary. Step 4, 2026-10-24. |
| D33 | Client, cache and fixtures (step 3) | Allow-list violations raise `download_denied` before any socket (every host and path prefix of D21 is checked, `..` segments and `paper_test/` refused). The disk cache stores JSON values after `strip_emails`, writes atomically, never fails a call on a disk error, and serves expired disk entries as `stale` within `stale_if_error_s` (7 d) across restarts. Endpoint definitions own version, envelope, query and required keys; `fetch()` caches the unwrapped value. Fixtures are recorded GET-only from a fixed scenario list, filtered to a 15-site fixture set, and every email is rewritten to `<hash>@example.org`; each transform is recorded in the manifest. The test router also checks URL-decoded requests for identity values. | Keeps the security rules in one place (client), restarts cheap, and fixtures small and free of personal data. Step 3, 2026-10-23. |
| D32 | Value-free configuration errors | `load_config` turns pydantic validation errors into `ConfigError` naming the setting and rule only (pydantic would echo the input); the CLI exits 2 with that message. A YAML section left empty (`cache:` with commented children) counts as absent. Over HTTP, `amf_ping` reports no identity fields at all, not just "unavailable". The upstream client treats any 3xx as an error (redirects are never followed). | A mistyped email must not land in a log; a hosted server's callers have no business learning what its operator configured. Step 2, 2026-10-23. |

## Tool surface (v0.1: 12 tools on stdio, 8 on HTTP)

| Tool | Surface | Transports | Hints (RO/D/I/OW) |
|---|---|---|---|
| `amf_ping` | core | both | RO, ¬D, I, OW |
| `amf_search_sites` | discovery | both | RO, ¬D, I, OW |
| `amf_get_site` | discovery | both | RO, ¬D, I, OW |
| `amf_get_availability` | availability | both | RO, ¬D, I, OW |
| `amf_search_variables` | variables | both | RO, ¬D, I, OW |
| `amf_describe_variables` | variables | both | RO, ¬D, I, OW |
| `amf_get_citation` | citation | both | RO, ¬D, I, OW |
| `amf_get_badm` | metadata | both | RO, ¬D, I, OW |
| `amf_download_data` | data | stdio | ¬RO, ¬D, ¬I, OW |
| `amf_list_files` | local | stdio | RO, ¬D, I, ¬OW |
| `amf_preview_data` | local | stdio | RO, ¬D, I, ¬OW |
| `amf_read_bif` | local | stdio | RO, ¬D, I, ¬OW |

Inputs and outputs per tool are in the plan (`research/2026-10-22-plan.md`, "Tool
surface"). Resources: `ameriflux://guide/{agent-workflow,identity,data-policy,products,
variable-grammar,file-formats,fluxnet2015-access}`, `ameriflux://reference/{acknowledgments,
vocabularies,fp-variables,fluxnet-variables,neon-crosswalk,lter-crosswalk}`, template
`ameriflux://site/{site_id}`. Prompts: `find_flux_sites`, `plan_site_analysis`,
`cite_flux_data`.

## Build order (one PR each)

1. `research/api-probe` — scaffold, this register, RESEARCH.md, GET-only probe ✅
   (`docs/install` — docs site, install script ✅)
2. `feat/core-port` — edi core, `amf_ping`, config with identity, transports, CI ✅
3. `feat/client-cache` — endpoints, client, ratelimit, cache, catalog, resolve, policy,
   privacy, fixtures and router ✅
4. `feat/discovery-tools` — `amf_search_sites`, `amf_get_site`, `amf_get_availability` ✅
5. `feat/variables-citation` — grammar, dictionaries, citation, `amf_get_badm`
6. `feat/local-readers` — `amf_list_files`, `amf_preview_data`, `amf_read_bif`
7. `feat/downloads` — `amf_download_data`; **merge gated on Q1 and Q4** (RESEARCH.md §12)
8. `feat/release-0.1.0` — prompts, docs, server.json, Docker, release
