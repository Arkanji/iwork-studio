#!/usr/bin/env python3
"""iWork Studio — .numbers operations (read / edit-cell / demo).

Read      : full semantic model (sheets/tables/cells) as JSON.
edit-cell : AtomicSwap write — backup -> tmp -> re-parse -> semantic gate ->
            atomic swap. Refuses chart files (GATE-CHART). Rolls back on failure.
demo      : create a small Arabic+English demo file via numbers-parser
            (pure Python, no GUI) — doubles as a self-test of the route.

Examples:
  edit_numbers.py read file.numbers
  edit_numbers.py edit-cell file.numbers --ref B3 --value "قيمة جديدة"
  edit_numbers.py edit-cell file.numbers --ref A1 --value 42 --sheet "بيانات" --table "جدول"
  edit_numbers.py demo --out /tmp/demo.numbers
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

from iwork_studio import numbers_io  # noqa: E402


def _emit(obj: dict, code: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="iWork Studio .numbers ops")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser("read", help="read semantic model as JSON")
    p_read.add_argument("path")

    p_edit = sub.add_parser("edit-cell", help="AtomicSwap cell edit")
    p_edit.add_argument("path")
    p_edit.add_argument("--ref", required=True, help="cell ref like A1 or B3")
    p_edit.add_argument("--value", required=True, help="new value (str/int/float parsed)")
    p_edit.add_argument("--sheet", default=None, help="sheet name (needed if >1 sheet)")
    p_edit.add_argument("--table", default=None, help="table name (needed if >1 table)")
    p_edit.add_argument("--backup-dir", default=None)

    p_demo = sub.add_parser("demo", help="create a demo .numbers (route self-test)")
    p_demo.add_argument("--out", required=True, help="output path (.numbers)")

    args = ap.parse_args()

    if args.cmd == "read":
        if not os.path.exists(args.path):
            return _emit({"error": f"file not found: {args.path}"}, 1)
        return _emit(numbers_io.read_numbers(args.path), 0)

    if args.cmd == "edit-cell":
        value: object = args.value
        for cast in (int, float):
            try:
                value = cast(args.value)
                break
            except ValueError:
                continue
        try:
            result = numbers_io.edit_cell(
                args.path,
                args.ref,
                value,
                sheet=args.sheet,
                table=args.table,
                backup_dir=args.backup_dir,
            )
            return _emit(result, 0)
        except Exception as exc:
            return _emit({"error": f"{type(exc).__name__}: {exc}",
                          "rolled_back": True}, 1)

    if args.cmd == "demo":
        import numbers_parser as np
        doc = np.Document()
        table = doc.sheets[0].tables[0]
        table.write(0, 0, "الاسم")
        table.write(0, 1, "Name")
        table.write(1, 0, "أحمد")
        table.write(1, 1, "Demo")
        table.write(2, 1, 3.14)
        out = os.path.abspath(args.out)
        if os.path.exists(out):
            os.remove(out)
        doc.save(out)
        # verify: re-parse and check the Arabic + values survived (GATE-1 semantic)
        model = numbers_io.read_numbers(out)
        cells = {c["ref"]: c["value"]
                 for t in model["sheets"][0]["tables"] for c in t["cells"]}
        checks = {
            "R1C1 == الاسم": cells.get("R1C1") == "الاسم",
            "R2C1 == أحمد": cells.get("R2C1") == "أحمد",
            "R3C2 == 3.14": cells.get("R3C2") == 3.14,
        }
        ok = all(checks.values())
        return _emit({"ok": ok, "path": out, "bytes": os.path.getsize(out),
                      "checks": checks}, 0 if ok else 1)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())