#!/usr/bin/env bash
# Run the live (Mac) test suite unattended — e.g. overnight, or from a local
# Claude Code session. Pulls the latest main, keeps the Mac awake while testing,
# writes a log to ~/.iwork-studio/probes/, and quits the iWork apps the run
# launched (never an app with your own documents open).
#
#   scripts/live.sh                 # full live suite
#   scripts/live.sh -k "tables"     # any extra pytest arguments
set -uo pipefail
cd "$(dirname "$0")/.."

log_dir="$HOME/.iwork-studio/probes"
mkdir -p "$log_dir"
log="$log_dir/live-$(date +%Y%m%d-%H%M%S).log"

git pull --ff-only --quiet || echo "git pull skipped (local changes or offline)" | tee -a "$log"
caffeinate -i uv run --extra test pytest -m aqua -q -rxs "$@" 2>&1 | tee -a "$log"
status=${PIPESTATUS[0]}
ln -sf "$log" "$log_dir/live-latest.log"
echo "log: $log"
exit "$status"
