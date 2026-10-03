"""iWork Studio — Numbers formatting (file-level, no app needed).

Column widths / row heights, number formats, cell styles (font, size, bold,
italic, underline, strikethrough, colours, alignment, wrap), borders, header
rows/columns, merges — via numbers-parser 4.19.

Every op rides the same protected write (`_protected_write`):
  1. GATE-CHART refusal; target sheet/table + range resolved and bounds-checked
  2. snapshot of the WHOLE document (every cell's value, formula, style,
     format, border; every table's widths, heights, headers, merges)
  3. versioned backup
  4. mutate a fresh Document, save to a temp file in the same directory
  5. re-open the temp file and compare with the snapshot:
       - every cell's value and formula unchanged (formatting never edits data)
       - only the declared aspects of the declared cells may differ
       - every other table is identical
       - the requested formatting reads back exactly
  6. os.replace (atomic) — on any mismatch the target is untouched

Field note (probe, numbers-parser 4.19): assigning attributes on `cell.style`
in place is silently NOT saved. Styles are therefore applied by deriving a new
named style from the cell's current style plus the requested overrides.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from numbers_parser import RGB, Border, Document
from numbers_parser.cell import CURRENCIES, NegativeNumberStyle

from iwork_studio.numbers_io import (
    CellRefError,
    ChartRefusalError,
    WriteVerificationError,
    _parse_ref,
    _prune_backups,
    _resolve_cell,
    _versioned_backup,
    contains_charts,
)

__all__ = [
    "set_dimensions",
    "set_number_format",
    "set_cell_style",
    "set_borders",
    "set_headers",
    "merge_cells",
    "read_layout",
    "FormatError",
]


class FormatError(ValueError):
    """Bad formatting request (unknown option, out of range, unsafe merge…)."""


_STYLE_FIELDS = (
    "alignment", "bg_color", "font_color", "font_size", "font_name", "bold", "italic",
    "strikethrough", "underline", "first_indent", "left_indent", "right_indent",
    "text_inset", "text_wrap",
)
_SIDES = ("top", "right", "bottom", "left")
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
_NEGATIVE = {
    "minus": NegativeNumberStyle.MINUS,
    "red": NegativeNumberStyle.RED,
    "parentheses": NegativeNumberStyle.PARENTHESES,
    "red_parentheses": NegativeNumberStyle.RED_AND_PARENTHESES,
}
_FORMATS = {"number", "currency", "percentage", "scientific", "fraction", "datetime", "text"}
_HALIGN = {"auto", "left", "center", "right", "justify"}
_VALIGN = {"top", "middle", "bottom"}


# ── helpers ───────────────────────────────────────────────────────────────────


def _rgb(value: str) -> RGB:
    m = _HEX.match(value or "")
    if not m:
        raise FormatError(f"colour {value!r} must be hex like #1A7F79")
    h = m.group(1)
    return RGB(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _hex(c: Any) -> str | None:
    if c is None:
        return None
    if isinstance(c, list):  # gradient fill
        return ",".join(_hex(x) or "" for x in c)
    return f"#{c.r:02x}{c.g:02x}{c.b:02x}" if hasattr(c, "r") else str(c)


def _cells_in(range_ref: str, num_rows: int, num_cols: int) -> list[tuple[int, int]]:
    parts = range_ref.replace(" ", "").upper().split(":")
    if len(parts) not in (1, 2):
        raise FormatError(f"bad range {range_ref!r}; use 'B2' or 'B2:D9'")
    r1, c1 = _parse_ref(parts[0])
    r2, c2 = _parse_ref(parts[-1])
    r1, r2 = sorted((r1, r2))
    c1, c2 = sorted((c1, c2))
    if r2 >= num_rows or c2 >= num_cols:
        raise CellRefError(f"range {range_ref!r} is outside the table ({num_rows} rows × {num_cols} cols)")
    return [(r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]


def _col_index(col: str | int) -> int:
    if isinstance(col, int):
        return col
    s = str(col).strip().upper()
    if s.isdigit():
        return int(s) - 1
    _, c = _parse_ref(f"{s}1")
    return c


def _style_snap(style: Any) -> dict | None:
    if style is None:
        return None
    out = {}
    for f in _STYLE_FIELDS:
        v = getattr(style, f, None)
        if f == "alignment" and v is not None:
            v = (getattr(v.horizontal, "name", None), getattr(v.vertical, "name", None))
        elif f in ("font_color", "bg_color"):
            v = _hex(v)
        out[f] = v
    return out


def _border_snap(cell: Any) -> dict | None:
    b = getattr(cell, "border", None)
    if b is None:
        return None
    out = {}
    for side in _SIDES:
        s = getattr(b, side, None)
        out[side] = None if s is None else (round(float(s.width), 3), _hex(s.color), getattr(s.style, "name", str(s.style)).lower())
    return out


def _cell_snap(cell: Any) -> dict:
    v = cell.value
    if hasattr(v, "isoformat"):
        v = v.isoformat()
    try:
        fv = cell.formatted_value
    except Exception:  # noqa: BLE001
        fv = None
    return {
        "value": v,
        "formula": cell.formula if cell.is_formula else None,
        "style": _style_snap(cell.style),
        "format": (type(cell).__name__, None if fv is None else str(fv)),
        "border": _border_snap(cell),
    }


def _table_snap(tb: Any) -> dict:
    return {
        "cells": {(r, c): _cell_snap(tb.cell(r, c)) for r in range(tb.num_rows) for c in range(tb.num_cols)},
        "widths": [tb.col_width(c) for c in range(tb.num_cols)],
        "heights": [tb.row_height(r) for r in range(tb.num_rows)],
        "headers": (tb.num_header_rows, tb.num_header_cols),
        "merges": sorted(str(m) for m in tb.merge_ranges),
        "shape": (tb.num_rows, tb.num_cols),
    }


def _doc_snap(doc: Document) -> dict:
    snap = {}
    for i in range(len(doc.sheets)):
        sh = doc.sheets[i]
        for j in range(len(sh.tables)):
            tb = sh.tables[j]
            snap[(sh.name, tb.name)] = _table_snap(tb)
    return snap


def read_layout(path: str | os.PathLike, *, sheet: str | None = None, table: str | None = None) -> dict:
    """Read-only formatting inspection of one table: widths, heights, headers,
    merges, and per-cell style / number format / borders."""
    doc = Document(str(path))
    sh, tb = _resolve_cell(doc, sheet, table)
    snap = _table_snap(tb)
    cells = []
    for (r, c), s in sorted(snap["cells"].items()):
        ref = f"{_col_letters(c)}{r + 1}"
        entry = {"ref": ref, "value": s["value"], "type": s["format"][0], "shown_as": s["format"][1]}
        if s["formula"]:
            entry["formula"] = s["formula"]
        if s["style"]:
            st = dict(s["style"])
            al = st.pop("alignment", None)
            if al:
                st["align"], st["valign"] = (al[0] or "").lower(), (al[1] or "").lower()
            entry["style"] = {k: v for k, v in st.items() if v not in (None, False, 0, 0.0)}
        if s["border"] and any(s["border"].values()):
            entry["border"] = {k: v for k, v in s["border"].items() if v}
        cells.append(entry)
    return {
        "file": str(Path(path).resolve()),
        "sheet": sh.name,
        "table": tb.name,
        "columns": {_col_letters(c): w for c, w in enumerate(snap["widths"])},
        "rows": {str(r + 1): h for r, h in enumerate(snap["heights"])},
        "header_rows": snap["headers"][0],
        "header_columns": snap["headers"][1],
        "merged": snap["merges"],
        "cells": cells,
    }


def _col_letters(c: int) -> str:
    s = ""
    c += 1
    while c:
        c, rem = divmod(c - 1, 26)
        s = chr(65 + rem) + s
    return s


# ── the protected write ───────────────────────────────────────────────────────


def _protected_write(
    path: str | os.PathLike,
    sheet: str | None,
    table: str | None,
    op: str,
    plan: Callable[[Document, Any], dict],
    *,
    backup_dir: str | os.PathLike | None = None,
    max_backups: int = 10,
    structural: bool = False,
) -> dict:
    """`plan(doc, table)` mutates and returns:
       {"cells": {aspect: set((r,c))}, "layout": set(keys), "check": fn(table_after) -> None, "summary": dict}
    aspects: style / format / border / value(never) ; layout keys: widths/heights/headers/merges.
    structural=True (row/column insert/delete): the target table's cells move, so
    its per-cell comparison is left to `check`; every other table is still compared."""
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    if contains_charts(target):
        raise ChartRefusalError(f"GATE-CHART: {target.name} contains charts; formatting writes are refused")

    before = _doc_snap(Document(str(target)))
    bdir = Path(backup_dir) if backup_dir else target.parent / f"{target.name}.backups"

    doc = Document(str(target))
    sh, tb = _resolve_cell(doc, sheet, table)
    key = (sh.name, tb.name)
    spec = plan(doc, tb)  # validates + mutates; raises FormatError before any backup

    backup = _versioned_backup(target, bdir)
    _prune_backups(bdir, max_backups)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.fmt", suffix=".numbers")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        doc.save(str(tmp))
        after_doc = Document(str(tmp))
        after = _doc_snap(after_doc)
        if set(after) != set(before):
            raise WriteVerificationError("sheets/tables changed — refusing swap")
        for k in before:
            if k != key and after[k] != before[k]:
                raise WriteVerificationError(f"table {k[1]!r} on sheet {k[0]!r} changed collaterally — refusing swap")
        b, a = before[key], after[key]
        if structural:
            _, tb_after = _resolve_cell(after_doc, sh.name, tb.name)
            spec["check"](tb_after)
            os.replace(tmp, target)
            return {"ok": True, "file": str(target), "op": op, "sheet": sh.name, "table": tb.name,
                    "backup": str(backup), **spec.get("summary", {})}
        if a["shape"] != b["shape"]:
            raise WriteVerificationError("table size changed — refusing swap")
        allowed = spec.get("cells", {})
        for rc, cb in b["cells"].items():
            ca = a["cells"][rc]
            ref = f"{_col_letters(rc[1])}{rc[0] + 1}"
            if (ca["value"], ca["formula"]) != (cb["value"], cb["formula"]):
                raise WriteVerificationError(f"{ref}: value/formula changed ({cb['value']!r} → {ca['value']!r}) — refusing swap")
            for aspect in ("style", "format", "border"):
                if ca[aspect] != cb[aspect] and rc not in allowed.get(aspect, set()):
                    raise WriteVerificationError(f"{ref}: {aspect} changed outside the requested cells — refusing swap")
        for lk in ("widths", "heights", "headers", "merges"):
            if a[lk] != b[lk] and lk not in spec.get("layout", set()):
                raise WriteVerificationError(f"{lk} changed unexpectedly — refusing swap")
        _, tb_after = _resolve_cell(after_doc, sh.name, tb.name)
        spec["check"](tb_after)
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return {"ok": True, "file": str(target), "op": op, "sheet": sh.name, "table": tb.name,
            "backup": str(backup), **spec.get("summary", {})}


# ── ops ───────────────────────────────────────────────────────────────────────


def set_dimensions(path, *, columns: dict | None = None, rows: dict | None = None,
                   sheet: str | None = None, table: str | None = None, **kw) -> dict:
    """columns: {"A": 120, "C": 80}; rows: {"1": 32} (1-based). Points, 1–2000."""
    if not columns and not rows:
        raise FormatError("give columns and/or rows")

    def plan(doc, tb):
        want_c = {}
        for k, v in (columns or {}).items():
            c = _col_index(k)
            if not 0 <= c < tb.num_cols:
                raise CellRefError(f"column {k!r} is outside the table ({tb.num_cols} columns)")
            want_c[c] = _size(v)
        want_r = {}
        for k, v in (rows or {}).items():
            r = int(k) - 1
            if not 0 <= r < tb.num_rows:
                raise CellRefError(f"row {k!r} is outside the table ({tb.num_rows} rows)")
            want_r[r] = _size(v)
        for c, w in want_c.items():
            tb.col_width(c, w)
        for r, h in want_r.items():
            tb.row_height(r, h)

        def check(t):
            for c, w in want_c.items():
                if t.col_width(c) != w:
                    raise WriteVerificationError(f"column {_col_letters(c)} width reads {t.col_width(c)}, wanted {w}")
            for r, h in want_r.items():
                if t.row_height(r) != h:
                    raise WriteVerificationError(f"row {r + 1} height reads {t.row_height(r)}, wanted {h}")

        layout = ({"widths"} if want_c else set()) | ({"heights"} if want_r else set())
        return {"layout": layout, "check": check,
                "summary": {"columns": {_col_letters(c): w for c, w in want_c.items()},
                            "rows": {str(r + 1): h for r, h in want_r.items()}}}

    return _protected_write(path, sheet, table, "set_dimensions", plan, **kw)


def _size(v) -> int:
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        raise FormatError(f"size {v!r} must be a number of points") from None
    if not 1 <= n <= 2000:
        raise FormatError(f"size {n} out of range 1–2000 points")
    return n


def set_number_format(path, cells: str, format: str, *, decimal_places: int | None = None,
                      thousands_separator: bool | None = None, negative_style: str | None = None,
                      currency_code: str | None = None, accounting: bool | None = None,
                      date_format: str | None = None,
                      sheet: str | None = None, table: str | None = None, **kw) -> dict:
    """format: number | currency | percentage | scientific | fraction | datetime | text."""
    fmt = (format or "").lower()
    if fmt not in _FORMATS:
        raise FormatError(f"format {format!r} not one of {sorted(_FORMATS)}")
    opts: dict = {}
    if decimal_places is not None:
        if not 0 <= int(decimal_places) <= 15:
            raise FormatError("decimal_places must be 0–15")
        opts["decimal_places"] = int(decimal_places)
    if thousands_separator is not None:
        opts["show_thousands_separator"] = bool(thousands_separator)
    if negative_style is not None:
        if negative_style not in _NEGATIVE:
            raise FormatError(f"negative_style must be one of {sorted(_NEGATIVE)}")
        opts["negative_style"] = _NEGATIVE[negative_style]
    if fmt == "currency":
        code = (currency_code or "").upper()
        if code not in CURRENCIES:
            raise FormatError(f"currency_code {currency_code!r} is not an ISO 4217 code numbers supports (e.g. SAR, USD, EUR)")
        opts["currency_code"] = code
        if accounting is not None:
            opts["use_accounting_style"] = bool(accounting)
    if fmt == "datetime":
        if not date_format:
            raise FormatError('datetime needs date_format, e.g. "d MMM yyyy"')
        opts["date_time_format"] = date_format

    def plan(doc, tb):
        targets = _cells_in(cells, tb.num_rows, tb.num_cols)
        before = {rc: _cell_snap(tb.cell(*rc))["format"][1] for rc in targets}
        for r, c in targets:
            tb.set_cell_formatting(r, c, fmt, **opts)

        def check(t):
            for rc in targets:
                if _cell_snap(t.cell(*rc))["format"][1] is None and before[rc] is not None:
                    raise WriteVerificationError(f"{_col_letters(rc[1])}{rc[0] + 1}: formatted value lost")

        shown = {f"{_col_letters(c)}{r + 1}": None for r, c in targets}
        return {"cells": {"format": set(targets), "style": set(targets)}, "check": check,
                "summary": {"cells": cells, "format": fmt, "options": {k: str(v) for k, v in opts.items()},
                            "_shown": shown}}

    result = _protected_write(path, sheet, table, "set_number_format", plan, **kw)
    # report what the user will now see
    doc = Document(result["file"])
    _, tb = _resolve_cell(doc, result["sheet"], result["table"])
    result["now_shown_as"] = {ref: _cell_snap(tb.cell(*_parse_ref(ref)))["format"][1] for ref in result.pop("_shown")}
    return result


def set_cell_style(path, cells: str, *, font_name: str | None = None, font_size: float | None = None,
                   bold: bool | None = None, italic: bool | None = None, underline: bool | None = None,
                   strikethrough: bool | None = None, font_color: str | None = None,
                   fill_color: str | None = None, align: str | None = None, valign: str | None = None,
                   wrap: bool | None = None, sheet: str | None = None, table: str | None = None, **kw) -> dict:
    """Change only the given style attributes of every cell in `cells`; all
    other attributes of those cells, and every other cell, stay as they are."""
    over: dict = {}
    if font_name is not None:
        over["font_name"] = str(font_name)
    if font_size is not None:
        if not 4 <= float(font_size) <= 400:
            raise FormatError("font_size must be 4–400 pt")
        over["font_size"] = float(font_size)
    for k, v in (("bold", bold), ("italic", italic), ("underline", underline),
                 ("strikethrough", strikethrough), ("text_wrap", wrap)):
        if v is not None:
            over[k] = bool(v)
    if font_color is not None:
        over["font_color"] = _rgb(font_color)
    if fill_color is not None:
        over["bg_color"] = _rgb(fill_color)
    if align is not None and align.lower() not in _HALIGN:
        raise FormatError(f"align must be one of {sorted(_HALIGN)}")
    if valign is not None and valign.lower() not in _VALIGN:
        raise FormatError(f"valign must be one of {sorted(_VALIGN)}")
    if not over and align is None and valign is None:
        raise FormatError("nothing to change — give at least one style attribute")

    def plan(doc, tb):
        targets = _cells_in(cells, tb.num_rows, tb.num_cols)
        for r, c in targets:
            cur = tb.cell(r, c).style
            kwargs = {f: getattr(cur, f) for f in _STYLE_FIELDS if getattr(cur, f, None) is not None}
            kwargs.update(over)
            if align is not None or valign is not None:
                from numbers_parser import Alignment

                h = align.lower() if align else (cur.alignment.horizontal.name.lower())
                v = valign.lower() if valign else (cur.alignment.vertical.name.lower())
                kwargs["alignment"] = Alignment("justified" if h == "justify" else h, v)
            new = doc.add_style(name=f"iws-{uuid.uuid4().hex[:10]}", **kwargs)
            tb.set_cell_style(r, c, new)

        def check(t):
            for r, c in targets:
                got = _style_snap(t.cell(r, c).style) or {}
                for f, v in over.items():
                    want = _hex(v) if f in ("font_color", "bg_color") else v
                    if got.get(f) != want:
                        raise WriteVerificationError(
                            f"{_col_letters(c)}{r + 1}: {f} reads {got.get(f)!r}, wanted {want!r}")
                al = got.get("alignment") or (None, None)
                if align is not None and (al[0] or "").lower() != ("justified" if align.lower() == "justify" else align.lower()):
                    raise WriteVerificationError(f"{_col_letters(c)}{r + 1}: align reads {al[0]!r}")
                if valign is not None and (al[1] or "").lower() != valign.lower():
                    raise WriteVerificationError(f"{_col_letters(c)}{r + 1}: valign reads {al[1]!r}")

        changed = sorted(list(over) + (["align"] if align else []) + (["valign"] if valign else []))
        return {"cells": {"style": set(targets)}, "check": check,
                "summary": {"cells": cells, "changed": changed}}

    return _protected_write(path, sheet, table, "set_cell_style", plan, **kw)


def set_borders(path, cells: str, *, sides: str | list[str] = "all", width: float = 1.0,
                color: str = "#000000", style: str = "solid",
                sheet: str | None = None, table: str | None = None, **kw) -> dict:
    """sides: all | outline | inner | top/right/bottom/left (or a list). style: solid | dashes | dots | none."""
    if style not in ("solid", "dashes", "dots", "none"):
        raise FormatError("style must be solid, dashes, dots or none")
    if not 0 <= float(width) <= 20:
        raise FormatError("width must be 0–20 pt")
    border = Border(float(width), _rgb(color), style)

    def plan(doc, tb):
        targets = _cells_in(cells, tb.num_rows, tb.num_cols)
        rows = sorted({r for r, _ in targets})
        cols = sorted({c for _, c in targets})
        r0, r1, c0, c1 = rows[0], rows[-1], cols[0], cols[-1]
        mode = sides if isinstance(sides, str) else None
        wanted: list[tuple[int, int, str]] = []
        for r, c in targets:
            if mode == "all":
                ss = list(_SIDES)
            elif mode == "outline":
                ss = [s for s, edge in (("top", r == r0), ("bottom", r == r1), ("left", c == c0), ("right", c == c1)) if edge]
            elif mode == "inner":
                ss = [s for s, inner in (("top", r > r0), ("bottom", r < r1), ("left", c > c0), ("right", c < c1)) if inner]
            else:
                ss = [sides] if isinstance(sides, str) else list(sides)
                bad = [s for s in ss if s not in _SIDES]
                if bad:
                    raise FormatError(f"unknown side(s) {bad}; use all, outline, inner or {list(_SIDES)}")
            wanted += [(r, c, s) for s in ss]
        for r, c, s in wanted:
            tb.set_cell_border(r, c, s, border)
        # a shared edge belongs to both neighbours
        touched = set()
        for r, c, s in wanted:
            touched.add((r, c))
            nr, nc = {"top": (r - 1, c), "bottom": (r + 1, c), "left": (r, c - 1), "right": (r, c + 1)}[s]
            if 0 <= nr < tb.num_rows and 0 <= nc < tb.num_cols:
                touched.add((nr, nc))

        def check(t):
            for r, c, s in wanted:
                b = _border_snap(t.cell(r, c)) or {}
                got = b.get(s)
                if style == "none":
                    continue
                if not got or got[1] != _hex(border.color) or abs(got[0] - float(width)) > 0.01:
                    raise WriteVerificationError(f"{_col_letters(c)}{r + 1} {s} border reads {got!r}")

        return {"cells": {"border": touched}, "check": check,
                "summary": {"cells": cells, "sides": sides, "edges_set": len(wanted)}}

    return _protected_write(path, sheet, table, "set_borders", plan, **kw)


def set_headers(path, *, header_rows: int | None = None, header_columns: int | None = None,
                sheet: str | None = None, table: str | None = None, **kw) -> dict:
    if header_rows is None and header_columns is None:
        raise FormatError("give header_rows and/or header_columns")

    def plan(doc, tb):
        if header_rows is not None:
            if not 0 <= int(header_rows) <= min(5, tb.num_rows):
                raise FormatError(f"header_rows must be 0–{min(5, tb.num_rows)}")
            tb.num_header_rows = int(header_rows)
        if header_columns is not None:
            if not 0 <= int(header_columns) <= min(5, tb.num_cols):
                raise FormatError(f"header_columns must be 0–{min(5, tb.num_cols)}")
            tb.num_header_cols = int(header_columns)

        def check(t):
            if header_rows is not None and t.num_header_rows != int(header_rows):
                raise WriteVerificationError(f"header rows read {t.num_header_rows}")
            if header_columns is not None and t.num_header_cols != int(header_columns):
                raise WriteVerificationError(f"header columns read {t.num_header_cols}")

        # header rows restyle cells in the app's rendering only; data/styles must not change
        return {"layout": {"headers"}, "check": check,
                "summary": {"header_rows": header_rows, "header_columns": header_columns}}

    return _protected_write(path, sheet, table, "set_headers", plan, **kw)


def merge_cells(path, cells: str, *, sheet: str | None = None, table: str | None = None, **kw) -> dict:
    """Merge a rectangular range. Refused if any cell other than the top-left
    holds data (merging would hide it) or if the range crosses the header edge."""

    def plan(doc, tb):
        targets = _cells_in(cells, tb.num_rows, tb.num_cols)
        if len(targets) < 2:
            raise FormatError("a merge needs at least two cells")
        anchor = targets[0]
        hidden = [f"{_col_letters(c)}{r + 1}" for r, c in targets[1:] if tb.cell(r, c).value not in (None, "")]
        if hidden:
            raise FormatError(f"merging would hide data in {hidden}; clear those cells first")
        rows = {r for r, _ in targets}
        cols = {c for _, c in targets}
        hr, hc = tb.num_header_rows, tb.num_header_cols
        if (hr and min(rows) < hr <= max(rows)) or (hc and min(cols) < hc <= max(cols)):
            raise FormatError("the range crosses the header edge; Numbers can't merge across it")
        if any(tb.cell(*rc).is_merged for rc in targets):
            raise FormatError("part of the range is already merged")
        tb.merge_cells(cells.replace(" ", "").upper())

        def check(t):
            if not t.cell(*anchor).is_merged:
                raise WriteVerificationError("merge did not take effect")

        return {"layout": {"merges"}, "cells": {"style": set(targets), "format": set(targets), "border": set(targets)},
                "check": check, "summary": {"merged": cells.upper()}}

    return _protected_write(path, sheet, table, "merge_cells", plan, **kw)
