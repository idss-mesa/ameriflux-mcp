# Directory Update Log

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
