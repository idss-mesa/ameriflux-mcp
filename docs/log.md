# Directory Update Log

## 2026-10-24
* **Creation**: [Downloads](tools/downloads.md) — `amf_download_data` (build step 7): products, the plan and its disclosure, the consent call and its checks, the transfer and integrity checks, what is written to disk.
* **Update**: [Download identity](getting-started/identity.md) — the tool now exists; the `?=<user ID>` tag is stripped and nothing written holds the identity; [Tool reference](tools/reference.md) regenerated (12 tools); [Roadmap](tools/roadmap.md) — step 7 done; [home](index.md), [Install](getting-started/install.md) and [Quickstart](getting-started/quickstart.md) — what works today.
* **Creation**: [Local files](tools/local-files.md) — `amf_list_files`, `amf_preview_data` and `amf_read_bif` (build step 6): local roots, file families, summaries, rows, QC filters, UTC offsets, the SUBSET view, BIF privacy and the archive safety rules.
* **Update**: [Tool reference](tools/reference.md) regenerated (11 tools); [Roadmap](tools/roadmap.md) — step 6 done; [home](index.md), [Install](getting-started/install.md) and [Quickstart](getting-started/quickstart.md) — what works today.
* **Creation**: [Variables](tools/variables.md) — `amf_search_variables` and `amf_describe_variables` (build step 5): the BASE and FLUXNET grammars, units and QC per resolution, the dictionaries, heights and coverage at a site.
* **Creation**: [Citations and BADM](tools/citation.md) — `amf_get_citation` (versioned citations, effective policy, verbatim acknowledgments, site funding, BibTeX) and `amf_get_badm`.
* **Update**: [Citing AmeriFlux and FLUXNET data](about/citing-ameriflux.md) — the FLUXNET2015 citation form and the FLUXNET2015 obligations as the policy page words them; [Tool reference](tools/reference.md) regenerated (8 tools); [Roadmap](tools/roadmap.md) — step 5 done; [home](index.md), [Install](getting-started/install.md) and [Quickstart](getting-started/quickstart.md) — what works today.
* **Creation**: [Discovery and availability](tools/discovery.md) — `amf_search_sites`, `amf_get_site` and `amf_get_availability` (build step 4), site naming, policy labelling, empty sites and verdicts, the Köppen caveat, and the reference resources.
* **Update**: [Tool reference](tools/reference.md) regenerated (4 tools); [Roadmap](tools/roadmap.md) — step 4 done; [home](index.md), [Install](getting-started/install.md) and [Quickstart](getting-started/quickstart.md) — what works today.

## 2026-10-23
* **Update**: [Tool reference](tools/reference.md) — `amf_ping` reports cache statistics (build step 3); [Roadmap](tools/roadmap.md) — step 3 done.
* **Creation**: [Tool reference](tools/reference.md), generated from the tool registry by `scripts/gen_tools_reference.py` (`amf_ping`).
* **Update**: [Configuration](getting-started/configuration.md) — the settings table is now generated from `config.py` by `scripts/gen_config_reference.py` (59 settings); value-free validation errors and the look-alike variables are documented.
* **Update**: [Install](getting-started/install.md), [home](index.md), [Quickstart](getting-started/quickstart.md), [Roadmap](tools/roadmap.md) and [For AI agents](about/ai-agents.md) — the server now starts and answers `amf_ping`; real `--check` output; troubleshooting for invalid configuration.
* **Creation**: Documentation site on Zensical (OKF v0.2), ported from edi-mcp and modelled on gbif-mcp's: home page, the `zensical.toml` configuration, the OKF validator, the `llms.txt` generator and the post-build agent surface (Markdown mirror, `okf:*` head metadata, `robots.txt`).
* **Creation**: [Install ameriflux-mcp](getting-started/install.md) for macOS, Linux and Windows: uv, git and access to the private repository, the `scripts/install.sh` installer (six agents, `--with-identity`, refuses to register a server that does not start), manual registration, Docker, verification, troubleshooting, upgrades and removal.
* **Creation**: [Quickstart](getting-started/quickstart.md), [Download identity](getting-started/identity.md), [Clients](getting-started/clients.md) and [Configuration](getting-started/configuration.md) (planned settings until build step 2 generates the table).
* **Creation**: [Roadmap](tools/roadmap.md) of the twelve planned tools and eight build steps.
* **Creation**: [For AI agents](about/ai-agents.md), [Citing AmeriFlux and FLUXNET data](about/citing-ameriflux.md) and [License](about/license.md).

## 2026-10-22
* **Creation**: Started the ameriflux-mcp documentation bundle (OKF v0.2) with this log.
