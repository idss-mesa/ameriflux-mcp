---
title: "Clients"
description: "Register ameriflux-mcp with Claude Code, Claude Desktop, Codex CLI, Gemini CLI, Goose, OpenCode and VS Code, or a hosted server over HTTP."
type: Guide
tags:
  - getting-started
  - clients
  - claude-code
  - codex
  - gemini
  - goose
generated:
  by: "claude/opus-5.5"
  at: "2026-10-23T00:00:00Z"
sources:
  - id: claude-code-mcp
    resource: "https://docs.claude.com/en/docs/claude-code/mcp"
    title: "Claude Code — MCP"
    author: "team:anthropic"
  - id: codex-mcp
    resource: "https://developers.openai.com/codex/cli/"
    title: "OpenAI Codex CLI"
    author: "team:openai"
  - id: gemini-mcp
    resource: "https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md"
    title: "Gemini CLI — MCP servers"
    author: "team:google"
  - id: goose-ext
    resource: "https://goose-docs.ai/docs/getting-started/using-extensions"
    title: "Goose — Using extensions"
    author: "team:block"
  - id: opencode-mcp
    resource: "https://opencode.ai/docs/mcp-servers/"
    title: "OpenCode — MCP servers"
    author: "team:opencode"
  - id: vscode-mcp
    resource: "https://code.visualstudio.com/docs/copilot/chat/mcp-servers"
    title: "VS Code — Use MCP servers"
    author: "team:microsoft"
status: draft
stale_after: "2027-04-23T00:00:00Z"
---

# Clients

Local clients start ameriflux-mcp themselves over **stdio**; hosted deployments are
reached over **Streamable HTTP**. The [install script](install.md#option-1-from-source-with-the-install-script-recommended)
(`scripts/install.sh`) writes the stdio entries below for Claude Code, Claude Desktop,
Codex CLI, Gemini CLI, Goose and OpenCode in one step; this page shows them for manual
setup. The examples use `ameriflux-mcp` on your `PATH` (see [Install](install.md));
replace it with an absolute path such as
`/home/me/ameriflux-mcp/.venv/bin/ameriflux-mcp` (Windows:
`C:\\Users\\me\\ameriflux-mcp\\.venv\\Scripts\\ameriflux-mcp.exe`) when the client does
not share your shell's `PATH`. JSON-configured clients do not expand `~` or `$HOME`, so
use absolute paths there.

The examples register the server **without** a download identity, which is all that
discovery, variables, citations and local previews need. To enable downloads, add the
variables from [Download identity](identity.md#the-settings) to the same `env` block
(or `-e` options); keep them in the client's environment settings, never in a shared or
committed file.

## Claude Code

```bash
claude mcp add ameriflux -s user -- ameriflux-mcp --transport stdio
claude mcp list
```

`-s user` makes the server available in every project[^claude-code-mcp]. Add
`-e NAME=value` options before `--` for the download identity.

## Claude Desktop

Edit `claude_desktop_config.json` and restart the app:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ameriflux": {
      "command": "/absolute/path/to/ameriflux-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

## Codex CLI

```bash
codex mcp add ameriflux -- ameriflux-mcp --transport stdio
codex mcp list
```

This writes the server into `~/.codex/config.toml`[^codex-mcp]; restart running
sessions. Without the CLI, add the table yourself:

```toml
[mcp_servers.ameriflux]
command = "/absolute/path/to/ameriflux-mcp"
args = []

# only for downloads:
# [mcp_servers.ameriflux.env]
# AMERIFLUX_USER_ID = "your-username"
```

## Gemini CLI

```bash
gemini mcp add --scope user ameriflux ameriflux-mcp
gemini mcp list
```

or add the entry to `~/.gemini/settings.json`[^gemini-mcp] (`.gemini/settings.json` in a
project):

```json
{
  "mcpServers": {
    "ameriflux": {
      "command": "/absolute/path/to/ameriflux-mcp",
      "args": []
    }
  }
}
```

## Goose

Add an extension to `~/.config/goose/config.yaml` (Windows:
`%APPDATA%\Block\goose\config\config.yaml`)[^goose-ext], then restart Goose Desktop or
start a new CLI session. `goose configure` → *Add Extension* → *Command-line Extension*
does the same interactively.

```yaml
extensions:
  ameriflux:
    enabled: true
    type: stdio
    name: ameriflux
    cmd: /absolute/path/to/ameriflux-mcp
    args: []
    envs: {}
    timeout: 300
```

## OpenCode

Add to `~/.config/opencode/opencode.json`[^opencode-mcp]. This is the layout OpenCode's
documentation shows. The install script writes `"mcp": {"servers": {…}}` instead unless
`opencode --version` reports 1.x; if your OpenCode does not pick the server up, move the
entry to the layout its documentation gives.

```json
{
  "mcp": {
    "ameriflux": {
      "type": "local",
      "command": ["/absolute/path/to/ameriflux-mcp", "--transport", "stdio"],
      "enabled": true
    }
  }
}
```

## VS Code

Add to `.vscode/mcp.json` in a workspace, or to your user configuration[^vscode-mcp].
For downloads, `inputs` prompts keep your identity out of the file:

```json
{
  "inputs": [
    { "type": "promptString", "id": "amf-user", "description": "AmeriFlux user ID" },
    { "type": "promptString", "id": "amf-email", "description": "Email registered with AmeriFlux", "password": true }
  ],
  "servers": {
    "ameriflux": {
      "type": "stdio",
      "command": "/absolute/path/to/ameriflux-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "AMERIFLUX_USER_ID": "${input:amf-user}",
        "AMERIFLUX_USER_EMAIL": "${input:amf-email}"
      }
    }
  }
}
```

Leave out `inputs` and `env` to run without downloads.

## Any other stdio client

Run `ameriflux-mcp --transport stdio` (bare `ameriflux-mcp` does the same), with the
download identity in the environment if you want downloads. The server speaks MCP
2026-07-28 and still accepts clients on earlier protocol revisions over stdio.

## A hosted server (HTTP)

```bash
claude mcp add --transport http ameriflux https://ameriflux-mcp.example.org/mcp
```

A hosted server offers the eight tools that need no identity and read no local files:
site search, site details, availability, the two variable tools, citations, BADM and
`amf_ping`. Downloads and the local file tools exist only on stdio, and no identity is
accepted over HTTP, by header or otherwise.

[^claude-code-mcp]: Claude Code — MCP. <https://docs.claude.com/en/docs/claude-code/mcp>
[^codex-mcp]: OpenAI Codex CLI. <https://developers.openai.com/codex/cli/>
[^gemini-mcp]: Gemini CLI — MCP servers. <https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md>
[^goose-ext]: Goose — Using extensions. <https://goose-docs.ai/docs/getting-started/using-extensions>
[^opencode-mcp]: OpenCode — MCP servers. <https://opencode.ai/docs/mcp-servers/>
[^vscode-mcp]: VS Code — Use MCP servers. <https://code.visualstudio.com/docs/copilot/chat/mcp-servers>
