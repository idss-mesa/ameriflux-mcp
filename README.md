# ameriflux-mcp

<!-- mcp-name: io.github.idss-mesa/ameriflux-mcp -->

[![MCP 2026-07-28](https://img.shields.io/badge/MCP-2026--07--28-blue)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-idss--mesa.github.io%2Fameriflux--mcp-teal)](https://idss-mesa.github.io/ameriflux-mcp/)

A [Model Context Protocol](https://modelcontextprotocol.io) server (spec **2026-07-28**)
for [AmeriFlux](https://ameriflux.lbl.gov) and [FLUXNET](https://fluxnet.org)
eddy-covariance data. It lets agents find flux tower sites, check which products and
years exist, understand FLUXNET variable names and QC flags, cite data under the right
data policy, download with the user's consent, and preview files: AmeriFlux BASE and BADM, the AmeriFlux FLUXNET
(FLUXNET-1F) product, and FLUXNET2015 FULLSET and SUBSET.

> **Status: v0.1.0.** Twelve tools (eight over HTTP), three prompts and the guide and
> reference resources described below. The AmeriFlux API is undocumented, so the server
> checks every response's shape and reports drift instead of guessing. See
> [DESIGN.md](DESIGN.md) for decisions, [RESEARCH.md](RESEARCH.md) for verified API
> facts, and [CHANGELOG.md](CHANGELOG.md) for what changed.

## Installation

Full instructions for macOS, Linux and Windows are in the documentation:
[docs/getting-started/install.md](docs/getting-started/install.md) (published at
<https://idss-mesa.github.io/ameriflux-mcp/> once the repository is public).

Prerequisites: [uv](https://docs.astral.sh/uv/), git, and read access to this private
repository (for example through `gh auth login`).

```bash
git clone https://github.com/idss-mesa/ameriflux-mcp.git
cd ameriflux-mcp
scripts/install.sh                  # registers the server with every agent it finds
scripts/install.sh --with-identity  # ... and stores your AmeriFlux download identity
```

`scripts/install.sh` creates the environment with `uv sync`, checks that
`ameriflux-mcp --version` runs (it never registers a command that does not start), and
registers the server with Claude Code, Claude
Desktop, OpenAI Codex CLI, Gemini CLI, Goose and OpenCode. On Windows run it from Git
Bash. `--dry-run` previews every change; `--uninstall` removes them.

Manual registration, for Claude Code:

```bash
claude mcp add ameriflux -s user -- /absolute/path/to/ameriflux-mcp/.venv/bin/ameriflux-mcp
```

[Clients](docs/getting-started/clients.md) has the entries for every other client.

Once v0.1.0 is on PyPI: `uvx ameriflux-mcp` (or `uv tool install ameriflux-mcp`). A
`Dockerfile` serves the read-only HTTP tools: `docker compose up -d`, then
`http://127.0.0.1:8080/mcp`.

## Tools

| Tool | What it does |
|---|---|
| `amf_ping` | Server version, protocol and configuration status |
| `amf_search_sites` | Find AmeriFlux, FLUXNET2015 and FLUXNET-CH4 sites by place, ecosystem, years, product and policy |
| `amf_get_site` | One site's metadata, DOIs, products and links to NEON/EDI |
| `amf_get_availability` | Which years each product has per site, and under which policy |
| `amf_search_variables` | Search the FP Standard and FLUXNET variable dictionaries |
| `amf_describe_variables` | Parse variable names (qualifiers, QC, units per resolution, heights) |
| `amf_get_citation` | Versioned citations, required acknowledgments and policy obligations |
| `amf_get_badm` | Site metadata (BADM): location, team, disturbance, funding, references, instruments and heights |
| `amf_download_data` | Opt-in, consented download through AmeriFlux's logged route (stdio only) |
| `amf_list_files` | Classify downloaded zips and CSVs |
| `amf_preview_data` | Summaries and row windows from local files, with QC filtering |
| `amf_read_bif` | Read BADM Interchange Format files |

The last four run only over stdio, on the user's machine. Prompts: `find_flux_sites`,
`plan_site_analysis`, `cite_flux_data`. Guides for agents: `ameriflux://guide/agent-workflow`,
`products`, `data-policy`, `variable-grammar`, `identity`, `file-formats`,
`fluxnet2015-access`.

## Downloads disclose who you are

AmeriFlux downloads go through a request that sends your name, email and stated purpose
to the site's principal investigators and to the AmeriFlux download log. ameriflux-mcp
never invents that information or lets a model write it: it comes only from your own
configuration, every download shows you the exact text first, and nothing is sent until
you confirm. `downloads.enabled=false` (or `--no-downloads`) removes the download tool. Discovery, availability, variables and citations need no identity at all.

## Data policy

AmeriFlux data are shared under the CC-BY-4.0 licence or the AmeriFlux Legacy policy;
FLUXNET2015 under CC-BY-4.0 (Tier 1) or Tier 2. Cite each site's DOI and include the
required acknowledgments: see the [AmeriFlux data policy](https://ameriflux.lbl.gov/data/data-policy/)
and the [FLUXNET data policy](https://fluxnet.org/data/data-policy/).

## License

MIT, Copyright (c) 2026 The Regents of the University of New Mexico. Third-party
credits are in [NOTICE](NOTICE).
