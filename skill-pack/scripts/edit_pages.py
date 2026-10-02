#!/usr/bin/env python3
r"""iWork Studio — .pages (Pages) operations (preflight / read / body ops).

preflight   : TCC + template-chooser check — ONE prompt, never retries.
read        : body text (AppleScript readback) + docx export paragraphs.
replace-all : verified body op 1 — find/replace across the whole body text.
set-body    : verified body op 2 — replace the ENTIRE body text.
              Use '-' as the text to read it from stdin (handles long bodies).

Anything richer than these two ops is general Pages authoring, REJECTED at
design — the library raises PagesOutOfScopeError. Do not bypass.

All AppleScript routes need an interactive Aqua session (headless = hard
fail with guidance, SC4). Run `preflight` first; a -1712 means a human must
dismiss a modal / approve TCC ONCE — never retry in a loop.

Examples:
  edit_pages.py preflight
  edit_pages.py read letter.pages
  edit_pages.py replace-all letter.pages "old line" "new line"
  edit_pages.py set-body letter.pages "Full replacement body"
  edit_pages.py set-body letter.pages - < body.txt
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

from iwork_studio import pages_io  # noqa: E402


def _emit(obj: dict, code: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="iWork Studio .pages ops")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight", help="TCC/template-chooser check (one prompt, no retry)")

    p_read = sub.add_parser("read", help="body text + docx paragraph model")
    p_read.add_argument("path")

    p_rep = sub.add_parser("replace-all", help="verified body op 1")
    p_rep.add_argument("path")
    p_rep.add_argument("find")
    p_rep.add_argument("replace")
    p_rep.add_argument("--backup-dir", default=None)

    p_set = sub.add_parser("set-body", help="verified body op 2 ('-' = read stdin)")
    p_set.add_argument("path")
    p_set.add_argument("text", help="new body text, or '-' for stdin")
    p_set.add_argument("--backup-dir", default=None)

    args = ap.parse_args()

    if args.cmd == "preflight":
        try:
            return _emit(pages_io.preflight(), 0)
        except Exception as exc:
            return _emit({"error": f"{type(exc).__name__}: {exc}"}, 1)

    if args.cmd == "read":
        if not os.path.exists(args.path):
            return _emit({"error": f"file not found: {args.path}"}, 1)
        try:
            return _emit(pages_io.read_pages(args.path), 0)
        except Exception as exc:
            return _emit({"error": f"{type(exc).__name__}: {exc}"}, 1)

    if args.cmd == "replace-all":
        try:
            result = pages_io.edit_pages_body(
                args.path, args.find, args.replace, mode="replace_all",
                backup_dir=args.backup_dir)
            return _emit(result, 0)
        except pages_io.PagesOutOfScopeError as exc:
            return _emit({"error": f"PagesOutOfScopeError: {exc}",
                          "hint": "general Pages authoring is out of scope "
                                  "(out of scope by design); only replace_all and "
                                  "set_body are verified"}, 1)
        except Exception as exc:
            return _emit({"error": f"{type(exc).__name__}: {exc}"}, 1)

    if args.cmd == "set-body":
        text = sys.stdin.read() if args.text == "-" else args.text
        try:
            result = pages_io.edit_pages_body(
                args.path, mode="set_body", new_body=text,
                backup_dir=args.backup_dir)
            return _emit(result, 0)
        except pages_io.PagesOutOfScopeError as exc:
            return _emit({"error": f"PagesOutOfScopeError: {exc}",
                          "hint": "general Pages authoring is out of scope "
                                  "(out of scope by design); only replace_all and "
                                  "set_body are verified"}, 1)
        except Exception as exc:
            return _emit({"error": f"{type(exc).__name__}: {exc}"}, 1)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())