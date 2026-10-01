#!/usr/bin/env python3
r"""iWork Studio — .key (Keynote) operations (read / replace).

read    : full text model as JSON (slides -> texts, plus schema_hash).
replace : find/replace across the deck via keynote-parser at the IWA/YAML
          level, under the AtomicSwap protocol (backup -> tmp -> re-parse ->
          schema-hash + text-change gates -> atomic swap -> manifest).
          \r-aware (Keynote paragraph separator) and \u06xx escape-aware.
          Refuses chart decks (GATE-CHART); files open/locked in Keynote
          raise FileLockedError -> use the AppleScript fallback route
          (iwork_studio.keynote_applescript.applescript_edit_text).

Examples:
  edit_key.py read deck.key
  edit_key.py replace deck.key "old text" "نص جديد"
  edit_key.py replace deck.key "colou?r" "color" --regex
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# ── pinned-venv bootstrap ────────────────────────────────────────────────────
_VENV_PY = os.path.expanduser("~/.hermes/iwork-venv/.venv/bin/python")
if os.path.exists(_VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(_VENV_PY):
    os.execv(_VENV_PY, [_VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SKILL_DIR)
# installed-skill layout: vendored package at <skill>/src
# repo layout: package at <repo>/src (skill-pack/scripts sits two levels under repo)
sys.path.insert(0, os.path.join(os.path.dirname(_SKILL_DIR), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_SKILL_DIR)), "src"))

from iwork_studio import keynote_io  # noqa: E402


def _emit(obj: dict, code: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="iWork Studio .key ops")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser("read", help="read text model as JSON")
    p_read.add_argument("path")

    p_rep = sub.add_parser("replace", help="deck-wide find/replace (AtomicSwap)")
    p_rep.add_argument("path")
    p_rep.add_argument("find")
    p_rep.add_argument("replace")
    p_rep.add_argument("--regex", action="store_true",
                       help="treat find as a regex (default: literal)")
    p_rep.add_argument("--backup-dir", default=None)

    args = ap.parse_args()

    if args.cmd == "read":
        if not os.path.exists(args.path):
            return _emit({"error": f"file not found: {args.path}"}, 1)
        return _emit(keynote_io.read_key(args.path), 0)

    if args.cmd == "replace":
        try:
            result = keynote_io.edit_text(
                args.path, args.find, args.replace,
                regex=args.regex, backup_dir=args.backup_dir,
            )
            return _emit(result, 0)
        except keynote_io.FileLockedError as exc:
            return _emit({"error": f"FileLockedError: {exc}",
                          "hint": "file is open in Keynote; close it and retry, "
                                  "or use the AppleScript fallback route "
                                  "(iwork_studio.keynote_applescript.applescript_edit_text)"},
                         1)
        except Exception as exc:
            return _emit({"error": f"{type(exc).__name__}: {exc}"}, 1)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())