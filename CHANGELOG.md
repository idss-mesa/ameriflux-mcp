# Changelog

All notable changes to ameriflux-mcp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
