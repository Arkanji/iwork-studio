#!/usr/bin/env python3
"""Probe — can Keynote's scripting create, fill and style tables on a slide?

Run on the Mac (logged-in GUI session, Keynote installed), from the repo root:

    uv run python scripts/probe_keynote_tables.py

Works on a throwaway copy of tests/fixtures/arabic.key in a temp folder, never
your files. Each step runs in its own try block, so one refusal doesn't hide the
rest. After saving, the copy is reopened to check the table persisted.

Results are INTERNAL: ~/.iwork-studio/probes/keynote_tables.json (outside the
repo, never committed). Printed to stdout too.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
FIXTURE = REPO / "tests" / "fixtures" / "arabic.key"
OUT = Path.home() / ".iwork-studio" / "probes" / "keynote_tables.json"

# Keynote's sandbox refuses AppleScript `open` on a temp path ("can't be opened right
# now. Operation not permitted"), so the deck is opened with JXA, then found by path.
def _jxa_open(app: str, path: Path) -> None:
    js = f"Application({json.dumps(app)}).open(Path({json.dumps(str(path))}));"
    subprocess.run(["osascript", "-l", "JavaScript", "-e", js], capture_output=True, text=True, timeout=180, check=True)


# Each step: (name, AppleScript run inside `tell d`, value returned as text).
STEPS = [
    ("make_table", 'set t to make new table at end of tables of slide 1 with properties '
                   '{row count:4, column count:3}\nreturn (count of tables of slide 1) as text'),
    ("table_props", 'set t to last table of slide 1\nreturn (row count of t as text) & "x" & '
                    '(column count of t as text) & " header rows " & (header row count of t as text)'),
    ("set_text", 'set t to last table of slide 1\nset value of cell 1 of row 1 of t to "Revenue"\n'
                 'return value of cell 1 of row 1 of t'),
    ("set_number", 'set t to last table of slide 1\nset value of cell 2 of row 2 of t to 1250.5\n'
                   'return (value of cell 2 of row 2 of t) as text'),
    ("set_arabic", 'set t to last table of slide 1\nset value of cell 1 of row 2 of t to "الإيرادات"\n'
                   'return value of cell 1 of row 2 of t'),
    ("set_formula", 'set t to last table of slide 1\nset value of cell 2 of row 3 of t to 100\n'
                    'set value of cell 2 of row 4 of t to "=SUM(B2:B3)"\n'
                    'return ((value of cell 2 of row 4 of t) as text) & " | " & (formula of cell 2 of row 4 of t)'),
    ("font", 'set t to last table of slide 1\nset font name of cell 1 of row 1 of t to "Avenir Next"\n'
             'set font size of cell 1 of row 1 of t to 18\n'
             'return (font name of cell 1 of row 1 of t) & " " & ((font size of cell 1 of row 1 of t) as text)'),
    ("text_color", 'set t to last table of slide 1\nset text color of cell 1 of row 1 of t to {65535, 65535, 65535}\n'
                   'return (text color of cell 1 of row 1 of t) as text'),
    ("fill", 'set t to last table of slide 1\nset background color of row 1 of t to {4112, 9252, 18504}\n'
             'return (background color of cell 1 of row 1 of t) as text'),
    ("alignment", 'set t to last table of slide 1\nset alignment of cell 2 of row 2 of t to right\n'
                  'return (alignment of cell 2 of row 2 of t) as text'),
    ("number_format", 'set t to last table of slide 1\nset format of cell 2 of row 2 of t to currency\n'
                      'return ((format of cell 2 of row 2 of t) as text) & " | " & '
                      '(formatted value of cell 2 of row 2 of t)'),
    ("geometry", 'set t to last table of slide 1\nset position of t to {80, 200}\nset width of t to 600\n'
                 'return ((position of t) as text) & " w " & ((width of t) as text) & " h " & ((height of t) as text)'),
    ("header_rows", 'set t to last table of slide 1\nset header row count of t to 1\n'
                    'return (header row count of t) as text'),
    ("add_row", 'set t to last table of slide 1\nset row count of t to 5\nreturn (row count of t) as text'),
    ("delete_table", 'set n to count of tables of slide 1\nmake new table at end of tables of slide 1\n'
                     'delete last table of slide 1\nreturn (n as text) & " → " & ((count of tables of slide 1) as text)'),
]

REREAD = ('set t to last table of slide 1\nreturn ((count of tables of slide 1) as text) & " | " & '
          '(value of cell 1 of row 1 of t) & " | " & (value of cell 1 of row 2 of t) & " | " & '
          '((value of cell 2 of row 4 of t) as text)')


def main() -> int:
    from iwork_studio.apps import app_name

    app = app_name("Keynote")
    tmp = Path(tempfile.mkdtemp(prefix="iws-probe-tables-"))
    deck = tmp / "probe.key"
    shutil.copytree(FIXTURE, deck) if FIXTURE.is_dir() else shutil.copy2(FIXTURE, deck)

    find = """    set d to missing value
    repeat with x in documents
      set fp to ""
      try
        set fp to POSIX path of ((file of x) as alias)
      end try
      if fp ends with "/" then set fp to text 1 thru -2 of fp
      if fp is (item 1 of argv) then
        set d to contents of x
        exit repeat
      end if
    end repeat
    if d is missing value then error "the probe deck isn't open in Keynote" number -10000"""

    def step_script(body: str) -> str:
        inner = "\n".join("      " + ln for ln in body.splitlines())
        return f"""on run argv
  tell application "{app}"
{find}
    tell d
{inner}
    end tell
  end tell
end run"""

    # One osascript per step: a step that doesn't compile (a verb Keynote lacks) or
    # fails is recorded, and the rest still run.
    results: dict = {"app": app, "steps": {}}
    deck = deck.resolve()
    _jxa_open(app, deck)
    for name, body in STEPS:
        r = subprocess.run(["osascript", "-e", step_script(body), str(deck)], capture_output=True, text=True,
                           timeout=120)
        results["steps"][name] = ({"status": "ok", "detail": r.stdout.strip()[:300]} if r.returncode == 0
                                  else {"status": "error", "detail": r.stderr.strip()[:300]})
    save = f"""on run argv
  tell application "{app}"
{find}
    save d
    close d saving no
  end tell
end run"""
    r = subprocess.run(["osascript", "-e", save, str(deck)], capture_output=True, text=True, timeout=120)
    results["save"] = "ok" if r.returncode == 0 else r.stderr.strip()[:300]
    _jxa_open(app, deck)
    r2 = subprocess.run(["osascript", "-e", step_script(REREAD), str(deck)], capture_output=True, text=True, timeout=120)
    results["reopen"] = (r2.stdout or r2.stderr).strip()[:500]
    # Best effort: never leave the probe deck open (only this path; never the user's documents).
    js = ("const a = Application(" + json.dumps(app) + "); a.documents().forEach(d => { try { "
          "if (d.file().toString() === " + json.dumps(str(deck)) + ") a.close(d, {saving: 'no'}); } catch (e) {} });")
    subprocess.run(["osascript", "-l", "JavaScript", "-e", js], capture_output=True, text=True, timeout=60)
    try:
        from iwork_studio import keynote_io
        info = keynote_io.read_key(deck)
        info.pop("path", None)
        results["parser_read"] = json.dumps(info, ensure_ascii=False, default=str)[:800]
    except Exception as exc:  # noqa: BLE001
        results["parser_read"] = f"error: {exc}"[:500]
    shutil.rmtree(tmp, ignore_errors=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results["save"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
