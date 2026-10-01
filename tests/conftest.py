"""Phase B test fixtures.

Creates fresh .numbers files by copying verified fixtures generated from
numbers-parser 4.19.0 on this venv (evidence/a3 + evidence/b6). Fixtures are
regenerated into the pytest tmp dir per-test so tests never mutate shared
evidence files.

Fixture provenance:
- numbers_fixture_src     : copy of evidence/a3/roundtrip_a3.numbers
                            (Numbers 15.4 file, sheet 'بيانات', table 'جدول' 4x3,
                            Arabic + English + number cells)
- chart_fixture_src       : copy of evidence/b6/chart_fixture.numbers
                            (built by make_chart_fixture.py via Numbers
                            AppleScript — contains one 2x2 chart)
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NUMBERS_SRC = REPO / "evidence" / "a3" / "roundtrip_a3.numbers"
CHART_SRC = REPO / "evidence" / "b6" / "chart_fixture.numbers"


@pytest.fixture()
def numbers_file(tmp_path) -> Path:
    """A fresh copy of the Arabic+English+numbers 4x3 fixture."""
    dest = tmp_path / "fixture.numbers"
    shutil.copy2(NUMBERS_SRC, dest)
    return dest


@pytest.fixture()
def chart_file(tmp_path) -> Path:
    """A .numbers file containing a chart (for GATE-CHART refusal)."""
    if not CHART_SRC.exists():
        pytest.skip("chart fixture not built (requires Aqua; run make_chart_fixture.py)")
    dest = tmp_path / "chart_fixture.numbers"
    shutil.copy2(CHART_SRC, dest)
    return dest