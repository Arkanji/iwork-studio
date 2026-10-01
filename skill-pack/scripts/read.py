#!/usr/bin/env python3
"""iWork Studio — read any .numbers / .key / .pages file into a JSON model.

Routes (capability matrix):
  .numbers -> iwork_studio.numbers_io.read_numbers  (pure parser, no GUI)
  .key     -> iwork_studio.keynote_io.read_key      (pure parser, no GUI)
  .pages   -> iwork_studio.pages_io.read_pages      (AppleScript — needs Aqua)

Output: one JSON object on stdout (UTF-8). Exit 0 on success.
"""
from __future__ import annotations

import os
import sys

# ── pinned-venv bootstrap ────────────────────────────────────────────────────
_VENV_PY = os.path.expanduser("~/.hermes/iwork-venv/.venv/bin/python")
if os.path.exists(_VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(_VENV_PY):
    os.execv(_VENV_PY, [_VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
# installed skill layout: vendored package sits next to scripts/
# repo layout: package lives in <repo>/src
sys.path.insert(0, _SKILL_DIR)
# installed-skill layout: vendored package at <skill>/src
# repo layout: package at <repo>/src (skill-pack/scripts sits two levels under repo)
sys.path.insert(0, os.path.join(os.path.dirname(_SKILL_DIR), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_SKILL_DIR)), "src"))

import json  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: read.py <file.numbers|.key|.pages>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    if not os.path.exists(path):
        print(json.dumps({"error": f"file not found: {path}"}, ensure_ascii=False))
        return 1
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".numbers":
            from iwork_studio import numbers_io
            model = numbers_io.read_numbers(path)
        elif ext == ".key":
            from iwork_studio import keynote_io
            model = keynote_io.read_key(path)
        elif ext == ".pages":
            from iwork_studio import pages_io
            model = pages_io.read_pages(path)
        else:
            print(json.dumps(
                {"error": f"unsupported extension {ext!r} — expected .numbers/.key/.pages"},
                ensure_ascii=False))
            return 2
        print(json.dumps(model, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # fail loud with the domain error class
        print(json.dumps(
            {"error": f"{type(exc).__name__}: {exc}",
             "hint": "AppleScript routes need an interactive Aqua session (headless = hard fail, SC4)"
             if "Aqua" in type(exc).__name__ else None},
            ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())