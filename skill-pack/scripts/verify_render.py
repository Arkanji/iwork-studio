#!/usr/bin/env python3
r"""iWork Studio — render verification for any iWork file.

Opens the file in its native app (Numbers/Keynote/Pages) via AppleScript,
exports a PDF, and asserts the PyMuPDF text layer contains the expected
fragment (ligature-aware for Arabic — 'الاسم' extracts as 'االسسم'-style
visual order; the matcher tolerates lam-alef split + bidi, never passes a
wrong-language render as OK).

This is the proof loop: 'file saved' is never evidence; the rendered PDF's
visible text is. Needs an interactive Aqua session (headless = hard fail).

Usage:
  verify_render.py <file> --assert-text "expected visible text" [--pages N]
  verify_render.py <file> --assert-text "تقديري"            # Arabic, ligature-aware

NOTE on Arabic fragments: the matcher is ligature-aware but bidi visual
order reorders WORDS in extracted text layers ('فقرة أولى' extracts as
'أولى فقرة'). Use SINGLE Arabic WORDS (or Latin fragments) for assertions
— same guidance as the Phase B/D evidence baselines.
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

from iwork_studio import pages_io, render_verify  # noqa: E402


def _emit(obj: dict, code: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="iWork Studio render-verify")
    ap.add_argument("path", help=".numbers / .key / .pages file")
    ap.add_argument("--assert-text", required=True,
                    help="text the rendered PDF's text layer must contain")
    ap.add_argument("--pages", type=int, default=None,
                    help="expected page/slide count (default: skip count check)")
    ap.add_argument("--keep-pdf", default=None,
                    help="copy the exported PDF here (evidence artifact)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        return _emit({"error": f"file not found: {args.path}"}, 1)
    ext = os.path.splitext(args.path)[1].lower()

    try:
        if ext == ".numbers":
            result = render_verify.verify_render(
                args.path, args.assert_text,
                expected_pages=args.pages or 1, keep_pdf=args.keep_pdf)
        elif ext == ".key":
            from iwork_studio import keynote_applescript
            result = keynote_applescript.verify_render(
                args.path, args.assert_text,
                expected_slides=args.pages, keep_pdf=args.keep_pdf)
        elif ext == ".pages":
            result = pages_io.verify_render(
                args.path, args.assert_text,
                expected_pages=args.pages, keep_pdf=args.keep_pdf)
        else:
            return _emit({"error": f"unsupported extension {ext!r}"}, 2)
        return _emit(result, 0)
    except Exception as exc:
        return _emit({"error": f"{type(exc).__name__}: {exc}",
                      "hint": "AppleScript routes need an interactive Aqua "
                              "session; a -1712 means a modal needs dismissing "
                              "once (run edit_pages.py preflight for Pages)"},
                     1)


if __name__ == "__main__":
    raise SystemExit(main())