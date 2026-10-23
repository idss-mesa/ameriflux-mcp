# Changelog

All notable changes to ameriflux-mcp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
