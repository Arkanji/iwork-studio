"""iWork Studio — app-driven ops (macOS + the app + a GUI session).

  numbers_set_formula   put a formula in a cell (Numbers computes it)
  numbers_sort          sort a table's body rows by a column
  pages_placeholders    list / fill template placeholders ("Name", "Date" …)
  keynote_set_transition  slide transition effect / duration / auto-advance
  keynote_add_image     place an image on a slide
  keynote_slideshow     start / stop / next / previous (no file change)
  create_document       new document from one of Apple's built-in templates

Same protocol as every other write: gates → snapshot → backup → op + in-place
save → fresh re-read → expectation check → restore on any mismatch.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from iwork_studio.apps import app_name

__all__ = [
    "set_formula", "sort_table", "list_placeholders", "fill_placeholders", "set_transition",
    "read_tables", "set_table_cells", "recalculate", "add_image", "add_chart", "slideshow", "create_document", "TRANSITIONS", "CHART_TYPES", "AppOpError",
]


class AppOpError(ValueError):
    """Bad request for an app-driven op (unknown effect, bad cell, unknown template…)."""


TRANSITIONS = (
    "no transition effect", "magic move", "dissolve", "fade through color", "move in", "push", "reveal",
    "wipe", "iris", "cube", "doorway", "flip", "flop", "page flip", "reflection", "revolving door", "scale",
    "swap", "swoosh", "twirl", "twist", "blinds", "color planes", "confetti", "drop", "droplet", "fall",
    "grid", "mosaic", "perspective", "pivot", "shimmer", "sparkle", "switch", "clothesline", "fade and move",
    "object cube", "object flip", "object pop", "object push", "object revolve", "object zoom", "swing",
)
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".heic", ".pdf", ".bmp", ".webp"}


def _jxa(kind: str, body: str, params: dict, timeout: int = 300) -> dict:
    from iwork_studio.keynote_slides import _assert_aqua

    _assert_aqua()
    script = ("function run(argv) {\n  const params = JSON.parse(argv[0]);\n"
              f"  const app = Application({json.dumps(app_name(kind))});\n{body}\n}}")
    r = subprocess.run(["osascript", "-l", "JavaScript", "-e", script, json.dumps(params)],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"JXA failed (rc={r.returncode}): {r.stderr.strip()[:500]}")
    return json.loads(r.stdout.strip() or "{}")


_OPEN_CHECK = """
  const already = app.documents().some(d => {
    try { const f = d.file(); return f && f.toString() === params.path; } catch (e) { return false; }
  });
  if (already) return JSON.stringify({open_in_app: true});
"""


def _edit_in_app(kind: str, path: Path, body: str, params: dict) -> dict:
    """open → body (has `doc`) → in-place save → close. Refuses a document already open."""
    out = _jxa(kind, _OPEN_CHECK + "  const doc = app.open(Path(params.path));\n  let result = {};\n  try {\n"
               + body + "\n    app.save(doc);\n  } finally {\n    app.close(doc, {saving: 'no'});\n  }\n"
               "  return JSON.stringify(result);", {"path": str(path), **params})
    if out.get("open_in_app"):
        from iwork_studio.keynote_slides import DocumentOpenError

        raise DocumentOpenError(f"{path.name} is open in {kind}. Save and close it first.")
    return out


def _restore(target: Path, backup: Path) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.rb", suffix=target.suffix)
    os.close(fd)
    shutil.copy2(backup, tmp)
    os.replace(tmp, target)


# ── Numbers (app computes formulas and sorts) ─────────────────────────────────


def _numbers_target(path, sheet, table, *, whole_document: bool = False):
    from numbers_parser import Document

    from iwork_studio import numbers_io as nio

    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    if target.suffix.lower() != ".numbers":
        raise AppOpError(f"{target.name} is not a .numbers file")
    doc = Document(str(target))
    if whole_document:
        return target, doc, None, None
    sh, tb = nio._resolve_cell(doc, sheet, table)
    return target, doc, sh, tb


def _values(doc) -> dict:
    out = {}
    for i in range(len(doc.sheets)):
        sh = doc.sheets[i]
        for j in range(len(sh.tables)):
            tb = sh.tables[j]
            for r in range(tb.num_rows):
                for c in range(tb.num_cols):
                    cell = tb.cell(r, c)
                    v = cell.value
                    out[(sh.name, tb.name, r, c)] = (
                        v.isoformat() if hasattr(v, "isoformat") else v, cell.formula if cell.is_formula else None)
    return out


# Numbers reads operators back in its own symbols (=B2*0.1 → B2×0.1).
_FOPS = str.maketrans({"×": "*", "÷": "/", "≠": "<>", "≤": "<=", "≥": ">=", "−": "-"})


def _fnorm(f: str | None) -> str:
    return re.sub(r"[\s$]", "", (f or "").lstrip("=").translate(_FOPS)).upper()


def _numbers_write(path, sheet, table, op: str, body: str, params: dict, expect, summary: dict,
                   backup_dir=None, max_backups: int = 10, whole_document: bool = False) -> dict:
    from numbers_parser import Document

    from iwork_studio import numbers_io as nio

    target, doc, sh, tb = _numbers_target(path, sheet, table, whole_document=whole_document)
    where = {} if whole_document else {"sheet": sh.name, "table": tb.name}
    before = _values(doc)
    has_charts = nio.contains_charts(target)  # Numbers does the edit itself, so its charts stay linked
    bdir = Path(backup_dir) if backup_dir else target.parent / f"{target.name}.backups"
    backup = nio._versioned_backup(target, bdir)
    nio._prune_backups(bdir, max_backups)
    try:
        out = _edit_in_app("Numbers", target, _COUNT_CHARTS + "    const chartsBefore = countCharts();\n" + body
                           + "    result.charts = [chartsBefore, countCharts()];\n",
                           {**where, **params})
        after_doc = Document(str(target))
        expect(before, _values(after_doc), after_doc)
        if isinstance(out, dict) and out.get("recalculated") is not None:
            summary = {**summary, "recalculated": out["recalculated"]}
        cb, ca = ((out or {}).get("charts") or [None, None])
        if has_charts and (cb is None or ca is None):
            raise nio.WriteVerificationError("this file has charts and Numbers doesn't report them, so the "
                                             "result can't be checked — rolled back")
        if cb != ca:
            raise nio.WriteVerificationError(f"charts went from {cb} to {ca} — rolled back")
    except Exception:
        _restore(target, backup)
        raise
    return {"ok": True, "file": str(target), "op": op, **where, "backup": str(backup), **summary}


_COUNT_CHARTS = """    const countCharts = () => {
      try { return doc.sheets().reduce((n, s) => n + s.charts().length, 0); } catch (e) { return null; }
    };
"""

# Numbers shows a formula's stored result and doesn't recalculate on open, so after
# no-app edits totals can be stale. Re-entering each formula as-is makes Numbers
# recompute it from the current inputs.
_RECALC_ALL = """    let recalculated = 0;
    doc.sheets().forEach(s => s.tables().forEach(t => {
      let fs = [];
      try { fs = t.cells.formula(); } catch (e) {}
      if (!fs.some(f => f)) return;
      const cells = t.cells();
      for (let i = 0; i < fs.length; i++) {
        if (fs[i]) { cells[i].value = fs[i]; recalculated++; }
      }
    }));
    result.recalculated = recalculated;
"""

_NUM_TABLE = """    const sh = doc.sheets.byName(params.sheet);
    const tb = sh.tables.byName(params.table);
"""


def set_formula(path, ref: str, formula: str, *, sheet: str | None = None, table: str | None = None, **kw) -> dict:
    """Put a formula (e.g. "=SUM(B2:B9)") in one cell; Numbers computes it.
    Every other cell's input is checked unchanged (computed results may update)."""
    from iwork_studio import numbers_io as nio

    if not isinstance(formula, str) or not formula.strip().startswith("="):
        raise AppOpError('formula must start with "=" (e.g. "=SUM(B2:B9)")')
    target, doc, sh, tb = _numbers_target(path, sheet, table)
    r, c = nio._parse_ref(ref)
    if not (0 <= r < tb.num_rows and 0 <= c < tb.num_cols):
        raise nio.CellRefError(f"{ref} is outside {tb.name!r} ({tb.num_rows} rows × {tb.num_cols} columns)")
    key = (sh.name, tb.name, r, c)
    from iwork_studio.numbers_format import _col_letters

    a1 = f"{_col_letters(c)}{r + 1}"

    def expect(before, after, after_doc):
        if set(after) != set(before):
            raise nio.WriteVerificationError("table shape changed — rolled back")
        got_formula = after[key][1]
        if got_formula is None:
            raise nio.WriteVerificationError(f"{ref} did not become a formula (reads {after[key][0]!r}) — rolled back")
        if _fnorm(got_formula) != _fnorm(formula):
            raise nio.WriteVerificationError(f"{ref} formula reads {got_formula!r}, wanted {formula!r} — rolled back")
        for k, (v, f) in before.items():
            if k == key:
                continue
            if f is None and after[k][1] is None and after[k][0] != v:
                raise nio.WriteVerificationError(f"{k[1]}!R{k[2] + 1}C{k[3] + 1} changed ({v!r} → {after[k][0]!r})")
            if f is not None and _fnorm(after[k][1]) != _fnorm(f):
                raise nio.WriteVerificationError(f"formula at {k[1]}!R{k[2] + 1}C{k[3] + 1} changed")
            if (f is None) != (after[k][1] is None):
                raise nio.WriteVerificationError(f"{k[1]}!R{k[2] + 1}C{k[3] + 1} changed kind")

    body = _RECALC_ALL + _NUM_TABLE + "    tb.cells.byName(params.ref).value = params.formula;\n"
    out = _numbers_write(path, sheet, table, "set_formula", body,
                         {"ref": a1, "formula": formula.strip()}, expect, {"ref": a1, "formula": formula.strip()}, **kw)
    from numbers_parser import Document

    t2 = nio._resolve_cell(Document(out["file"]), out["sheet"], out["table"])[1]
    out["result"] = t2.cell(r, c).value
    return out


def recalculate(path, **kw) -> dict:
    """Make Numbers recompute every formula from the current values (after no-app edits,
    Numbers keeps showing the old results). Formulas and all other values are checked unchanged."""
    from iwork_studio import numbers_io as nio

    def expect(before, after, after_doc):
        if set(after) != set(before):
            raise nio.WriteVerificationError("table shape changed — rolled back")
        for k, (v, f) in before.items():
            if f is None:
                if after[k][1] is not None or not _same(after[k][0], v):
                    raise nio.WriteVerificationError(f"{k[1]}!R{k[2] + 1}C{k[3] + 1} changed — rolled back")
            elif _fnorm(after[k][1]) != _fnorm(f):
                raise nio.WriteVerificationError(f"formula at {k[1]}!R{k[2] + 1}C{k[3] + 1} changed — rolled back")

    out = _numbers_write(path, None, None, "recalculate", _RECALC_ALL, {}, expect, {}, whole_document=True, **kw)
    return out


# Numbers' sort moves a formula with its row but keeps its references relative, so a
# formula that reads another row (=B2*0.1 below a base figure) ends up reading the
# wrong row or #REF!. Those tables are refused, or sorted as a values-only copy.
_REF = re.compile(
    r"(?:((?:'(?:[^']|'')+'|[^\s()=+\-*/×÷^&<>,:\"']+)(?:\s[^\s()=+\-*/×÷^&<>,:\"']+)*)::)?"
    r"(?<![\w$.])\$?[A-Z]{1,3}(\$?)(\d+)(?::\$?[A-Z]{1,3}(\$?)(\d+))?(?![\w(])")


def _refs(formula: str):
    """(table or None, first row, last row, row is locked) per cell/range reference; rows 0-based."""
    text = re.sub(r'"(?:[^"]|"")*"', '""', formula or "")
    for m in _REF.finditer(text):
        tname = m.group(1)
        if tname:
            tname = tname.strip()
            if tname.startswith("'") and tname.endswith("'"):
                tname = tname[1:-1].replace("''", "'")
        r1 = int(m.group(3)) - 1
        r2 = int(m.group(5)) - 1 if m.group(5) else r1
        yield tname, min(r1, r2), max(r1, r2), bool(m.group(2)) and (not m.group(5) or bool(m.group(4)))


def _cross_row_formulas(tb) -> list[tuple[int, int, str]]:
    """Body-row formulas that read another row of this table, locked ($B$2) or not: a
    sort breaks them. References into other tables survive a sort."""
    out = []
    for r in range(tb.num_header_rows, tb.num_rows):
        for c in range(tb.num_cols):
            cell = tb.cell(r, c)
            if not cell.is_formula:
                continue
            for tname, r1, r2, _locked in _refs(cell.formula):
                if (tname is None or tname == tb.name) and (r1, r2) != (r, r):
                    out.append((r, c, cell.formula))
                    break
    return out


class SortBreaksFormulasError(AppOpError):
    """The table's formulas read other rows; sorting it in place would break them."""


def sort_table(path, column: str, *, descending: bool = False, sheet: str | None = None,
               table: str | None = None, to_new_table: bool = False, new_table_name: str | None = None,
               **kw) -> dict:
    """Sort the table's body rows (header rows stay put) by a column letter.

    to_new_table=True leaves the table as it is and puts a sorted copy of its values
    (no formulas) in a new table on the same sheet; use it when the table's formulas
    read other rows, which an in-place sort would break."""
    from iwork_studio import numbers_io as nio
    from iwork_studio.numbers_format import _col_letters

    target, doc, sh, tb = _numbers_target(path, sheet, table)
    _, c = nio._parse_ref(f"{column}1")
    if not 0 <= c < tb.num_cols:
        raise nio.CellRefError(f"column {column!r} is outside the table ({tb.num_cols} columns)")
    h = tb.num_header_rows
    if tb.num_rows - h < 2:
        raise AppOpError("nothing to sort (fewer than two body rows)")
    if list(tb.merge_ranges):
        raise AppOpError("this table has merged cells; Numbers can't sort it")
    order = "descending" if descending else "ascending"
    if new_table_name is not None and not to_new_table:
        raise AppOpError("new_table_name goes with to_new_table=true")
    if not to_new_table:
        risky = _cross_row_formulas(tb)
        if risky:
            r, cc, f = risky[0]
            raise SortBreaksFormulasError(
                f"{len(risky)} formula(s) in {tb.name!r} read other rows (e.g. {_col_letters(cc)}{r + 1}: ={f}); "
                "sorting the table would break them (#REF! or the wrong rows). Use to_new_table=true for a "
                "sorted copy of the values in a new table, leaving this table, its formulas and charts as they are")

    def rows(vals, name):
        return [tuple(vals[(sh.name, name, r, cc)][0] for cc in range(tb.num_cols)) for r in range(tb.num_rows)]

    def check_sorted(body):
        nums = [row[c] for row in body if isinstance(row[c], (int, float)) and not isinstance(row[c], bool)]
        if nums != sorted(nums, reverse=descending):
            raise nio.WriteVerificationError(f"column {column} is not in {order} order")

    summary = {"column": column.upper(), "order": order, "rows_sorted": tb.num_rows - h}
    if to_new_table:
        if tb.num_cols < 2:
            raise AppOpError("Numbers can't make a one-column table; sort this one in Numbers")
        names = {t.name for s in doc.sheets for t in s.tables}
        if new_table_name is not None:
            name = str(new_table_name).strip()
            if not name or "::" in name:
                raise AppOpError("new_table_name must be a plain table name")
            if name in names:
                raise AppOpError(f"a table named {name!r} already exists; pick another name")
        else:
            name, n = f"{tb.name} sorted", 2
            while name in names:
                name, n = f"{tb.name} sorted {n}", n + 1

        def expect_copy(before, after, after_doc):
            new = {k: v for k, v in after.items() if k[:2] == (sh.name, name)}
            if set(after) - set(new) != set(before):
                raise nio.WriteVerificationError("tables other than the new one changed shape — rolled back")
            for k, (v, f) in before.items():
                if (f is None) != (after[k][1] is None) or (f is None and not _same(after[k][0], v)) \
                        or (f is not None and _fnorm(after[k][1]) != _fnorm(f)):
                    raise nio.WriteVerificationError(f"{k[1]}!R{k[2] + 1}C{k[3] + 1} changed — rolled back")
            t2 = nio._resolve_cell(after_doc, sh.name, name)[1]
            if (t2.num_rows, t2.num_cols) != (tb.num_rows, tb.num_cols) or t2.num_header_rows != h:
                raise nio.WriteVerificationError("the new table's size or header rows don't match — rolled back")
            if any(f for (v, f) in new.values()):
                raise nio.WriteVerificationError("the new table has formulas; it should hold values only — rolled back")
            # a formula's result becomes a plain number in the copy: compare to 12 digits
            def norm(rs):
                return [tuple(float(f"{v:.12g}") if isinstance(v, float) else v for v in r) for r in rs]

            src, cp = norm(rows(after, tb.name)), norm(rows(after, name))
            if cp[:h] != src[:h]:
                raise nio.WriteVerificationError("the new table's header rows don't match — rolled back")
            if Counter(cp[h:]) != Counter(src[h:]):
                raise nio.WriteVerificationError("the new table's rows don't match the table's values — rolled back")
            check_sorted(cp[h:])

        body = _NUM_TABLE + """    if (sh.tables().some(t => t.name() === params.name)) throw new Error('table exists: ' + params.name);
    const nr = tb.rowCount(), nc = tb.columnCount();
    const vals = tb.cells.value();  // row by row
    sh.tables.push(app.Table({name: params.name, rowCount: nr, columnCount: nc}));
    const nt = sh.tables.byName(params.name);
    nt.headerRowCount = params.h;
    try { nt.headerColumnCount = tb.headerColumnCount(); } catch (e) {}
    try { nt.footerRowCount = 0; } catch (e) {}
    const cells = nt.cells();
    vals.forEach((v, i) => { if (v !== null && v !== undefined && v !== '') cells[i].value = v; });
    nt.sort({by: nt.columns[params.col], direction: params.dir});
    try { const p = tb.position(); nt.position = {x: p.x, y: p.y + tb.height() + 40}; } catch (e) {}
"""
        out = _numbers_write(path, sheet, table, "sort", body, {"col": c, "dir": order, "name": name, "h": h},
                             expect_copy, {**summary, "new_table": name, "values_only": True}, **kw)
        out["next"] = (f"{tb.name!r} is unchanged; the sorted values are in {name!r}. To chart them, build a Keynote "
                       f"chart slide from it (keynote_build_deck, chart from this file, table {name!r}).")
        return out

    def expect(before, after, after_doc):
        if set(after) != set(before):
            raise nio.WriteVerificationError("table shape changed — rolled back")
        for k, v in before.items():
            if (k[0], k[1]) != (sh.name, tb.name) and after[k] != v:
                raise nio.WriteVerificationError(f"table {k[1]!r} changed collaterally — rolled back")
        rb, ra = rows(before, tb.name), rows(after, tb.name)
        if ra[:h] != rb[:h]:
            raise nio.WriteVerificationError("header rows changed — rolled back")
        if Counter(ra[h:]) != Counter(rb[h:]):
            raise nio.WriteVerificationError("rows were altered, not just reordered — rolled back (formulas that "
                                             "read other rows break when Numbers sorts; to_new_table=true sorts a "
                                             "copy of the values instead)")
        check_sorted(ra[h:])

    body = _NUM_TABLE + ("    tb.sort({by: tb.columns[params.col], direction: params.dir});\n")
    return _numbers_write(path, sheet, table, "sort", body, {"col": c, "dir": order}, expect, summary, **kw)


# ── Pages placeholders (template fields like "Name", "Date") ─────────────────

_US, _RS = "\x1f", "\x1e"

# Pages refuses AppleScript `open (POSIX file …)` on files outside its sandbox
# ("Operation not permitted"); JXA `app.open(Path(…))` is granted access. So the
# document is opened with JXA, and AppleScript then finds that open document by
# its exact file path — never "front document" — before reading or writing.
_PAGES_FIND = """    set d to missing value
    repeat with x in documents
      set fp to ""
      try
        set fp to POSIX path of ((file of x) as alias)
      end try
      if fp ends with "/" then set fp to text 1 thru -2 of fp
      if fp is (item 1 of argv) then
        set d to contents of x
        exit repeat
      end if
    end repeat
    if d is missing value then error "the document isn't open in Pages" number -10000
"""


def _pages_open(path: Path, *, open_it: bool = True) -> bool:
    """Open `path` in Pages via JXA (if open_it). Returns True if it was already open."""
    out = _jxa("Pages", _OPEN_CHECK + """  if (params.open_it) app.open(Path(params.path));
  return JSON.stringify({open_in_app: false});""", {"path": str(path), "open_it": open_it}, timeout=180)
    return bool(out.get("open_in_app"))


def _pages_close(path: Path) -> None:
    """Close `path` in Pages without saving, if it is open (cleanup after a failure)."""
    try:
        _jxa("Pages", """  app.documents().forEach(d => {
    try { const f = d.file(); if (f && f.toString() === params.path) app.close(d, {saving: 'no'}); } catch (e) {}
  });
  return JSON.stringify({});""", {"path": str(path)}, timeout=60)
    except Exception:  # noqa: BLE001 — best effort; the original error matters more
        pass


def _pages_placeholders(path: Path) -> list[dict]:
    """AppleScript: [{tag, text}] in document order (open → read → close, no save)."""
    from iwork_studio import pages_io

    pages_io._assert_aqua()
    name = app_name("Pages")
    if '"' in name:
        raise AppOpError(f"refusing unsafe app name {name!r}")
    keep_open = _pages_open(path)
    script = f"""on run argv
  tell application "{name}"
{_PAGES_FIND}    set out to ""
    try
      repeat with ph in (every placeholder text of d)
        set t to ""
        try
          set t to tag of ph
          if t is missing value then set t to ""
        end try
        set x to ""
        try
          set x to (ph as text)
        end try
        set out to out & (t as text) & (character id 31) & x & (character id 30)
      end repeat
    on error errMsg number errNum
      if (item 2 of argv) is "close" then close d saving no
      error errMsg number errNum
    end try
    if (item 2 of argv) is "close" then close d saving no
    return out
  end tell
end run"""
    r = subprocess.run(["osascript", "-e", script, str(path), "keep" if keep_open else "close"],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        if not keep_open:
            _pages_close(path)
        raise RuntimeError(f"AppleScript failed (rc={r.returncode}): {r.stderr.strip()[:400]}")
    out = []
    for rec in r.stdout.rstrip("\n").split(_RS):
        if _US in rec:
            tag, text = rec.split(_US, 1)
            out.append({"tag": tag, "text": text})
    return out


def _pages_texts(path: Path) -> dict:
    """Every text the document holds: body (None for page-layout documents) and,
    in order, each text box / shape's text (None if Pages won't list them)."""
    body = """
  const doc = app.open(Path(params.path));
  const out = {body: null, items: null};
  try {
    try { const b = doc.bodyText(); out.body = (b === null || b === undefined) ? null : b.toString(); } catch (e) {}
    try {
      const items = [];
      for (const coll of ['textItems', 'shapes']) {
        const xs = doc[coll]();
        for (let i = 0; i < xs.length; i++) {
          let t = null;
          try { t = xs[i].objectText().toString(); } catch (e) {}
          items.push(t);
        }
      }
      out.items = items;
    } catch (e) {}
  } finally {
    app.close(doc, {saving: 'no'});
  }
  return JSON.stringify(out);"""
    return _jxa("Pages", body, {"path": str(path)})


def _expected_texts(before: dict, phs: list[dict], values: dict) -> dict:
    """Body: placeholders replaced in document order. Text boxes: every occurrence of a
    filled placeholder's text replaced (longest first)."""
    exp = {"body": before["body"], "items": before["items"]}
    if before["body"] is not None:
        body, cursor = before["body"], 0
        for p in phs:
            if p["tag"] in values and p["text"]:
                i = body.find(p["text"], cursor)
                if i >= 0:
                    body = body[:i] + values[p["tag"]] + body[i + len(p["text"]):]
                    cursor = i + len(values[p["tag"]])
        exp["body"] = body
    if before["items"] is not None:
        subs = sorted({(p["text"], values[p["tag"]]) for p in phs if p["tag"] in values and p["text"]},
                      key=lambda x: -len(x[0]))
        items = []
        for t in before["items"]:
            if t is not None:
                for old, new in subs:
                    t = t.replace(old, new)
            items.append(t)
        exp["items"] = items
    return exp


def list_placeholders(path) -> dict:
    target = Path(path).resolve()
    if target.suffix.lower() != ".pages":
        raise AppOpError(f"{target.name} is not a .pages document")
    from iwork_studio import pages_io

    pages_io.preflight()
    phs = _pages_placeholders(target)
    return {"file": str(target), "placeholders": phs, "tags": sorted({p["tag"] for p in phs})}


def fill_placeholders(path, values: dict, *, backup_dir=None, max_backups: int = 10) -> dict:
    """values = {"Name": "وليد", "Date": "3 Oct"} — fill every placeholder with that tag.
    Works for word-processing and page-layout documents. The body and every text box
    are checked to equal the originals with exactly those placeholders filled."""
    from iwork_studio import pages_io

    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    if target.suffix.lower() != ".pages":
        raise AppOpError(f"{target.name} is not a .pages document")
    if not values or not all(isinstance(k, str) and isinstance(v, str) for k, v in values.items()):
        raise AppOpError('values must be {"Tag": "text", …}')
    if "" in values:
        raise AppOpError("untagged placeholders can't be targeted; use pages_list_placeholders for the tags")
    pages_io.preflight()
    if _pages_open(target, open_it=False):
        from iwork_studio.keynote_slides import DocumentOpenError

        raise DocumentOpenError(f"{target.name} is open in Pages. Save and close it first.")
    phs = _pages_placeholders(target)
    tags = {p["tag"] for p in phs}
    unknown = sorted(set(values) - tags)
    if unknown:
        raise AppOpError(f"no placeholder tagged {unknown}; this document has {sorted(tags)}")
    by_text: dict = {}
    for p in phs:
        by_text.setdefault(p["text"], set()).add(p["tag"])
    clash = sorted({t for p in phs if p["tag"] in values for t in by_text[p["text"]] if t not in values})
    if clash:
        raise AppOpError(f"placeholders {clash} show the same text as ones being filled, so the result "
                         f"can't be checked; fill them too")
    before = _pages_texts(target)
    expected = _expected_texts(before, phs, values)

    name = app_name("Pages")
    if '"' in name:
        raise AppOpError(f"refusing unsafe app name {name!r}")
    pairs = [x for k, v in values.items() for x in (k, v)]
    script = f"""on run argv
  tell application "{name}"
{_PAGES_FIND}    try
      repeat with i from 2 to (count of argv) by 2
        set t to item i of argv
        set v to item (i + 1) of argv
        tell d to set (every placeholder text whose tag is t) to v
      end repeat
      save d
    on error errMsg number errNum
      close d saving no
      error errMsg number errNum
    end try
    close d saving no
  end tell
end run"""
    bdir = Path(backup_dir) if backup_dir else target.parent / f"{target.name}.backups"
    backup = pages_io._versioned_backup(target, bdir)
    pages_io._prune_backups(bdir, max_backups)
    try:
        if _pages_open(target):
            raise RuntimeError(f"{target.name} was opened in Pages meanwhile; nothing written")
        r = subprocess.run(["osascript", "-e", script, str(target), *pairs], capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"AppleScript failed (rc={r.returncode}): {r.stderr.strip()[:400]}")
        after = _pages_texts(target)
        if after["body"] != expected["body"]:
            raise pages_io.EditVerificationError("body text after filling is not the original with just the "
                                                 "placeholders filled — rolled back")
        if expected["items"] is not None and after["items"] is not None and after["items"] != expected["items"]:
            raise pages_io.EditVerificationError("text boxes after filling are not the originals with just the "
                                                 "placeholders filled — rolled back")
        now = _pages_placeholders(target)
        left = [p for p in now if p["tag"] in values and p["text"] != values[p["tag"]]]
        if left:
            raise pages_io.EditVerificationError(f"placeholders still unfilled: {[p['tag'] for p in left]} — rolled back")
        others = lambda xs: Counter((p["tag"], p["text"]) for p in xs if p["tag"] not in values)  # noqa: E731
        if others(now) != others(phs):
            gone, new = others(phs) - others(now), others(now) - others(phs)
            raise pages_io.EditVerificationError(
                f"other placeholders changed — rolled back (before: {sorted(gone)[:5]}, after: {sorted(new)[:5]})")
    except Exception:
        _pages_close(target)  # never leave our window open over the restored file
        _restore(target, backup)
        raise
    return {"ok": True, "file": str(target), "filled": sorted(values), "backup": str(backup)}


# ── Pages tables (existing tables; AppleScript only — JXA can't see them) ────

_CELL = re.compile(r"^[A-Z]{1,3}[1-9][0-9]{0,4}$")
_MAX_TABLE_CELLS = 10000

_PAGES_TABLE_HELPERS = """
property US : character id 31
property RS : character id 30

on pad(n)
  set n to n as integer
  if n < 10 then return "0" & (n as text)
  return n as text
end pad

on ser(v)
  if v is missing value then return "e" & US
  set k to class of v
  if k is integer or k is real then return "n" & US & (v as text)
  if k is boolean then return "b" & US & (v as text)
  if k is date then
    set s to time of v
    return "d" & US & ((year of v) as integer as text) & "-" & pad(month of v as integer) & "-" & pad(day of v) & "T" & pad(s div 3600) & ":" & pad((s mod 3600) div 60) & ":" & pad(s mod 60)
  end if
  return "t" & US & (v as text)
end ser
"""

_PAGES_READ_TABLES = """    set out to ""
    set ts to every table of d
    repeat with t in ts
      set nm to name of t
      set rc to row count of t
      set cc to column count of t
      set out to out & "T" & US & nm & US & (rc as text) & US & (cc as text) & RS
      if rc * cc <= (item 3 of argv) as integer then
        set names to name of every cell of t
        set vals to value of every cell of t
        set fvals to formatted value of every cell of t
        set fms to {}
        try
          set fms to formula of every cell of t
        end try
        repeat with i from 1 to count of names
          set f to ""
          try
            set f to item i of fms
            if f is missing value then set f to ""
          end try
          set fv to item i of fvals
          if fv is missing value then set fv to ""
          set out to out & "C" & US & (item i of names) & US & my ser(item i of vals) & US & (fv as text) & US & (f as text) & RS
        end repeat
      end if
    end repeat
"""


def _num(text: str):
    t = text.strip().replace(",", ".")
    f = float(t)
    return int(f) if f.is_integer() and "e" not in t.lower() and abs(f) < 2 ** 53 else f


def _parse_tables(raw: str) -> list[dict]:
    tables: list[dict] = []
    for rec in raw.rstrip("\n").split(_RS):
        parts = rec.split(_US)
        if parts[0] == "T" and len(parts) >= 4:
            tables.append({"index": len(tables) + 1, "name": parts[1], "rows": int(parts[2]),
                           "columns": int(parts[3]), "cells": {}})
        elif parts[0] == "C" and len(parts) >= 6 and tables:
            ref, kind, val, shown, formula = parts[1], parts[2], parts[3], parts[4], parts[5]
            value = {"e": None, "n": lambda: _num(val), "b": lambda: val == "true", "d": val, "t": val}[kind]
            value = value() if callable(value) else value
            cell = {"value": value, "shown_as": shown}
            if formula:
                cell["formula"] = formula
            if kind == "d":
                cell["type"] = "date"
            tables[-1]["cells"][ref] = cell
    for t in tables:
        if not t["cells"] and t["rows"] * t["columns"] > 0:
            t["truncated"] = f"more than {_MAX_TABLE_CELLS} cells; not read"
    return tables


def _pages_script(path: Path, inner: str, args: list[str], *, write: bool) -> str:
    """JXA opens the document (sandbox access); AppleScript finds it by path and runs
    `inner`. Our window is closed afterwards; a document the user had open is refused
    for writes and left open for reads."""
    from iwork_studio import pages_io

    pages_io._assert_aqua()
    name = app_name("Pages")
    if '"' in name:
        raise AppOpError(f"refusing unsafe app name {name!r}")
    was_open = _pages_open(path)
    if was_open and write:
        from iwork_studio.keynote_slides import DocumentOpenError

        raise DocumentOpenError(f"{path.name} is open in Pages. Save and close it first.")
    close = "close" if not was_open else "keep"
    script = f"""{_PAGES_TABLE_HELPERS}
on run argv
  tell application "{name}"
{_PAGES_FIND}    try
{inner}
    on error errMsg number errNum
      if (item 2 of argv) is "close" then close d saving no
      error errMsg number errNum
    end try
    if (item 2 of argv) is "close" then close d saving no
    return out
  end tell
end run"""
    r = subprocess.run(["osascript", "-e", script, str(path), close, *map(str, args)],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        if not was_open:
            _pages_close(path)
        raise RuntimeError(f"AppleScript failed (rc={r.returncode}): {r.stderr.strip()[:400]}")
    return r.stdout


def read_tables(path) -> dict:
    """Every table in a .pages document: name, size, and each cell's value, shown text and formula."""
    from iwork_studio import pages_io

    target = Path(path).resolve()
    if target.suffix.lower() != ".pages":
        raise AppOpError(f"{target.name} is not a .pages document")
    if not target.exists():
        raise FileNotFoundError(target)
    pages_io.preflight()
    tables = _parse_tables(_pages_script(target, _PAGES_READ_TABLES, [_MAX_TABLE_CELLS], write=False))
    return {"file": str(target), "tables": tables}


def _same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)))
    return (a in (None, "") and b in (None, "")) or a == b


def set_table_cells(path, table, cells: dict, *, backup_dir=None, max_backups: int = 10) -> dict:
    """Write cells of an existing table: table = name or 1-based number; cells = {"B2": 1200,
    "C3": "تم", "D9": "=SUM(D2:D8)"}. Numbers stay numbers; "=…" makes a formula.
    Every other cell of every table, and the body text, are checked unchanged."""
    from iwork_studio import pages_io

    target = Path(path).resolve()
    if target.suffix.lower() != ".pages":
        raise AppOpError(f"{target.name} is not a .pages document")
    if not target.exists():
        raise FileNotFoundError(target)
    if not cells or len(cells) > 500:
        raise AppOpError("give 1–500 cells, like {\"B2\": 1200}")
    plan = {}
    for ref, v in cells.items():
        r = str(ref).strip().upper()
        if not _CELL.match(r):
            raise AppOpError(f"bad cell {ref!r}; use A1-style references like B2")
        if isinstance(v, bool) or not (v is None or isinstance(v, (int, float, str))):
            raise AppOpError(f"{r}: values must be text, a number, a formula (\"=…\") or null to clear")
        if isinstance(v, (int, float)):
            _as_number(v)  # validates finite
        plan[r] = v
    pages_io.preflight()
    if _pages_open(target, open_it=False):
        from iwork_studio.keynote_slides import DocumentOpenError

        raise DocumentOpenError(f"{target.name} is open in Pages. Save and close it first.")

    before = read_tables(target)["tables"]
    named = [t["index"] for t in before if t["name"] == str(table)]
    if not named and (isinstance(table, int) or str(table).isdigit()):
        idx = int(table)
        if not 1 <= idx <= len(before):
            raise AppOpError(f"table {table} out of range (document has {len(before)} tables)")
    else:
        hits = named
        if len(hits) != 1:
            raise AppOpError(f"{len(hits)} tables named {table!r}; tables: {[t['name'] for t in before]} "
                             "(pass the table number instead)")
        idx = hits[0]
    tb = before[idx - 1]
    if tb.get("truncated"):
        raise AppOpError(f"table {tb['name']!r} is too large to verify ({tb['rows']}×{tb['columns']})")
    missing = [r for r in plan if r not in tb["cells"]]
    if missing:
        raise AppOpError(f"{missing[:5]} outside table {tb['name']!r} ({tb['rows']} rows × {tb['columns']} columns)")
    try:
        body_before = pages_io.read_body_text(target)
    except pages_io.OutOfScopeError:
        body_before = None  # page layout

    lines, args = [], []
    for r, v in plan.items():
        if isinstance(v, (int, float)):
            rhs = _as_number(v)
        else:
            args.append("" if v is None else v)
            rhs = f"(item {2 + len(args)} of argv)"
        lines.append(f'      set value of cell "{r}" of table {idx} of d to {rhs}')
    inner = "\n".join(lines) + "\n      save d\n      set out to \"ok\""

    bdir = Path(backup_dir) if backup_dir else target.parent / f"{target.name}.backups"
    backup = pages_io._versioned_backup(target, bdir)
    pages_io._prune_backups(bdir, max_backups)
    try:
        _pages_script(target, inner, args, write=True)
        after = read_tables(target)["tables"]
        if [(t["name"], t["rows"], t["columns"]) for t in after] != [(t["name"], t["rows"], t["columns"]) for t in before]:
            raise pages_io.EditVerificationError("tables were added, removed or resized — rolled back")
        for t_b, t_a in zip(before, after):
            for ref, cb in t_b["cells"].items():
                ca = t_a["cells"].get(ref, {})
                if t_b["index"] == idx and ref in plan:
                    want = plan[ref]
                    if isinstance(want, str) and want.startswith("="):
                        if not ca.get("formula"):
                            raise pages_io.EditVerificationError(f"{ref} did not become a formula — rolled back")
                    elif not _same(ca.get("value"), want):
                        hint = (" (Pages turns text that looks like a number or date into one; pass a real "
                                "number, or different text)" if isinstance(want, str) else "")
                        raise pages_io.EditVerificationError(
                            f"{ref} reads {ca.get('value')!r}, wanted {want!r}{hint} — rolled back")
                    continue
                if cb.get("formula"):
                    if ca.get("formula") != cb["formula"]:
                        raise pages_io.EditVerificationError(f"formula in {t_b['name']}!{ref} changed — rolled back")
                elif not _same(ca.get("value"), cb.get("value")):
                    raise pages_io.EditVerificationError(
                        f"{t_b['name']}!{ref} changed ({cb.get('value')!r} → {ca.get('value')!r}) — rolled back")
        if body_before is not None and pages_io.read_body_text(target) != body_before:
            raise pages_io.EditVerificationError("the body text changed — rolled back")
    except Exception:
        _pages_close(target)
        _restore(target, backup)
        raise
    got = after[idx - 1]["cells"]
    return {"ok": True, "file": str(target), "table": tb["name"], "backup": str(backup),
            "cells": {r: got[r] for r in plan}}


# ── Keynote: transitions, images, slideshow ───────────────────────────────────


def set_transition(path, slide: int, effect: str, *, duration: float | None = None, delay: float | None = None,
                   automatic: bool | None = None, **kw) -> dict:
    """Transition into `slide` (1-based). effect: one of TRANSITIONS. duration/delay in seconds;
    automatic=True advances on its own after `delay`."""
    from iwork_studio import keynote_slides as ks
    from iwork_studio import keynote_theme as kt

    eff = (effect or "").strip().lower()
    if eff in ("none", "no transition"):
        eff = "no transition effect"
    if eff not in TRANSITIONS:
        raise AppOpError(f"unknown effect {effect!r}; choose one of: {', '.join(TRANSITIONS)}")
    for nm, v in (("duration", duration), ("delay", delay)):
        if v is not None and not 0 <= float(v) <= 60:
            raise AppOpError(f"{nm} must be 0–60 seconds")

    def plan(before):
        n = len(before["slides"])
        if not isinstance(slide, int) or not 1 <= slide <= n:
            raise kt.ThemeError(f"slide {slide!r} out of range (deck has {n})")

        def expect(b, a):
            kt._same_slide_count(b, a)
            for i, (x, y) in enumerate(zip(b["slides"], a["slides"]), start=1):
                if kt._sig(x) != kt._sig(y) or x.get("images") != y.get("images"):
                    raise ks.SlideOpVerificationError(f"slide {i} content changed")
                if i != slide and x.get("transition") != y.get("transition"):
                    raise ks.SlideOpVerificationError(f"slide {i} transition changed collaterally")
            t = a["slides"][slide - 1].get("transition") or {}
            if str(t.get("effect", "")).lower().replace("_", " ") != eff:
                raise ks.SlideOpVerificationError(f"transition reads {t.get('effect')!r}, wanted {eff!r}")
            if duration is not None and abs(float(t.get("duration") or 0) - float(duration)) > 0.05:
                raise ks.SlideOpVerificationError(f"duration reads {t.get('duration')!r}, wanted {duration}")
            if automatic is not None and bool(t.get("automatic")) != bool(automatic):
                raise ks.SlideOpVerificationError(f"auto-advance reads {t.get('automatic')!r}")

        props = {"transitionEffect": eff}
        if duration is not None:
            props["transitionDuration"] = float(duration)
        if delay is not None:
            props["transitionDelay"] = float(delay)
        if automatic is not None:
            props["automaticTransition"] = bool(automatic)
        script = "    doc.slides[params.n - 1].transitionProperties = params.props;\n"
        return script, {"n": slide, "props": props}, expect, {
            "slide": slide, "effect": eff, "duration": duration, "delay": delay, "automatic": automatic,
            "previous": before["slides"][slide - 1].get("transition")}

    return kt._run(path, "set_transition", plan, **kw)


def add_image(path, slide: int, image, *, x: float | None = None, y: float | None = None,
              width: float | None = None, **kw) -> dict:
    """Place an image file on `slide` (1-based). Position x/y and width in points (height keeps the ratio)."""
    from iwork_studio import keynote_slides as ks
    from iwork_studio import keynote_theme as kt

    img = Path(image).expanduser().resolve()
    if not img.is_file():
        raise FileNotFoundError(img)
    if img.suffix.lower() not in _IMAGE_EXTS:
        raise AppOpError(f"{img.name}: use an image file ({', '.join(sorted(_IMAGE_EXTS))})")
    if img.stat().st_size > 100 * 1024 * 1024:
        raise AppOpError("image is larger than 100 MB")
    if width is not None and not 1 <= float(width) <= 10000:
        raise AppOpError("width must be 1–10000 pt")

    def plan(before):
        n = len(before["slides"])
        if not isinstance(slide, int) or not 1 <= slide <= n:
            raise kt.ThemeError(f"slide {slide!r} out of range (deck has {n})")
        if before["slides"][slide - 1].get("images") is None:
            raise kt.ThemeError("this Keynote doesn't report slide images; can't verify, refusing")

        def expect(b, a):
            kt._same_slide_count(b, a)
            for i, (bx, ax) in enumerate(zip(b["slides"], a["slides"]), start=1):
                if kt._sig(bx) != kt._sig(ax):
                    raise ks.SlideOpVerificationError(f"slide {i} text changed")
                want = (bx["images"] or 0) + (1 if i == slide else 0)
                if ax.get("images") != want:
                    raise ks.SlideOpVerificationError(f"slide {i} has {ax.get('images')} images, expected {want}")

        script = ("    const s = doc.slides[params.n - 1];\n"
                  "    const im = app.Image({file: Path(params.image)});\n"
                  "    s.images.push(im);\n"
                  "    const placed = s.images[s.images.length - 1];\n"
                  "    if (params.width !== null) placed.width = params.width;\n"
                  "    if (params.x !== null && params.y !== null) placed.position = {x: params.x, y: params.y};\n")
        return script, {"n": slide, "image": str(img), "x": x, "y": y, "width": width}, expect, {
            "slide": slide, "image": img.name}

    return kt._run(path, "add_image", plan, **kw)


CHART_TYPES = {
    "bar": "vertical_bar_2d", "stacked_bar": "stacked_vertical_bar_2d",
    "horizontal_bar": "horizontal_bar_2d", "stacked_horizontal_bar": "stacked_horizontal_bar_2d",
    "line": "line_2d", "area": "area_2d", "stacked_area": "stacked_area_2d",
    "pie": "pie_2d", "scatter": "scatterplot_2d",
    "bar_3d": "vertical_bar_3d", "stacked_bar_3d": "stacked_vertical_bar_3d",
    "horizontal_bar_3d": "horizontal_bar_3d", "stacked_horizontal_bar_3d": "stacked_horizontal_bar_3d",
    "line_3d": "line_3d", "area_3d": "area_3d", "stacked_area_3d": "stacked_area_3d", "pie_3d": "pie_3d",
}


def _as_number(v) -> str:
    """A number as an AppleScript literal (plain decimal, no exponent)."""
    from decimal import Decimal

    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
        raise AppOpError(f"{v!r} isn't a finite number")
    d = Decimal(repr(float(v))) if isinstance(v, float) else Decimal(v)
    return format(d, "f")


def add_chart(path, slide: int, rows: list[str], columns: list[str], data: list[list], *,
              type: str = "bar", group_by: str = "row", **kw) -> dict:
    """Add a chart to `slide` (1-based) from data: one data row per entry in `rows` (series
    or categories, depending on group_by), one value per entry in `columns`.
    type: bar, stacked_bar, horizontal_bar, stacked_horizontal_bar, line, area,
    stacked_area, pie, scatter (and *_3d). Every slide's text and other charts are checked."""
    from iwork_studio import keynote_slides as ks
    from iwork_studio import keynote_theme as kt

    kind = CHART_TYPES.get(str(type).lower())
    if not kind:
        raise AppOpError(f"unknown chart type {type!r}; choose one of: {', '.join(CHART_TYPES)}")
    if group_by not in ("row", "column"):
        raise AppOpError('group_by must be "row" or "column"')
    if not rows or not columns:
        raise AppOpError("give at least one row name and one column name")
    if len(rows) > 100 or len(columns) > 100:
        raise AppOpError("at most 100 rows × 100 columns")
    if len(data) != len(rows) or any(len(r) != len(columns) for r in data):
        raise AppOpError(f"data must be {len(rows)} rows × {len(columns)} values (one row per row name)")
    literal = "{" + ", ".join("{" + ", ".join(_as_number(v) for v in r) + "}" for r in data) + "}"
    names = [str(x) for x in rows] + [str(x) for x in columns]

    def plan(before):
        n = len(before["slides"])
        if not isinstance(slide, int) or not 1 <= slide <= n:
            raise kt.ThemeError(f"slide {slide!r} out of range (deck has {n})")
        if before["slides"][slide - 1].get("charts") is None:
            raise kt.ThemeError("this Keynote doesn't report slide charts; can't verify, refusing")

        def expect(b, a):
            kt._same_slide_count(b, a)
            for i, (x, y) in enumerate(zip(b["slides"], a["slides"]), start=1):
                if kt._sig(x) != kt._sig(y) or x.get("images") != y.get("images"):
                    raise ks.SlideOpVerificationError(f"slide {i} content changed")
                want = (x["charts"] or 0) + (1 if i == slide else 0)
                if y.get("charts") != want:
                    raise ks.SlideOpVerificationError(f"slide {i} has {y.get('charts')} charts, expected {want}")

        # values are embedded as validated number literals; names travel as argv
        body = f"""        set n to (item 2 of argv) as integer
        set nr to (item 3 of argv) as integer
        set nc to (item 4 of argv) as integer
        set rn to {{}}
        repeat with i from 1 to nr
          set end of rn to item (4 + i) of argv
        end repeat
        set cn to {{}}
        repeat with i from 1 to nc
          set end of cn to item (4 + nr + i) of argv
        end repeat
        add chart slide n row names rn column names cn data {literal} type {kind} group by chart {group_by}"""
        script = {"applescript": body, "args": [slide, len(rows), len(columns), *names]}
        return script, {}, expect, {"slide": slide, "type": str(type).lower(), "rows": len(rows),
                                    "columns": len(columns)}

    return kt._run(path, "add_chart", plan, **kw)


def slideshow(action: str, path=None, *, from_slide: int = 1) -> dict:
    """start (needs path) · stop · next · previous. Doesn't change the file."""
    act = (action or "").lower()
    if act == "start":
        if not path:
            raise AppOpError("start needs the deck's path")
        target = Path(path).resolve()
        if not target.exists():
            raise FileNotFoundError(target)
        body = """
  let doc = app.documents().find(d => { try { const f = d.file(); return f && f.toString() === params.path; } catch (e) { return false; } });
  if (!doc) doc = app.open(Path(params.path));
  const n = doc.slides().length;
  if (params.from < 1 || params.from > n) return JSON.stringify({error: `slide ${params.from} out of range (1–${n})`});
  app.activate();
  app.start(doc, {from: doc.slides[params.from - 1]});
  return JSON.stringify({playing: app.playing()});"""
        out = _jxa("Keynote", body, {"path": str(target), "from": int(from_slide)})
        if out.get("error"):
            raise AppOpError(out["error"])
        return {"ok": True, "action": "start", "file": str(target), "from_slide": int(from_slide), **out}
    bodies = {
        "stop": "  if (app.playing()) app.stop(app.documents[0]);\n  return JSON.stringify({playing: app.playing()});",
        "next": "  if (!app.playing()) return JSON.stringify({error: 'no slideshow is playing'});\n"
                "  app.showNext();\n  return JSON.stringify({playing: true});",
        "previous": "  if (!app.playing()) return JSON.stringify({error: 'no slideshow is playing'});\n"
                    "  app.showPrevious();\n  return JSON.stringify({playing: true});",
    }
    if act not in bodies:
        raise AppOpError("action must be start, stop, next or previous")
    out = _jxa("Keynote", bodies[act], {})
    if out.get("error"):
        raise AppOpError(out["error"])
    return {"ok": True, "action": act, **out}


# ── new document from a built-in template ─────────────────────────────────────

_KINDS = {".numbers": "Numbers", ".key": "Keynote", ".pages": "Pages"}


def create_document(path, template: str | None = None) -> dict:
    """New .numbers / .key / .pages from Apple's built-in templates (Keynote: themes).
    The app saves the new document into a temp folder; it's checked, then moved into place."""
    dst = Path(path).expanduser().resolve()
    kind = _KINDS.get(dst.suffix.lower())
    if not kind:
        raise AppOpError("the new file must end in .numbers, .key or .pages")
    if dst.exists():
        raise AppOpError(f"{dst} already exists; choose another name")
    coll, prop = ("themes", "documentTheme") if kind == "Keynote" else ("templates", "documentTemplate")
    work = Path(tempfile.mkdtemp(prefix="iwork-new-"))
    tmp = work / dst.name
    body = f"""
  const names = app.{coll}().map(t => t.name());
  const want = params.template || (names.includes('Blank') ? 'Blank' : (names.includes('Basic White') ? 'Basic White' : names[0]));
  if (!names.includes(want)) return JSON.stringify({{unknown: want, available: names}});
  const doc = app.Document({{{prop}: app.{coll}.byName(want)}});
  app.documents.push(doc);
  const made = app.documents[0];
  try {{
    app.save(made, {{in: Path(params.out)}});
  }} finally {{
    app.close(made, {{saving: 'no'}});
  }}
  return JSON.stringify({{template: want}});"""
    try:
        out = _jxa(kind, body, {"template": template, "out": str(tmp)})
        if out.get("unknown"):
            raise AppOpError(f"unknown template {out['unknown']!r}; available: {out['available']}")
        if not tmp.exists():
            raise AppOpError(f"{kind} reported success but saved no file")
        if kind == "Numbers":
            from iwork_studio.numbers_io import read_numbers

            read_numbers(tmp)
        elif kind == "Keynote":
            from iwork_studio.keynote_io import read_key

            read_key(tmp)
        else:
            from iwork_studio.pages_io import document_info

            document_info(tmp)  # opens in Pages; page-layout templates have no body text
        if dst.exists():
            raise AppOpError(f"{dst} appeared while creating; not overwriting")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp), str(dst))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"ok": True, "file": str(dst), "app": kind, "template": out["template"]}
