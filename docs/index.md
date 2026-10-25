---
okf_version: "0.2"
title: ameriflux-mcp
description: "ameriflux-mcp is a Model Context Protocol (MCP 2026-07-28) server that gives AI agents compact access to AmeriFlux and FLUXNET eddy-covariance flux tower data."
---

# ameriflux-mcp

**ameriflux-mcp** is a [Model Context Protocol](https://modelcontextprotocol.io/){target=_blank}
server for [AmeriFlux](https://ameriflux.lbl.gov/){target=_blank} and
[FLUXNET](https://fluxnet.org/){target=_blank} eddy-covariance data. AmeriFlux
publishes carbon, water and energy fluxes from more than 850 flux towers across the
Americas; FLUXNET2015 adds 212 sites worldwide. ameriflux-mcp lets AI agents and coding
assistants find towers, check which products and years exist, understand FLUXNET
variable names and QC flags, cite data under the right data policy, and preview the
files: AmeriFlux BASE and BADM, the AmeriFlux FLUXNET (FLUXNET-1F) product, and
FLUXNET2015 FULLSET and SUBSET.

The server implements the **MCP 2026-07-28** specification (stateless core) on the
Python `mcp` 2.x SDK. It speaks `stdio` for local clients such as Claude Code and Claude
Desktop, and stateless Streamable HTTP at `/mcp` when hosted. It is developed by
[idss-mesa](https://github.com/idss-mesa){target=_blank} at the University of New
Mexico and released under the MIT license.

!!! warning "Under construction: build step 6 of 8"

    Site search, site details, data availability, variables, citations, BADM and local
    file previews work today; downloads arrive in build step 7 (see the
    [roadmap](tools/roadmap.md)).
    The [tool reference](tools/reference.md) lists what the current build offers.

## Install in one minute

```bash
git clone https://github.com/idss-mesa/ameriflux-mcp.git
cd ameriflux-mcp
scripts/install.sh            # registers the server with every agent it finds
```

Then ask your agent to call `amf_ping`. [Install ameriflux-mcp](getting-started/install.md)
covers macOS, Linux and Windows, manual registration, Docker and troubleshooting.

!!! note "Downloads disclose who you are"

    Finding sites, checking availability, describing variables and getting citations
    need no account. Downloading data goes through AmeriFlux's own request, which sends
    your name, email and stated purpose to the site's principal investigators. That
    information comes only from your configuration, you see it before anything is sent,
    and nothing is sent until you confirm. See [Download identity](getting-started/identity.md).

## Documentation

This site is an [Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md){target=_blank}
knowledge bundle: every page carries YAML frontmatter with `type`, provenance and
lifecycle fields, and the whole corpus is available to agents at [`llms.txt`](llms.txt)
and [`llms-full.txt`](llms-full.txt).

* [Getting started](getting-started/index.md) - Install ameriflux-mcp on macOS, Linux or Windows, connect an MCP client, set up the download identity and tune the configuration.
* [Tools](tools/index.md) - The generated reference of the tools in this build, and the roadmap of the twelve planned tools.
* [About](about/index.md) - How agents should consume this site, how to cite AmeriFlux and FLUXNET data, licenses, and the change log.

## Where to get help

* Bugs and feature requests: [GitHub issues](https://github.com/idss-mesa/ameriflux-mcp/issues){target=_blank}.
* Questions about the data themselves: the [AmeriFlux data products](https://ameriflux.lbl.gov/data/flux-data-products/){target=_blank}
  pages and the [FLUXNET2015 dataset](https://fluxnet.org/data/fluxnet2015-dataset/){target=_blank} pages.
