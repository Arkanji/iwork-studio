#!/usr/bin/env python3
"""Probe — observe the Keynote slide ops on a live Mac.

Run on the Mac (logged-in GUI session, Keynote installed and not showing a
dialog), from the repo root:

    uv run python scripts/probe_keynote_slides.py
    uv run python scripts/probe_keynote_slides.py --allow-creator-studio   # Creator-Studio-only Mac

Each op runs on a fresh throwaway copy of tests/fixtures/arabic.key (in a temp
folder, never your files) through the full write protocol: backup → app op →
in-place save → re-read → expectation gate → parser gate → rollback on failure.

Keynote opens and closes on screen while it runs. The first run may ask
"Terminal wants to control Keynote" — click OK.

A step that hangs (e.g. the save dialog Creator Studio is reported to show)
is abandoned after --timeout seconds, rolled back, and the probe stops so
Keynote isn't hit again while stuck.

Results are INTERNAL: ~/.iwork-studio/probes/keynote_slides.json (outside the
repo, never committed, no hostname or user name). An op that PASSES may be
added to keynote_slides.VERIFIED_OPS. An op that FAILS proved the gate works.
"""

from __future__ import annotations

import argparse
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

FIXTURE = REPO / "tests" / "fixtures" / "arabic.key"
OUT = Path.home() / ".iwork-studio" / "probes" / "keynote_slides.json"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Live probe of Keynote slide ops")
    ap.add_argument("--allow-creator-studio", action="store_true",
                    help="probe 'Keynote Creator Studio' when it is the only Keynote installed")
    ap.add_argument("--timeout", type=int, default=90,
                    help="seconds before a stuck Keynote call is abandoned (default 90)")
    args = ap.parse_args()
    if args.allow_creator_studio:
        os.environ["IWORK_STUDIO_ALLOW_CREATOR_STUDIO"] = "1"

    from iwork_studio import keynote_io, keynote_slides as ks
    from iwork_studio.apps import CreatorStudioUnverifiedError, app_bundle_candidates, app_name

    try:
        keynote = app_name("Keynote")
    except CreatorStudioUnverifiedError:
        print("Only 'Keynote Creator Studio' is installed on this Mac.\n"
              "Re-run with --allow-creator-studio to probe it (throwaway copies only):\n\n"
              "    uv run python scripts/probe_keynote_slides.py --allow-creator-studio\n")
        return 2
    ks.APP_TIMEOUT = args.timeout

    try:
        version = subprocess.run(["osascript", "-e", f'version of application "{keynote}"'],
                                 capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        version = f"unknown ({exc})"

    def two_distinct_slides(f):
        # slide 2 = copy of slide 1 marked with a note, so order is observable
        ks.duplicate_slide(f, 1)
        ks.set_presenter_notes(f, 2, "B")

    # (label, op, setup, action) — the rollback check compares against the
    # deck as it was AFTER setup, i.e. right before the action under test.
    probes = [
        ("notes", "notes", None, lambda f: ks.set_presenter_notes(f, 1, "ملاحظات المتحدث — speaker notes")),
        ("skip", "skip", None, lambda f: ks.set_skipped(f, 1, True)),
        ("duplicate", "duplicate", None, lambda f: ks.duplicate_slide(f, 1)),
        ("add-end", "add", None, lambda f: ks.add_slide(f)),
        ("add-front", "add", None, lambda f: ks.add_slide(f, after=0)),
        ("move", "move", two_distinct_slides, lambda f: ks.move_slide(f, 2, 1)),
        ("delete", "delete", two_distinct_slides, lambda f: ks.delete_slide(f, 1)),
    ]
    results = {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "macos": platform.mac_ver()[0],
        "keynote_app": keynote,
        "keynote_bundles": app_bundle_candidates("Keynote"),
        "keynote_version": version,
        "parser_version": keynote_io.KEYPAD_VERSION,
        "timeout_s": args.timeout,
        "probes": [],
    }
    print(f"Probing {keynote} {version} — Keynote will open and close on screen.\n")

    stuck = False
    for label, op, setup, run in probes:
        if stuck:
            results["probes"].append({"probe": label, "op": op, "status": "SKIPPED", "error": "Keynote stuck on an earlier step"})
            print(f"{label:10s} SKIPPED  (Keynote stuck on an earlier step)")
            continue
        with tempfile.TemporaryDirectory(prefix=f"probe-{op}-") as tmp:
            f = Path(tmp) / "probe.key"
            shutil.copy2(FIXTURE, f)
            entry = {"probe": label, "op": op}
            sha_before = None
            try:
                if setup:
                    setup(f)
                sha_before = _sha(f)
                entry["slides_before"] = len(ks.read_slides(f))
                entry["result"] = {k: v for k, v in run(f).items() if k not in ("file", "backup")}
                inv = ks.read_slides(f)
                entry["slides_after"] = len(inv)
                entry["inventory_after"] = inv
                entry["status"] = "PASS"
            except subprocess.TimeoutExpired:
                stuck = True
                entry["status"] = "HANG"
                entry["error"] = (f"Keynote did not answer within {args.timeout}s — likely a dialog "
                                  "on screen (Creator Studio save bug?). Dismiss it in Keynote.")
                entry["rolled_back_byte_exact"] = sha_before is not None and _sha(f) == sha_before
            except Exception as exc:  # noqa: BLE001
                entry["status"] = "FAIL"
                entry["error"] = f"{type(exc).__name__}: {exc}"
                entry["traceback"] = traceback.format_exc()[-2000:].replace(str(Path.home()), "~")
                entry["rolled_back_byte_exact"] = (_sha(f) == sha_before) if sha_before else "setup failed"
            results["probes"].append(entry)
            extra = ""
            if entry["status"] != "PASS":
                extra = f"  rolled back: {entry.get('rolled_back_byte_exact')}\n           {entry.get('error', '')[:600]}"
            print(f"{label:10s} {entry['status']}{extra}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    passed = [p["probe"] for p in results["probes"] if p["status"] == "PASS"]
    print(f"\nPASS {len(passed)}/{len(probes)}: {passed}")
    print("Full results (internal, not in the repo): ~/.iwork-studio/probes/keynote_slides.json")
    return 0 if len(passed) == len(probes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
