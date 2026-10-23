---
title: "Configuration"
description: "Configure ameriflux-mcp with a YAML file, AMERIFLUX_MCP_ environment variables or flags; precedence rules and the planned settings."
type: Reference
tags:
  - getting-started
  - configuration
  - environment
generated:
  by: "claude/opus-5.5"
  at: "2026-10-23T00:00:00Z"
sources:
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design (decisions D12, D17-D23, D25)"
    author: "team:idss-mesa"
  - id: plan
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/research/2026-10-22-plan.md"
    title: "ameriflux-mcp implementation plan"
    author: "team:idss-mesa"
status: draft
stale_after: "2027-01-23T00:00:00Z"
---

# Configuration

ameriflux-mcp runs with no configuration at all: the defaults serve stdio, cache
AmeriFlux API responses, keep tool results small, strip contact emails and confine
downloads to `~/ameriflux-downloads`. Settings come from four layers; a higher layer
wins:

1. **Command-line flags** (only a handful of common settings).
2. **Environment variables** named `AMERIFLUX_MCP_<SECTION>__<FIELD>`, with a double
   underscore descending into nested sections at any depth, for example
   `AMERIFLUX_MCP_CACHE__TTL_S__CATALOG=3600`. List settings take a comma-separated
   value: `AMERIFLUX_MCP_LOCAL__ROOTS=/data/fluxnet2015,/data/shared`. The empty string,
   `none` and `null` mean "unset".
3. **A YAML file** passed with `--config path.yaml`, using the same section and field
   names.
4. **Built-in defaults** (the table below).

Unknown keys in the YAML file or the environment are ignored with a warning, so a typo
does not stop the server but is visible in its log. ameriflux-mcp does not load `.env`
files itself; export the variables (`set -a; . ./.env; set +a`) before starting it.

!!! note "Planned settings"

    The configuration module is part of build step 2. Until then the table below is
    written from the design[^design] and plan[^plan]; from step 2 on it is generated
    from the code (`scripts/gen_config_reference.py`) and CI fails if it drifts.

## The download identity

Identity is read from the environment or the YAML file only, never from flags or tool
arguments, and is used only by the download tool. The plain names
(`AMERIFLUX_USER_ID`, `AMERIFLUX_USER_EMAIL`, `AMERIFLUX_USER_NAME`,
`AMERIFLUX_INTENDED_USE`, `AMERIFLUX_DESCRIPTION`) are what other AmeriFlux tools use;
the namespaced `AMERIFLUX_MCP_IDENTITY__…` forms take precedence when set.
`AMERIFLUX_MCP_IDENTITY__IS_TEST` has no plain form and no default. See
[Download identity](identity.md) for what each value is and who sees it.

## Command-line flags

| Flag | Sets |
| --- | --- |
| `--config PATH` | YAML file to load |
| `--transport {stdio,http}` | `server.transport` |
| `--bind-address`, `--bind-port` | `server.bind_address`, `server.bind_port` |
| `--log-level` | `server.log_level` |
| `--download-dir PATH` | `downloads.directory` |
| `--no-downloads` | `downloads.enabled = false` |
| `--print-config` | print the effective configuration as YAML (identity shown as `***`) and exit |
| `--check` | load the configuration, call `amf_ping` in-process (no network request), print a JSON report, exit 0 or 1 |
| `--version` | print the version |

## A YAML example

```yaml
# ameriflux-mcp.yaml — pass with: ameriflux-mcp --config ameriflux-mcp.yaml
identity:
  profiles:
    default:
      intended_use: other_research
      description: "Comparing drought responses of semi-arid grassland GPP across New Mexico towers."
downloads:
  directory: /data/ameriflux-downloads
local:
  roots: [/data/fluxnet2015]          # FLUXNET2015 zips you downloaded from fluxnet.org
cache:
  disk_dir: /data/cache/ameriflux-mcp
server:
  log_level: info
```

Keep the user ID and email in the environment rather than in a YAML file you share or
commit.

## Automatic values

* `downloads.enabled`: the download tool exists only on stdio; over HTTP it is never
  listed, whatever this says. `--no-downloads` (or `false`) removes it on stdio too.
* `cache.disk_dir`: the on-disk cache is on for stdio and off for HTTP unless a
  directory is configured, so containers without a writable home still start.
* `privacy.allow_contact_emails`: off on every transport. Contact emails of tower teams
  and DOI contributors appear only when this is on **and** a tool call asks for
  contacts.

## Planned settings

<!-- BEGIN GENERATED CONFIG (scripts/gen_config_reference.py; do not edit) -->

| Setting (YAML path) | Environment variable | Default | Description |
| --- | --- | --- | --- |
| `identity.user_id` | `AMERIFLUX_MCP_IDENTITY__USER_ID`<br>(or `AMERIFLUX_USER_ID`) | unset | AmeriFlux username sent with downloads. |
| `identity.user_email` | `AMERIFLUX_MCP_IDENTITY__USER_EMAIL`<br>(or `AMERIFLUX_USER_EMAIL`) | unset | Email registered with AmeriFlux, sent with downloads. |
| `identity.user_name` | `AMERIFLUX_MCP_IDENTITY__USER_NAME`<br>(or `AMERIFLUX_USER_NAME`) | unset | Optional name sent with downloads. |
| `identity.profiles.<name>.intended_use` | `AMERIFLUX_MCP_IDENTITY__PROFILES__DEFAULT__INTENDED_USE`<br>(or `AMERIFLUX_INTENDED_USE`) | unset | Intended-use code 1–6 or key. |
| `identity.profiles.<name>.description` | `AMERIFLUX_MCP_IDENTITY__PROFILES__DEFAULT__DESCRIPTION`<br>(or `AMERIFLUX_DESCRIPTION`) | unset | 20–1000 characters, your own words; ` [ameriflux-mcp]` is appended. |
| `identity.is_test` | `AMERIFLUX_MCP_IDENTITY__IS_TEST` | unset | Must be set before any download; no default. |
| `downloads.enabled` | `AMERIFLUX_MCP_DOWNLOADS__ENABLED` | unset (true on stdio) | Offer the download tool; never available over HTTP. |
| `downloads.directory` | `AMERIFLUX_MCP_DOWNLOADS__DIRECTORY` | `~/ameriflux-downloads` | Directory every download is confined to. |
| `downloads.max_files_per_call` | `AMERIFLUX_MCP_DOWNLOADS__MAX_FILES_PER_CALL` | `50` | Most files one download call transfers. |
| `downloads.max_bytes_per_call` | `AMERIFLUX_MCP_DOWNLOADS__MAX_BYTES_PER_CALL` | `2147483648` | Most bytes one download call transfers (2 GiB). |
| `downloads.max_file_bytes` | `AMERIFLUX_MCP_DOWNLOADS__MAX_FILE_BYTES` | `1073741824` | Largest single file accepted (1 GiB). |
| `local.roots` | `AMERIFLUX_MCP_LOCAL__ROOTS` | `[]` | Extra directories the local file tools may read (the download directory is always included). |
| `privacy.allow_contact_emails` | `AMERIFLUX_MCP_PRIVACY__ALLOW_CONTACT_EMAILS` | `false` | Allow contact emails in results when a call asks for contacts. |
| `cache.enabled` | `AMERIFLUX_MCP_CACHE__ENABLED` | `true` | Cache AmeriFlux API responses. |
| `cache.disk_dir` | `AMERIFLUX_MCP_CACHE__DISK_DIR` | `~/.cache/ameriflux-mcp` (stdio) | On-disk cache, personal fields removed; unset over HTTP. |
| `cache.ttl_s.catalog` | `AMERIFLUX_MCP_CACHE__TTL_S__CATALOG` | `21600` | Site catalog (6 h). |
| `cache.ttl_s.availability` | `AMERIFLUX_MCP_CACHE__TTL_S__AVAILABILITY` | `21600` | Availability lists (6 h). |
| `cache.ttl_s.fluxnet2015` | `AMERIFLUX_MCP_CACHE__TTL_S__FLUXNET2015` | `2592000` | Frozen FLUXNET2015 and FLUXNET-CH4 lists (30 d). |
| `cache.ttl_s.citations` | `AMERIFLUX_MCP_CACHE__TTL_S__CITATIONS` | `86400` | DOI citations (24 h, memory only). |
| `upstream.requests_per_second` | `AMERIFLUX_MCP_UPSTREAM__REQUESTS_PER_SECOND` | `2.0` | Rate limit towards the AmeriFlux API. |
| `upstream.max_concurrency` | `AMERIFLUX_MCP_UPSTREAM__MAX_CONCURRENCY` | `4` | Simultaneous upstream requests. |
| `limits.max_result_bytes` | `AMERIFLUX_MCP_LIMITS__MAX_RESULT_BYTES` | `50000` | Tool results are trimmed (with `page.truncated`) to fit. |
| `limits.preview_max_rows` | `AMERIFLUX_MCP_LIMITS__PREVIEW_MAX_ROWS` | `500` | Most rows `amf_preview_data` returns. |
| `limits.preview_scan_max_bytes` | `AMERIFLUX_MCP_LIMITS__PREVIEW_SCAN_MAX_BYTES` | `268435456` | Most bytes a preview scans (256 MiB). |
| `server.transport` | `AMERIFLUX_MCP_SERVER__TRANSPORT` | `stdio` | `stdio` or `http` (stateless Streamable HTTP at `/mcp`). |
| `server.bind_address` | `AMERIFLUX_MCP_SERVER__BIND_ADDRESS` | `127.0.0.1` | HTTP bind address. |
| `server.bind_port` | `AMERIFLUX_MCP_SERVER__BIND_PORT` | `8080` | HTTP bind port. |
| `server.log_level` | `AMERIFLUX_MCP_SERVER__LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` or `critical` (stderr). |

<!-- END GENERATED CONFIG -->

[^design]: ameriflux-mcp design. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md>
[^plan]: ameriflux-mcp implementation plan. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/research/2026-10-22-plan.md>
