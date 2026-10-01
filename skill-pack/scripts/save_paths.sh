#!/bin/bash
# iWork Studio — shared AppleScript save-path helpers (GATE-SAVE).
#
# Ground truth (verified, evidence/a3 + Phase B/C/D):
#   - `save in <arbitrary path>`  → DENIED by the iWork app sandbox. Never use.
#   - in-place `save` (no path)   → VERIFIED WORKING for Numbers, Keynote, Pages
#                                  (file must already exist on disk).
#   - `export ... as ...`         → the safe route for artifacts (PDF, docx).
#
# Source this file; use the helpers, never raw save-in paths.

# die with a loud message (fail-loud, never silently proceed)
iwork_die() {
  echo "GATE-SAVE: $*" >&2
  exit 1
}

# Assert that a path is inside the file's own directory-family (in-place save
# semantics). The ONLY save forms allowed in this skill are:
#   1. app.open(path) + mutate + app.save(doc)          — in-place, on-disk file
#   2. app.export(doc, {to: Path(out), as: 'PDF'|'Microsoft Word'|…})
# Any `save in <path>` is a bug — iwork_die.
iwork_check_no_save_in() {
  # grep an AppleScript/JXA source for the forbidden pattern
  local script_file="$1"
  if grep -n -i -- "save.*in\|saving in\|save in " "$script_file" >/dev/null 2>&1; then
    iwork_die "'save in <path>' is FORBIDDEN (iWork sandbox denies it). Use in-place save or export."
  fi
}

# Export-to-PDF template (JXA). Usage: iwork_export_pdf <app_name> <src> <out_pdf>
# app_name: 'Keynote' | 'Numbers' | 'Pages'
iwork_export_pdf() {
  local app="$1" src="$2" out="$3"
  osascript -l JavaScript - <<'EOF' "$app" "$src" "$out"
  function run(argv) {
    const [appName, src, out] = argv;
    const app = Application(appName);
    const doc = app.open(Path(src));
    app.export(doc, {to: Path(out), as: 'PDF'});
    app.close(doc, {saving: 'no'});
    return 'ok';
  }
  EOF
}

# Read-back body/text helper (JXA). Usage: iwork_read_body <app_name> <src>
# (Pages: bodyText; kept generic for Keynote text items if needed.)
iwork_read_body() {
  local app="$1" src="$2"
  osascript -l JavaScript - <<'EOF' "$app" "$src"
  function run(argv) {
    const [appName, src] = argv;
    const app = Application(appName);
    const doc = app.open(Path(src));
    const txt = doc.bodyText().toString();
    app.close(doc, {saving: 'no'});
    return txt;
  }
  EOF
}