"""Numbers formatting writes — headless. Each op: exact readback, nothing else changes."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import numbers_format as nf  # noqa: E402
from iwork_studio.numbers_io import CellRefError, WriteVerificationError  # noqa: E402


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _cell(layout, ref):
    return next(c for c in layout["cells"] if c["ref"] == ref)


def test_dimensions(numbers_file):
    r = nf.set_dimensions(numbers_file, columns={"A": 160, "3": 90}, rows={"1": 32})
    lay = nf.read_layout(numbers_file)
    assert lay["columns"]["A"] == 160 and lay["columns"]["C"] == 90 and lay["rows"]["1"] == 32
    assert Path(r["backup"]).exists()


def test_cell_style_changes_only_requested_attributes(numbers_file):
    before = nf.read_layout(numbers_file)
    nf.set_cell_style(numbers_file, "A1:C1", bold=True, font_color="#FFFFFF", fill_color="#1A7F79",
                      align="center", font_size=12)
    after = nf.read_layout(numbers_file)
    a1 = _cell(after, "A1")["style"]
    assert a1["bold"] and a1["font_color"] == "#ffffff" and a1["bg_color"] == "#1a7f79"
    assert a1["align"] == "center" and a1["font_size"] == 12.0
    assert a1["font_name"] == _cell(before, "A1")["style"]["font_name"]  # untouched attribute kept
    for ref in ("A2", "B2", "C3"):
        assert _cell(after, ref) == _cell(before, ref)  # cells outside the range untouched


def test_arabic_values_untouched_by_styling(numbers_file):
    nf.set_cell_style(numbers_file, "A1:C4", italic=True)
    vals = {c["ref"]: c["value"] for c in nf.read_layout(numbers_file)["cells"]}
    assert vals["A1"] == "الاسم" and vals["A2"] == "أحمد"


def test_currency_format_shows_sar(numbers_file):
    r = nf.set_number_format(numbers_file, "B2:B3", "currency", currency_code="SAR", decimal_places=2)
    assert r["now_shown_as"] == {"B2": "SAR 34.00", "B3": "SAR 3.14"}


def test_borders_outline(numbers_file):
    nf.set_borders(numbers_file, "A1:C3", sides="outline", width=1.5, color="#1A7F79")
    lay = nf.read_layout(numbers_file)
    assert _cell(lay, "A1")["border"]["top"][1] == "#1a7f79"
    assert "border" not in _cell(lay, "B2") or not _cell(lay, "B2")["border"].get("top")


def test_headers_and_merge(numbers_file):
    nf.set_headers(numbers_file, header_rows=1)
    nf.merge_cells(numbers_file, "A4:C4")
    lay = nf.read_layout(numbers_file)
    assert lay["header_rows"] == 1 and lay["merged"] == ["A4:C4"]


@pytest.mark.parametrize("call,err", [
    (lambda f: nf.merge_cells(f, "A2:B2"), nf.FormatError),                         # would hide B2's data
    (lambda f: nf.set_number_format(f, "B2", "currency", currency_code="XYZ"), nf.FormatError),
    (lambda f: nf.set_cell_style(f, "A1:Z99", bold=True), CellRefError),            # out of range
    (lambda f: nf.set_borders(f, "Z9", sides="top"), CellRefError),                 # border bounds (#218)
    (lambda f: nf.set_cell_style(f, "A1", font_color="red"), nf.FormatError),
    (lambda f: nf.set_dimensions(f, columns={"A": 99999}), nf.FormatError),
    (lambda f: nf.set_cell_style(f, "A1"), nf.FormatError),                          # nothing to do
])
def test_bad_requests_change_nothing(numbers_file, call, err):
    before = _sha(numbers_file)
    with pytest.raises(err):
        call(numbers_file)
    assert _sha(numbers_file) == before
    assert not (numbers_file.parent / f"{numbers_file.name}.backups").exists()


def test_silently_dropped_style_is_caught(numbers_file, monkeypatch):
    """#174 shape: a style the library accepts but doesn't persist must fail the readback."""
    from numbers_parser import Style, Table

    real = Table.set_cell_style
    monkeypatch.setattr(Table, "set_cell_style", lambda self, r, c, st: real(self, r, c, Style(bold=True)))
    before = _sha(numbers_file)
    with pytest.raises(WriteVerificationError):
        nf.set_cell_style(numbers_file, "B2", italic=True)
    assert _sha(numbers_file) == before


def test_collateral_change_is_caught(numbers_file, monkeypatch):
    """A mutation that also touches a cell outside the request is refused."""
    from numbers_parser import Table

    real = Table.set_cell_style

    def sneaky(self, r, c, st):
        real(self, r, c, st)
        real(self, 3, 2, st)  # C4 — not requested

    monkeypatch.setattr(Table, "set_cell_style", sneaky)
    before = _sha(numbers_file)
    with pytest.raises(WriteVerificationError, match="C4"):
        nf.set_cell_style(numbers_file, "A1", bold=False, italic=True)
    assert _sha(numbers_file) == before


def test_chart_file_refused(chart_file):
    from iwork_studio.numbers_io import ChartRefusalError

    with pytest.raises(ChartRefusalError):
        nf.set_cell_style(chart_file, "A1", bold=True)


@pytest.mark.aqua
def test_live_render_shows_the_formatting(numbers_file):
    """On a Mac: what the parser wrote is what Numbers actually draws."""
    from iwork_studio import format_check as fc

    nf.set_cell_style(numbers_file, "A3", bold=True, font_color="#C0392B", font_size=16)
    r = fc.verify_format(numbers_file, "Test", color="#C0392B", bold=True, size=16)
    assert r["ok"]
