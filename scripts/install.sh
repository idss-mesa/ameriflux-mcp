#!/usr/bin/env bash
#
# Register the ameriflux-mcp server with AI coding agents.
#
# Supported agents:
#   claude          Claude Code CLI            (claude mcp add, user scope)
#   claude-desktop  Claude Desktop app         (claude_desktop_config.json)
#   codex           OpenAI Codex CLI           (codex mcp add, or ~/.codex/config.toml)
#   gemini          Gemini CLI                 (gemini mcp add, or ~/.gemini/settings.json)
#   goose           Block Goose CLI / Desktop  (~/.config/goose/config.yaml)
#   opencode        OpenCode                   (~/.config/opencode/opencode.json, v1 or v2 schema)
#
# Usage:
#   scripts/install.sh [options]
#
#   --agents LIST     Comma-separated agents from the list above, or "all".
#                     Default: every agent whose CLI or config file is found on this machine.
#   --scope SCOPE     user (default) or project. "project" writes the agent's project-level
#                     config in the current directory (claude, codex, gemini, opencode).
#   --name NAME       Server name to register (default: ameriflux).
#   --command PATH    The ameriflux-mcp executable to register. Default: this clone's
#                     .venv/bin/ameriflux-mcp (created with `uv sync` when missing).
#   --with-identity   Store your AmeriFlux download identity in each agent's server env:
#                     AMERIFLUX_USER_ID, AMERIFLUX_USER_EMAIL, AMERIFLUX_USER_NAME (optional),
#                     AMERIFLUX_INTENDED_USE, AMERIFLUX_DESCRIPTION, AMERIFLUX_MCP_IDENTITY__IS_TEST.
#                     Read from the environment, or prompted for on a terminal. Only the
#                     download tool uses them, and they are sent to the site PIs when you
#                     confirm a download. There is no flag that takes these values.
#   --env KEY=VALUE   Extra environment variable for the server (repeatable; not identity).
#   --prefer-files    Edit config files directly even when an agent CLI is available.
#   --uninstall       Remove the server registration instead of adding it.
#   --dry-run         Show what would change without writing anything.
#   --no-sync         Do not run `uv sync` when the clone's .venv/bin/ameriflux-mcp is missing.
#   --no-verify       Register even if `ameriflux-mcp --version` does not run.
#   -h, --help        Show this help.
#
# Examples:
#   scripts/install.sh                          # register with every detected agent
#   scripts/install.sh --with-identity          # ... and store your download identity
#   scripts/install.sh --agents claude,goose    # just Claude Code and Goose
#   scripts/install.sh --agents all --dry-run   # preview every agent's config change
#   scripts/install.sh --uninstall              # remove the registration everywhere
#
set -euo pipefail

SERVER_NAME="ameriflux"
AGENTS=""
SCOPE="user"
DRY_RUN=0
UNINSTALL=0
PREFER_FILES=0
NO_SYNC=0
WITH_IDENTITY=0
NO_VERIFY=0
COMMAND_OPT=""
EXTRA_ENV=()

usage() { sed -n '2,43p' "$0" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agents) AGENTS="$2"; shift 2 ;;
    --agents=*) AGENTS="${1#*=}"; shift ;;
    --scope) SCOPE="$2"; shift 2 ;;
    --scope=*) SCOPE="${1#*=}"; shift ;;
    --name) SERVER_NAME="$2"; shift 2 ;;
    --command) COMMAND_OPT="$2"; shift 2 ;;
    --with-identity) WITH_IDENTITY=1; shift ;;
    --env) EXTRA_ENV+=("$2"); shift 2 ;;
    --prefer-files) PREFER_FILES=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-sync) NO_SYNC=1; shift ;;
    --no-verify) NO_VERIFY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$SCOPE" in user|project) ;; *) echo "--scope must be user or project" >&2; exit 2 ;; esac

for kv in "${EXTRA_ENV[@]:-}"; do
  [[ -z "$kv" ]] && continue
  if [[ "$kv" != *=* ]]; then echo "--env expects KEY=VALUE (got '$kv')" >&2; exit 2; fi
  case "${kv%%=*}" in
    AMERIFLUX_USER_ID|AMERIFLUX_USER_EMAIL|AMERIFLUX_USER_NAME|AMERIFLUX_INTENDED_USE|AMERIFLUX_DESCRIPTION|AMERIFLUX_MCP_IDENTITY__*)
      echo "error: identity settings cannot be passed with --env (they would land in your shell" >&2
      echo "history). Export them and use --with-identity, or let --with-identity prompt for them." >&2
      exit 2 ;;
  esac
done

# ---------------------------------------------------------------- platform
OS="$(uname -s)"
WINDOWS=0
case "$OS" in MINGW*|MSYS*|CYGWIN*) WINDOWS=1 ;; esac

# Paths written into agent configs must be native: C:\... on Windows (Git Bash).
native_path() {
  if [[ $WINDOWS -eq 1 ]] && command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi
}
# Paths handed to the config editor (Windows Python accepts C:/... as well).
editor_path() {
  if [[ $WINDOWS -eq 1 ]] && command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

# ---------------------------------------------------------------- locate the server
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ $WINDOWS -eq 1 ]]; then VENV_BIN="$REPO_DIR/.venv/Scripts"; EXE=".exe"; else VENV_BIN="$REPO_DIR/.venv/bin"; EXE=""; fi

if [[ -n "$COMMAND_OPT" ]]; then
  SERVER_CMD="$COMMAND_OPT"
else
  SERVER_CMD="$VENV_BIN/ameriflux-mcp$EXE"
  if [[ $UNINSTALL -eq 0 && ! -x "$SERVER_CMD" ]]; then
    if [[ $NO_SYNC -eq 1 || $DRY_RUN -eq 1 ]]; then
      echo "note: $SERVER_CMD does not exist yet; run 'uv sync' in $REPO_DIR." >&2
    elif command -v uv >/dev/null 2>&1; then
      echo "Creating the server environment (uv sync)..."
      (cd "$REPO_DIR" && uv sync --no-dev)
    else
      echo "error: uv is not on PATH. Install uv (https://docs.astral.sh/uv/) or pass --command." >&2
      exit 1
    fi
  fi
fi
SERVER_CMD_NATIVE="$(native_path "$SERVER_CMD")"

# Refuse to register a command that does not start: a broken entry in every agent's
# config is worse than none. (Before build step 2 the package has no server yet.)
if [[ $UNINSTALL -eq 0 && $NO_VERIFY -eq 0 ]]; then
  if ! SERVER_VERSION="$("$SERVER_CMD" --version 2>/dev/null)"; then
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "note: '$SERVER_CMD --version' did not run; a real install would stop here." >&2
    else
      echo "error: '$SERVER_CMD --version' did not run, so nothing was registered." >&2
      echo "  Run 'uv sync' in $REPO_DIR (or check --command), then try again." >&2
      echo "  ameriflux-mcp is under construction: the server starts from build step 2 on." >&2
      exit 1
    fi
  fi
fi

# Python for the config editor: an override, this clone's venv, python3, or uv's.
if [[ -n "${AMERIFLUX_INSTALL_PYTHON:-}" ]]; then
  PY=("$AMERIFLUX_INSTALL_PYTHON")
elif [[ -x "$VENV_BIN/python$EXE" ]]; then
  PY=("$VENV_BIN/python$EXE")
elif command -v python3 >/dev/null 2>&1; then
  PY=(python3)
elif command -v uv >/dev/null 2>&1; then
  PY=(uv run --no-project python)
else
  echo "error: no Python found for editing config files; install uv or Python 3." >&2
  exit 1
fi

# ---------------------------------------------------------------- download identity (never printed)
# Everything here is sent to the site PIs and the AmeriFlux download log when the user
# confirms a download, so it must come from the user: the environment or a prompt.
ID_USER=""; ID_EMAIL=""; ID_NAME=""; ID_USE=""; ID_DESC=""; ID_TEST=""
ask() {  # ask VAR "prompt": keep $VAR from the environment, else prompt on a terminal
  local __var="$1" __prompt="$2" __val="${!1:-}"
  if [[ -z "$__val" && -t 0 ]]; then read -rp "$__prompt" __val; fi
  printf '%s' "$__val"
}
if [[ $WITH_IDENTITY -eq 1 && $UNINSTALL -eq 0 ]]; then
  if [[ ! -t 0 ]]; then
    missing=()
    for v in AMERIFLUX_USER_ID AMERIFLUX_USER_EMAIL AMERIFLUX_INTENDED_USE AMERIFLUX_DESCRIPTION AMERIFLUX_MCP_IDENTITY__IS_TEST; do
      [[ -z "${!v:-}" ]] && missing+=("$v")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
      echo "error: --with-identity needs ${missing[*]} in the environment or an interactive terminal." >&2
      exit 2
    fi
  fi
  [[ -t 0 ]] && echo "Your AmeriFlux download identity. It is sent to the site PIs when you confirm a download."
  ID_USER="$(ask AMERIFLUX_USER_ID "AmeriFlux user ID: " | tr -d '[:space:]')"
  ID_EMAIL="$(ask AMERIFLUX_USER_EMAIL "Email registered with AmeriFlux: " | tr -d '[:space:]')"
  ID_NAME="$(ask AMERIFLUX_USER_NAME "Your name (optional, Enter to skip): ")"
  ID_USE="$(ask AMERIFLUX_INTENDED_USE "Intended use (1 synthesis, 2 model, 3 remote sensing, 4 other research, 5 education, 6 other): " | tr -d '[:space:]')"
  ID_DESC="$(ask AMERIFLUX_DESCRIPTION "Describe how you will use the data (20-1000 characters, in your own words): ")"
  ID_TEST="$(ask AMERIFLUX_MCP_IDENTITY__IS_TEST "Send downloads as test requests? (true/false): " | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
  [[ -z "$ID_USER" ]] && { echo "error: the AmeriFlux user ID is empty." >&2; exit 2; }
  if [[ ! "$ID_EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; then
    echo "error: '${ID_EMAIL:+<email>}' is not an email address." >&2; exit 2
  fi
  case "$ID_USE" in
    1|2|3|4|5|6|synthesis|model|remote_sensing|other_research|education|other) ;;
    *) echo "error: intended use must be 1-6 (or synthesis, model, remote_sensing, other_research, education, other)." >&2; exit 2 ;;
  esac
  if [[ ${#ID_DESC} -lt 20 || ${#ID_DESC} -gt 1000 ]]; then
    echo "error: the description must be 20-1000 characters (got ${#ID_DESC})." >&2; exit 2
  fi
  case "$ID_TEST" in true|false) ;; *) echo "error: is_test must be true or false." >&2; exit 2 ;; esac
fi

# Environment passed to the server
SERVER_ENV=()
if [[ -n "$ID_USER" ]]; then
  SERVER_ENV+=("AMERIFLUX_USER_ID=$ID_USER" "AMERIFLUX_USER_EMAIL=$ID_EMAIL")
  [[ -n "$ID_NAME" ]] && SERVER_ENV+=("AMERIFLUX_USER_NAME=$ID_NAME")
  SERVER_ENV+=("AMERIFLUX_INTENDED_USE=$ID_USE" "AMERIFLUX_DESCRIPTION=$ID_DESC" "AMERIFLUX_MCP_IDENTITY__IS_TEST=$ID_TEST")
fi
if [[ ${#EXTRA_ENV[@]} -gt 0 ]]; then SERVER_ENV+=("${EXTRA_ENV[@]}"); fi

# ---------------------------------------------------------------- agent config paths
if [[ $WINDOWS -eq 1 ]]; then
  APPDATA_DIR="$(cygpath -u "${APPDATA:-$HOME/AppData/Roaming}" 2>/dev/null || printf '%s' "${APPDATA:-$HOME/AppData/Roaming}")"
  CLAUDE_DESKTOP_CFG="$APPDATA_DIR/Claude/claude_desktop_config.json"
  GOOSE_CFG="$APPDATA_DIR/Block/goose/config/config.yaml"
elif [[ "$OS" == Darwin ]]; then
  CLAUDE_DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
  GOOSE_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/goose/config.yaml"
else
  CLAUDE_DESKTOP_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/Claude/claude_desktop_config.json"
  GOOSE_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/goose/config.yaml"
fi
CODEX_USER_CFG="${CODEX_HOME:-$HOME/.codex}/config.toml"
CODEX_PROJECT_CFG="$PWD/.codex/config.toml"
GEMINI_USER_CFG="$HOME/.gemini/settings.json"
GEMINI_PROJECT_CFG="$PWD/.gemini/settings.json"
OPENCODE_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"

have() { command -v "$1" >/dev/null 2>&1; }
mask() {
  local s="$*" v
  for v in "$ID_EMAIL" "$ID_USER" "$ID_NAME"; do
    if [[ ${#v} -ge 3 ]]; then s="${s//"$v"/***}"; fi  # shorter values would garble output
  done
  printf '%s' "$s"
}
log()  { printf '%s\n' "$(mask "$*")"; }
say()  { printf '  %s\n' "$(mask "$*")"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$(mask "$*")"; }

run() {
  # Print (with identity masked) and, unless dry-run, execute a command. Its output is
  # masked too, in case an agent CLI echoes the env it stored; pipefail keeps its status.
  say "\$ $*"
  if [[ $DRY_RUN -eq 0 ]]; then
    "$@" 2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do say "$line"; done
  fi
}

# ---------------------------------------------------------------- config editing helper (python)
# edit_config <format> <file> : merges/removes the server entry, preserving everything else.
# format: claude-json | gemini-json | opencode-v1 | opencode-v2 | toml | goose-yaml
# The server env travels in CFG_ENV (an environment variable), never on a command line.
edit_config() {
  local format="$1" file
  file="$(editor_path "$2")"
  local env_lines=""
  for kv in "${SERVER_ENV[@]:-}"; do [[ -n "$kv" ]] && env_lines+="$kv"$'\n'; done
  CFG_FORMAT="$format" CFG_FILE="$file" CFG_NAME="$SERVER_NAME" CFG_SERVER="$SERVER_CMD_NATIVE" \
  CFG_ENV="$env_lines" CFG_UNINSTALL="$UNINSTALL" CFG_DRY="$DRY_RUN" \
  "${PY[@]}" - <<'PY'
import json
import os
import re
import shutil
import sys

fmt = os.environ["CFG_FORMAT"]
file = os.environ["CFG_FILE"]
name = os.environ["CFG_NAME"]
server = os.environ["CFG_SERVER"]
uninstall = os.environ["CFG_UNINSTALL"] == "1"
dry = os.environ["CFG_DRY"] == "1"
env = {}
for line in os.environ.get("CFG_ENV", "").split("\n"):
    if "=" in line and line.index("=") > 0:
        k, v = line.split("=", 1)
        env[k] = v
SECRET_KEYS = {"AMERIFLUX_USER_ID", "AMERIFLUX_USER_EMAIL", "AMERIFLUX_USER_NAME"}
IDENTITY_KEYS = SECRET_KEYS | {"AMERIFLUX_INTENDED_USE", "AMERIFLUX_DESCRIPTION", "AMERIFLUX_MCP_IDENTITY__IS_TEST"}
secrets = [v for k, v in env.items() if k in SECRET_KEYS and v]


def masked(text):
    for s in secrets:
        text = text.replace(s, "***")
    return text


exists = os.path.exists(file)
original = open(file, encoding="utf-8").read() if exists else ""


def parse_json(text):
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except ValueError as e:
        print(f"  ! {file} is not plain JSON ({e}). Edit it by hand; see the install guide.", file=sys.stderr)
        sys.exit(3)


def dump(obj):
    return json.dumps(obj, indent=2) + "\n"


def q(s):
    return json.dumps(s)  # TOML basic strings and YAML double-quoted strings share JSON escaping here


if fmt in ("claude-json", "gemini-json"):
    cfg = parse_json(original)
    servers = cfg.setdefault("mcpServers", {})
    if uninstall:
        servers.pop(name, None)
    else:
        entry = {"command": server, "args": []}
        if env:
            entry["env"] = env
        servers[name] = entry
    new = dump(cfg)
elif fmt in ("opencode-v1", "opencode-v2"):
    cfg = parse_json(original)
    cfg.setdefault("$schema", "https://opencode.ai/config.json")
    mcp = cfg.setdefault("mcp", {})
    entry = {"type": "local", "command": [server]}
    if env:
        entry["environment"] = env
    if fmt == "opencode-v2":
        servers = mcp.setdefault("servers", {})
        if uninstall:
            servers.pop(name, None)
        else:
            servers[name] = entry
    elif uninstall:
        mcp.pop(name, None)
    else:
        mcp[name] = {**entry, "enabled": True}
    new = dump(cfg)
elif fmt == "toml":
    # Replace or append the [mcp_servers.<name>] table and its [mcp_servers.<name>.env] sub-table.
    header = f"[mcp_servers.{name}]"
    out, skipping = [], False
    for line in original.split("\n"):
        t = line.strip()
        if t in (header, f"[mcp_servers.{name}.env]"):
            skipping = True
            continue
        if skipping and t.startswith("["):
            skipping = False
        if not skipping:
            out.append(line)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).rstrip()
    if not uninstall:
        block = f"{header}\ncommand = {q(server)}\nargs = []\n"
        if env:
            block += f"\n[mcp_servers.{name}.env]\n" + "\n".join(f"{k} = {q(v)}" for k, v in env.items()) + "\n"
        text = (text + "\n\n" if text else "") + block
    elif text:
        text += "\n"
    new = text
elif fmt == "goose-yaml":
    # Map-style `extensions:` block as written by current Goose releases.
    lines = original.split("\n")
    ext = next((i for i, l in enumerate(lines) if re.match(r"^extensions:\s*$", l)), -1)
    block = [
        f"  {name}:",
        "    enabled: true",
        "    type: stdio",
        f"    name: {name}",
        "    description: \"AmeriFlux and FLUXNET flux tower data: sites, variables, citations and files\"",
        f"    cmd: {q(server)}",
        "    args: []",
        "    envs:" + ("" if env else " {}"),
        *[f"      {k}: {q(v)}" for k, v in env.items()],
        "    env_keys: []",
        "    timeout: 300",
        "    bundled: null",
    ]
    if ext == -1:
        out = "\n".join(lines).rstrip()
        if not uninstall:
            out = (out + "\n" if out else "") + "extensions:\n" + "\n".join(block) + "\n"
        elif out:
            out += "\n"
    else:
        end = ext + 1
        while end < len(lines) and (lines[end] == "" or re.match(r"^\s", lines[end])):
            end += 1
        kept, skipping = [], False
        own = re.compile(rf"^  {re.escape(name)}:\s*$")
        for l in lines[ext + 1 : end]:
            if own.match(l):
                skipping = True
                continue
            if skipping and re.match(r"^  \S", l):
                skipping = False
            if skipping:
                continue
            kept.append(l)
        while kept and kept[-1] == "":
            kept.pop()
        body = kept if uninstall else kept + block
        out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines[: ext + 1] + body + [""] + lines[end:]))
        if not out.endswith("\n"):
            out += "\n"
    new = out
else:
    print(f"unknown format {fmt}", file=sys.stderr)
    sys.exit(2)

if new == original:
    print(f"  = {file} already up to date")
    sys.exit(0)
if uninstall and not exists:
    print(f"  = {file} does not exist; nothing to remove")
    sys.exit(0)
if dry:
    print(f"  ~ would {'remove the entry from' if uninstall else 'write'} {file}{'' if exists else ' (new file)'}:")
    if uninstall:
        shown = f'(entry "{name}" removed; everything else kept)'
    elif fmt == "toml":
        ls = new.split("\n")
        start = next((i for i, l in enumerate(ls) if l.strip() == f"[mcp_servers.{name}]"), 0)
        shown = "\n".join(ls[start:]).rstrip()
    elif fmt == "goose-yaml":
        ls = new.split("\n")
        start = next((i for i, l in enumerate(ls) if l == f"  {name}:"), 0)
        end = start + 1
        while end < len(ls) and ls[end].startswith("    "):
            end += 1
        shown = "\n".join(ls[start:end])
    else:
        cfg = json.loads(new)
        if fmt == "opencode-v2":
            part = {"mcp": {"servers": {name: cfg["mcp"]["servers"][name]}}}
        elif fmt == "opencode-v1":
            part = {"mcp": {name: cfg["mcp"][name]}}
        else:
            part = {"mcpServers": {name: cfg["mcpServers"][name]}}
        shown = json.dumps(part, indent=2) + ("\n(merged into the existing file; other settings kept)" if exists else "")
    print("\n".join("      " + l for l in masked(shown).split("\n")))
else:
    os.makedirs(os.path.dirname(file) or ".", exist_ok=True)
    if exists:
        shutil.copy2(file, file + ".bak")  # keeps the original's (possibly owner-only) mode
        if secrets or any(k in original for k in IDENTITY_KEYS):
            try:
                os.chmod(file + ".bak", 0o600)  # the backup may hold the identity
            except OSError:
                pass
    with open(file, "w", encoding="utf-8") as fh:
        fh.write(new)
    if secrets and not uninstall:
        try:
            os.chmod(file, 0o600)  # the file now holds the download identity
        except OSError:
            pass
    backup = f" (backup: {os.path.basename(file)}.bak)" if exists else ""
    print(f"  \u2714 {'removed from' if uninstall else 'wrote'} {file}{backup}")
PY
}

# ---------------------------------------------------------------- per-agent installers
install_claude() {
  log "Claude Code"
  if have claude && [[ $PREFER_FILES -eq 0 ]]; then
    local scope="$SCOPE"
    if [[ $UNINSTALL -eq 1 ]]; then
      run claude mcp remove --scope "$scope" "$SERVER_NAME" || warn "not registered in scope $scope"
    else
      # `-e` is variadic in the claude CLI, so it must come after the server name.
      local args=(claude mcp add --scope "$scope" "$SERVER_NAME")
      for kv in "${SERVER_ENV[@]:-}"; do [[ -n "$kv" ]] && args+=(-e "$kv"); done
      args+=(-- "$SERVER_CMD_NATIVE")
      if claude mcp get "$SERVER_NAME" >/dev/null 2>&1; then
        say "already registered; replacing"
        [[ $DRY_RUN -eq 0 ]] && claude mcp remove --scope "$scope" "$SERVER_NAME" >/dev/null 2>&1 || true
      fi
      run "${args[@]}"
    fi
  else
    warn "claude CLI not found; install Claude Code, then run: claude mcp add --scope user $SERVER_NAME -- $SERVER_CMD_NATIVE"
  fi
}

install_claude_desktop() {
  log "Claude Desktop ($CLAUDE_DESKTOP_CFG)"
  if [[ $SCOPE == project ]]; then say "Claude Desktop has no project scope; writing user config"; fi
  edit_config claude-json "$CLAUDE_DESKTOP_CFG"
  [[ $UNINSTALL -eq 0 && $DRY_RUN -eq 0 ]] && say "restart Claude Desktop to load the server"
  return 0
}

install_codex() {
  local cfg="$CODEX_USER_CFG"; [[ $SCOPE == project ]] && cfg="$CODEX_PROJECT_CFG"
  log "Codex CLI ($cfg)"
  if have codex && [[ $PREFER_FILES -eq 0 && $SCOPE == user ]]; then
    if [[ $UNINSTALL -eq 1 ]]; then
      run codex mcp remove "$SERVER_NAME" || warn "not registered"
    else
      local args=(codex mcp add "$SERVER_NAME")
      for kv in "${SERVER_ENV[@]:-}"; do [[ -n "$kv" ]] && args+=(--env "$kv"); done
      args+=(-- "$SERVER_CMD_NATIVE")
      if codex mcp get "$SERVER_NAME" >/dev/null 2>&1; then
        say "already registered; replacing"
        [[ $DRY_RUN -eq 0 ]] && codex mcp remove "$SERVER_NAME" >/dev/null 2>&1 || true
      fi
      run "${args[@]}"
    fi
  else
    edit_config toml "$cfg"
  fi
}

install_gemini() {
  local cfg="$GEMINI_USER_CFG"; [[ $SCOPE == project ]] && cfg="$GEMINI_PROJECT_CFG"
  log "Gemini CLI ($cfg)"
  if have gemini && [[ $PREFER_FILES -eq 0 ]]; then
    if [[ $UNINSTALL -eq 1 ]]; then
      run gemini mcp remove --scope "$SCOPE" "$SERVER_NAME" || warn "not registered in scope $SCOPE"
    else
      local args=(gemini mcp add --scope "$SCOPE" --transport stdio)
      for kv in "${SERVER_ENV[@]:-}"; do [[ -n "$kv" ]] && args+=(-e "$kv"); done
      args+=("$SERVER_NAME" "$SERVER_CMD_NATIVE")
      run "${args[@]}"
    fi
  else
    edit_config gemini-json "$cfg"
  fi
}

install_goose() {
  log "Goose ($GOOSE_CFG)"
  if [[ $SCOPE == project ]]; then say "Goose has no project scope; writing user config"; fi
  edit_config goose-yaml "$GOOSE_CFG"
  [[ $UNINSTALL -eq 0 && $DRY_RUN -eq 0 ]] && say "restart Goose (Desktop) or start a new session (CLI) to load the extension"
  return 0
}

install_opencode() {
  local cfg
  if [[ $SCOPE == project ]]; then
    cfg="$PWD/opencode.json"; [[ -f "$PWD/opencode.jsonc" ]] && cfg="$PWD/opencode.jsonc"
  else
    cfg="$OPENCODE_USER_DIR/opencode.json"; [[ -f "$OPENCODE_USER_DIR/opencode.jsonc" ]] && cfg="$OPENCODE_USER_DIR/opencode.jsonc"
  fi
  # OpenCode 2.x nests servers under mcp.servers; 1.x keys them directly under mcp.
  local fmt="opencode-v2"
  if have opencode; then
    local major; major="$(opencode --version 2>/dev/null | grep -oE '[0-9]+' | head -1 || true)"
    [[ -n "$major" && "$major" -lt 2 ]] && fmt="opencode-v1"
  fi
  log "OpenCode ($cfg, ${fmt#opencode-} schema)"
  edit_config "$fmt" "$cfg"
}

# ---------------------------------------------------------------- choose agents
detect_agents() {
  local found=()
  have claude && found+=(claude)
  [[ -f "$CLAUDE_DESKTOP_CFG" || -d "$(dirname "$CLAUDE_DESKTOP_CFG")" ]] && found+=(claude-desktop)
  { have codex || [[ -f "$CODEX_USER_CFG" ]]; } && found+=(codex)
  { have gemini || [[ -f "$GEMINI_USER_CFG" ]]; } && found+=(gemini)
  { have goose || [[ -f "$GOOSE_CFG" ]]; } && found+=(goose)
  { have opencode || [[ -d "$OPENCODE_USER_DIR" ]]; } && found+=(opencode)
  printf '%s\n' "${found[@]:-}"
}

ALL_AGENTS=(claude claude-desktop codex gemini goose opencode)
if [[ -z "$AGENTS" ]]; then
  SELECTED=()
  while IFS= read -r a; do [[ -n "$a" ]] && SELECTED+=("$a"); done < <(detect_agents)
  if [[ ${#SELECTED[@]} -eq 0 ]]; then
    echo "No supported agents detected. Use --agents to pick from: ${ALL_AGENTS[*]}" >&2
    exit 1
  fi
  log "Detected agents: ${SELECTED[*]}"
elif [[ "$AGENTS" == all ]]; then
  SELECTED=("${ALL_AGENTS[@]}")
else
  IFS=',' read -r -a SELECTED <<<"$AGENTS"
fi

log "Server: $SERVER_NAME -> $SERVER_CMD_NATIVE"
if [[ $UNINSTALL -eq 0 ]]; then
  [[ -n "${SERVER_VERSION:-}" ]] && log "Version: $SERVER_VERSION"
  if [[ -n "$ID_USER" ]]; then
    log "Download identity: stored in each agent's server env (sent to site PIs only when you confirm a download)"
    if [[ " ${EXTRA_ENV[*]:-} " != *" AMERIFLUX_MCP_DOWNLOADS__ENABLED=true "* ]]; then
      log "Downloads: off (the default); add --env AMERIFLUX_MCP_DOWNLOADS__ENABLED=true to offer the download tool"
    fi
  else
    log "Download identity: not stored; everything except downloads works without it (see --with-identity)"
  fi
fi
[[ $DRY_RUN -eq 1 ]] && log "(dry run: nothing will be written)"
[[ $UNINSTALL -eq 1 ]] && log "(uninstall mode)"
echo

FAILED=()
for agent in "${SELECTED[@]}"; do
  case "$agent" in
    claude)         install_claude ;;
    claude-desktop) install_claude_desktop ;;
    codex)          install_codex ;;
    gemini)         install_gemini ;;
    goose)          install_goose ;;
    opencode)       install_opencode ;;
    *) warn "unknown agent '$agent' (choose from: ${ALL_AGENTS[*]})"; FAILED+=("$agent") ;;
  esac || FAILED+=("$agent")
  echo
done

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "Finished with problems for: ${FAILED[*]}" >&2
  exit 1
fi
if [[ $UNINSTALL -eq 0 && $DRY_RUN -eq 0 ]]; then
  log "Done. Restart desktop apps, then ask your agent to \"call amf_ping\"."
fi
