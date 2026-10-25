# Changelog

All notable changes to ameriflux-mcp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `amf_list_files` (build step 6, stdio only): AmeriFlux and FLUXNET files in the download
  directory and `local.roots`, with archive members classified by family, kind (data,
  ERA, BIFVARINFO, BIF, aux table), site, resolution, years and version, and unsafe
  members flagged.
- `amf_preview_data`: summaries (count, missing, min, max, mean, units, out-of-range) and
  row pages of BASE, AmeriFlux FLUXNET and FLUXNET2015 CSVs read inside their zips, with
  time windows, QC filters, UTC timestamps from the site's BIF, the SUBSET view, aux
  tables and a byte and time budget.
- `amf_read_bif`: BIF workbooks and CSVs (also inside archives) by group, with UTC
  offsets, the recorded DOI citation and funding acknowledgments; personal data withheld
  by default.
- `ameriflux/files/`: file-name grammar, a safe zip reader (zip slip, symlinks, bombs,
  overruns), timestamps, a streaming CSV reader, a minimal xlsx reader and the BIF parser.
- Resources: `ameriflux://guide/file-formats` and `ameriflux://guide/fluxnet2015-access`.
- Docs: the Local files page.

### Changed

- `limits.tools_list_max_bytes` is 80 000 (59 945 B measured with 11 stdio tools).
- NOTICE credits the FLUXNET Shuttle file-name pattern and the vendored US-CRT sample.

- `amf_search_variables` (build step 5): the FP Standard list (live, with QA/QC ranges)
  and the FLUXNET dictionaries (AmeriFlux FLUXNET from ONEFlux v1.3; FLUXNET2015 FULLSET
  and SUBSET) by words, category and resolution, with units per resolution and SUBSET
  membership.
- `amf_describe_variables`: decodes BASE and FLUXNET names (qualifiers, positions,
  processing tokens, dictionary templates such as `NEE_VUT_XX` and `TS_F_MDS_#`), with
  units and QC meaning per resolution, sign conventions and `didYouMean`; with `site`,
  whether the site measures it, sensor heights and instruments, and yearly coverage from
  amerifluxr's dated snapshot.
- `amf_get_citation`: AmeriFlux's versioned citation per site DOI (BASE-BADM, BADM via
  the BASE DOI, FLUXNET), FLUXNET2015 citations built as the FLUXNET DOI page shows them,
  a DataCite fallback with a `versionMissing` warning, the effective policy with its
  obligations, verbatim acknowledgments, Legacy site funding, the data-availability
  sentence, processing references and optional BibTeX.
- `amf_get_badm`: a site's BADM as the API exposes it (location, IGBP and climate, team,
  disturbance, funding, reference papers, instruments and measurement heights).
- Resources: `ameriflux://guide/data-policy`, `ameriflux://guide/variable-grammar`,
  `ameriflux://reference/fp-variables`, `ameriflux://reference/fluxnet-variables` and
  `ameriflux://reference/acknowledgments`.
- `scripts/build_variable_dictionaries.py` builds `fluxnet-variables.json` (webdoc
  dictionaries plus ONEFlux var_info at a pinned commit, µ restored) and the
  `fp-variables.json` snapshot.
- `scripts/record_fixtures.py record --add` records only new scenarios; fixtures now
  cover the measurement-height page and CSV, the coverage snapshot and DataCite.
- Nightly live tests for the new sources, the webdoc ETags and every verbatim policy
  sentence.
- Docs: the Variables and Citations and BADM pages.

### Changed

- FLUXNET2015 obligations follow the FLUXNET policy page's wording (list sites by ID or
  DOI, in a table for Tier Two; contact providers when research begins); the Data
  Availability sentence is required when a paper has that section.
- `source.backend` is `mixed` when one call reads several services.
- NOTICE credits amerifluxr, ONEFlux and the FLUXNET2015 dictionaries, and ships in the
  wheel and sdist.

- `amf_search_sites` (build step 4): AmeriFlux, FLUXNET2015 and FLUXNET-CH4 sites by
  words, collection, product and policy, IGBP, Köppen, country, state, status, member
  network, bounding box or distance, data years, measured variables and gas species; years
  per product, facets over all matches, paging.
- `amf_get_site`: one site by ID (any case), NEON code, FLUXNET2015 old ID or name, with
  AmeriFlux's ecosystem and climate descriptions, the policy and what it asks, DOIs, years
  per product, team (contacts under the two-flag rule), measured variables and links to
  NEON (DP4.00200.001) and to LTER data in EDI.
- `amf_get_availability`: published years per site, product and policy, each row labelled
  with the policy its data are shared under; BIF membership; requested sites without data
  and why; the policy verdict per product with obligations and their union.
- Resources: `ameriflux://reference/vocabularies` (built by
  `scripts/build_site_vocabularies.py` from AmeriFlux's IGBP and Köppen text, with a caveat
  on its swapped Bsh/Bsk wording), `ameriflux://reference/neon-crosswalk` (live),
  `ameriflux://reference/lter-crosswalk` (curated draft, EDI scopes verified) and the
  `ameriflux://site/{site_id}` template.
- Docs: the Discovery and availability page.

### Changed

- Test servers use the largest rate-limit burst, so replayed fixtures never sleep (the
  suite runs in about 7 s).

- The full upstream client (build step 3): host and path allow-list (D21; `paper_test/`
  and `..` refused with `download_denied` before any connection), GET/HEAD only, no
  redirects, per-host rate limiting (2 req/s; 1 per 15 s to ameriflux.lbl.gov), retries
  on network errors, 5xx, Cloudflare 52x and 429 (`Retry-After`), byte caps, and error
  text scrubbed of secrets and emails.
- Response cache: in-memory TTL per family with single-flight and stale-if-error, plus a
  disk layer on stdio (`~/.cache/ameriflux-mcp`) that never stores emails and never holds
  DOI records; `amf_ping` now reports cache statistics.
- Endpoint table (version, envelope, required keys) with drift detection, and typed
  upstream models.
- Site catalog merging the AmeriFlux, FLUXNET2015 and FLUXNET-CH4 lists; site resolution
  by ID (any case), FLUXNET2015 renames, NEON code or fuzzy name (`ambiguous_input`,
  `not_found` with suggestions); the NEON crosswalk; the product × policy matrix with
  input normalization; the policy engine (Legacy and Tier Two escalation, FLUXNET
  eligibility, obligations and their union); privacy helpers.
- Recorded fixtures (29 GET responses, filtered to 15 fixture sites, emails rewritten to
  example.org) with `scripts/record_fixtures.py record|check` and a router that fails on
  unrecorded requests, POSTs, off-list hosts, `paper_test/` and identity sent upstream;
  nightly live smoke tests (GET only) in CI.

- Core server ported from edi-mcp (build step 2): tool registry with result-size budget
  and MRTR continuations, MCP 2026-07-28 adapter (structured results, cache hints,
  `server/discover`), stdio and stateless Streamable HTTP transports with `/healthz` and
  `/readyz`, structlog logging that masks credentials, emails and user IDs, and the
  structured error codes (`auth_required`, `upstream_forbidden`, `upstream_unavailable`
  for Cloudflare 52x, drift as `upstream_error`, ...).
- Configuration (`AMERIFLUX_MCP_*`, YAML, flags): upstream, identity, cache, limits,
  downloads, local, privacy and server sections. The download identity reads
  `AMERIFLUX_USER_ID`, `AMERIFLUX_USER_EMAIL`, `AMERIFLUX_USER_NAME`,
  `AMERIFLUX_INTENDED_USE` and `AMERIFLUX_DESCRIPTION` (namespaced forms win), named
  profiles, and `AMERIFLUX_MCP_IDENTITY__IS_TEST` with no default; look-alike names are
  warned about and ignored; invalid values exit 2 without echoing them; the identity is
  never resolved over HTTP.
- `amf_ping`: version, protocol, transport, identity status as booleans and profile names,
  downloads, local roots; `check_api=true` makes one GET to the AmeriFlux API.
- A minimal GET-only upstream client (no redirects, byte cap, endpoint labels).
- Resource `ameriflux://guide/identity`.
- `ameriflux-mcp` CLI: `--check` (offline), `--print-config` (identity masked),
  `--version`, transport and download flags; `config.yaml.example`.
- Generated documentation: the tool reference and the configuration table, drift-checked
  in CI; CI runs ruff, mypy --strict, tests with coverage on Python 3.11–3.13, macOS and an
  MCP 2026-07-28 conformance job.

- Documentation site (Zensical, OKF v0.2) modelled on gbif-mcp's and ported from
  edi-mcp: installation for macOS, Linux and Windows, quickstart, download identity,
  clients, configuration, roadmap, agent guide, citing AmeriFlux and FLUXNET data, and
  license pages; `llms.txt`/`llms-full.txt`; the OKF validator and post-build agent
  surface; a docs workflow that validates and builds on every PR and deploys to GitHub
  Pages once the repository is public.
- `scripts/install.sh` registers ameriflux-mcp with Claude Code, Claude Desktop, Codex
  CLI, Gemini CLI, Goose and OpenCode (ported from edi-mcp). `--with-identity` stores the
  AmeriFlux download identity from the environment or prompts, validates it and masks the
  user ID, email and name in all output; `--env` refuses identity variables; the script
  refuses to register a command whose `--version` does not run (`--no-verify` skips
  that). Hermetic tests run it in a sandboxed HOME.
- CI workflow: ruff, the probe self-test and the tests on Linux and macOS.
- Scaffold (build step 1): LICENSE, NOTICE, README, CLAUDE.md, AGENTS.md, DESIGN.md
  (decisions D1–D31), RESEARCH.md (evidence E1–E55), the 2026-10-22 research dossier and
  approved plan under `research/`, and the draft questions for AmeriFlux and FLUXNET
  support (`research/questions.md`).
- `scripts/probe_api.py`: a stdlib-only probe of the amfcdn.lbl.gov API (endpoint shapes,
  DOI citations, catalog field shapes, Measurement Height file). It sends GET and HEAD
  only, to an allow-list of hosts and paths, and scrubs email addresses from its output.
- `tests/test_probe_no_post.py`: the probe never names POST, never sends a request body
  and refuses other methods, hosts and paths before opening a connection.
