# Changelog

All notable changes to ameriflux-mcp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Scaffold (build step 1): LICENSE, NOTICE, README, CLAUDE.md, AGENTS.md, DESIGN.md
  (decisions D1–D31), RESEARCH.md (evidence E1–E55), the 2026-10-22 research dossier and
  approved plan under `research/`, and the draft questions for AmeriFlux and FLUXNET
  support (`research/questions.md`).
- `scripts/probe_api.py`: a stdlib-only probe of the amfcdn.lbl.gov API (endpoint shapes,
  DOI citations, catalog field shapes, Measurement Height file). It sends GET and HEAD
  only, to an allow-list of hosts and paths, and scrubs email addresses from its output.
- `tests/test_probe_no_post.py`: the probe never names POST, never sends a request body
  and refuses other methods, hosts and paths before opening a connection.
