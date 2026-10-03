#!/bin/sh
# iWork Studio — one-line setup for the Claude desktop app (macOS).
#
#   curl -LsSf https://raw.githubusercontent.com/Arkanji/iwork-studio/main/install.sh | sh
#   … | sh -s -- --roots ~/Documents ~/Desktop     # optional: only allow these folders
#
# 1. installs uv (Astral's Python tool runner) if it is missing — no Python install needed
# 2. adds iWork Studio to Claude's config with the absolute uvx path,
#    keeping every other server and backing the config up first
set -eu

if [ "$(uname)" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then
  echo "iWork Studio needs Apple's Command Line Tools (for git). Starting their installer…"
  xcode-select --install || true
  echo "When that finishes, run this command again."
  exit 1
fi

if ! command -v uvx >/dev/null 2>&1; then
  echo "Installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
  export PATH
fi

echo "Adding iWork Studio to the Claude desktop app (first run downloads ~60 MB)…"
uvx --from git+https://github.com/Arkanji/iwork-studio iwork-studio-mcp install "$@"
