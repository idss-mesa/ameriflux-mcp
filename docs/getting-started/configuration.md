---
title: "Configuration"
description: "Configure ameriflux-mcp with a YAML file, AMERIFLUX_MCP_ environment variables or flags; precedence rules and every setting with its default."
type: Reference
tags:
  - getting-started
  - configuration
  - environment
generated:
  by: "claude/opus-5.5"
  at: "2026-10-23T00:00:00Z"
sources:
  - id: config-module
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/src/ameriflux_mcp/config.py"
    title: "ameriflux-mcp configuration model (config.py)"
    author: "team:idss-mesa"
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design (decisions D12, D17-D23, D25)"
    author: "team:idss-mesa"
status: stable
stale_after: "2027-04-23T00:00:00Z"
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
does not stop the server but is visible in its log. Invalid values stop the server with
exit code 2 and a message naming the setting and the rule, never the value you gave (so a
mistyped email does not end up in a log). ameriflux-mcp does not load `.env` files
itself; export the variables (`set -a; . ./.env; set +a`) before starting it.

The table at the end is generated from the code[^config-module]
(`scripts/gen_config_reference.py`); CI fails if it drifts.

## The download identity

Identity is read from the environment or the YAML file only, never from flags or tool
arguments, and is used only by the download tool. The plain names
(`AMERIFLUX_USER_ID`, `AMERIFLUX_USER_EMAIL`, `AMERIFLUX_USER_NAME`,
`AMERIFLUX_INTENDED_USE`, `AMERIFLUX_DESCRIPTION`) are what other AmeriFlux tools use;
the namespaced `AMERIFLUX_MCP_IDENTITY__…` forms take precedence when set.
`AMERIFLUX_MCP_IDENTITY__IS_TEST` has no plain form and no default. Look-alike names
(`AMERIFLUX_EMAIL`, `AMERIFLUX_USERNAME`, `AMERIFLUX_USER`, `AMERIFLUX_TOKEN`,
`AMERIFLUX_API_KEY`, `AMF_USER_ID`, `AMF_USER_EMAIL`, `AMF_EMAIL`) are not read; the
server logs a warning, without the value, when one is set. See
[Download identity](identity.md) for what each value is and who sees it.

## Command-line flags

| Flag | Sets |
| --- | --- |
| `--config PATH` | YAML file to load |
| `--transport {stdio,http}` | `server.transport` |
| `--bind-address`, `--bind-port` | `server.bind_address`, `server.bind_port` |
| `--log-level` | `server.log_level` |
| `--download-dir PATH` | `downloads.directory` |
| `--downloads` | `downloads.enabled = true` (stdio only) |
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

* `downloads.enabled`: **off by default** until AmeriFlux confirms third-party use of
  its download request. Set it to `true` (or pass `--downloads`) to list the download
  tool on stdio; over HTTP it is never listed, whatever this says. `--no-downloads`
  forces it off.
* `cache.disk_dir`: the on-disk cache is on for stdio and off for HTTP unless a
  directory is configured, so containers without a writable home still start.
* `privacy.allow_contact_emails`: off on every transport. Contact emails of tower teams
  and DOI contributors appear only when this is on **and** a tool call asks for
  contacts.

## All settings

<!-- BEGIN GENERATED CONFIG (scripts/gen_config_reference.py; do not edit) -->

| Setting (YAML path) | Environment variable | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `upstream.api_base_url` | `AMERIFLUX_MCP_UPSTREAM__API_BASE_URL` | str | `https://amfcdn.lbl.gov/api` | AmeriFlux API base URL (v1 and v2 paths are appended per endpoint). |
| `upstream.user_agent_suffix` | `AMERIFLUX_MCP_UPSTREAM__USER_AGENT_SUFFIX` | str \| null | unset | Text appended to the User-Agent header. |
| `upstream.connect_timeout_s` | `AMERIFLUX_MCP_UPSTREAM__CONNECT_TIMEOUT_S` | float | `10.0` | TCP/TLS connect timeout. |
| `upstream.read_timeout_s` | `AMERIFLUX_MCP_UPSTREAM__READ_TIMEOUT_S` | float | `60.0` | Default read timeout. |
| `upstream.download_read_timeout_s` | `AMERIFLUX_MCP_UPSTREAM__DOWNLOAD_READ_TIMEOUT_S` | float | `300.0` | Read timeout for data file downloads. |
| `upstream.requests_per_second` | `AMERIFLUX_MCP_UPSTREAM__REQUESTS_PER_SECOND` | float | `2.0` | Rate limit towards the AmeriFlux API (local policy). |
| `upstream.max_concurrency` | `AMERIFLUX_MCP_UPSTREAM__MAX_CONCURRENCY` | int | `4` | Maximum simultaneous upstream requests. |
| `upstream.max_response_bytes` | `AMERIFLUX_MCP_UPSTREAM__MAX_RESPONSE_BYTES` | int | `20971520` | Largest upstream response body read into memory (the site catalog is 1.7 MB). |
| `upstream.retries.max_attempts` | `AMERIFLUX_MCP_UPSTREAM__RETRIES__MAX_ATTEMPTS` | int | `3` | Attempts per upstream call, including the first. |
| `upstream.retries.backoff_base_s` | `AMERIFLUX_MCP_UPSTREAM__RETRIES__BACKOFF_BASE_S` | float | `0.5` | Base of the exponential backoff (0.5 * 2^n seconds). |
| `upstream.retries.backoff_max_s` | `AMERIFLUX_MCP_UPSTREAM__RETRIES__BACKOFF_MAX_S` | float | `8.0` | Cap on a single backoff sleep. |
| `upstream.retries.retry_after_default_s` | `AMERIFLUX_MCP_UPSTREAM__RETRIES__RETRY_AFTER_DEFAULT_S` | float | `1.0` | Wait used on HTTP 429 when no Retry-After header is sent. |
| `identity.user_id` | `AMERIFLUX_MCP_IDENTITY__USER_ID`<br>(or `AMERIFLUX_USER_ID`) | SecretStr \| null | unset | AmeriFlux username sent with downloads (or AMERIFLUX_USER_ID). |
| `identity.user_email` | `AMERIFLUX_MCP_IDENTITY__USER_EMAIL`<br>(or `AMERIFLUX_USER_EMAIL`) | SecretStr \| null | unset | Email registered with AmeriFlux, sent with downloads (or AMERIFLUX_USER_EMAIL). |
| `identity.user_name` | `AMERIFLUX_MCP_IDENTITY__USER_NAME`<br>(or `AMERIFLUX_USER_NAME`) | SecretStr \| null | unset | Optional name sent with downloads (or AMERIFLUX_USER_NAME). |
| `identity.profiles.<name>.intended_use` | `AMERIFLUX_MCP_IDENTITY__PROFILES__<NAME>__INTENDED_USE`<br>(default profile: `AMERIFLUX_INTENDED_USE`) | `synthesis` \| `model` \| `remote_sensing` \| `other_research` \| `education` \| `other` \| null | unset | Intended-use category: 1-6 or synthesis, model, remote_sensing, other_research, education, other. |
| `identity.profiles.<name>.description` | `AMERIFLUX_MCP_IDENTITY__PROFILES__<NAME>__DESCRIPTION`<br>(default profile: `AMERIFLUX_DESCRIPTION`) | str \| null | unset | How you will use the data, in your own words (20-1000 characters); ' [ameriflux-mcp]' is appended when sent. |
| `identity.is_test` | `AMERIFLUX_MCP_IDENTITY__IS_TEST` | bool \| null | unset | Send downloads as test requests. Must be set before any download. |
| `cache.enabled` | `AMERIFLUX_MCP_CACHE__ENABLED` | bool | `true` | Cache AmeriFlux API responses. |
| `cache.max_entries` | `AMERIFLUX_MCP_CACHE__MAX_ENTRIES` | int | `1024` | Overall in-memory entry cap. |
| `cache.stale_if_error_s` | `AMERIFLUX_MCP_CACHE__STALE_IF_ERROR_S` | int | `604800` | How long an expired entry may be served when a refresh fails. |
| `cache.disk_dir` | `AMERIFLUX_MCP_CACHE__DISK_DIR` | Path \| null | unset | On-disk cache (personal fields removed). Unset: ~/.cache/ameriflux-mcp on stdio, none over http. |
| `cache.ttl_s.catalog` | `AMERIFLUX_MCP_CACHE__TTL_S__CATALOG` | int | `21600` | Site catalog (6 h). |
| `cache.ttl_s.availability` | `AMERIFLUX_MCP_CACHE__TTL_S__AVAILABILITY` | int | `21600` | Availability lists (6 h). |
| `cache.ttl_s.fluxnet2015` | `AMERIFLUX_MCP_CACHE__TTL_S__FLUXNET2015` | int | `2592000` | Frozen FLUXNET2015 and FLUXNET-CH4 lists (30 d). |
| `cache.ttl_s.variables` | `AMERIFLUX_MCP_CACHE__TTL_S__VARIABLES` | int | `86400` | FP Standard variable list (24 h). |
| `cache.ttl_s.citations` | `AMERIFLUX_MCP_CACHE__TTL_S__CITATIONS` | int | `86400` | DOI citations (24 h, memory only). |
| `cache.ttl_s.dictionaries` | `AMERIFLUX_MCP_CACHE__TTL_S__DICTIONARIES` | int | `2592000` | FLUXNET variable dictionaries (30 d). |
| `cache.ttl_s.heights` | `AMERIFLUX_MCP_CACHE__TTL_S__HEIGHTS` | int | `86400` | Measurement heights (24 h). |
| `cache.ttl_s.coverage` | `AMERIFLUX_MCP_CACHE__TTL_S__COVERAGE` | int | `604800` | Variable coverage snapshots (7 d). |
| `limits.default_limit` | `AMERIFLUX_MCP_LIMITS__DEFAULT_LIMIT` | int | `25` | Default page size where a tool does not set its own. |
| `limits.max_limit` | `AMERIFLUX_MCP_LIMITS__MAX_LIMIT` | int | `200` | Largest page size any tool accepts. |
| `limits.max_result_bytes` | `AMERIFLUX_MCP_LIMITS__MAX_RESULT_BYTES` | int | `50000` | Tool results are trimmed (with page.truncated) to fit this many bytes of compact JSON. |
| `limits.hard_max_result_bytes` | `AMERIFLUX_MCP_LIMITS__HARD_MAX_RESULT_BYTES` | int | `200000` | A result still larger than this after trimming fails with result_too_large. |
| `limits.max_resource_bytes` | `AMERIFLUX_MCP_LIMITS__MAX_RESOURCE_BYTES` | int | `1048576` | Largest resource read returned; larger ones fail with result_too_large. |
| `limits.preview_max_rows` | `AMERIFLUX_MCP_LIMITS__PREVIEW_MAX_ROWS` | int | `500` | Most rows amf_preview_data returns. |
| `limits.preview_scan_max_bytes` | `AMERIFLUX_MCP_LIMITS__PREVIEW_SCAN_MAX_BYTES` | int | `268435456` | Most bytes a preview scans (256 MiB). |
| `limits.preview_time_budget_s` | `AMERIFLUX_MCP_LIMITS__PREVIEW_TIME_BUDGET_S` | float | `20.0` | Wall-clock budget for one preview scan. |
| `limits.zip_member_max_bytes` | `AMERIFLUX_MCP_LIMITS__ZIP_MEMBER_MAX_BYTES` | int | `1073741824` | Largest zip member read (uncompressed). |
| `limits.tools_list_max_bytes` | `AMERIFLUX_MCP_LIMITS__TOOLS_LIST_MAX_BYTES` | int | `85000` | Conformance bound on the serialized tools/list result: 67,948 B measured with the 12 stdio tools of v0.1.0, x1.25 (as neon-mcp). |
| `downloads.enabled` | `AMERIFLUX_MCP_DOWNLOADS__ENABLED` | bool | `false` | Offer the download tool (stdio only; never over http). Off by default until AmeriFlux confirms third-party use of its download request (research/questions.md Q1). |
| `downloads.directory` | `AMERIFLUX_MCP_DOWNLOADS__DIRECTORY` | Path | `~/ameriflux-downloads` | Directory every download is confined to (created on first use). |
| `downloads.max_files_per_call` | `AMERIFLUX_MCP_DOWNLOADS__MAX_FILES_PER_CALL` | int | `50` | Most files one download call transfers. |
| `downloads.max_bytes_per_call` | `AMERIFLUX_MCP_DOWNLOADS__MAX_BYTES_PER_CALL` | int | `2147483648` | Most bytes one download call transfers (2 GiB). |
| `downloads.max_file_bytes` | `AMERIFLUX_MCP_DOWNLOADS__MAX_FILE_BYTES` | int | `1073741824` | Largest single file accepted (1 GiB). |
| `local.roots` | `AMERIFLUX_MCP_LOCAL__ROOTS` | list[Path] | `[]` | Extra directories the local file tools may read (the download directory is always included), e.g. FLUXNET2015 zips from fluxnet.org. |
| `privacy.allow_contact_emails` | `AMERIFLUX_MCP_PRIVACY__ALLOW_CONTACT_EMAILS` | bool | `false` | Allow team and contributor emails in results when a call asks for contacts. |
| `server.transport` | `AMERIFLUX_MCP_SERVER__TRANSPORT` | `stdio` \| `http` | `stdio` | stdio (local clients) or http (stateless Streamable HTTP at /mcp). |
| `server.bind_address` | `AMERIFLUX_MCP_SERVER__BIND_ADDRESS` | str | `127.0.0.1` | HTTP bind address. |
| `server.bind_port` | `AMERIFLUX_MCP_SERVER__BIND_PORT` | int | `8080` | HTTP bind port. |
| `server.public_base_url` | `AMERIFLUX_MCP_SERVER__PUBLIC_BASE_URL` | str \| null | unset | Public URL of a hosted deployment; its host/origin join the allow-lists. |
| `server.allowed_hosts` | `AMERIFLUX_MCP_SERVER__ALLOWED_HOSTS` | list[str] | `[]` | Host header allow-list (DNS-rebinding protection). |
| `server.allowed_origins` | `AMERIFLUX_MCP_SERVER__ALLOWED_ORIGINS` | list[str] | `[]` | Origin header allow-list (DNS-rebinding protection). |
| `server.dns_rebinding_protection` | `AMERIFLUX_MCP_SERVER__DNS_REBINDING_PROTECTION` | bool \| null | unset | Force DNS-rebinding protection on/off. Unset: SDK default (on for loopback binds or when allow-lists are set). |
| `server.json_response` | `AMERIFLUX_MCP_SERVER__JSON_RESPONSE` | bool | `false` | Answer POST /mcp with application/json instead of a single SSE frame. |
| `server.max_request_body_size` | `AMERIFLUX_MCP_SERVER__MAX_REQUEST_BODY_SIZE` | int | `1048576` | Largest accepted request body in bytes. |
| `server.tools_list_ttl_ms` | `AMERIFLUX_MCP_SERVER__TOOLS_LIST_TTL_MS` | int | `300000` | ttlMs advertised on tools/list. |
| `server.log_level` | `AMERIFLUX_MCP_SERVER__LOG_LEVEL` | `debug` \| `info` \| `warning` \| `error` \| `critical` | `info` | Log verbosity. |
| `server.instructions_extra` | `AMERIFLUX_MCP_SERVER__INSTRUCTIONS_EXTRA` | str \| null | unset | Text appended to the server instructions. |

<!-- END GENERATED CONFIG -->

[^config-module]: ameriflux-mcp configuration model. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/src/ameriflux_mcp/config.py>
