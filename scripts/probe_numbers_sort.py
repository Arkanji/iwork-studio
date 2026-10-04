#!/usr/bin/env python3
"""Probe — what does a Numbers sort do to formulas, and can a sorted copy go in a new table?

Run on the Mac (logged-in GUI session, Numbers installed), from the repo root:

    uv run python scripts/probe_numbers_sort.py

Works on a test book it builds in a temp folder (synthetic numbers), plus a copy
of tests/fixtures/chart.numbers; never your files. Each step runs on its own, so
one refusal doesn't hide the rest.

Tables in the test book, each sorted by its value column:
  Rel       formulas point at another row, relative (=B2*0.1)
  Abs       the same, locked ($B$2)
  Ext       formulas point at a separate input table (=Inputs::B2*0.1)
  RowLocal  formulas use only their own row (=B2*C2)
Then: a new table is made, filled with Rel's values and sorted, in the book
and in the chart file (charts counted before and after).

Results are INTERNAL: ~/.iwork-studio/probes/numbers_sort.json (outside the
repo, never committed). Printed to stdout too.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
CHART = REPO / "tests" / "fixtures" / "chart.numbers"
OUT = Path.home() / ".iwork-studio" / "probes" / "numbers_sort.json"

FORMULAS = {
    "Rel": {(2, 1): "=B2*0.1", (3, 1): "=B2*0.5", (4, 1): "=B2*2"},
    "Abs": {(2, 1): "=$B$2*0.1", (3, 1): "=$B$2*0.5", (4, 1): "=$B$2*2"},
    "Ext": {(2, 1): "=Inputs::B2*0.1", (3, 1): "=Inputs::B2*0.5", (4, 1): "=Inputs::B2*2"},
    "RowLocal": {(1, 3): "=B2*C2", (2, 3): "=B3*C3", (3, 3): "=B4*C4", (4, 3): "=B5*C5"},
}
SORT_COL = {"Rel": 1, "Abs": 1, "Ext": 1, "RowLocal": 3}


def _book(path: Path) -> None:
    from iwork_studio import numbers_structure as ns

    two = [["Item", "Amount"], ["Base", 1000], ["Small", None], ["Half", None], ["Double", None]]
    ext = [["Item", "Amount"], ["Fixed", 50], ["Small", None], ["Half", None], ["Double", None]]
    ns.create(path, [{"name": "S", "tables": [
        {"name": "Rel", "rows": two},
        {"name": "Abs", "rows": two},
        {"name": "Inputs", "rows": [["Name", "Value"], ["Base", 1000]]},
        {"name": "Ext", "rows": ext},
        {"name": "RowLocal", "rows": [["Item", "Qty", "Price", "Total"], ["Pens", 3, 40, None],
                                      ["Books", 1, 15, None], ["Bags", 2, 90, None], ["Cups", 5, 4, None]]},
    ]}])


def _js(app: str, path: Path, body: str, params: dict | None = None) -> dict:
    """Run `body` with `d` = the open document at `path`; body returns a JSON-able value."""
    script = ("function run(argv) {\n  const params = JSON.parse(argv[0]);\n"
              f"  const app = Application({json.dumps(app)});\n"
              "  const d = app.documents().find(x => { try { return x.file().toString() === params.path; } "
              "catch (e) { return false; } });\n"
              "  if (!d) throw new Error('probe document is not open');\n"
              "  const out = (() => {\n" + body + "\n  })();\n  return JSON.stringify(out);\n}")
    r = subprocess.run(["osascript", "-l", "JavaScript", "-e", script, json.dumps({"path": str(path), **(params or {})})],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return {"status": "error", "detail": r.stderr.strip()[:400]}
    try:
        return {"status": "ok", "value": json.loads(r.stdout.strip() or "null")}
    except json.JSONDecodeError:
        return {"status": "ok", "value": r.stdout.strip()[:400]}


def _open(app: str, path: Path) -> None:
    js = f"Application({json.dumps(app)}).open(Path({json.dumps(str(path))}));"
    subprocess.run(["osascript", "-l", "JavaScript", "-e", js], capture_output=True, text=True, timeout=180, check=True)


READ = """    const t = d.sheets.byName('S').tables.byName(params.table);
    return t.rows().map(r => r.cells().map(c => { let f = null; try { f = c.formula(); } catch (e) {}
      return [c.value(), f || null]; }));"""

CHARTS = "    return d.sheets().reduce((n, s) => n + s.charts().length, 0);"


def _pairs(rows: list, value_col: int) -> Counter:
    """(item, value) per body row: what a sort must keep together."""
    return Counter((r[0][0], r[value_col][0]) for r in rows[1:])


def main() -> int:
    from iwork_studio.apps import app_name

    app = app_name("Numbers")
    tmp = Path(tempfile.mkdtemp(prefix="iws-probe-sort-"))
    book = (tmp / "probe.numbers").resolve()
    _book(book)
    res: dict = {"app": app, "tables": {}, "new_table": {}, "chart_file": {}}

    _open(app, book)
    for name, cells in FORMULAS.items():
        for (r, c), f in cells.items():
            out = _js(app, book, "    const t = d.sheets.byName('S').tables.byName(params.table);\n"
                      "    const cell = t.rows()[params.r].cells()[params.c];\n"
                      "    cell.value = params.f; return [cell.value(), cell.formula()];",
                      {"table": name, "r": r, "c": c, "f": f})
            if out["status"] != "ok":
                res["tables"].setdefault(name, {})["set_formula_error"] = out["detail"]

    for name, col in SORT_COL.items():
        entry = res["tables"].setdefault(name, {})
        before = _js(app, book, READ, {"table": name})
        srt = _js(app, book, "    const t = d.sheets.byName('S').tables.byName(params.table);\n"
                  "    t.sort({by: t.columns[params.col], direction: 'ascending'}); return 'sorted';",
                  {"table": name, "col": col})
        after = _js(app, book, READ, {"table": name})
        entry.update({"before": before.get("value", before), "sort": srt["status"] if srt["status"] == "ok" else srt,
                      "after": after.get("value", after)})
        if before["status"] == "ok" and after["status"] == "ok":
            entry["values_kept_with_their_rows"] = _pairs(before["value"], col) == _pairs(after["value"], col)
            entry["sorted_values"] = [r[col][0] for r in after["value"][1:]]
            entry["any_ref_error"] = any("REF" in str(c[1] or "") or "REF" in str(c[0]) for r in after["value"] for c in r)

    # A sorted copy: a new table filled with Rel's current values (no formulas), then sorted.
    mk = _js(app, book, """    const sh = d.sheets.byName('S');
    const src = sh.tables.byName('Rel');
    const vals = src.rows().map(r => r.cells().map(c => c.value()));
    const t = app.Table({name: 'Rel sorted', rowCount: vals.length, columnCount: vals[0].length});
    sh.tables.push(t);
    const nt = sh.tables.byName('Rel sorted');
    let header = null; try { header = src.headerRowCount(); nt.headerRowCount = header; } catch (e) {}
    vals.forEach((row, i) => row.forEach((v, j) => { if (v !== null) nt.rows()[i].cells()[j].value = v; }));
    nt.sort({by: nt.columns[1], direction: 'ascending'});
    let pos = null; try { pos = [src.position(), nt.position()]; } catch (e) {}
    return {tables: sh.tables().map(x => x.name()), header: header, pos: pos,
            rows: nt.rows().map(r => r.cells().map(c => c.value()))};""")
    res["new_table"]["make_fill_sort"] = mk
    res["new_table"]["source_after"] = _js(app, book, READ, {"table": "Rel"}).get("value")

    save = _js(app, book, "    app.save(d); app.close(d, {saving: 'no'}); return 'saved';")
    res["save"] = save["status"] if save["status"] == "ok" else save
    try:
        from numbers_parser import Document

        doc = Document(str(book))
        res["parser_reread"] = {t.name: [[(t.cell(r, c).value, t.cell(r, c).formula if t.cell(r, c).is_formula else None)
                                          for c in range(t.num_cols)] for r in range(t.num_rows)]
                                for t in doc.sheets[0].tables}
    except Exception as exc:  # noqa: BLE001
        res["parser_reread"] = f"error: {exc}"[:400]

    # The same new-table route on a file with a chart: is the chart kept?
    chart = (tmp / "chart.numbers").resolve()
    shutil.copy2(CHART, chart)
    _open(app, chart)
    res["chart_file"]["charts_before"] = _js(app, chart, CHARTS)
    res["chart_file"]["tables"] = _js(app, chart, """    return d.sheets().map(s => ({sheet: s.name(), tables: s.tables().map(t => ({
      name: t.name(), rows: t.rowCount(), cols: t.columnCount(), header: t.headerRowCount()}))}));""")
    res["chart_file"]["make_fill_sort"] = _js(app, chart, """    const sh = d.sheets()[0];
    const src = sh.tables()[0];
    const vals = src.rows().map(r => r.cells().map(c => c.value()));
    const name = src.name() + ' sorted';
    sh.tables.push(app.Table({name: name, rowCount: vals.length, columnCount: vals[0].length}));
    const nt = sh.tables.byName(name);
    try { nt.headerRowCount = src.headerRowCount(); } catch (e) {}
    vals.forEach((row, i) => row.forEach((v, j) => { if (v !== null) nt.rows()[i].cells()[j].value = v; }));
    nt.sort({by: nt.columns[vals[0].length - 1], direction: 'descending'});
    return {name: name, rows: nt.rows().map(r => r.cells().map(c => c.value()))};""")
    res["chart_file"]["charts_after"] = _js(app, chart, CHARTS)
    save = _js(app, chart, "    app.save(d); app.close(d, {saving: 'no'}); return 'saved';")
    res["chart_file"]["save"] = save["status"] if save["status"] == "ok" else save
    _open(app, chart)
    res["chart_file"]["charts_after_reopen"] = _js(app, chart, CHARTS)
    _js(app, chart, "    app.close(d, {saving: 'no'}); return 'closed';")

    # Quit Numbers only if the probe left nothing else open.
    js = f"const a = Application({json.dumps(app)}); if (a.running() && a.documents().length === 0) a.quit();"
    subprocess.run(["osascript", "-l", "JavaScript", "-e", js], capture_output=True, text=True, timeout=60)
    shutil.rmtree(tmp, ignore_errors=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["save"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
