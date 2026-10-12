#!/usr/bin/env python3
"""Probe — can a chart be added to a Numbers sheet through scripting (no UI scripting)?

Run on the Mac (logged-in GUI session, Numbers installed), from the repo root:

    uv run python scripts/probe_numbers_chart.py

Works on a throwaway copy of the bundled sample (synthetic data), never your files.
Each variant runs on its own, so one refusal doesn't hide the rest. Only the
scripting dictionary is tried: no System Events / menu clicks (out of our safety
model even if they work). After saving, the copy is reopened and charts are counted.

Results are INTERNAL: ~/.iwork-studio/probes/numbers_chart.json (outside the repo,
never committed). Printed to stdout too.
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
SAMPLE = REPO / "src" / "iwork_studio" / "samples" / "sample-sales.numbers"
OUT = Path.home() / ".iwork-studio" / "probes" / "numbers_chart.json"

FIND = """    set d to missing value
    repeat with x in documents
      set fp to ""
      try
        set fp to POSIX path of ((file of x) as alias)
      end try
      if fp is (item 1 of argv) then
        set d to contents of x
        exit repeat
      end if
    end repeat
    if d is missing value then error "the probe file isn't open in Numbers" number -10000"""

# (name, AppleScript run inside `tell d`)
VARIANTS = [
    ("dictionary_has_add_chart", 'return (count of charts of sheet 1) as text'),
    ("add_chart_on_sheet", 'tell sheet 1 to add chart chart type vertical_bar_2d data range range "A1:E5" of table 1 of sheet 1\n'
                           'return (count of charts of sheet 1) as text'),
    ("add_chart_selection", 'set selection range of table 1 of sheet 1 to range "A1:E5" of table 1 of sheet 1\n'
                            'tell sheet 1 to add chart\nreturn (count of charts of sheet 1) as text'),
    ("make_new_chart", 'tell sheet 1 to make new chart\nreturn (count of charts of sheet 1) as text'),
]


def _jxa(js: str) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-l", "JavaScript"], input=js, capture_output=True, text=True, timeout=180)


def main() -> int:
    from iwork_studio.apps import app_name

    app = app_name("Numbers")
    tmp = Path(tempfile.mkdtemp(prefix="iws-probe-chart-"))
    book = (tmp / "probe.numbers").resolve()
    shutil.copy2(SAMPLE, book)
    res: dict = {"app": app, "variants": {}}

    _jxa(f"Application({json.dumps(app)}).open(Path({json.dumps(str(book))}));")
    for name, body in VARIANTS:
        inner = "\n".join("      " + ln for ln in body.splitlines())
        script = f'on run argv\n  tell application "{app}"\n{FIND}\n    tell d\n{inner}\n    end tell\n  end tell\nend run'
        r = subprocess.run(["osascript", "-e", script, str(book)], capture_output=True, text=True, timeout=120)
        res["variants"][name] = ({"status": "ok", "detail": r.stdout.strip()[:300]} if r.returncode == 0
                                 else {"status": "error", "detail": r.stderr.strip()[:300]})
    count = (f"const a = Application({json.dumps(app)}); const d = a.documents().find(x => {{ try {{ return "
             f"x.file().toString() === {json.dumps(str(book))}; }} catch (e) {{ return false; }} }}); ")
    r = _jxa(count + "a.save(d); const n = d.sheets().reduce((s, sh) => s + sh.charts().length, 0); "
                     "a.close(d, {saving: 'no'}); JSON.stringify({charts_after_save: n});")
    res["save"] = (r.stdout or r.stderr).strip()[:300]
    _jxa(f"Application({json.dumps(app)}).open(Path({json.dumps(str(book))}));")
    r = _jxa(count + "const n = d.sheets().reduce((s, sh) => s + sh.charts().length, 0); "
                     "a.close(d, {saving: 'no'}); JSON.stringify({charts_after_reopen: n});")
    res["reopen"] = (r.stdout or r.stderr).strip()[:300]
    _jxa(f"const a = Application({json.dumps(app)}); if (a.running() && a.documents().length === 0) a.quit();")
    shutil.rmtree(tmp, ignore_errors=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
