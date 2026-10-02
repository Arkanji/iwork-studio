#!/usr/bin/env python3
"""Build the chart-container .numbers fixture (GATE-CHART).

Pivot from the original GUI plan (AppleEvents to Numbers time out in
unattended sessions on this box, verified 2026-10-01 — same -1712 class as
Phase A): the fixture is Apple's OWN bundled 21_Simple_Charts template, a
real Numbers-produced document with real chart instances. The .nmbtemplate
package IS a .numbers zip package (same layout); renamed copy is the
fixture. No fabrication: chart data is genuine Numbers output.

Output: tests/fixtures/chart.numbers
Run:    ~/.hermes/iwork-venv/.venv/bin/python tests/make_chart_fixture.py
"""
import shutil
import sys
import warnings
from pathlib import Path

from numbers_parser import Document

REPO = Path(__file__).resolve().parents[1]
SRC = Path(
    "/Applications/Numbers Creator Studio.app/Contents/SharedSupport/Templates/"
    "21_Simple_Charts/Traditional.nmbtemplate"
)
DEST = REPO / "tests" / "fixtures" / "chart.numbers"


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, DEST)
    print(f"copied: {SRC.name} -> {DEST} ({DEST.stat().st_size} bytes)")

    # Verify it carries the chart signal with our detector (both directions).
    # NOTE: numbers-parser cannot OPEN the renamed template as a document
    # (templates omit DataList.iwa/preview.jpg/ViewState that .numbers files
    # carry — verified scripts/compare_packages.py). That is acceptable for
    # the GATE-CHART fixture: edit_cell refuses chart files BEFORE parsing,
    # so the refusal path never reaches Document(). App-openability of the
    # renamed template is NOT verified (no GUI session this run — honest gap).
    sys.path.insert(0, str(REPO / "src"))
    from iwork_studio.numbers_io import contains_charts

    plain = REPO / "tests" / "fixtures" / "arabic.numbers"
    print("contains_charts(chart_fixture):", contains_charts(DEST))
    print("contains_charts(plain fixture):", contains_charts(plain))
    assert contains_charts(DEST), "chart fixture does NOT trip the chart detector — FAIL"
    assert not contains_charts(plain), "plain fixture FALSELY trips the chart detector — FAIL"
    print("OK: fixture trips GATE-CHART detector; plain fixture does not")
    return 0


if __name__ == "__main__":
    sys.exit(main())