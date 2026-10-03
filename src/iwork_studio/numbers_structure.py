"""iWork Studio — create Numbers files and change table structure (no app needed).

  create(path, sheets)            new .numbers from data (refuses to overwrite)
  import_csv(csv, path)           CSV → new .numbers (UTF-8 / Arabic safe)
  insert(path, "rows"|"columns")  add rows/columns (at the end, or at a position)
  delete(path, "rows"|"columns")  remove rows/columns
  add_table(path, …)              new table on an existing or new sheet
  create_from_template(src, dst)  copy any iWork document as a starting point

Safety:
  - Every structural change re-reads the saved copy and checks that every
    pre-existing cell kept its value and formula at its expected new position,
    and that every other table is identical — then swaps atomically.
  - numbers-parser does NOT rewrite formula references when rows/columns
    shift. In a table that contains formulas, inserting or deleting anywhere
    but the end is refused (do that in Numbers, which updates references).
"""

from __future__ import annotations

import csv
import io
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from numbers_parser import Document

from iwork_studio.numbers_format import FormatError, _doc_snap, _protected_write
from iwork_studio.numbers_io import WriteVerificationError, read_numbers

__all__ = ["create", "import_csv", "insert", "delete", "add_table", "create_from_template", "StructureError"]

_PLAIN_NUMBER = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")  # ASCII only: Arabic-Indic digits stay text
_MAX = 10000


class StructureError(FormatError):
    """Bad structural request (would break formulas, would overwrite, out of range…)."""


def _clean(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float)):
        return v
    return str(v)


def _verify_new(path: Path, spec: list[dict]) -> None:
    model = read_numbers(path)
    got = {(s["name"], t["name"]): t for s in model["sheets"] for t in s["tables"]}
    for sh in spec:
        for tb in sh["tables"]:
            t = got.get((sh["name"], tb["name"]))
            if t is None:
                raise WriteVerificationError(f"table {tb['name']!r} on {sh['name']!r} missing after save")
            cells = {c["ref"]: c["value"] for c in t["cells"]}
            for r, row in enumerate(tb["rows"]):
                for c, v in enumerate(row):
                    want, have = _clean(v), cells.get(f"R{r + 1}C{c + 1}")
                    if want in (None, "") and have in (None, ""):
                        continue
                    if isinstance(want, float) or isinstance(have, float):
                        if want is None or have is None or abs(float(want) - float(have)) > 1e-12 * max(1.0, abs(float(want))):
                            raise WriteVerificationError(f"{sh['name']}/{tb['name']} R{r + 1}C{c + 1}: {have!r} ≠ {want!r}")
                    elif want != have:
                        raise WriteVerificationError(f"{sh['name']}/{tb['name']} R{r + 1}C{c + 1}: {have!r} ≠ {want!r}")


def _normalise_spec(sheets: list[dict]) -> list[dict]:
    if not sheets:
        raise StructureError("give at least one sheet with one table")
    out, seen = [], set()
    for i, sh in enumerate(sheets, start=1):
        name = str(sh.get("name") or f"Sheet {i}")
        if name in seen:
            raise StructureError(f"duplicate sheet name {name!r}")
        seen.add(name)
        tables = sh.get("tables") or [{"rows": sh.get("rows", [[""]])}]
        tnorm = []
        for j, tb in enumerate(tables, start=1):
            rows = [list(r) for r in (tb.get("rows") or [[""]])]
            nr, nc = len(rows), max((len(r) for r in rows), default=1)
            if nr > _MAX or nc > 1000:
                raise StructureError("table too large (max 10000 rows × 1000 columns)")
            rows = [r + [None] * (nc - len(r)) for r in rows]
            tnorm.append({"name": str(tb.get("name") or f"Table {j}"), "rows": rows,
                          "header_rows": int(tb.get("header_rows", 1 if nr > 1 else 0)),
                          "header_columns": int(tb.get("header_columns", 0))})
        out.append({"name": name, "tables": tnorm})
    return out


def _fill(tb, rows):
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if v not in (None, ""):
                tb.write(r, c, _clean(v))


def create(path, sheets: list[dict]) -> dict:
    """sheets = [{"name": "Sales", "tables": [{"name": "Q1", "rows": [["Region", "Revenue"], ["الرياض", 1200]],
    "header_rows": 1}]}]. Refuses to overwrite an existing file."""
    target = Path(path).resolve()
    if target.suffix.lower() != ".numbers":
        raise StructureError("the new file must end in .numbers")
    if target.exists():
        raise StructureError(f"{target} already exists; choose another name")
    spec = _normalise_spec(sheets)
    first, t0 = spec[0], spec[0]["tables"][0]
    doc = Document(sheet_name=first["name"], table_name=t0["name"],
                   num_header_rows=min(t0["header_rows"], len(t0["rows"])),
                   num_header_cols=min(t0["header_columns"], len(t0["rows"][0])),
                   num_rows=max(len(t0["rows"]), 1), num_cols=max(len(t0["rows"][0]), 1))
    _fill(doc.sheets[0].tables[0], t0["rows"])
    for j, tb in enumerate(first["tables"][1:], start=1):
        t = doc.sheets[0].add_table(tb["name"], num_rows=len(tb["rows"]), num_cols=len(tb["rows"][0]),
                                    num_header_rows=tb["header_rows"], num_header_cols=tb["header_columns"])
        _fill(t, tb["rows"])
    for sh in spec[1:]:
        tb0 = sh["tables"][0]
        doc.add_sheet(sh["name"], tb0["name"], num_rows=len(tb0["rows"]), num_cols=len(tb0["rows"][0]))
        new_sheet = doc.sheets[len(doc.sheets) - 1]
        t = new_sheet.tables[0]
        t.num_header_rows, t.num_header_cols = tb0["header_rows"], tb0["header_columns"]
        _fill(t, tb0["rows"])
        for tb in sh["tables"][1:]:
            t = new_sheet.add_table(tb["name"], num_rows=len(tb["rows"]), num_cols=len(tb["rows"][0]),
                                    num_header_rows=tb["header_rows"], num_header_cols=tb["header_columns"])
            _fill(t, tb["rows"])
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.new", suffix=".numbers")
    os.close(fd)
    try:
        doc.save(tmp)
        _verify_new(Path(tmp), spec)
        if target.exists():
            raise StructureError(f"{target} appeared while creating; not overwriting")
        os.replace(tmp, target)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return {"ok": True, "file": str(target),
            "sheets": [{"name": s["name"], "tables": [{"name": t["name"], "rows": len(t["rows"]),
                                                       "columns": len(t["rows"][0])} for t in s["tables"]]}
                       for s in spec]}


def import_csv(csv_path, path, *, delimiter: str | None = None, header_rows: int = 1,
               sheet: str = "Sheet 1", table: str = "Table 1", numbers: bool = True) -> dict:
    """CSV → new .numbers. Plain numbers (1234, -5.5) become numbers when numbers=True;
    anything else (dates, "$1,234", Arabic-Indic digits) stays text exactly as written."""
    src = Path(csv_path).resolve()
    text = src.read_bytes().decode("utf-8-sig")
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter)]
    if not rows:
        raise StructureError("the CSV is empty")

    def conv(v: str):
        return (float(v) if "." in v else int(v)) if numbers and _PLAIN_NUMBER.match(v.strip() or "x") else v

    data = [[conv(v) for v in r] for r in rows]
    result = create(path, [{"name": sheet, "tables": [{"name": table, "rows": data, "header_rows": header_rows}]}])
    result["imported_rows"] = len(rows)
    result["delimiter"] = delimiter
    return result


def _has_formulas(tb) -> bool:
    return any(tb.cell(r, c).is_formula for r in range(tb.num_rows) for c in range(tb.num_cols))


def _expect_shift(before: dict, axis: str, at: int, count: int, op: str):
    """Map old (r,c) → new (r,c) after inserting/deleting `count` at `at`."""
    def move(rc):
        r, c = rc
        i = r if axis == "rows" else c
        if op == "insert":
            j = i + count if i >= at else i
        else:
            if at <= i < at + count:
                return None
            j = i - count if i >= at + count else i
        return (j, c) if axis == "rows" else (r, j)
    return {rc: move(rc) for rc in before}


def _structural(path, sheet, table, axis: str, op: str, at: int | None, count: int,
                values: list[list] | None, **kw) -> dict:
    if axis not in ("rows", "columns"):
        raise StructureError('what must be "rows" or "columns"')
    if not 1 <= int(count) <= _MAX:
        raise StructureError(f"count must be 1–{_MAX}")

    def plan(doc, tb):
        size = tb.num_rows if axis == "rows" else tb.num_cols
        pos = size if (op == "insert" and at is None) else (int(at) - 1 if at is not None else None)
        if pos is None:
            raise StructureError("delete needs a start position (1-based)")
        if op == "insert" and not 0 <= pos <= size:
            raise StructureError(f"position {at} out of range (1–{size + 1})")
        if op == "delete" and not (0 <= pos and pos + count <= size):
            raise StructureError(f"rows/columns {at}–{pos + count} are outside the table (1–{size})")
        if op == "delete" and count >= size:
            raise StructureError("can't delete every row/column of a table")
        at_end = op == "insert" and pos == size
        if _has_formulas(tb) and not at_end:
            raise StructureError("this table has formulas, and shifting rows/columns here would leave their "
                                 "references pointing at the wrong cells. Do this in Numbers, or append at the end.")
        if list(tb.merge_ranges) and not at_end:
            raise StructureError("this table has merged cells; shifting rows/columns through them is refused. "
                                 "Unmerge first in Numbers, or append at the end.")
        before = {(r, c): (tb.cell(r, c).value, tb.cell(r, c).formula if tb.cell(r, c).is_formula else None)
                  for r in range(tb.num_rows) for c in range(tb.num_cols)}
        mapping = _expect_shift(before, axis, pos, count, op)
        written: dict = {}
        if op == "insert":
            (tb.add_row if axis == "rows" else tb.add_column)(count, None if at_end else pos)
            for i, line in enumerate(values or []):
                for j, v in enumerate(line):
                    if v in (None, ""):
                        continue
                    if i >= count:
                        raise StructureError("more value lines than inserted rows/columns")
                    r, c = (pos + i, j) if axis == "rows" else (j, pos + i)
                    if r >= tb.num_rows or c >= tb.num_cols:
                        raise StructureError("values don't fit the table")
                    tb.write(r, c, _clean(v))
                    written[(r, c)] = _clean(v)
        else:
            (tb.delete_row if axis == "rows" else tb.delete_column)(count, pos)

        def check(t):
            for old, new in mapping.items():
                if new is None:
                    continue
                cell = t.cell(*new)
                got = (cell.value, cell.formula if cell.is_formula else None)
                if got != before[old]:
                    raise WriteVerificationError(f"cell moved from R{old[0] + 1}C{old[1] + 1} to R{new[0] + 1}C{new[1] + 1} "
                                                 f"reads {got!r}, expected {before[old]!r}")
            for (r, c), v in written.items():
                got = t.cell(r, c).value
                if isinstance(v, float) or isinstance(got, float):
                    if got is None or abs(float(got) - float(v)) > 1e-12 * max(1.0, abs(float(v))):
                        raise WriteVerificationError(f"new cell R{r + 1}C{c + 1} reads {got!r}, expected {v!r}")
                elif got != v:
                    raise WriteVerificationError(f"new cell R{r + 1}C{c + 1} reads {got!r}, expected {v!r}")
            expected_size = size + count if op == "insert" else size - count
            got_size = t.num_rows if axis == "rows" else t.num_cols
            if got_size != expected_size:
                raise WriteVerificationError(f"{axis}: {got_size}, expected {expected_size}")

        return {"check": check, "summary": {"what": axis, "op": op, "at": pos + 1, "count": count}}

    out = _protected_write(path, sheet, table, f"{op}_{axis}", plan, structural=True, **kw)
    from iwork_studio.numbers_io import recalc_note

    return {**out, **recalc_note(read_numbers(out["file"]))}


def insert(path, what: str, count: int = 1, at: int | None = None, values: list[list] | None = None,
           *, sheet: str | None = None, table: str | None = None, **kw) -> dict:
    """Insert `count` rows/columns before 1-based position `at` (omit = append at the end).
    `values`: optional lines of values for the new rows (or columns)."""
    return _structural(path, sheet, table, what, "insert", at, count, values, **kw)


def delete(path, what: str, at: int, count: int = 1, *, sheet: str | None = None, table: str | None = None, **kw) -> dict:
    """Delete `count` rows/columns starting at 1-based position `at`. Recoverable via the backup."""
    return _structural(path, sheet, table, what, "delete", at, count, None, **kw)


def add_table(path, table_name: str, rows: list[list], *, sheet: str | None = None, new_sheet: str | None = None,
              header_rows: int = 1, header_columns: int = 0, backup_dir=None, max_backups: int = 10) -> dict:
    """Add a table (with data) to an existing sheet, or to a new sheet `new_sheet`.
    Every existing table is verified unchanged."""
    from iwork_studio.numbers_io import (ChartRefusalError, _prune_backups, _versioned_backup, contains_charts)

    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    if contains_charts(target):
        raise ChartRefusalError(f"GATE-CHART: {target.name} contains charts; writes are refused")
    spec = _normalise_spec([{"name": new_sheet or sheet or "x",
                             "tables": [{"name": table_name, "rows": rows, "header_rows": header_rows,
                                         "header_columns": header_columns}]}])[0]
    tb_spec = spec["tables"][0]
    before = _doc_snap(Document(str(target)))
    doc = Document(str(target))
    names = [doc.sheets[i].name for i in range(len(doc.sheets))]
    if new_sheet:
        if new_sheet in names:
            raise StructureError(f"sheet {new_sheet!r} already exists")
        doc.add_sheet(new_sheet, table_name, num_rows=len(tb_spec["rows"]), num_cols=len(tb_spec["rows"][0]))
        sh = doc.sheets[len(doc.sheets) - 1]
        t = sh.tables[0]
        t.num_header_rows, t.num_header_cols = tb_spec["header_rows"], tb_spec["header_columns"]
    else:
        idx = names.index(sheet) if sheet else 0
        if sheet and sheet not in names:
            raise StructureError(f"no sheet named {sheet!r}; sheets: {names}")
        sh = doc.sheets[idx]
        if table_name in [sh.tables[j].name for j in range(len(sh.tables))]:
            raise StructureError(f"table {table_name!r} already exists on {sh.name!r}")
        t = sh.add_table(table_name, num_rows=len(tb_spec["rows"]), num_cols=len(tb_spec["rows"][0]),
                         num_header_rows=tb_spec["header_rows"], num_header_cols=tb_spec["header_columns"])
    _fill(t, tb_spec["rows"])
    bdir = Path(backup_dir) if backup_dir else target.parent / f"{target.name}.backups"
    backup = _versioned_backup(target, bdir)
    _prune_backups(bdir, max_backups)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.tbl", suffix=".numbers")
    os.close(fd)
    try:
        doc.save(tmp)
        after = _doc_snap(Document(tmp))
        for k, v in before.items():
            if after.get(k) != v:
                raise WriteVerificationError(f"existing table {k[1]!r} on {k[0]!r} changed — refusing swap")
        _verify_new(Path(tmp), [{"name": sh.name, "tables": [tb_spec]}])
        os.replace(tmp, target)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return {"ok": True, "file": str(target), "sheet": sh.name, "table": table_name,
            "rows": len(tb_spec["rows"]), "columns": len(tb_spec["rows"][0]), "backup": str(backup)}


def create_from_template(template, path) -> dict:
    """Start a new document from an existing one (your own template): copy, then check it opens."""
    src, dst = Path(template).resolve(), Path(path).resolve()
    if src.suffix.lower() not in (".numbers", ".key", ".pages"):
        raise StructureError("the template must be a .numbers, .key or .pages document")
    if dst.suffix.lower() != src.suffix.lower():
        raise StructureError(f"the new file must also end in {src.suffix}")
    if dst.exists():
        raise StructureError(f"{dst} already exists; choose another name")
    fd, tmp = tempfile.mkstemp(dir=str(dst.parent), prefix=f".{dst.name}.new", suffix=dst.suffix)
    os.close(fd)
    os.unlink(tmp)
    try:
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, tmp)
        if Path(tmp).is_file() and not zipfile.is_zipfile(tmp):
            raise StructureError("the template is not a valid iWork document")
        if dst.suffix.lower() == ".numbers":
            read_numbers(tmp)
        elif dst.suffix.lower() == ".key":
            from iwork_studio.keynote_io import read_key

            read_key(tmp)
        os.replace(tmp, dst)
    except Exception:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        elif os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return {"ok": True, "file": str(dst), "from_template": str(src)}
