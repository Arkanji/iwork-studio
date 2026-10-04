#!/usr/bin/env bash
# Build the Claude Desktop extension (dist/iwork-studio-<version>.mcpb).
# Needs Node (npx). The bundle carries the source + uv.lock; Claude Desktop's uv
# runtime installs the dependencies on first launch.
set -euo pipefail
cd "$(dirname "$0")/.."
version=$(python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp mcpb/manifest.json pyproject.toml uv.lock README.md LICENSE THIRD_PARTY_NOTICES.md PRIVACY.md .python-version "$stage/"
mkdir -p "$stage/src" && cp -R src/iwork_studio "$stage/src/"
find "$stage" -name "__pycache__" -type d -prune -exec rm -rf {} +
[ -f mcpb/icon.png ] && cp mcpb/icon.png "$stage/"
mkdir -p dist
npx -y @anthropic-ai/mcpb validate "$stage/manifest.json"
npx -y @anthropic-ai/mcpb pack "$stage" "dist/iwork-studio-$version.mcpb"
echo "built dist/iwork-studio-$version.mcpb"
