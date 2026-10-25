# CLAUDE.md — ameriflux-mcp

ameriflux-mcp is a Model Context Protocol server (MCP **2026-07-28**, stateless core) for
AmeriFlux and FLUXNET eddy-covariance data (BASE, BADM/BIF, AmeriFlux FLUXNET, FLUXNET2015
FULLSET/SUBSET, FLUXNET-CH4 discovery), to be published at
https://github.com/idss-mesa/ameriflux-mcp. Python 3.11+, `mcp>=2.0,<3` (low-level
`Server`), pydantic v2, httpx, structlog, defusedxml. It is a sibling of
`idss-mesa/edi-mcp` (core template) and `idss-mesa/neon-mcp` (downloads, ratelimit,
resolve, prompts, Docker, release). `DESIGN.md` records every decision (the D-numbers)
and `RESEARCH.md` the verified API facts (E-numbers); read them before changing
behaviour. `research/` holds the raw 2026-10-22 dossier and the approved plan.

## Status

Build order (one PR each): 1 scaffold + GET-only API probe ✅ (+ docs site and install
script ✅) → 2 core port from edi-mcp (registry, adapter, config, errors, identity config,
transports, `amf_ping`, conformance tests, CI) ✅ → 3 client/cache/catalog/resolve/policy/
privacy + recorded fixtures ✅ → 4 discovery tools (`amf_search_sites`, `amf_get_site`,
`amf_get_availability`, vocabularies/crosswalk resources, site template) ✅ → 5 variables, citation, BADM
(`amf_search_variables`, `amf_describe_variables`, `amf_get_citation`, `amf_get_badm`,
policy/grammar guides, FP/FLUXNET/acknowledgment references) ✅ → 6 local readers
(`amf_list_files`, `amf_preview_data`, `amf_read_bif`, file-formats and FLUXNET2015-access
guides) ✅ → 7 downloads (`amf_download_data`, ledger, verified transfers; built, merge
gated on AmeriFlux support answering Q1 and Q4; see `research/questions.md`) → 8
prompts, docs, server.json, Docker, v0.1.0.

## Commands

```bash
uv sync --all-extras
uv run pytest                                   # hermetic (FixtureRouter); coverage >= 85
uv run python scripts/record_fixtures.py check  # fixtures: allow-listed GETs, small, no real emails
uv run python scripts/record_fixtures.py record # re-record live (GET only), then check + promote
uv run python scripts/record_fixtures.py record --add   # record only new scenarios, merge
uv run python scripts/build_variable_dictionaries.py    # rebuild FLUXNET/FP dictionaries (--check offline)
AMERIFLUX_MCP_LIVE=1 uv run pytest -m live tests/live   # live smoke (GET only)
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy --strict src
uv run ameriflux-mcp --check                    # offline JSON report
python3 scripts/probe_api.py --selftest         # GET-only probe guards (live: --json probe.json)
scripts/install.sh --agents all --dry-run       # installer (test only in a sandboxed HOME)
uv run python scripts/gen_tools_reference.py && uv run python scripts/gen_config_reference.py
uv run python scripts/okf_validate.py docs && uv run python scripts/gen_llms_txt.py
uv run zensical build --clean --strict
```

Docs follow AGENTS.md (OKF frontmatter, `docs/log.md` entry, regenerate `llms.txt` and the
two references; CI fails on drift). GitHub Pages deploys only once the repository is
public (free plan).

## Fixed decisions (do not re-litigate)

- Tool prefix `amf_`; inputs snake_case; outputs camelCase.
- **Never POST upstream except** the one consented `data_download` request made by
  `amf_download_data` with `confirm=true`. That request sends the user's identity and
  intended use to the site PIs and the AmeriFlux download log. Probes, tests, fixtures
  and live CI are GET/HEAD only (D11, D28).
- Never construct `ftp.fluxdata.org` download URLs; never touch `paper_test/`; never
  automate the fluxnet.org login (D11, D15).
- Identity (user_id, email, intended use, description, is_test) comes from env/YAML
  only, never from tool arguments, flags, logs, caches or fixtures; `is_test` has no
  default; identity-bearing tools are stdio only (D12, D17, D25).
- Contact emails are stripped by default and never persisted (D19).
- Validate the product × policy matrix client-side: the AmeriFlux network answers bad
  enums with 200 and empty rows (D6).
- Read-mostly v1; downloads stdio-only, confined, behind `downloads.enabled` (D18).
- Config: `AMERIFLUX_MCP_<SECTION>__<FIELD>`; precedence flag > env > YAML > defaults;
  `.env` is not auto-loaded.
- MIT, Copyright (c) 2026 The Regents of the University of New Mexico.

## Code map

`server.py` is the only SDK-coupled module (adapter); `registry.py` validates tools, fails
fast with `auth_required` for `requires_key` tools (meaning: needs the download identity)
and enforces the result budget; tools in `tools/<family>.py` are
`async (args, ctx) -> OutputModel`; `context.py` builds the per-call `ToolContext`
(`ctx.identity` is `None` over HTTP or when incomplete); `config.py` loads settings
(identity fallbacks, value-free `ConfigError`); `ameriflux/identity.py` resolves and
reports the identity (booleans only); `ameriflux/client.py` is the one HTTP client
(allow-list `ALLOWED`, GET/HEAD only, no redirects, retries, rate limit via
`ratelimit.py`, `fetch(endpoint)` caches through `cache.py`); `ameriflux/endpoints.py`
defines each endpoint's version, envelope and required keys (drift); `models/upstream.py`
types the rows; `ameriflux/catalog.py` builds the `SiteIndex` (AmeriFlux + FLUXNET2015 +
FLUXNET-CH4); `resolve.py` turns site arguments into IDs; `products.py` holds the D6
matrix; `policy.py` the D10 engine; `privacy.py` strips emails; `errors.py` maps upstream
failures (D24); `ameriflux/reference.py` loads the static vocabularies and the curated
LTER crosswalk; `ameriflux/variables/` holds the name grammar (`grammar.py`), the FP and
FLUXNET dictionaries (`dictionaries.py`, live FP with snapshot fallback), measurement
heights (`heights.py`) and amerifluxr coverage (`coverage.py`); `ameriflux/citation.py`
builds citations from the DOI API (FLUXNET2015 constructed, DataCite fallback) and
`ameriflux/acknowledgments.py` holds the verbatim policy texts; tools:
`tools/sites.py` (search, get_site, shared product/years models),
`tools/availability.py`, `tools/variables.py`, `tools/citation.py`, `tools/badm.py`,
`tools/local.py` (stdio-only file tools), `tools/download.py` (`amf_download_data`: plan,
consent checks, the one POST, transfers, manifest); `ameriflux/ledger.py` keeps the URLs
logged requests returned (the only files fetched; `?=` tag stripped) and
`ameriflux/downloads.py` does the HEAD/GET/verify/sidecar steps; `ameriflux/files/` holds the file-name grammar
(`filenames.py`), root confinement (`paths.py`), the safe zip reader (`zipsafe.py`),
`timestamps.py`, the streaming CSV reader (`csvstream.py`), `xlsx.py`, `bif.py` and the
root walker (`inventory.py`); `transport/` holds stdio and stateless HTTP; `resources.py`
serves the guides (identity, data policy, variable grammar), the references and
`ameriflux://site/{site_id}`;
`prompts.py` is empty until step 8. `scripts/build_site_vocabularies.py` rebuilds
`resources_static/vocabularies.json` (one GET of the site-search page);
`scripts/build_variable_dictionaries.py` rebuilds `fluxnet-variables.json` and
`fp-variables.json`. Tests: `conftest.py`
builds servers on `tests/fixture_router.py` (recorded fixtures in `tests/fixtures/`,
15 fixture sites: never assert network-wide counts); `tests/helpers` has `IDENTITY_ENV`,
`PRIVATE_VALUES` (must never appear in output), `call_ok`/`call_err` and the ASGI
harness; `tests/archives.py` builds the synthetic local archives (only
`tests/data/AMF_US-CRT_BASE_HH_2-5.csv` is real); `tests/test_tools_download.py` fakes
the POST and the file server (`FileServer`); the only real POST is
`tests/live/test_live_download.py`, run by the manual `live-download` workflow. Also `scripts/probe_api.py` (GET/HEAD-only probe), `scripts/install.sh`, the
docs site (`docs/`, `zensical.toml`) and its generators. The target layout is in
`research/2026-10-22-plan.md` ("Architecture and port map").
