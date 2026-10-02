#!/usr/bin/env python3
"""Probe — observe the Keynote slide ops on a live Mac (pinned iWork).

Run on the Mac (logged-in GUI session, Keynote installed, Keynote NOT showing
a dialog), from the repo root:

    python scripts/probe_keynote_slides.py

Each op runs on a fresh copy of tests/fixtures/arabic.key through the
full write protocol (backup → app op → in-place save → re-read → expectation
gate → parser gate → rollback on failure). Results are INTERNAL: they go to
~/.iwork-studio/probes/ (outside the repo, never committed). An op that
PASSES may be added to keynote_slides.VERIFIED_OPS.
An op that FAILS proved the gate works: the file was rolled back.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
os.environ.pop("IWORK_STUDIO_DISABLE_SLIDE_OPS", None)

from iwork_studio import keynote_io, keynote_slides as ks  # noqa: E402
from iwork_studio.apps import app_name  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "arabic.key"
OUT = Path.home() / ".iwork-studio" / "probes" / "keynote_slides.json"

PROBES = [
    ("notes", lambda f: ks.set_presenter_notes(f, 1, "ملاحظات المتحدث — speaker notes")),
    ("skip", lambda f: ks.set_skipped(f, 1, True)),
    ("duplicate", lambda f: ks.duplicate_slide(f, 1)),
    ("add", lambda f: ks.add_slide(f, after=1)),
    ("move", lambda f: (ks.duplicate_slide(f, 1), ks.move_slide(f, 1, 2))[-1]),
    ("delete", lambda f: (ks.duplicate_slide(f, 1), ks.delete_slide(f, 2))[-1]),
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _keynote_version() -> str:
    try:
        return subprocess.run(
            ["osascript", "-e", f'version of application "{app_name("Keynote")}"'],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"unknown ({exc})"


def main() -> int:
    results = {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "host": platform.node(),
        "macos": platform.mac_ver()[0],
        "keynote_app": app_name("Keynote"),
        "keynote_version": _keynote_version(),
        "parser_version": keynote_io.KEYPAD_VERSION,
        "fixture": str(FIXTURE.relative_to(REPO)),
        "probes": [],
    }
    for op, run in PROBES:
        with tempfile.TemporaryDirectory(prefix=f"probe-g-{op}-") as tmp:
            f = Path(tmp) / "probe.key"
            shutil.copy2(FIXTURE, f)
            sha_before = _sha(f)
            entry = {"op": op}
            try:
                entry["slides_before"] = len(ks.read_slides(f))
                entry["result"] = run(f)
                inv = ks.read_slides(f)
                entry["slides_after"] = len(inv)
                entry["inventory_after"] = inv
                entry["status"] = "PASS"
            except Exception as exc:  # noqa: BLE001
                entry["status"] = "FAIL"
                entry["error"] = f"{type(exc).__name__}: {exc}"
                entry["traceback"] = traceback.format_exc()[-2000:]
                entry["rolled_back_byte_exact"] = _sha(f) == sha_before
            results["probes"].append(entry)
            print(f"{op:10s} {entry['status']}  {entry.get('error', '')}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nresults (internal) → {OUT}")
    passed = [p["op"] for p in results["probes"] if p["status"] == "PASS"]
    print(f"PASS: {passed}\nIf these look right, set VERIFIED_OPS = frozenset({set(passed)!r}) "
          "in src/iwork_studio/keynote_slides.py.")
    return 0 if len(passed) == len(PROBES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
