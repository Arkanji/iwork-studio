"""Numbers create / CSV import / insert-delete rows & columns / add table — headless."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from numbers_parser import Document  # noqa: E402

from iwork_studio import numbers_structure as ns  # noqa: E402
from iwork_studio.numbers_io import WriteVerificationError, read_numbers  # noqa: E402


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _grid(path, sheet=None, table=None):
    doc = Document(str(path))
    sh = doc.sheets[sheet] if sheet else doc.sheets[0]
    tb = sh.tables[table] if table else sh.tables[0]
    return [[tb.cell(r, c).value for c in range(tb.num_cols)] for r in range(tb.num_rows)]


@pytest.fixture()
def book(tmp_path):
    p = tmp_path / "book.numbers"
    ns.create(p, [{"name": "Sales", "tables": [{"name": "Q1", "rows": [
        ["Region", "Revenue"], ["الرياض", 1200], ["جدة", 950.5], ["الدمام", 700]]}]},
        {"name": "Other", "tables": [{"name": "T", "rows": [["x", 1]]}]}])
    return p


# ── create / import ──────────────────────────────────────────────────────────

def test_create_round_trips_values_and_names(book):
    m = read_numbers(book)
    assert [s["name"] for s in m["sheets"]] == ["Sales", "Other"]
    assert _grid(book, "Sales") == [["Region", "Revenue"], ["الرياض", 1200], ["جدة", 950.5], ["الدمام", 700]]


def test_create_refuses_overwrite_and_bad_suffix(book, tmp_path):
    before = _sha(book)
    with pytest.raises(ns.StructureError):
        ns.create(book, [{"rows": [[1]]}])
    assert _sha(book) == before
    with pytest.raises(ns.StructureError):
        ns.create(tmp_path / "x.xlsx", [{"rows": [[1]]}])


def test_create_rejects_duplicate_sheets(tmp_path):
    with pytest.raises(ns.StructureError):
        ns.create(tmp_path / "d.numbers", [{"name": "A"}, {"name": "A"}])


def test_integers_are_stored_exactly(tmp_path):
    p = tmp_path / "n.numbers"
    ns.create(p, [{"rows": [[12, 0.0003, -5.5, 123456789.123, 2 ** 40]]}])
    assert _grid(p) == [[12, 0.0003, -5.5, 123456789.123, 2 ** 40]]


def test_import_csv_keeps_text_exact(tmp_path):
    src = tmp_path / "in.csv"
    src.write_bytes("name;amount;note\nأحمد;12;١٢٣\nb;-5.5;$1,234\n".encode("utf-8-sig"))
    out = ns.import_csv(src, tmp_path / "c.numbers")
    assert out["delimiter"] == ";" and out["imported_rows"] == 3
    assert _grid(tmp_path / "c.numbers") == [["name", "amount", "note"], ["أحمد", 12, "١٢٣"], ["b", -5.5, "$1,234"]]


def test_import_csv_all_text(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    ns.import_csv(src, tmp_path / "c.numbers", numbers=False)
    assert _grid(tmp_path / "c.numbers") == [["a", "b"], ["1", "2"]]


# ── insert / delete ──────────────────────────────────────────────────────────

def test_insert_row_in_middle_with_values(book):
    out = ns.insert(book, "rows", 1, at=2, values=[["مكة", 300]], sheet="Sales")
    assert out["op"] == "insert" and Path(out["backup"]).exists()
    assert _grid(book, "Sales") == [["Region", "Revenue"], ["مكة", 300], ["الرياض", 1200], ["جدة", 950.5],
                                    ["الدمام", 700]]
    assert _grid(book, "Other") == [["x", 1]]


def test_append_column(book):
    ns.insert(book, "columns", values=[["Growth", 0.1, 0.2, 0.3]], sheet="Sales")
    assert [r[2] for r in _grid(book, "Sales")] == ["Growth", 0.1, 0.2, 0.3]


def test_delete_rows(book):
    ns.delete(book, "rows", at=2, count=2, sheet="Sales")
    assert _grid(book, "Sales") == [["Region", "Revenue"], ["الدمام", 700]]


def test_delete_column(book):
    ns.delete(book, "columns", at=1, sheet="Sales")
    assert _grid(book, "Sales") == [["Revenue"], [1200], [950.5], [700]]


@pytest.mark.parametrize("call", [
    lambda b: ns.delete(b, "rows", at=1, count=4, sheet="Sales"),       # every row
    lambda b: ns.delete(b, "rows", at=4, count=2, sheet="Sales"),       # past the end
    lambda b: ns.insert(b, "rows", at=9, sheet="Sales"),                # out of range
    lambda b: ns.insert(b, "cells", sheet="Sales"),                     # bad axis
    lambda b: ns.insert(b, "rows", 1, at=2, values=[[1], [2]], sheet="Sales"),  # too many lines
])
def test_bad_requests_leave_file_untouched(book, call):
    before = _sha(book)
    with pytest.raises(ns.StructureError):
        call(book)
    assert _sha(book) == before


def test_formula_tables_only_append(book, monkeypatch):
    monkeypatch.setattr(ns, "_has_formulas", lambda tb: True)
    before = _sha(book)
    with pytest.raises(ns.StructureError, match="formulas"):
        ns.insert(book, "rows", at=2, sheet="Sales")
    assert _sha(book) == before
    ns.insert(book, "rows", sheet="Sales")  # appending is fine
    assert len(_grid(book, "Sales")) == 5


def test_verification_failure_rolls_back(book, monkeypatch):
    real = ns._expect_shift
    monkeypatch.setattr(ns, "_expect_shift", lambda *a: {k: v for k, v in real(*a).items()} | {(1, 0): (1, 0)})
    before = _sha(book)
    with pytest.raises(WriteVerificationError):
        ns.insert(book, "rows", at=2, sheet="Sales")
    assert _sha(book) == before


# ── add table / templates ────────────────────────────────────────────────────

def test_add_table_to_existing_and_new_sheet(book):
    ns.add_table(book, "Extra", [["k"], [9]], sheet="Sales")
    ns.add_table(book, "New", [["a", "b"], [1, 2]], new_sheet="Fresh")
    m = read_numbers(book)
    names = {(s["name"], t["name"]) for s in m["sheets"] for t in s["tables"]}
    assert {("Sales", "Q1"), ("Sales", "Extra"), ("Fresh", "New"), ("Other", "T")} <= names
    assert _grid(book, "Fresh") == [["a", "b"], [1, 2]]
    assert _grid(book, "Sales", "Q1")[1] == ["الرياض", 1200]


def test_add_table_refuses_duplicates(book):
    before = _sha(book)
    with pytest.raises(ns.StructureError):
        ns.add_table(book, "Q1", [["a"]], sheet="Sales")
    with pytest.raises(ns.StructureError):
        ns.add_table(book, "Z", [["a"]], new_sheet="Other")
    assert _sha(book) == before


def test_create_from_template(book, tmp_path):
    out = ns.create_from_template(book, tmp_path / "copy.numbers")
    assert _grid(out["file"], "Sales") == _grid(book, "Sales")
    with pytest.raises(ns.StructureError):
        ns.create_from_template(book, tmp_path / "copy.numbers")
    with pytest.raises(ns.StructureError):
        ns.create_from_template(book, tmp_path / "copy.key")


def test_create_from_keynote_template(tmp_path):
    out = ns.create_from_template(REPO / "tests" / "fixtures" / "arabic.key", tmp_path / "new.key")
    assert Path(out["file"]).exists()


def test_older_parser_artifacts_read_as_written():
    # arabic.numbers holds 34 as 33.999999999999996 (an older numbers-parser write)
    assert _grid(REPO / "tests" / "fixtures" / "arabic.numbers")[1][1] == 34


# ── formulas must survive library re-saves (upstream report: re-save → #REF!) ─

def test_edit_cell_refuses_a_save_that_breaks_a_formula(book, monkeypatch):
    import copy

    from iwork_studio import numbers_io as nio

    real = nio.read_numbers
    calls = {"n": 0}

    def fake(path):
        calls["n"] += 1
        m = copy.deepcopy(real(path))
        cell = next(c for c in m["sheets"][0]["tables"][0]["cells"] if c["ref"] == "R4C2")
        cell["formula"] = "SUM(B2:B3)" if calls["n"] == 1 else "#REF!"
        return m

    monkeypatch.setattr(nio, "read_numbers", fake)
    before = _sha(book)
    with pytest.raises(WriteVerificationError):
        nio.edit_cell(book, "A2", "x", sheet="Sales")
    assert _sha(book) == before


@pytest.mark.aqua
def test_live_formulas_survive_library_writes(book):
    """A formula made by Numbers must come through every no-app write intact."""
    from iwork_studio import app_ops, numbers_format
    from iwork_studio.numbers_io import edit_cell

    def formula():
        t = Document(str(book)).sheets["Sales"].tables[0]
        c = t.cell(4, 1)
        return c.formula if c.is_formula else None

    ns.insert(book, "rows", values=[["Total", None]], sheet="Sales")
    app_ops.set_formula(book, "B5", "=SUM(B2:B4)", sheet="Sales")
    f0 = formula()
    assert f0 and "REF" not in f0

    edit_cell(book, "B2", 2000, sheet="Sales")
    numbers_format.set_cell_style(book, "A1:B1", bold=True, sheet="Sales")
    numbers_format.set_number_format(book, "B2:B5", "currency", currency_code="SAR", sheet="Sales")
    ns.insert(book, "columns", values=[["Note"]], sheet="Sales")
    assert formula() == f0

    # Numbers still computes it from the edited value: 2000 + 950.5 + 700
    out = app_ops.set_formula(book, "C5", "=B5", sheet="Sales")
    assert abs(out["result"] - 3650.5) < 1e-9
