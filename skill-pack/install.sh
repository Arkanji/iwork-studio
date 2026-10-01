#!/bin/bash
# iWork Studio — skill installer.
# Assembles the installed skill at ~/.hermes/skills/iwork-studio/ from this
# skill-pack/ directory PLUS a vendored copy of the library (src/iwork_studio)
# so the skill is self-contained. Re-run after any library change.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"          # .../iwork-studio/skill-pack
REPO="$(cd "$HERE/.." && pwd)"                # .../iwork-studio
DEST="${HERMES_HOME:-$HOME/.hermes}/skills/iwork-studio"

echo "Installing iwork-studio skill -> $DEST"
rm -rf "$DEST"
mkdir -p "$DEST"

# SKILL.md + scripts + references (verbatim)
cp "$HERE/SKILL.md" "$DEST/SKILL.md"
cp -R "$HERE/scripts" "$DEST/scripts"
cp -R "$HERE/references" "$DEST/references"
chmod +x "$DEST/scripts/"*.py "$DEST/scripts/save_paths.sh"

# vendored library copy (self-contained skill; scripts fall back to repo src)
mkdir -p "$DEST/src"
cp -R "$REPO/src/iwork_studio" "$DEST/src/iwork_studio"
find "$DEST/src" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf "$DEST/src/iwork_studio/__pycache__" || true

echo "Installed. Files:"
find "$DEST" -type f | sort
echo
echo "Smoke test (demo create):"
"$DEST/scripts/edit_numbers.py" demo --out /tmp/iwork_skill_install_test.numbers