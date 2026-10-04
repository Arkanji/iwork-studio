"""Keynote tables: validated, written through AppleScript, every cell read back, rolled back on mismatch."""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import design, keynote_deck as kd, keynote_io, keynote_slides as ks, keynote_table as ktab  # noqa: E402
from iwork_studio import keynote_theme as kt, numbers_structure as ns  # noqa: E402

GRID = [["المنطقة", "Q1", "Q2"], ["الرياض", 1200, 1500.5], ["Jeddah", 950, None]]


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _slide(n, tables):
    return {"slide": n, "layout": "Title Only", "items": [{"index": 0, "text": f"Slide {n}", "font": "F", "size": 40.0,
                                                           "color": "#000000"}],
            "images": 0, "charts": 0, "tables": tables}


def _made(grid, header_rows=1):
    return {"rows": len(grid), "cols": len(grid[0]), "header_rows": header_rows, "values": copy.deepcopy(grid)}


OTHER = {"rows": 2, "cols": 2, "header_rows": 1, "values": [["a", "b"], [1, 2]]}


@pytest.fixture()
def deck(tmp_path, monkeypatch):
    d = tmp_path / "d.key"
    d.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    state = {"before": {"theme": "Basic White", "slides": [_slide(1, []), _slide(2, [OTHER])]},
             "after": None, "script": None, "args": None, "styles": None, "reads": 0}

    def read(path):
        state["reads"] += 1
        return copy.deepcopy(state["before"] if state["script"] is None else state["after"])

    def run_as(target, body, args):
        state["script"], state["args"] = body, args
        Path(target).write_bytes(b"keynote wrote this")

    def jxa(body, params, timeout=None):
        return state["styles"]

    monkeypatch.delenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", raising=False)
    monkeypatch.setattr(kt, "read_style", read)
    monkeypatch.setattr(kt, "_applescript_op", run_as)
    monkeypatch.setattr(ks, "_jxa", jxa)
    monkeypatch.setattr(keynote_io, "read_key", lambda p: {})
    return d, state


def _after(state, slide1_tables, slide2_tables=None):
    state["after"] = {"theme": "Basic White", "slides": [_slide(1, slide1_tables), _slide(2, slide2_tables or [OTHER])]}


def test_add_table_ok(deck):
    d, state = deck
    _after(state, [_made(GRID)])
    out = ktab.add_table(d, 1, GRID)
    assert out["ok"] and (out["rows"], out["columns"], out["header_rows"]) == (3, 3, 1) and Path(out["backup"]).exists()
    body = state["script"]
    assert "tell slide n" in body and "make new table with properties" in body
    assert "set value of cell 2 of row 2 to 1200" in body and "set value of cell 3 of row 2 to 1500.5" in body
    # text travels as argv, never spliced into the script
    assert "الرياض" not in body and "الرياض" in state["args"] and "cell 3 of row 3" not in body


def test_text_turned_into_number_rolls_back(deck):
    d, state = deck
    before = _sha(d)
    grid = [["Metric", "Value"], ["Growth", "12%"]]
    made = _made(grid)
    made["values"][1][1] = 0.12
    _after(state, [made])
    with pytest.raises(ks.SlideOpVerificationError, match="pass numbers as numbers"):
        ktab.add_table(d, 1, grid)
    assert _sha(d) == before


def test_other_slide_table_changed_rolls_back(deck):
    d, state = deck
    before = _sha(d)
    changed = copy.deepcopy(OTHER)
    changed["values"][1][0] = 9
    _after(state, [_made(GRID)], [changed])
    with pytest.raises(ks.SlideOpVerificationError, match="slide 2"):
        ktab.add_table(d, 1, GRID)
    assert _sha(d) == before


def test_wrong_shape_rolls_back(deck):
    d, state = deck
    _after(state, [_made(GRID[:2])])
    with pytest.raises(ks.SlideOpVerificationError, match="2×3"):
        ktab.add_table(d, 1, GRID)


def test_no_table_made_rolls_back(deck):
    d, state = deck
    _after(state, [])
    with pytest.raises(ks.SlideOpVerificationError, match="0 tables, expected 1"):
        ktab.add_table(d, 1, GRID)


def test_existing_table_on_same_slide_kept(deck):
    d, state = deck
    _after(state, [], [OTHER, _made(GRID)])
    out = ktab.add_table(d, 2, GRID)
    assert out["ok"]


def _styles_for(grid, kit_name, h=1, break_font=False):
    k = design.get_kit(kit_name)
    plan = ktab._style_plan(grid, h, k)
    cells = [[{} for _ in grid[0]] for _ in grid]
    for (r, c), st in plan.items():
        cells[r][c] = {"font": st["font"], "color": [v for v in kt._rgb16(st["color"])],
                       "fill": kt._rgb16(st["fill"]) if st["fill"] else None, "align": "right" if st["right"] else "auto"}
    if break_font:
        cells[1][0]["font"] = "Helvetica"
    return {"cells": cells, "geometry": {"x": 80, "y": 300, "width": 1200, "height": 300}}


def test_kit_styles_every_cell_and_checks_them(deck):
    d, state = deck
    _after(state, [_made(GRID)])
    state["styles"] = _styles_for(GRID, "banking")
    out = ktab.add_table(d, 1, GRID, kit="banking", x=80, y=300, width=1200)
    assert out["kit"] == "banking"
    body = state["script"]
    assert "set background color of row 1 to" in body and "set alignment of cell 2 of row 2 to right" in body
    assert "set position to {80, 300}" in body and "set width to 1200" in body
    k = design.get_kit("banking")
    assert k["fonts"]["heading_ar"] in state["args"] and k["fonts"]["body"] in state["args"]
    plan = ktab._style_plan(GRID, 1, k)
    assert plan[(1, 0)]["font"] == k["fonts"]["body_ar"]  # Arabic cell → Arabic font
    assert plan[(0, 1)]["fill"] == k["colors"]["header_fill"] and plan[(2, 0)]["fill"] == k["colors"]["band"]
    assert plan[(1, 1)]["right"] and not plan[(1, 0)]["right"]


def test_kit_font_missing_rolls_back(deck):
    d, state = deck
    before = _sha(d)
    _after(state, [_made(GRID)])
    state["styles"] = _styles_for(GRID, "banking", break_font=True)
    with pytest.raises(ks.SlideOpVerificationError, match="font reads 'Helvetica'"):
        ktab.add_table(d, 1, GRID, kit="banking")
    assert _sha(d) == before


def test_position_checked(deck):
    d, state = deck
    _after(state, [_made(GRID)])
    state["styles"] = {"cells": [], "geometry": {"x": 0, "y": 0, "width": 500, "height": 100}}
    with pytest.raises(ks.SlideOpVerificationError, match="position"):
        ktab.add_table(d, 1, GRID, x=80, y=300)


@pytest.mark.parametrize("rows,kw,msg", [
    ([], {}, "list of rows"),
    ([[1]] * 51, {}, "at most 50 rows"),
    ([["a"] * 16], {}, "15 columns"),
    ([[True]], {}, "cell value"),
    ([[{"x": 1}]], {}, "cell value"),
    (GRID, {"header_rows": 3}, "header_rows"),
    (GRID, {"x": 10}, "both x and y"),
    (GRID, {"width": -5}, "positive"),
])
def test_bad_table_refused_before_backup(deck, rows, kw, msg):
    d, state = deck
    with pytest.raises(ktab.TableError, match=msg):
        ktab.add_table(d, 1, rows, **kw)
    assert state["script"] is None and not (d.parent / f"{d.name}.backups").exists()


def test_slide_out_of_range(deck):
    d, _ = deck
    with pytest.raises(kt.ThemeError, match="out of range"):
        ktab.add_table(d, 9, GRID)


def test_unreported_tables_refused(deck):
    d, state = deck
    state["before"]["slides"][0]["tables"] = None
    with pytest.raises(kt.ThemeError, match="doesn't report slide tables"):
        ktab.add_table(d, 1, GRID)


def test_short_rows_padded_and_formula_checked_exists(deck):
    d, state = deck
    _after(state, [_made([["Region", "Q1"], ["Riyadh", 1], ["Total", 1]])])
    assert ktab.add_table(d, 1, [["Region", "Q1"], ["Riyadh", 1], ["Total", "=SUM(B2)"]])["ok"]
    assert ktab._normalise([["a", "b"], ["c"]]) == [["a", "b"], ["c", None]]
    _after(state, [_made([["Region", "Q1"], ["Riyadh", 1], ["Total", None]])])
    state["script"] = None
    d.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    with pytest.raises(ks.SlideOpVerificationError, match="row 3, column 2"):  # a formula must produce a result
        ktab.add_table(d, 1, [["Region", "Q1"], ["Riyadh", 1], ["Total", "=SUM(B2)"]])


def test_other_ops_refuse_to_change_tables(deck):
    d, state = deck
    before = _sha(d)
    changed = copy.deepcopy(OTHER)
    changed["values"][0][0] = "z"
    _after(state, [], [changed])

    def plan(b):
        return {"applescript": "", "args": []}, {}, (lambda x, y: None), {}

    with pytest.raises(ks.SlideOpVerificationError, match="table"):
        kt._run(d, "set_theme", plan)
    assert _sha(d) == before


# ── From a Numbers table, and in build_deck ───────────────────────────────────


@pytest.fixture()
def report(tmp_path):
    p = tmp_path / "report.numbers"
    ns.create(p, [{"name": "S", "tables": [{"name": "T", "rows": [
        ["المنطقة", "Q1", "Q2", "Note"], ["الرياض", 1200, 1500, "x"], [None, None, None, None], ["Jeddah", 950.5, 990, "y"]]}]}])
    return p


def test_rows_from_numbers(report):
    rows, h = ktab.table_rows_from_numbers(report, columns=["Q2"])
    assert h == 1 and rows == [["المنطقة", "Q2"], ["الرياض", 1500], ["Jeddah", 990]]
    rows, _ = ktab.table_rows_from_numbers(report, max_rows=1)
    assert len(rows) == 2 and rows[1][0] == "الرياض"
    with pytest.raises(ktab.TableError, match="not in the table's header"):
        ktab.table_rows_from_numbers(report, columns=["Q9"])
    with pytest.raises(ktab.TableError, match="existing .numbers"):
        ktab.table_rows_from_numbers(report.with_suffix(".csv"))


def test_build_deck_table_slide(monkeypatch, tmp_path, report):
    from iwork_studio import app_ops

    calls = []
    style = {"theme": "Basic White", "layouts": ["Title", "Title Only", "Title & Bullets"],
             "slides": [{"slide": 1, "layout": "Title", "items": [], "tables": []}]}
    monkeypatch.setattr(app_ops, "create_document", lambda p, t=None: (Path(p).write_bytes(b"d"), {"template": "Basic White"})[1])

    def stop(*a, **k):
        raise RuntimeError("stop after layouts")

    monkeypatch.setattr(kt, "read_style", lambda p: copy.deepcopy(style))
    monkeypatch.setattr(kt, "_applescript_op", lambda t, b, a: calls.append(a) or stop())
    with pytest.raises(RuntimeError, match="stop"):
        kd.build_deck(tmp_path / "t.key", [{"title": "By region", "table": {"from": str(report), "columns": ["Q1"]}}])
    assert calls[0] == [1, "Title Only"] and not (tmp_path / "t.key").exists()
    with pytest.raises(kd.DeckError, match="not both"):
        kd.build_deck(tmp_path / "t.key", [{"title": "x", "table": {"rows": GRID}, "chart": {"rows": ["a"], "columns": ["b"], "data": [[1]]}}])
    with pytest.raises(kd.DeckError, match="slide 1: at most 50 rows"):
        kd.build_deck(tmp_path / "t.key", [{"title": "x", "table": {"rows": [[1]] * 60}}])


@pytest.mark.aqua
def test_live_add_table_with_kit(tmp_path):
    d = tmp_path / "t.key"
    d.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    out = ktab.add_table(d, 1, GRID, kit="banking")
    assert out["ok"] and out["rows"] == 3


@pytest.mark.aqua
def test_live_build_deck_with_table(tmp_path, report):
    out = kd.build_deck(tmp_path / "table.key", [
        {"title": "Revenue by region"},
        {"title": "الرياض تقود النمو", "table": {"from": str(report), "columns": ["Q1", "Q2"]}},
    ], kit="midnight")
    assert out["ok"] and out["tables"] == {2: {"rows": 3, "columns": 3}}
