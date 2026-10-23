---
title: "Tool reference"
description: "Every ameriflux-mcp tool with its inputs, result fields, upstream endpoints and annotations, generated from the tool registry."
type: MCP Tool Reference
tags:
  - tools
  - reference
  - generated
generated:
  by: "process:gen_tools_reference"
  at: "2026-10-23T00:00:00Z"
sources:
  - id: registry
    resource: "https://github.com/idss-mesa/ameriflux-mcp/tree/main/src/ameriflux_mcp/tools"
    title: "ameriflux-mcp tool registry"
    author: "team:idss-mesa"
status: stable
---

# Tool reference

Generated from the tool registry by `scripts/gen_tools_reference.py`; do not edit by hand. 1 tools are registered. Inputs are snake_case and outputs camelCase. Every result also carries `resolved`, `notes`, `nextSteps` and `source` (whose `backend` says what answered: the AmeriFlux API, its file server, or nothing upstream), and failures return `structuredContent.error` with a stable `code`. Tools still to come are on the [roadmap](roadmap.md).

| Tool | Title | Family | Download identity |
| --- | --- | --- | --- |
| [`amf_ping`](#amf_ping) | Check ameriflux-mcp status | [core](roadmap.md) | no |

## amf_ping

**Check ameriflux-mcp status.** Liveness and capability report: server version, protocol and transport; whether a download identity is configured (booleans and profile names only, never the values) and which tools need it; whether downloads are enabled and where files go. With check_api=true it also makes one small request to the AmeriFlux API to confirm connectivity. Next: read ameriflux://guide/identity to set up downloads.

| | |
| --- | --- |
| Surface | `core` |
| Download identity | not needed |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET amfcdn.lbl.gov/api/v1/fp_var` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `check_api` | boolean |  | false | Also make one small request to the AmeriFlux API (the FP Standard variable list) to confirm connectivity. |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `pong` | `ok` |  |
| `version` | string |  |
| `protocolVersion` | string |  |
| `transport` | `stdio` \\| `http` |  |
| `identity` | IdentityReport |  |
| `identityRequiredTools` | array of string | Registered tools that need the download identity (auth_required without it). |
| `downloadsEnabled` | boolean |  |
| `downloadDir` | string \\| null |  |
| `localRoots` | array of string \\| null | Directories the local file tools may read (stdio only). |
| `endpoints` | Endpoints |  |
| `cache` | CacheReport |  |
| `upstream` | UpstreamCheck \\| null | Present when check_api was requested. |
