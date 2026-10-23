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

Build order (one PR each): 1 scaffold + GET-only API probe ✅ → 2 core port from edi-mcp
(registry, adapter, config, errors, identity config, transports, `amf_ping`,
conformance tests, CI) → 3 client/cache/catalog/resolve/policy/privacy + fixtures → 4
discovery tools → 5 variables, citation, BADM → 6 local readers → 7 downloads (merge
gated on AmeriFlux support answering Q1 and Q4; see `research/questions.md`) → 8
prompts, docs, server.json, Docker, v0.1.0.

## Commands

```bash
python3 scripts/probe_api.py --selftest            # offline guard checks
python3 scripts/probe_api.py --json probe.json      # live GET-only probe (P1, P4, P7, P8)
uv run --no-project --with pytest python -m pytest tests -o addopts=""   # step 1 tests
uvx ruff check scripts tests && uvx ruff format --check scripts tests
```

From step 2 on, the edi commands apply (`uv sync --all-extras`, `uv run pytest`,
`uv run mypy --strict src`, `record_fixtures.py check`, live tests with
`AMERIFLUX_MCP_LIVE=1 uv run pytest -m live tests/live`).

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

Step 1 only: `scripts/probe_api.py` (GET/HEAD-only probe with a host/path allow-list
and email scrubbing), `tests/test_probe_no_post.py`, `src/ameriflux_mcp/__init__.py`.
The target layout is in DESIGN.md and `research/2026-10-22-plan.md` ("Architecture and
port map").
