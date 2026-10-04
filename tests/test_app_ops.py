"""App-driven ops (formula, sort, placeholders, transitions, images, slideshow, create)
— request validation and rollback, with the app stubbed."""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from numbers_parser import Document  # noqa: E402

from iwork_studio import app_ops, numbers_structure as ns  # noqa: E402
from iwork_studio import keynote_io, keynote_slides as ks, keynote_theme as kt, pages_io  # noqa: E402
from iwork_studio.numbers_io import CellRefError, WriteVerificationError  # noqa: E402


def _tiny_png(size: int = 64) -> bytes:
    """A solid teal PNG, no imaging library needed."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    row = b"\x00" + bytes((0x1A, 0x7F, 0x79)) * size
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * size)) + chunk(b"IEND", b""))


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture()
def book(tmp_path):
    p = tmp_path / "book.numbers"
    ns.create(p, [{"name": "S", "tables": [{"name": "T", "rows": [
        ["Name", "Amount"], ["ب", 30], ["أ", 10], ["ج", 20]]}]}])
    return p


def _rewrite(path, fn):
    doc = Document(str(path))
    fn(doc.sheets[0].tables[0])
    doc.save(str(path))


# ── Numbers: formula ─────────────────────────────────────────────────────────

def test_formula_must_start_with_equals(book):
    with pytest.raises(app_ops.AppOpError):
        app_ops.set_formula(book, "B5", "SUM(B2:B4)")


def test_formula_cell_out_of_range(book):
    with pytest.raises(CellRefError):
        app_ops.set_formula(book, "Z99", "=1")


def test_formula_not_applied_rolls_back(book, monkeypatch):
    before = _sha(book)
    # the "app" writes a plain value instead of a formula, and touches another cell
    monkeypatch.setattr(app_ops, "_edit_in_app",
                        lambda kind, path, body, params: _rewrite(path, lambda t: (t.write(1, 1, 999))))
    with pytest.raises(WriteVerificationError):
        app_ops.set_formula(book, "B4", "=SUM(B2:B3)")
    assert _sha(book) == before


def test_set_formula_recalculates_first(book, monkeypatch):
    seen = {}

    def fake(kind, path, body, params):
        seen["body"] = body
        raise RuntimeError("stop")

    monkeypatch.setattr(app_ops, "_edit_in_app", fake)
    with pytest.raises(RuntimeError):
        app_ops.set_formula(book, "B4", "=1")
    assert seen["body"].index("cells[i].value = fs[i]") < seen["body"].index("byName(params.ref)")


def test_recalculate_ok(book, monkeypatch):
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda k, p, b, params: {"charts": [0, 0], "recalculated": 2})
    out = app_ops.recalculate(book)
    assert out["ok"] and out["recalculated"] == 2 and "sheet" not in out


def test_recalculate_that_changes_an_input_rolls_back(book, monkeypatch):
    before = _sha(book)

    def bad(k, p, b, params):
        _rewrite(p, lambda t: t.write(1, 1, 31))
        return {"charts": [0, 0], "recalculated": 1}

    monkeypatch.setattr(app_ops, "_edit_in_app", bad)
    with pytest.raises(WriteVerificationError):
        app_ops.recalculate(book)
    assert _sha(book) == before


def test_formula_body_targets_the_named_cell(book, monkeypatch):
    seen = {}

    def fake(kind, path, body, params):
        seen.update(params, kind=kind, body=body)
        raise RuntimeError("stop")

    monkeypatch.setattr(app_ops, "_edit_in_app", fake)
    with pytest.raises(RuntimeError):
        app_ops.set_formula(book, "R4C2", "=SUM(B2:B3)")
    assert seen["kind"] == "Numbers" and seen["ref"] == "B4" and seen["sheet"] == "S" and seen["table"] == "T"
    assert "byName(params.ref)" in seen["body"]



@pytest.mark.parametrize("typed,read_back", [("=B2*0.1", "B2×0.1"), ("=B2/4", "B2÷4"), ("=IF(B2<>0,1,0)", "IF(B2≠0,1,0)"),
                                             ("=IF(B2<=C2,1,0)", "IF(B2≤C2,1,0)"), ("=SUM($B$2:B9)", "SUM($B$2:B9)")])
def test_formula_read_back_in_numbers_symbols(typed, read_back):
    assert app_ops._fnorm(typed) == app_ops._fnorm(read_back)
    assert app_ops._fnorm("=B2*0.1") != app_ops._fnorm("B3×0.1")

# ── Numbers: sort ────────────────────────────────────────────────────────────

def _sorted_rows(t, desc=False):
    rows = sorted([[t.cell(r, 0).value, t.cell(r, 1).value] for r in range(1, t.num_rows)],
                  key=lambda x: x[1], reverse=desc)
    for i, (a, b) in enumerate(rows, start=1):
        t.write(i, 0, a)
        t.write(i, 1, b)


def test_sort_ok(book, monkeypatch):
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda k, p, b, params: _rewrite(p, _sorted_rows))
    out = app_ops.sort_table(book, "B")
    assert out["rows_sorted"] == 3
    t = Document(str(book)).sheets[0].tables[0]
    assert [t.cell(r, 1).value for r in range(t.num_rows)] == ["Amount", 10, 20, 30]


def test_sort_wrong_order_rolls_back(book, monkeypatch):
    before = _sha(book)
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda k, p, b, params: _rewrite(p, lambda t: _sorted_rows(t, True)))
    with pytest.raises(WriteVerificationError, match="order"):
        app_ops.sort_table(book, "B")
    assert _sha(book) == before


def test_sort_that_alters_data_rolls_back(book, monkeypatch):
    before = _sha(book)
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda k, p, b, params: _rewrite(p, lambda t: t.write(2, 0, "X")))
    with pytest.raises(WriteVerificationError):
        app_ops.sort_table(book, "B")
    assert _sha(book) == before


def test_sort_bad_column(book):
    with pytest.raises(CellRefError):
        app_ops.sort_table(book, "Q")



@pytest.mark.parametrize("formula,refs", [
    ("B2×0.1", [(None, 1, 1, False)]),
    ("$B$2×0.1", [(None, 1, 1, True)]),
    ("Inputs::B2×0.1", [("Inputs", 1, 1, False)]),
    ("Sales Plan::$B$2×4", [("Sales Plan", 1, 1, True)]),
    ("SUM(B2:B9)", [(None, 1, 8, False)]),
    ("Sheet 1::Inputs::B2", [("Inputs", 1, 1, False)]),
    ("LOG10(B2)+C3", [(None, 1, 1, False), (None, 2, 2, False)]),
    ('"B2 الإيرادات"&D4', [(None, 3, 3, False)]),
])
def test_formula_refs(formula, refs):
    assert list(app_ops._refs(formula)) == refs


class _Cell:
    def __init__(self, f=None):
        self.is_formula, self.formula = f is not None, f


class _Table:
    name, num_header_rows, num_cols = "T", 1, 2

    def __init__(self, formulas):
        self.f, self.num_rows = formulas, 5

    def cell(self, r, c):
        return _Cell(self.f.get((r, c)))


def test_cross_row_formulas_found():
    # a row's own cells, other tables and a header-only formula are safe (Numbers keeps those)
    safe = {(1, 1): "A2×2", (2, 1): "Inputs::B2×0.1", (3, 1): "Inputs::$B$2×0.1", (0, 1): "SUM(B2:B5)"}
    assert app_ops._cross_row_formulas(_Table(safe)) == []
    for f in ("B2×0.1", "$B$2×0.1", "T::B2×0.1", "SUM(B2:B5)", "B$1×A3"):
        assert app_ops._cross_row_formulas(_Table({(2, 1): f})) == [(2, 1, f)], f


def test_sort_refuses_formulas_that_read_other_rows(book, monkeypatch):
    before = _sha(book)
    monkeypatch.setattr(app_ops, "_cross_row_formulas", lambda tb: [(2, 1, "B2×0.1")])
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda *a: pytest.fail("the app must not run"))
    with pytest.raises(app_ops.SortBreaksFormulasError, match="to_new_table"):
        app_ops.sort_table(book, "B")
    assert _sha(book) == before


def _copy_sorted(name="T sorted", tamper=None):
    def edit(kind, path, body, params):
        assert params["name"] == name and params["h"] == 1
        doc = Document(str(path))
        src = doc.sheets[0].tables[0]
        rows = [[src.cell(r, c).value for c in range(src.num_cols)] for r in range(src.num_rows)]
        rows = rows[:1] + sorted(rows[1:], key=lambda x: x[1])
        t = doc.sheets[0].add_table(table_name=name, num_rows=len(rows), num_cols=2, num_header_rows=1,
                                    num_header_cols=0)
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                t.write(r, c, v)
        if tamper:
            tamper(doc)
        doc.save(str(path))
    return edit


def test_sort_to_new_table(book, monkeypatch):
    monkeypatch.setattr(app_ops, "_cross_row_formulas", lambda tb: pytest.fail("no check needed for a copy"))
    monkeypatch.setattr(app_ops, "_edit_in_app", _copy_sorted())
    out = app_ops.sort_table(book, "B", to_new_table=True)
    assert out["new_table"] == "T sorted" and out["values_only"] and "unchanged" in out["next"]
    src, cp = Document(str(book)).sheets[0].tables
    assert [src.cell(r, 1).value for r in range(4)] == ["Amount", 30, 10, 20]
    assert [cp.cell(r, 1).value for r in range(4)] == ["Amount", 10, 20, 30]
    assert [cp.cell(r, 0).value for r in range(1, 4)] == ["أ", "ج", "ب"]


@pytest.mark.parametrize("tamper", [
    lambda doc: doc.sheets[0].tables[1].write(2, 1, 99),        # a value lost in the copy
    lambda doc: doc.sheets[0].tables[0].write(1, 0, "X"),       # the original table touched
    lambda doc: doc.sheets[0].tables[1].write(1, 1, 25),        # copy not in order
])
def test_sort_to_new_table_mismatch_rolls_back(book, monkeypatch, tamper):
    before = _sha(book)
    monkeypatch.setattr(app_ops, "_edit_in_app", _copy_sorted(tamper=tamper))
    with pytest.raises(WriteVerificationError):
        app_ops.sort_table(book, "B", to_new_table=True)
    assert _sha(book) == before


def test_sort_to_new_table_names(book, monkeypatch):
    monkeypatch.setattr(app_ops, "_edit_in_app", _copy_sorted())
    app_ops.sort_table(book, "B", to_new_table=True)
    with pytest.raises(app_ops.AppOpError, match="already exists"):
        app_ops.sort_table(book, "B", table="T", to_new_table=True, new_table_name="T sorted")
    monkeypatch.setattr(app_ops, "_edit_in_app", _copy_sorted("T sorted 2"))
    assert app_ops.sort_table(book, "B", table="T", to_new_table=True)["new_table"] == "T sorted 2"
    with pytest.raises(app_ops.AppOpError, match="to_new_table"):
        app_ops.sort_table(book, "B", table="T", new_table_name="X")

# ── Pages placeholders ───────────────────────────────────────────────────────

@pytest.fixture()
def letter(tmp_path, monkeypatch):
    p = tmp_path / "letter.pages"
    p.write_bytes(b"original")
    state = {"before": {"body": "Dear [Name],\rSee you on [Date].", "items": ["Sender [Name]", None]},
             "phs": [{"tag": "Name", "text": "[Name]"}, {"tag": "Date", "text": "[Date]"}],
             "after": None, "after_phs": []}
    reads = {"texts": 0, "phs": 0}

    def texts(path):
        reads["texts"] += 1
        return copy.deepcopy(state["before"] if reads["texts"] == 1 else state["after"])

    def phs(path):
        reads["phs"] += 1
        return copy.deepcopy(state["phs"] if reads["phs"] == 1 else state["after_phs"])

    class R:
        returncode, stderr = 0, ""

    def run(cmd, **kw):
        p.write_bytes(b"changed by app")
        return R()

    monkeypatch.setattr(pages_io, "preflight", lambda: {"ok": True})
    monkeypatch.setattr(app_ops, "_pages_texts", texts)
    monkeypatch.setattr(app_ops, "_pages_placeholders", phs)
    monkeypatch.setattr(app_ops.subprocess, "run", run)
    state["open_in_pages"] = False
    monkeypatch.setattr(app_ops, "_pages_open", lambda path, open_it=True: state["open_in_pages"])
    monkeypatch.setattr(app_ops, "_pages_close", lambda path: None)
    return p, state


def test_fill_placeholders_ok(letter):
    p, state = letter
    state["after"] = {"body": "Dear سارة,\rSee you on 3 Oct.", "items": ["Sender سارة", None]}
    out = app_ops.fill_placeholders(p, {"Name": "سارة", "Date": "3 Oct"})
    assert out["filled"] == ["Date", "Name"] and p.read_bytes() == b"changed by app"


def test_fill_placeholders_page_layout(letter):
    p, state = letter
    state["before"] = {"body": None, "items": ["[Name]", "Date: [Date]", "Footer"]}
    state["after"] = {"body": None, "items": ["سارة", "Date: 3 Oct", "Footer"]}
    assert app_ops.fill_placeholders(p, {"Name": "سارة", "Date": "3 Oct"})["ok"]


def test_fill_placeholders_unexpected_body_rolls_back(letter):
    p, state = letter
    state["after"] = {"body": "Dear سارة,\rSee you on 3 Oct. EXTRA", "items": ["Sender سارة", None]}
    with pytest.raises(pages_io.EditVerificationError):
        app_ops.fill_placeholders(p, {"Name": "سارة", "Date": "3 Oct"})
    assert p.read_bytes() == b"original"


def test_fill_placeholders_text_box_damage_rolls_back(letter):
    p, state = letter
    state["before"] = {"body": None, "items": ["[Name]", "Footer"]}
    state["after"] = {"body": None, "items": ["سارة", ""]}
    with pytest.raises(pages_io.EditVerificationError, match="text boxes"):
        app_ops.fill_placeholders(p, {"Name": "سارة"})
    assert p.read_bytes() == b"original"


def test_fill_placeholders_other_placeholder_changed_rolls_back(letter):
    p, state = letter
    state["after"] = {"body": "Dear سارة,\rSee you on [Date].", "items": ["Sender سارة", None]}
    state["after_phs"] = [{"tag": "Date", "text": "?"}]
    with pytest.raises(pages_io.EditVerificationError, match="other placeholders"):
        app_ops.fill_placeholders(p, {"Name": "سارة"})
    assert p.read_bytes() == b"original"


def test_fill_placeholders_refuses_document_open_in_pages(letter):
    p, state = letter
    state["open_in_pages"] = True
    with pytest.raises(ks.DocumentOpenError):
        app_ops.fill_placeholders(p, {"Name": "x"})
    assert p.read_bytes() == b"original" and not (p.parent / "letter.pages.backups").exists()


def test_placeholder_reader_opens_with_jxa_and_finds_by_path(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(pages_io, "_assert_aqua", lambda: None)
    monkeypatch.setattr(app_ops, "_pages_open", lambda path, open_it=True: calls.append("jxa-open") or False)

    class R:
        returncode, stderr, stdout = 0, "", "Name\x1f[Name]\x1e\x1f\x1e"

    def run(cmd, **kw):
        calls.append(cmd)
        return R()

    monkeypatch.setattr(app_ops.subprocess, "run", run)
    out = app_ops._pages_placeholders(tmp_path / "l.pages")
    assert out == [{"tag": "Name", "text": "[Name]"}, {"tag": "", "text": ""}]
    script = calls[1][2]
    assert calls[0] == "jxa-open" and "open (POSIX file" not in script and "front document" not in script
    assert calls[1][-1] == "close"


def test_fill_placeholders_order_change_is_fine(letter):
    p, state = letter
    state["phs"] = [{"tag": "Name", "text": "[Name]"}, {"tag": "A", "text": "a"}, {"tag": "B", "text": "b"}]
    state["before"] = {"body": None, "items": ["[Name]", "a", "b"]}
    state["after"] = {"body": None, "items": ["سارة", "a", "b"]}
    state["after_phs"] = [{"tag": "B", "text": "b"}, {"tag": "A", "text": "a"}]
    assert app_ops.fill_placeholders(p, {"Name": "سارة"})["ok"]


def test_fill_placeholders_refuses_untagged(letter):
    p, _ = letter
    with pytest.raises(app_ops.AppOpError, match="untagged"):
        app_ops.fill_placeholders(p, {"": "x"})


def test_fill_placeholders_unknown_tag(letter):
    p, _ = letter
    with pytest.raises(app_ops.AppOpError, match="Nope"):
        app_ops.fill_placeholders(p, {"Nope": "x"})
    assert p.read_bytes() == b"original"


def test_fill_placeholders_refuses_ambiguous_texts(letter):
    p, state = letter
    state["phs"] = [{"tag": "A", "text": "[Text]"}, {"tag": "B", "text": "[Text]"}]
    with pytest.raises(app_ops.AppOpError, match="same text"):
        app_ops.fill_placeholders(p, {"A": "x"})


def test_page_layout_has_no_body_text(monkeypatch, tmp_path):
    monkeypatch.setattr(pages_io, "_jxa", lambda script, timeout=180: "null")
    with pytest.raises(pages_io.PagesOutOfScopeError, match="page-layout"):
        pages_io.read_body_text(tmp_path / "x.pages")


# ── Pages tables ─────────────────────────────────────────────────────────────

TABLES = [
    {"index": 1, "name": "Budget", "rows": 3, "columns": 2, "cells": {
        "A1": {"value": "البند", "shown_as": "البند"}, "B1": {"value": "Amount", "shown_as": "Amount"},
        "A2": {"value": "Rent", "shown_as": "Rent"}, "B2": {"value": 1200, "shown_as": "1,200"},
        "A3": {"value": "Total", "shown_as": "Total"}, "B3": {"value": 1200, "shown_as": "1,200", "formula": "SUM(B2)"}}},
    {"index": 2, "name": "Notes", "rows": 1, "columns": 1, "cells": {"A1": {"value": "x", "shown_as": "x"}}},
]


@pytest.fixture()
def tables_doc(tmp_path, monkeypatch):
    p = tmp_path / "t.pages"
    p.write_bytes(b"original")
    state = {"after": None, "reads": 0, "scripts": [], "body_after": "body", "open": False}

    def read(path):
        state["reads"] += 1
        return {"file": str(path), "tables": copy.deepcopy(TABLES if state["reads"] == 1 else state["after"])}

    def script(path, inner, args, *, write):
        state["scripts"].append((inner, args))
        p.write_bytes(b"changed by app")
        return "ok"

    body = {"n": 0}

    def read_body(path):
        body["n"] += 1
        return "body" if body["n"] == 1 else state["body_after"]

    monkeypatch.setattr(pages_io, "preflight", lambda: {"ok": True})
    monkeypatch.setattr(pages_io, "read_body_text", read_body)
    monkeypatch.setattr(app_ops, "read_tables", read)
    monkeypatch.setattr(app_ops, "_pages_script", script)
    monkeypatch.setattr(app_ops, "_pages_open", lambda path, open_it=True: state["open"])
    monkeypatch.setattr(app_ops, "_pages_close", lambda path: None)
    return p, state


def _tables_after(**cells):
    t = copy.deepcopy(TABLES)
    for ref, v in cells.items():
        t[0]["cells"][ref].update(v)
    return t


def test_set_table_cells_ok(tables_doc):
    p, state = tables_doc
    state["after"] = _tables_after(B2={"value": 1500.5}, A2={"value": "إيجار"}, B3={"value": 1500.5})
    out = app_ops.set_table_cells(p, "Budget", {"b2": 1500.5, "A2": "إيجار"})
    assert out["ok"] and out["cells"]["B2"]["value"] == 1500.5
    inner, args = state["scripts"][0]
    assert 'set value of cell "B2" of table 1 of d to 1500.5' in inner
    assert 'set value of cell "A2" of table 1 of d to (item 3 of argv)' in inner
    assert args == ["إيجار"]  # text travels as argv, never inside the script


def test_set_table_cells_formula(tables_doc):
    p, state = tables_doc
    state["after"] = _tables_after(A3={"value": 1200, "formula": "MAX(B2)"})
    assert app_ops.set_table_cells(p, 1, {"A3": "=MAX(B2)"})["ok"]


def test_formula_cells_may_recompute(tables_doc):
    p, state = tables_doc
    state["after"] = _tables_after(B2={"value": 99}, B3={"value": 99})  # B3 = SUM(B2) recalculated
    assert app_ops.set_table_cells(p, "Budget", {"B2": 99})["ok"]


def test_collateral_cell_change_rolls_back(tables_doc):
    p, state = tables_doc
    state["after"] = _tables_after(B2={"value": 99}, A1={"value": "?"})
    with pytest.raises(pages_io.EditVerificationError, match="A1"):
        app_ops.set_table_cells(p, "Budget", {"B2": 99})
    assert p.read_bytes() == b"original"


def test_text_turned_into_number_rolls_back(tables_doc):
    p, state = tables_doc
    state["after"] = _tables_after(A2={"value": 123})
    with pytest.raises(pages_io.EditVerificationError, match="looks like a number"):
        app_ops.set_table_cells(p, "Budget", {"A2": "123"})
    assert p.read_bytes() == b"original"


def test_body_change_rolls_back(tables_doc):
    p, state = tables_doc
    state["after"] = _tables_after(B2={"value": 5}, B3={"value": 5})
    state["body_after"] = "body changed"
    with pytest.raises(pages_io.EditVerificationError, match="body"):
        app_ops.set_table_cells(p, "Budget", {"B2": 5})
    assert p.read_bytes() == b"original"


def test_table_resized_rolls_back(tables_doc):
    p, state = tables_doc
    after = _tables_after(B2={"value": 5})
    after[1]["rows"] = 2
    state["after"] = after
    with pytest.raises(pages_io.EditVerificationError, match="resized"):
        app_ops.set_table_cells(p, "Budget", {"B2": 5})
    assert p.read_bytes() == b"original"


@pytest.mark.parametrize("table,cells,msg", [
    ("Nope", {"B2": 1}, "tables named"),
    (3, {"B2": 1}, "out of range"),
    ("Budget", {"Z9": 1}, "outside"),
    ("Budget", {"B 2": 1}, "bad cell"),
    ("Budget", {"B2": True}, "values must be"),
    ("Budget", {"B2": float("inf")}, "finite"),
    ("Budget", {}, "1–500"),
])
def test_set_table_cells_bad_requests(tables_doc, table, cells, msg):
    p, state = tables_doc
    with pytest.raises(app_ops.AppOpError, match=msg):
        app_ops.set_table_cells(p, table, cells)
    assert p.read_bytes() == b"original" and state["scripts"] == []


def test_table_named_like_a_number(tables_doc, monkeypatch):
    p, state = tables_doc
    named = copy.deepcopy(TABLES)
    named[1]["name"] = "1"
    state["reads"] = 0

    def read(path):
        state["reads"] += 1
        return {"file": str(path), "tables": copy.deepcopy(named)}

    monkeypatch.setattr(app_ops, "read_tables", read)
    app_ops.set_table_cells(p, "1", {"A1": "x"})  # the table *named* "1" is table 2
    assert "of table 2 of d" in state["scripts"][0][0]


def test_set_table_cells_refuses_open_document(tables_doc):
    p, state = tables_doc
    state["open"] = True
    with pytest.raises(ks.DocumentOpenError):
        app_ops.set_table_cells(p, "Budget", {"B2": 1})


def test_set_table_cells_page_layout(tables_doc, monkeypatch):
    p, state = tables_doc

    def no_body(path):
        raise pages_io.OutOfScopeError("page layout")

    monkeypatch.setattr(pages_io, "read_body_text", no_body)
    state["after"] = _tables_after(B2={"value": 7}, B3={"value": 7})
    assert app_ops.set_table_cells(p, "Budget", {"B2": 7})["ok"]


def test_parse_tables():
    us, rs = "\x1f", "\x1e"
    raw = (f"T{us}Budget{us}2{us}1{rs}C{us}A1{us}n{us}3,5{us}3.50{us}{rs}C{us}A2{us}d{us}2026-10-03T00:00:00{us}3 Oct{us}{rs}"
           f"T{us}Big{us}200{us}100{rs}")
    t = app_ops._parse_tables(raw)
    assert t[0]["cells"]["A1"]["value"] == 3.5 and t[0]["cells"]["A2"]["type"] == "date"
    assert "truncated" in t[1]


# ── Keynote: transitions / images ────────────────────────────────────────────

STYLE = {"theme": "Basic White", "layouts": ["Title"], "slides": [
    {"slide": 1, "layout": "Title", "images": 0, "charts": 0, "transition": {"effect": "no transition effect", "duration": 1.0,
                                                                 "delay": 0.0, "automatic": False},
     "items": [{"index": 0, "text": "عرض", "font": "HelveticaNeue", "size": 40.0, "color": "#000000"}]},
    {"slide": 2, "layout": "Title", "images": 1, "charts": 1, "transition": {"effect": "no transition effect", "duration": 1.0,
                                                                 "delay": 0.0, "automatic": False},
     "items": [{"index": 0, "text": "Two", "font": "HelveticaNeue", "size": 40.0, "color": "#000000"}]},
]}


@pytest.fixture()
def deck(tmp_path, monkeypatch):
    d = tmp_path / "deck.key"
    d.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    state = {"after": None, "as": []}

    def fake_as(target, body, args):
        state["as"].append((body, args))
        Path(target).write_bytes(b"app wrote this")

    monkeypatch.setattr(kt, "_applescript_op", fake_as)
    reads = {"n": 0}

    def fake_read(path):
        reads["n"] += 1
        return copy.deepcopy(STYLE if reads["n"] == 1 else state["after"])

    def fake_jxa(body, params, timeout=None):
        Path(params["path"]).write_bytes(b"app wrote this")
        return {"ok": True}

    monkeypatch.delenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", raising=False)
    monkeypatch.setattr(kt, "read_style", fake_read)
    monkeypatch.setattr(ks, "_jxa", fake_jxa)
    monkeypatch.setattr(kt.keynote_io, "read_key", lambda p: {})
    return d, state


def _with(fn):
    a = copy.deepcopy(STYLE)
    fn(a)
    return a


def test_transition_ok(deck):
    d, state = deck
    state["after"] = _with(lambda a: a["slides"][0]["transition"].update(effect="dissolve", duration=2.0))
    out = app_ops.set_transition(d, 1, "Dissolve", duration=2)
    assert out["effect"] == "dissolve"


def test_transition_collateral_rolls_back(deck):
    d, state = deck
    before = _sha(d)

    def bad(a):
        a["slides"][0]["transition"]["effect"] = "dissolve"
        a["slides"][1]["transition"]["effect"] = "push"

    state["after"] = _with(bad)
    with pytest.raises(ks.SlideOpVerificationError):
        app_ops.set_transition(d, 1, "dissolve")
    assert _sha(d) == before


def test_transition_unknown_effect(deck):
    d, _ = deck
    with pytest.raises(app_ops.AppOpError, match="unknown effect"):
        app_ops.set_transition(d, 1, "explode")


def test_add_image_ok(deck, tmp_path):
    d, state = deck
    img = tmp_path / "logo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    state["after"] = _with(lambda a: a["slides"][0].update(images=1))
    assert app_ops.add_image(d, 1, img, width=200)["image"] == "logo.png"


def test_add_image_wrong_slide_rolls_back(deck, tmp_path):
    d, state = deck
    before = _sha(d)
    img = tmp_path / "logo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    state["after"] = _with(lambda a: a["slides"][1].update(images=2))
    with pytest.raises(ks.SlideOpVerificationError):
        app_ops.add_image(d, 1, img)
    assert _sha(d) == before


def test_add_image_rejects_non_images(deck, tmp_path):
    d, _ = deck
    f = tmp_path / "notes.txt"
    f.write_text("x")
    with pytest.raises(app_ops.AppOpError):
        app_ops.add_image(d, 1, f)


# ── Keynote charts ───────────────────────────────────────────────────────────

def test_add_chart_ok(deck):
    d, state = deck
    state["after"] = _with(lambda a: a["slides"][0].update(charts=1))
    out = app_ops.add_chart(d, 1, ["2025", "2026"], ["Q1", "Q2", "Q3"], [[1, 2.5, -3], [4, 5, 0.0003]], type="line")
    assert out["type"] == "line" and out["rows"] == 2 and out["columns"] == 3
    body, args = state["as"][0]
    assert "type line_2d group by chart row" in body
    assert "data {{1, 2.5, -3}, {4, 5, 0.0003}}" in body
    assert args == [1, 2, 3, "2025", "2026", "Q1", "Q2", "Q3"]  # names travel as argv, never in the script


def test_add_chart_wrong_slide_rolls_back(deck):
    d, state = deck
    before = _sha(d)
    state["after"] = _with(lambda a: a["slides"][1].update(charts=2))
    with pytest.raises(ks.SlideOpVerificationError):
        app_ops.add_chart(d, 1, ["a"], ["x"], [[1]])
    assert _sha(d) == before


@pytest.mark.parametrize("kw", [
    {"type": "donut"},
    {"data": [[1, 2]]},                       # wrong width
    {"data": [["1"]]},                        # not a number
    {"data": [[True]]},
    {"data": [[float("nan")]]},
    {"group_by": "diagonal"},
])
def test_add_chart_bad_requests(deck, kw):
    d, state = deck
    args = {"rows": ["a"], "columns": ["x"], "data": [[1]], **kw}
    with pytest.raises(app_ops.AppOpError):
        app_ops.add_chart(d, 1, args.pop("rows"), args.pop("columns"), args.pop("data"), **args)
    assert state["as"] == []


def test_other_ops_check_charts_are_kept(deck):
    d, state = deck
    before = _sha(d)

    def lost(a):
        a["slides"][0]["transition"]["effect"] = "dissolve"
        a["slides"][1]["charts"] = 0

    state["after"] = _with(lost)
    with pytest.raises(ks.SlideOpVerificationError):
        app_ops.set_transition(d, 1, "dissolve")
    assert _sha(d) == before


def test_chart_deck_allowed_for_app_ops(tmp_path, deck):
    _, state = deck
    d = tmp_path / "chart.key"
    d.write_bytes((REPO / "tests" / "fixtures" / "chart.key").read_bytes())
    state["after"] = _with(lambda a: a["slides"][0]["transition"].update(effect="push"))
    assert app_ops.set_transition(d, 1, "push")["ok"]


def test_chart_deck_refused_when_charts_unreported(tmp_path, deck, monkeypatch):
    d = tmp_path / "chart.key"
    d.write_bytes((REPO / "tests" / "fixtures" / "chart.key").read_bytes())
    blind = copy.deepcopy(STYLE)
    for sl in blind["slides"]:
        sl["charts"] = None
    monkeypatch.setattr(kt, "read_style", lambda p: copy.deepcopy(blind))
    with pytest.raises(keynote_io.ChartRefusalError):
        app_ops.set_transition(d, 1, "push")


# ── Numbers app ops on files with charts ─────────────────────────────────────

@pytest.fixture()
def chart_book(book, monkeypatch):
    """A Numbers file the gate sees as holding charts."""
    from iwork_studio import numbers_io

    monkeypatch.setattr(numbers_io, "contains_charts", lambda p: True)
    return book


def _numbers_op(path, out):
    return app_ops._numbers_write(path, None, None, "test", "", {}, lambda b, a, d: None, {})


def test_numbers_app_op_keeps_charts(chart_book, monkeypatch):
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda k, p, b, params: {"charts": [1, 1]})
    assert _numbers_op(chart_book, None)["ok"]


def test_numbers_app_op_chart_lost_rolls_back(chart_book, monkeypatch):
    before = _sha(chart_book)

    def lose(k, p, b, params):
        p.write_bytes(p.read_bytes())  # app "saved"
        return {"charts": [1, 0]}

    monkeypatch.setattr(app_ops, "_edit_in_app", lose)
    with pytest.raises(WriteVerificationError, match="charts"):
        _numbers_op(chart_book, None)
    assert _sha(chart_book) == before


def test_numbers_app_op_refuses_unreported_charts(chart_book, monkeypatch):
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda k, p, b, params: {"charts": [None, None]})
    with pytest.raises(WriteVerificationError, match="doesn't report"):
        _numbers_op(chart_book, None)


def test_numbers_body_counts_charts(book, monkeypatch):
    seen = {}

    def fake(kind, path, body, params):
        seen["body"] = body
        return {"charts": [0, 0]}

    monkeypatch.setattr(app_ops, "_edit_in_app", fake)
    app_ops._numbers_write(book, None, None, "t", "    // op\n", {}, lambda b, a, d: None, {})
    assert seen["body"].index("chartsBefore = countCharts()") < seen["body"].index("// op")
    assert "result.charts = [chartsBefore, countCharts()]" in seen["body"]


# ── slideshow / create ───────────────────────────────────────────────────────

def test_slideshow_bad_action():
    with pytest.raises(app_ops.AppOpError):
        app_ops.slideshow("dance")


def test_create_document_refuses_existing_and_bad_suffix(tmp_path):
    (tmp_path / "a.key").write_bytes(b"x")
    with pytest.raises(app_ops.AppOpError):
        app_ops.create_document(tmp_path / "a.key")
    with pytest.raises(app_ops.AppOpError):
        app_ops.create_document(tmp_path / "a.docx")


def test_create_document_moves_checked_file(tmp_path, monkeypatch):
    def fake(kind, body, params, timeout=300):
        Path(params["out"]).write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
        return {"template": "Basic White"}

    monkeypatch.setattr(app_ops, "_jxa", fake)
    out = app_ops.create_document(tmp_path / "new.key")
    assert out["template"] == "Basic White" and Path(out["file"]).exists()


def test_create_pages_document_checks_it_opens(tmp_path, monkeypatch):
    def fake(kind, body, params, timeout=300):
        Path(params["out"]).write_bytes(b"pages zip")
        return {"template": "Classic Letter"}

    monkeypatch.setattr(app_ops, "_jxa", fake)
    opened = []
    monkeypatch.setattr(pages_io, "document_info", lambda p: opened.append(p) or {"kind": "page layout"})
    out = app_ops.create_document(tmp_path / "l.pages", "Classic Letter")
    assert opened and Path(out["file"]).read_bytes() == b"pages zip"


def test_create_document_unknown_template(tmp_path, monkeypatch):
    monkeypatch.setattr(app_ops, "_jxa", lambda *a, **k: {"unknown": "Nope", "available": ["Blank"]})
    with pytest.raises(app_ops.AppOpError, match="Blank"):
        app_ops.create_document(tmp_path / "new.numbers", "Nope")
    assert not (tmp_path / "new.numbers").exists()


# ── live (macOS + the apps): pytest -m aqua ──────────────────────────────────

@pytest.mark.aqua
def test_live_numbers_sort_then_formula(book):
    assert app_ops.sort_table(book, "B")["ok"]
    t = Document(str(book)).sheets[0].tables[0]
    assert [t.cell(r, 1).value for r in range(1, 4)] == [10, 20, 30]
    ns.insert(book, "rows", values=[["المجموع", None]])
    out = app_ops.set_formula(book, "B5", "=SUM(B2:B4)")
    assert out["ok"] and out["result"] == 60


@pytest.mark.aqua
def test_live_sort_formulas_that_read_other_rows(tmp_path):
    p = tmp_path / "plan.numbers"
    ns.create(p, [{"name": "S", "tables": [{"name": "T", "rows": [
        ["Item", "Amount"], ["Base", 1000], ["Small", None], ["Half", None], ["Double", None]]}]}])
    for ref, f in (("B3", "=B2*0.1"), ("B4", "=B2*0.5"), ("B5", "=B2*2")):
        app_ops.set_formula(p, ref, f)
    before = _sha(p)
    with pytest.raises(app_ops.SortBreaksFormulasError):
        app_ops.sort_table(p, "B")
    assert _sha(p) == before
    out = app_ops.sort_table(p, "B", descending=True, to_new_table=True)
    src, cp = Document(str(p)).sheets[0].tables
    assert out["new_table"] == cp.name == "T sorted"
    assert [src.cell(r, 1).value for r in range(1, 5)] == [1000, 100, 500, 2000]
    assert [cp.cell(r, 1).value for r in range(1, 5)] == [2000, 1000, 500, 100]
    assert [cp.cell(r, 0).value for r in range(1, 5)] == ["Double", "Base", "Half", "Small"]
    assert not any(cp.cell(r, c).is_formula for r in range(5) for c in range(2))

@pytest.mark.aqua
@pytest.mark.parametrize("ext", [".numbers", ".key", ".pages"])
def test_live_create_from_builtin_template(tmp_path, ext):
    out = app_ops.create_document(tmp_path / f"new{ext}")
    assert out["ok"] and Path(out["file"]).exists()


@pytest.mark.aqua
def test_live_keynote_transition_and_image(tmp_path):
    deck = tmp_path / "deck.key"
    deck.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    assert app_ops.set_transition(deck, 1, "dissolve", duration=1.5)["ok"]
    img = tmp_path / "dot.png"
    img.write_bytes(_tiny_png())
    assert app_ops.add_image(deck, 1, img, x=100, y=100, width=64)["ok"]


@pytest.mark.aqua
def test_live_pages_placeholders(tmp_path):
    from iwork_studio import helpers

    names = [n for n in helpers.list_templates("pages")["templates"] if "letter" in n.lower()]
    if not names:
        pytest.skip("no letter template in this Pages")
    for i, name in enumerate(names[:4]):
        doc = tmp_path / f"letter{i}.pages"
        app_ops.create_document(doc, name)  # page-layout templates must create fine too
        tags = [t for t in app_ops.list_placeholders(doc)["tags"] if t]
        if tags:
            out = app_ops.fill_placeholders(doc, {tags[0]: "تجربة"})
            assert out["ok"]
            return
    pytest.skip(f"no placeholders in {names[:4]}")


@pytest.mark.aqua
def test_live_keynote_add_chart_then_edit(tmp_path):
    deck = tmp_path / "deck.key"
    deck.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    out = app_ops.add_chart(deck, 1, ["2025", "2026"], ["Q1", "Q2", "Q3"], [[10, 20, 30], [15, 25, 35]])
    assert out["ok"]
    assert keynote_io.contains_charts(deck)
    # the deck now has a chart; app-driven edits still work and keep it
    assert app_ops.set_transition(deck, 1, "dissolve")["ok"]
    assert ks.duplicate_slide(deck, 1)["ok"]


@pytest.mark.aqua
def test_live_pages_arabic_direction(tmp_path):
    """Writing Arabic into Pages: text must be exact, and we learn how Pages sets direction."""
    doc = tmp_path / "ar.pages"
    app_ops.create_document(doc)  # Blank: word processing
    out = pages_io.edit_pages_body(doc, mode="set_body", new_body="مرحبا بكم\rهذا اختبار")
    assert out["after"] == "مرحبا بكم\rهذا اختبار"
    rep = out["direction"]
    assert rep["checked"], "the Word export used for the direction check failed"
    out2 = pages_io.edit_pages_body(doc, "اختبار", "تجربة")  # rolls back if an RTL paragraph flips
    assert out2["direction"]["checked"]
    if rep.get("arabic_paragraphs_left_to_right"):
        pytest.xfail(f"Pages stores new Arabic paragraphs left-to-right: {rep}")


@pytest.mark.aqua
def test_live_pages_tables(tmp_path):
    """Find a built-in Pages template with a table, read it, write text/number/formula cells."""
    from iwork_studio import helpers

    names = helpers.list_templates("pages")["templates"]
    words = ("invoice", "budget", "schedule", "table", "planner", "report")
    picks = sorted((n for n in names if any(w in n.lower() for w in words)),
                   key=lambda n: next(i for i, w in enumerate(words) if w in n.lower()))[:8]
    seen = {}
    for i, name in enumerate(picks):
        doc = tmp_path / f"t{i}.pages"
        app_ops.create_document(doc, name)
        tables = app_ops.read_tables(doc)["tables"]
        seen[name] = [(t["name"], t["rows"], t["columns"]) for t in tables]
        usable = [t for t in tables if not t.get("truncated") and t["rows"] >= 2 and t["columns"] >= 2]
        if not usable:
            continue
        t = usable[0]
        free = [r for r, c in t["cells"].items() if not c.get("formula")]
        out = app_ops.set_table_cells(doc, t["index"], {free[0]: "تجربة", free[1]: 1234.5})
        assert out["cells"][free[0]]["value"] == "تجربة" and out["cells"][free[1]]["value"] == 1234.5
        return
    pytest.skip(f"no usable table; tables found per template: {seen}")


@pytest.mark.aqua
def test_live_slideshow_start_stop(tmp_path):
    deck = tmp_path / "deck.key"
    deck.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    assert app_ops.slideshow("start", deck)["ok"]
    assert app_ops.slideshow("stop")["playing"] is False
