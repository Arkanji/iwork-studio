"""Value fidelity on Numbers writes — headless.

The Numbers *app* auto-parses formatted strings ("$1,234.56" → 1234.56) and
locale decimal separators (upstream reports). iWork Studio writes through
numbers-parser, which must store exactly what was asked for: a string stays
a string, Arabic-Indic digits stay Arabic-Indic, numbers stay numbers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import numbers_io  # noqa: E402


def _cell(path, ref_rc: str):
    model = numbers_io.read_numbers(path)
    cells = {c["ref"]: c["value"] for c in model["sheets"][0]["tables"][0]["cells"]}
    return cells[ref_rc]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("$1,234.56", id="currency-string-not-parsed"),
        pytest.param("1.234,56", id="eu-decimal-string"),
        pytest.param("١٢٣٫٤٥", id="arabic-indic-digits"),
        pytest.param("٪١٥", id="arabic-percent"),
        pytest.param("‏مرحبا", id="rtl-mark-kept"),
        pytest.param("=SUM(A1:A2)", id="formula-text-stays-text"),
    ],
)
def test_strings_stored_verbatim(numbers_file, value):
    numbers_io.edit_cell(numbers_file, "B2", value)
    got = _cell(numbers_file, "R2C2")
    assert got == value and isinstance(got, str)


@pytest.mark.parametrize("value", [2500, 3.14, -0.5])
def test_numbers_stay_numbers(numbers_file, value):
    numbers_io.edit_cell(numbers_file, "B2", value)
    assert _cell(numbers_file, "R2C2") == pytest.approx(value)
