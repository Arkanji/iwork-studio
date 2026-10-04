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
    ("add_row", 'set t to last table of slide 1\nadd row below row 4 of t\nreturn (row count of t) as text'),
    ("delete_table", 'set n to count of tables of slide 1\nmake new table at end of tables of slide 1\n'
                     'delete last table of slide 1\nreturn (n as text) & " → " & ((count of tables of slide 1) as text)'),
]

REREAD = ('set t to last table of slide 1\nreturn ((count of tables of slide 1) as text) & " | " & '
          '(value of cell 1 of row 1 of t) & " | " & (value of cell 1 of row 2 of t) & " | " & '
          '((value of cell 2 of row 4 of t) as text)')


def _wrap(name: str, body: str) -> str:
    return f"""      try
        set r to my step_{name}(d)
        set out to out & "{name}" & tab & "ok" & tab & r & linefeed
      on error m number n
        set out to out & "{name}" & tab & "error" & tab & (n as text) & " " & m & linefeed
      end try"""


def main() -> int:
    from iwork_studio.apps import app_name

    app = app_name("Keynote")
    tmp = Path(tempfile.mkdtemp(prefix="iws-probe-tables-"))
    deck = tmp / "probe.key"
    shutil.copytree(FIXTURE, deck) if FIXTURE.is_dir() else shutil.copy2(FIXTURE, deck)

    handlers = []
    calls = []
    for name, body in STEPS:
        inner = "\n".join("    " + ln for ln in body.splitlines())
        handlers.append(f'on step_{name}(d)\n  tell application "{app}"\n  tell d\n{inner}\n  end tell\n  end tell\nend step_{name}')
        calls.append(_wrap(name, body))
    script = "\n\n".join(handlers) + f"""

on run argv
  tell application "{app}"
    set d to open (POSIX file (item 1 of argv))
  end tell
  set out to ""
{chr(10).join(calls)}
  tell application "{app}"
    save d
    close d saving no
  end tell
  return out
end run"""
    reread = f"""on run argv
  tell application "{app}"
    set d to open (POSIX file (item 1 of argv))
    try
      tell d
{REREAD}
      end tell
    on error m number n
      close d saving no
      return "error " & (n as text) & " " & m
    end try
  end tell
end run"""
    # REREAD returns from inside the tell, so close happens on the next open; close explicitly after.
    results: dict = {"app": app, "steps": {}}
    r = subprocess.run(["osascript", "-e", script, str(deck)], capture_output=True, text=True, timeout=300)
    results["rc"] = r.returncode
    results["stderr"] = r.stderr.strip()[:800]
    for line in r.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            results["steps"][parts[0]] = {"status": parts[1], "detail": parts[2]}
    r2 = subprocess.run(["osascript", "-e", reread, str(deck)], capture_output=True, text=True, timeout=120)
    results["reopen"] = (r2.stdout or r2.stderr).strip()[:500]
    try:
        from iwork_studio import keynote_io
        results["parser_read"] = json.dumps(keynote_io.read_key(deck), ensure_ascii=False, default=str)[:800]
    except Exception as exc:  # noqa: BLE001
        results["parser_read"] = f"error: {exc}"[:500]
    shutil.rmtree(tmp, ignore_errors=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
