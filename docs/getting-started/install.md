---
title: "Install ameriflux-mcp"
description: "Install ameriflux-mcp on macOS, Linux or Windows with uv and the install script, register it by hand, verify, upgrade or remove it."
type: Guide
tags:
  - getting-started
  - install
  - uv
  - install-script
  - windows
generated:
  by: "claude/opus-5.5"
  at: "2026-10-23T00:00:00Z"
sources:
  - id: uv
    resource: "https://docs.astral.sh/uv/"
    title: "uv documentation"
    author: "team:astral"
  - id: uv-install
    resource: "https://docs.astral.sh/uv/getting-started/installation/"
    title: "Installing uv"
    author: "team:astral"
  - id: gh
    resource: "https://cli.github.com/"
    title: "GitHub CLI"
    author: "team:github"
  - id: repo
    resource: "https://github.com/idss-mesa/ameriflux-mcp"
    title: "ameriflux-mcp source repository"
    author: "team:idss-mesa"
status: draft
stale_after: "2027-04-23T00:00:00Z"
---

# Install ameriflux-mcp

ameriflux-mcp is a Python 3.11+ package with one command, `ameriflux-mcp`, that MCP
clients start over stdio. These instructions cover macOS, Linux and Windows.

!!! warning "Under construction: build step 4 of 8"

    ameriflux-mcp is being built in eight steps (see the [roadmap](../tools/roadmap.md)).
    The server installs and starts on every client below, and site search, site details
    and data availability work today; variables, citations, local files and downloads
    arrive in steps 5–7. The [tool reference](../tools/reference.md) always lists what the
    current build offers. Every step on this page works as written today.

!!! note "Private repository and no PyPI release yet"

    The repository is private for now, so you need read access to
    [idss-mesa/ameriflux-mcp](https://github.com/idss-mesa/ameriflux-mcp){target=_blank}[^repo]
    and git credentials (see [Access the repository](#access-the-repository)). The first
    PyPI release, as `ameriflux-mcp`, is the last build step.

## Prerequisites

- [uv](https://docs.astral.sh/uv/){target=_blank}[^uv], which installs Python 3.11+ for
  ameriflux-mcp if your system lacks it and keeps the server in its own environment.
- git, to clone the repository.
- Access to the private repository on GitHub, for example through the
  [GitHub CLI](https://cli.github.com/){target=_blank}[^gh].
- Optional: an [AmeriFlux account](identity.md), only for downloading data. Everything
  else works without one.

### Install uv

=== "macOS"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # or: brew install uv
    ```

=== "Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # or your distribution's package, if it ships uv 0.5 or newer
    ```

=== "Windows (PowerShell)"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # or: winget install --id=astral-sh.uv -e
    ```

Open a new terminal afterwards so `uv` is on your `PATH`, and check with
`uv --version`[^uv-install].

### Install git

=== "macOS"

    ```bash
    xcode-select --install        # Apple's command-line tools include git
    # or: brew install git
    ```

=== "Linux"

    ```bash
    sudo apt install git          # Debian, Ubuntu
    sudo dnf install git          # Fedora, RHEL
    ```

=== "Windows"

    ```powershell
    winget install --id Git.Git -e
    ```

    Git for Windows includes **Git Bash**, which the install script needs on Windows.

### Access the repository

While the repository is private, clone it with credentials GitHub accepts. The GitHub
CLI is the simplest route on every platform:

=== "macOS"

    ```bash
    brew install gh
    gh auth login                 # choose GitHub.com, HTTPS, and log in with a browser
    ```

=== "Linux"

    ```bash
    # install gh from https://cli.github.com/ (packages for apt, dnf, zypper, ...)
    gh auth login
    ```

=== "Windows (PowerShell)"

    ```powershell
    winget install --id GitHub.cli -e
    gh auth login
    ```

`gh auth login` also sets up git's credential helper, so plain `git clone https://…`
and `uv tool install git+https://…` work afterwards. An SSH key added to your GitHub
account works too: clone `git@github.com:idss-mesa/ameriflux-mcp.git` instead.

## Option 1: From source with the install script (recommended)

=== "macOS / Linux"

    ```bash
    git clone https://github.com/idss-mesa/ameriflux-mcp.git
    cd ameriflux-mcp
    scripts/install.sh
    ```

=== "Windows (Git Bash)"

    ```bash
    git clone https://github.com/idss-mesa/ameriflux-mcp.git
    cd ameriflux-mcp
    scripts/install.sh --dry-run    # check the paths it will write first
    scripts/install.sh
    ```

`scripts/install.sh` creates the server environment (`uv sync`) if
`.venv/bin/ameriflux-mcp` is missing, checks that `ameriflux-mcp --version` runs, then
registers that executable with every supported agent it finds on your machine: Claude
Code, Claude Desktop, OpenAI Codex CLI, Gemini CLI, Goose and OpenCode. It prefers each
agent's own CLI when one is installed (`claude mcp add`, `codex mcp add`,
`gemini mcp add`) and otherwise merges an entry into the agent's config file, keeping
everything else in the file and leaving a `.bak` copy.

```bash
scripts/install.sh --with-identity               # also store your download identity (see below)
scripts/install.sh --agents all --dry-run        # preview the change for every agent
scripts/install.sh --agents claude,goose         # just Claude Code and Goose
scripts/install.sh --scope project               # project-level config (claude, codex, gemini, opencode)
scripts/install.sh --env AMERIFLUX_MCP_SERVER__LOG_LEVEL=debug   # any extra environment variable
scripts/install.sh --command "$(command -v ameriflux-mcp)"       # register a uv-tool install instead
scripts/install.sh --uninstall                   # remove the registration everywhere
```

| Agent | What the script does |
| --- | --- |
| `claude` (Claude Code) | `claude mcp add --scope user ameriflux -- /path/to/ameriflux-mcp/.venv/bin/ameriflux-mcp` |
| `claude-desktop` | adds `mcpServers.ameriflux` to `claude_desktop_config.json` |
| `codex` (OpenAI Codex CLI) | `codex mcp add ameriflux -- …`, or an `[mcp_servers.ameriflux]` table in `~/.codex/config.toml` |
| `gemini` (Gemini CLI) | `gemini mcp add --scope user ameriflux …`, or `mcpServers.ameriflux` in `~/.gemini/settings.json` |
| `goose` | adds an `ameriflux` stdio extension to `~/.config/goose/config.yaml` |
| `opencode` | adds `mcp.servers.ameriflux` (v2) or `mcp.ameriflux` (v1) to `~/.config/opencode/opencode.json` |

The script writes the absolute path of the executable, because desktop apps do not
inherit your shell `PATH`. It needs bash; macOS's built-in bash 3.2 is enough. Restart
desktop apps (Claude Desktop, Goose Desktop) after installing.

### The download identity and the script

Only the download tool needs an identity, and everything in it is sent to the site
PIs when you confirm a download ([Download identity](identity.md) explains why). There
is deliberately no option that takes these values on the command line, since command
lines end up in shell history and process lists. `--with-identity` reads them from your
environment, or asks for each missing one on a terminal:

```bash
scripts/install.sh --with-identity
# AmeriFlux user ID: ...
# Email registered with AmeriFlux: ...
# Your name (optional, Enter to skip):
# Intended use (1 synthesis, 2 model, 3 remote sensing, 4 other research, 5 education, 6 other): ...
# Describe how you will use the data (20-1000 characters, in your own words): ...
# Send downloads as test requests? (true/false): ...
```

The answers are stored in each agent's server `env` as `AMERIFLUX_USER_ID`,
`AMERIFLUX_USER_EMAIL`, `AMERIFLUX_USER_NAME`, `AMERIFLUX_INTENDED_USE`,
`AMERIFLUX_DESCRIPTION` and `AMERIFLUX_MCP_IDENTITY__IS_TEST`.

- They are stored **in plain text** in each agent's config file. The script restricts
  the files it writes, and their `.bak` copies, to your user (mode `600`), and masks your
  user ID, email and name as `***` in everything it prints, including the output of the
  agent CLIs it calls.
- For agents registered through their own CLI (Claude Code, Codex, Gemini CLI), the
  values are passed to that CLI's `mcp add` command and are briefly visible in the
  process list. Add `--prefer-files` to have Codex and Gemini CLI configured by file.
- Without `--with-identity` nothing is stored. Discovery, availability, variables,
  citations and local previews work as usual; the download tool explains what is
  missing when you ask it to download.

### Windows

On Windows, run the script from **Git Bash** (installed with Git for Windows) or
register by hand (Option 2). Git Bash converts paths to Windows form, uses
`.venv\Scripts\ameriflux-mcp.exe`, and writes Claude Desktop's config under
`%APPDATA%\Claude` and Goose's under `%APPDATA%\Block\goose\config`. Git Bash support
has not been tested as widely as macOS and Linux; check the result with `--dry-run`
first. Do not run the script inside WSL to configure Windows apps: it would write WSL's
own config files, which Claude Desktop for Windows never reads. (Inside WSL, for agents
that also run inside WSL, it works as on Linux.)

## Option 2: Install the package and register it by hand

=== "uv tool (recommended)"

    ```bash
    uv tool install git+https://github.com/idss-mesa/ameriflux-mcp
    ```

    This puts `ameriflux-mcp` in uv's tool directory (`~/.local/bin` on macOS and
    Linux, `%USERPROFILE%\.local\bin` on Windows) and uses your git credentials for the
    private repository. Upgrade with
    `uv tool install --reinstall git+https://github.com/idss-mesa/ameriflux-mcp`.

=== "From source"

    ```bash
    git clone https://github.com/idss-mesa/ameriflux-mcp.git
    cd ameriflux-mcp
    uv sync                      # creates .venv with the package
    uv run ameriflux-mcp --version
    ```

=== "PyPI (from v0.1.0)"

    ```bash
    uv tool install ameriflux-mcp
    # or: pipx install ameriflux-mcp
    ```

    Not published yet; the PyPI release is build step 8.

Then find the executable's absolute path, which is what desktop apps need:

=== "macOS / Linux"

    ```bash
    command -v ameriflux-mcp     # e.g. /Users/you/.local/bin/ameriflux-mcp
    # from source: /path/to/ameriflux-mcp/.venv/bin/ameriflux-mcp
    ```

=== "Windows (PowerShell)"

    ```powershell
    (Get-Command ameriflux-mcp).Source  # e.g. C:\Users\you\.local\bin\ameriflux-mcp.exe
    # from source: C:\path\to\ameriflux-mcp\.venv\Scripts\ameriflux-mcp.exe
    ```

and register it with your client. The shortest form, for Claude Code:

```bash
claude mcp add ameriflux -s user -- ameriflux-mcp
```

Claude Desktop, and other JSON-configured clients:

```json
{
  "mcpServers": {
    "ameriflux": {
      "command": "/ABSOLUTE/PATH/TO/ameriflux-mcp",
      "args": []
    }
  }
}
```

Use absolute paths (not `~/` or `./`). On Windows escape backslashes:
`"C:\\Users\\You\\.local\\bin\\ameriflux-mcp.exe"`. To enable downloads, add an `env`
block with your identity ([Download identity](identity.md#give-it-to-ameriflux-mcp)).
[Clients](clients.md) has the entries for Claude Desktop, Codex CLI, Gemini CLI, Goose,
OpenCode, VS Code and hosted servers.

## Option 3: Docker (from build step 8)

The repository will ship a `Dockerfile` that serves stateless Streamable HTTP on port
8080 as a non-root user, with a `/healthz` health check:

```bash
git clone https://github.com/idss-mesa/ameriflux-mcp.git && cd ameriflux-mcp
docker build -t ameriflux-mcp .
docker run --rm --read-only --tmpfs /tmp -p 127.0.0.1:8080:8080 ameriflux-mcp
```

Point an HTTP-capable client at `http://127.0.0.1:8080/mcp`. Over HTTP the server
offers the eight discovery, variable and citation tools; downloads and local file tools
are stdio only, and no identity is ever accepted over HTTP.

## Verify the installation

```bash
ameriflux-mcp --version     # ameriflux-mcp 0.1.0
ameriflux-mcp --check       # {"ok": true, "version": "0.1.0", "protocolVersion": "2026-07-28", "transport": "stdio", "identityConfigured": false, "downloadsEnabled": true}
```

`--check` loads your configuration, calls `amf_ping` in-process and prints a one-line
JSON report: version, protocol, transport, whether a download identity is configured
(as booleans, never the values) and whether downloads are enabled. It makes no network
request. To check that AmeriFlux answers, ask your agent to call `amf_ping` with
`check_api=true` once the server is connected. `--print-config` shows the effective
settings with identity values replaced by `***`.

In Claude Code, `claude mcp list` runs a health check and shows `ameriflux` as
connected. To talk to the server directly over stdio:

```bash
# 2026-07-28 client: every request carries the protocol envelope in _meta
echo '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{},"io.modelcontextprotocol/clientInfo":{"name":"manual","version":"0"}}}}' \
  | ameriflux-mcp

# 2025-era client: classic initialize handshake, then tools/list
printf '%s\n%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | ameriflux-mcp
```

Both print JSON-RPC responses on stdout (logs go to stderr) and exit once stdin closes.
`server/discover` reports the server's capabilities and instructions; `tools/list` lists
every tool available in that build.

## Configuration

Nothing is required. The settings most people touch:

```bash
AMERIFLUX_MCP_SERVER__LOG_LEVEL=info           # debug | info | warning | error | critical (stderr)
AMERIFLUX_MCP_DOWNLOADS__DIRECTORY=            # where downloads go (default ~/ameriflux-downloads)
AMERIFLUX_MCP_LOCAL__ROOTS=                    # extra folders the file tools may read (e.g. FLUXNET2015 zips)
AMERIFLUX_MCP_DOWNLOADS__ENABLED=false         # turn the download tool off entirely
```

ameriflux-mcp does not read `.env` files on its own. See [Configuration](configuration.md)
for every setting, the YAML file and the precedence rules.

## Troubleshooting

**The install script says "nothing was registered".** `ameriflux-mcp --version` did not
run, so the script refused to register a broken command. Run `uv sync` in the clone (or
reinstall with `uv tool install --reinstall …`) and try again; run the command yourself
to see its error; `scripts/install.sh --dry-run` shows what it would do without stopping.

**The server exits at once with "invalid configuration".** A setting failed validation
(exit code 2). The message names the setting and the rule, for example
`identity.user_email: Value error, user_email is not an email address`; it never repeats
the value, so check the variable yourself. `ameriflux-mcp --print-config` shows the
effective settings once they load.

**`git clone` fails with "Repository not found" or asks for a password.** The repository
is private: GitHub answers 404 to anyone without access. Ask an idss-mesa maintainer for
access, then run `gh auth login` (or use SSH) so git sends your credentials.

**`ameriflux-mcp: command not found` from a desktop app.** Desktop apps do not read your
shell profile. Use the executable's absolute path as the `command`; the install script
does this for you.

**Server shows as disconnected.** Run the configured command yourself with `--check`. If
it fails, re-create the environment (`uv sync` in a clone, or
`uv tool install --reinstall git+https://github.com/idss-mesa/ameriflux-mcp`). Claude
Desktop logs live in `~/Library/Logs/Claude/` (macOS) or `%APPDATA%\Claude\logs\`
(Windows); in Claude Code, `claude mcp get ameriflux` shows the connection status.

**`identityConfigured` is `false` although you set the variables.** They did not reach
the server process: desktop apps do not see variables exported in your shell. Put them in
the client's `env` block, or re-run the install script with `--with-identity`.

**Downloads report `auth_required` with `is_test_unset`.** `is_test` has no default on
purpose; set `AMERIFLUX_MCP_IDENTITY__IS_TEST` to `true` or `false` (see
[Download identity](identity.md#is_test)).

**Port already in use.** MCP over stdio uses no network port; a port error comes from an
HTTP deployment (`--transport http`, port 8080 by default) or something else on your
machine.

**Windows paths.** In JSON, write backslashes doubled (`C:\\Users\\…`) or use forward
slashes. Point at `ameriflux-mcp.exe`, not the extension-less name.

## Upgrading

```bash
# install script / from source
git pull origin main && uv sync
# uv tool
uv tool install --reinstall git+https://github.com/idss-mesa/ameriflux-mcp
```

Registrations made by the install script keep pointing at `.venv/bin/ameriflux-mcp`, so
`git pull && uv sync` is enough; restart desktop apps afterwards.

## Uninstallation

`--uninstall` leaves each edited file's `.bak` copy behind; if you used
`--with-identity`, those backups (owner-only, like the files) still contain your user
ID and email, so delete them too.

```bash
scripts/install.sh --uninstall       # remove the server from every agent config
cd .. && rm -rf ameriflux-mcp        # if installed from source
uv tool uninstall ameriflux-mcp      # if installed with uv tool
rm -rf ~/.cache/ameriflux-mcp        # the response cache (from build step 3)
```

Downloaded data in `~/ameriflux-downloads` is yours; remove it separately if you no
longer need it.

## Next steps

- [Quickstart](quickstart.md): a first session.
- [Download identity](identity.md): what downloads disclose and how to configure them.
- [Clients](clients.md): per-client configuration.
- [Configuration](configuration.md): every setting.

[^uv]: uv documentation. <https://docs.astral.sh/uv/>
[^uv-install]: Installing uv. <https://docs.astral.sh/uv/getting-started/installation/>
[^gh]: GitHub CLI. <https://cli.github.com/>
[^repo]: ameriflux-mcp source repository. <https://github.com/idss-mesa/ameriflux-mcp>
