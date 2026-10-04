"""iWork Studio — tables on Keynote slides.

  add_table(path, slide, rows, header_rows=1, kit=None, x=None, y=None, width=None)

Rides the Keynote write protocol (keynote_theme._run): backup → AppleScript in
Keynote → in-place save → re-read every slide → compare → rollback on any mismatch.

Probed on Keynote (Creator Studio): `tell slide n to make new table with properties
{row count, column count, header row count}` works; the `make new table at end of
tables of slide n` form fails (-10000), as does deleting a table — so a failed add
is undone by restoring the backup, never by deleting. Cell values, fonts, text and
fill colours and alignment all read back through JXA, so each one is checked.

With a design kit the table is styled like numbers_apply_design: header band (fill,
heading font, contrast-checked text), body font and colour, alternate-row banding,
number columns right-aligned; Arabic cells get the kit's Arabic fonts.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["add_table", "table_rows_from_numbers", "TableError", "MAX_ROWS", "MAX_COLS"]

MAX_ROWS, MAX_COLS = 50, 15
_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


class TableError(ValueError):
    """Bad table data or placement."""


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf"))


def _normalise(rows) -> list[list]:
    if not isinstance(rows, list) or not rows or not all(isinstance(r, list) for r in rows):
        raise TableError("rows must be a list of rows, each a list of cell values")
    width = max(len(r) for r in rows)
    if width == 0:
        raise TableError("the table has no columns")
    if len(rows) > MAX_ROWS or width > MAX_COLS:
        raise TableError(f"at most {MAX_ROWS} rows × {MAX_COLS} columns on a slide (got {len(rows)} × {width}); "
                         "split it, or show the key rows")
    out = []
    for r in rows:
        row = []
        for v in list(r) + [None] * (width - len(r)):
            if v is None or v == "":
                row.append(None)
            elif _is_num(v):
                row.append(v)
            elif isinstance(v, str):
                row.append(v)
            else:
                raise TableError(f"cell value {v!r}: use text, a number, or null")
        out.append(row)
    return out


def table_rows_from_numbers(src, *, sheet: str | None = None, table: str | None = None,
                            columns: list[str] | None = None, max_rows: int | None = None) -> tuple[list[list], int]:
    """(rows, header_rows) from a Numbers table: header row(s) included, blank rows
    dropped, optionally only the named columns (by header text; the first column stays)."""
    from numbers_parser import Document

    from iwork_studio.numbers_io import _resolve_cell

    p = Path(str(src)).expanduser()
    if p.suffix.lower() != ".numbers" or not p.is_file():
        raise TableError(f"table source {str(src)!r} must be an existing .numbers file")
    try:
        _, tb = _resolve_cell(Document(str(p)), sheet, table)
    except Exception as exc:  # noqa: BLE001
        raise TableError(str(exc)) from exc
    h = max(1, tb.num_header_rows)
    grid = []
    for r in range(tb.num_rows):
        vals = []
        for c in range(tb.num_cols):
            v = tb.cell(r, c).value
            if hasattr(v, "isoformat"):
                v = tb.cell(r, c).formatted_value or v.isoformat()
            elif not (v is None or isinstance(v, str) or _is_num(v)):
                v = tb.cell(r, c).formatted_value or str(v)
            vals.append(v)
        if r >= h and all(v in (None, "") for v in vals):
            continue
        grid.append(vals)
    if columns:
        head = [str(v or "").strip() for v in grid[h - 1]]
        missing = [c for c in columns if c not in head]
        if missing:
            raise TableError(f"columns {missing} not in the table's header: {head[1:]}")
        keep = [0] + [head.index(c) for c in columns if head.index(c) != 0]
        grid = [[row[i] for i in keep] for row in grid]
    if max_rows is not None:
        grid = grid[:h + max(0, int(max_rows))]
    return grid, h


def _as_literal(v) -> str:
    from iwork_studio.app_ops import _as_number

    return _as_number(v)


def _numeric_cols(rows: list[list], h: int) -> set[int]:
    cols = set()
    for c in range(len(rows[0])):
        vals = [r[c] for r in rows[h:] if r[c] is not None]
        if vals and sum(_is_num(v) for v in vals) >= len(vals) / 2:
            cols.add(c)
    return cols


def _style_plan(rows: list[list], h: int, kit: dict) -> dict:
    """Per cell: font, text colour, fill (or None), right-aligned?"""
    from iwork_studio.design import contrast

    c = kit["colors"]
    body_color = c.get("table_text", c["body"] if contrast(c["body"], "#FFFFFF") >= 4.5 else "#0F172A")
    nums = _numeric_cols(rows, h)
    plan = {}
    for r, row in enumerate(rows):
        for col, v in enumerate(row):
            ar = isinstance(v, str) and bool(_ARABIC.search(v))
            if r < h:
                st = {"font": kit["fonts"]["heading_ar" if ar else "heading"], "color": c["header_text"],
                      "fill": c["header_fill"]}
            else:
                st = {"font": kit["fonts"]["body_ar" if ar else "body"], "color": body_color,
                      "fill": c["band"] if (r - h) % 2 == 1 else None}
            st["right"] = col in nums
            plan[(r, col)] = st
    return plan


_READ_TABLE_STYLES = """
  const doc = app.open(Path(params.path));
  const t = doc.slides[params.slide - 1].tables()[params.index];
  const out = t.rows().map(r => r.cells().map(c => {
    const o = {};
    try { o.font = c.fontName(); } catch (e) {}
    try { o.color = c.textColor(); } catch (e) {}
    try { o.fill = c.backgroundColor(); } catch (e) {}
    try { o.align = String(c.alignment()); } catch (e) {}
    return o;
  }));
  let geo = null;
  try { const p = t.position(); geo = {x: p.x, y: p.y, width: t.width(), height: t.height()}; } catch (e) {}
  app.close(doc, {saving: 'no'});
  return JSON.stringify({cells: out, geometry: geo});
"""


def _same_value(want, got) -> bool:
    if want is None:
        return got in (None, "")
    if _is_num(want):
        return _is_num(got) and abs(float(got) - float(want)) <= 1e-9 * max(1.0, abs(float(want)))
    if isinstance(want, str) and want.startswith("="):
        return got not in (None, "")  # a formula: its result is checked to exist, not its value
    return isinstance(got, str) and got == want


def add_table(path, slide: int, rows: list[list], *, header_rows: int = 1, kit=None,
              x: float | None = None, y: float | None = None, width: float | None = None, **kw) -> dict:
    """Add a table to `slide` (1-based). rows = [[header…], [row…], …]: text, numbers, or
    null for empty; text starting with "=" is a formula. kit (name or dict) styles it."""
    from iwork_studio import keynote_slides as ks
    from iwork_studio import keynote_theme as kt

    grid = _normalise(rows)
    nr, nc = len(grid), len(grid[0])
    if not isinstance(header_rows, int) or not 0 <= header_rows < max(nr, 2):
        raise TableError(f"header_rows must be between 0 and {max(nr - 1, 1)}")
    for name, v in (("x", x), ("y", y), ("width", width)):
        if v is not None and not _is_num(v):
            raise TableError(f"{name} must be a number (points)")
    if (x is None) != (y is None):
        raise TableError("give both x and y (points from the slide's top-left), or neither")
    if width is not None and width <= 0:
        raise TableError("width must be positive")
    k = None
    if kit is not None:
        from iwork_studio import design

        k = design.get_kit(kit)
    styles = _style_plan(grid, header_rows, k) if k else {}

    # Values: numbers inline as validated literals, text through argv (never spliced into the script).
    args: list = [slide, nr, nc, header_rows]
    lines = ["        set n to (item 2 of argv) as integer",
             "        tell slide n",
             "          set t to make new table with properties {row count:(item 3 of argv) as integer, "
             "column count:(item 4 of argv) as integer, header row count:(item 5 of argv) as integer, "
             "header column count:0}",
             "        end tell",
             "        tell t"]
    for r, row in enumerate(grid, start=1):
        for c, v in enumerate(row, start=1):
            if v is None:
                continue
            if _is_num(v):
                lines.append(f"          set value of cell {c} of row {r} to {_as_literal(v)}")
            else:
                args.append(v)
                lines.append(f"          set value of cell {c} of row {r} to item {len(args) + 1} of argv")
    if k:
        fonts: dict[str, int] = {}

        def font_arg(f):
            if f not in fonts:
                args.append(f)
                fonts[f] = len(args) + 1
            return f"item {fonts[f]} of argv"

        def rgb(hexcolor):
            return "{" + ", ".join(str(v) for v in kt._rgb16(hexcolor)) + "}"

        for r in range(nr):
            fill = styles[(r, 0)]["fill"]
            if fill:
                lines.append(f"          set background color of row {r + 1} to {rgb(fill)}")
        for (r, c), st in sorted(styles.items()):
            ref = f"cell {c + 1} of row {r + 1}"
            lines.append(f"          set font name of {ref} to {font_arg(st['font'])}")
            lines.append(f"          set text color of {ref} to {rgb(st['color'])}")
            if st["right"]:
                lines.append(f"          set alignment of {ref} to right")
    if x is not None and y is not None:
        lines.append(f"          set position to {{{_as_literal(x)}, {_as_literal(y)}}}")
    if width is not None:
        lines.append(f"          set width to {_as_literal(width)}")
    lines.append("        end tell")
    body = "\n".join(lines)

    def plan(before):
        n = len(before["slides"])
        if not isinstance(slide, int) or not 1 <= slide <= n:
            raise kt.ThemeError(f"slide {slide!r} out of range (deck has {n})")
        if any(s.get("tables") is None for s in before["slides"]):
            raise kt.ThemeError("this Keynote doesn't report slide tables; can't verify, refusing")
        target = Path(path).resolve()

        def expect(b, a):
            kt._same_slide_count(b, a)
            for i, (p, q) in enumerate(zip(b["slides"], a["slides"]), start=1):
                if kt._sig(p) != kt._sig(q) or p.get("images") != q.get("images") or p.get("charts") != q.get("charts"):
                    raise ks.SlideOpVerificationError(f"slide {i} content changed")
                if i != slide and p.get("tables") != q.get("tables"):
                    raise ks.SlideOpVerificationError(f"slide {i}: a table changed")
            old, new = b["slides"][slide - 1]["tables"], a["slides"][slide - 1]["tables"] or []
            if len(new) != len(old) + 1:
                raise ks.SlideOpVerificationError(f"slide {slide} has {len(new)} tables, expected {len(old) + 1}")
            rest = list(new)
            for t in old:  # every table that was there is still there, unchanged
                if t not in rest:
                    raise ks.SlideOpVerificationError(f"slide {slide}: an existing table changed")
                rest.remove(t)
            added = rest[0]
            index = new.index(added)
            if (added["rows"], added["cols"], added["header_rows"]) != (nr, nc, header_rows):
                raise ks.SlideOpVerificationError(
                    f"new table is {added['rows']}×{added['cols']} with {added['header_rows']} header rows, "
                    f"wanted {nr}×{nc} with {header_rows}")
            got = added.get("values")
            if got is None:
                raise ks.SlideOpVerificationError("Keynote didn't report the new table's cells; can't verify")
            for r, row in enumerate(grid):
                for c, want in enumerate(row):
                    if not _same_value(want, got[r][c]):
                        hint = " (Keynote read the text as a number or date; pass numbers as numbers)" \
                            if isinstance(want, str) and not isinstance(got[r][c], str) else ""
                        raise ks.SlideOpVerificationError(
                            f"cell row {r + 1}, column {c + 1} reads {got[r][c]!r}, wanted {want!r}{hint}")
            if k or (x is not None and y is not None) or width is not None:
                st = ks._jxa(_READ_TABLE_STYLES, {"path": str(target), "slide": slide, "index": index})
                for (r, c), w in styles.items():
                    cell = st["cells"][r][c]
                    if not kt._font_eq(cell.get("font"), w["font"]):
                        raise ks.SlideOpVerificationError(
                            f"cell row {r + 1}, column {c + 1}: font reads {cell.get('font')!r}, wanted {w['font']!r} "
                            "(is that font installed on this Mac?)")
                    if not kt._close(kt._color_hex(cell.get("color")), w["color"].lower()):
                        raise ks.SlideOpVerificationError(f"cell row {r + 1}, column {c + 1}: text colour didn't land")
                    if w["fill"] and not kt._close(kt._color_hex(cell.get("fill")), w["fill"].lower()):
                        raise ks.SlideOpVerificationError(f"cell row {r + 1}, column {c + 1}: fill didn't land")
                    if w["right"] and "right" not in str(cell.get("align") or "").lower():
                        raise ks.SlideOpVerificationError(f"cell row {r + 1}, column {c + 1}: not right-aligned")
                geo = st.get("geometry") or {}
                if x is not None and y is not None and (abs(geo.get("x", 1e9) - x) > 1 or abs(geo.get("y", 1e9) - y) > 1):
                    raise ks.SlideOpVerificationError(f"table position reads {geo}, wanted ({x}, {y})")
                if width is not None and abs(geo.get("width", 1e9) - width) > 1:
                    raise ks.SlideOpVerificationError(f"table width reads {geo.get('width')}, wanted {width}")

        return {"applescript": body, "args": args}, {}, expect, {
            "slide": slide, "rows": nr, "columns": nc, "header_rows": header_rows, "kit": k["name"] if k else None}

    return kt._run(path, "add_table", plan, **kw)
