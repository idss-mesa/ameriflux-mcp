# ameriflux-mcp

<!-- mcp-name: io.github.idss-mesa/ameriflux-mcp -->

[![MCP 2026-07-28](https://img.shields.io/badge/MCP-2026--07--28-blue)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-idss--mesa.github.io%2Fameriflux--mcp-teal)](https://idss-mesa.github.io/ameriflux-mcp/)

A [Model Context Protocol](https://modelcontextprotocol.io) server (spec **2026-07-28**)
for [AmeriFlux](https://ameriflux.lbl.gov) and [FLUXNET](https://fluxnet.org)
eddy-covariance data. It will let agents find flux tower sites, check which products and
years exist, understand FLUXNET variable names and QC flags, cite data under the right
data policy, and preview files: AmeriFlux BASE and BADM, the AmeriFlux FLUXNET
(FLUXNET-1F) product, and FLUXNET2015 FULLSET and SUBSET.

> **Status: under construction (build step 1 of 8).** No tools work yet, and the
> `ameriflux-mcp` command starts from build step 2. See [DESIGN.md](DESIGN.md) for
> decisions, [RESEARCH.md](RESEARCH.md) for verified API facts, and
> `research/2026-10-22-plan.md` for the build plan.

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
`ameriflux-mcp --version` runs (until build step 2 it does not, so the script stops
without registering anything), and registers the server with Claude Code, Claude
Desktop, OpenAI Codex CLI, Gemini CLI, Goose and OpenCode. On Windows run it from Git
Bash. `--dry-run` previews every change; `--uninstall` removes them.

Manual registration, for Claude Code:

```bash
claude mcp add ameriflux -s user -- /absolute/path/to/ameriflux-mcp/.venv/bin/ameriflux-mcp
```

[Clients](docs/getting-started/clients.md) has the entries for every other client.

## Planned tools (v0.1)

| Tool | What it does |
|---|---|
| `amf_ping` | Server version, protocol and configuration status |
| `amf_search_sites` | Find AmeriFlux, FLUXNET2015 and FLUXNET-CH4 sites by place, ecosystem, years, product and policy |
| `amf_get_site` | One site's metadata, DOIs, products and links to NEON/EDI |
| `amf_get_availability` | Which years each product has per site, and under which policy |
| `amf_search_variables` | Search the FP Standard and FLUXNET variable dictionaries |
| `amf_describe_variables` | Parse variable names (qualifiers, QC, units per resolution, heights) |
| `amf_get_citation` | Versioned citations, required acknowledgments and policy obligations |
| `amf_get_badm` | Site metadata (BADM) from the catalog |
| `amf_download_data` | Opt-in, consented download through AmeriFlux's logged route (stdio only) |
| `amf_list_files` | Classify downloaded zips and CSVs |
| `amf_preview_data` | Summaries and row windows from local files, with QC filtering |
| `amf_read_bif` | Read BADM Interchange Format files |

## Downloads disclose who you are

AmeriFlux downloads go through a request that sends your name, email and stated purpose
to the site's principal investigators and to the AmeriFlux download log. ameriflux-mcp
will never invent that information or let a model write it: it comes only from your own
configuration, every download shows you the exact text first, and nothing is sent until
you confirm. Discovery, availability, variables and citations need no identity at all.

## Data policy

AmeriFlux data are shared under the CC-BY-4.0 licence or the AmeriFlux Legacy policy;
FLUXNET2015 under CC-BY-4.0 (Tier 1) or Tier 2. Cite each site's DOI and include the
required acknowledgments: see the [AmeriFlux data policy](https://ameriflux.lbl.gov/data/data-policy/)
and the [FLUXNET data policy](https://fluxnet.org/data/data-policy/).

## License

MIT, Copyright (c) 2026 The Regents of the University of New Mexico. Third-party
credits are in [NOTICE](NOTICE).
