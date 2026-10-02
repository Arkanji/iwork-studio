#!/usr/bin/env python3
"""Build the chart-container .key fixture (GATE-CHART, C4).

Live Keynote `add chart` AppleScript (verified dictionary support, sdef
enumeration legacy chart type): create a fresh deck, add one 2D bar chart,
save IN-PLACE (GATE-SAVE), close, then verify with our detector BOTH ways:
  - detector(charts fixture) must be True
  - detector(plain fixture tests/fixtures/arabic.key) must be False

Output: tests/fixtures/chart.key
Run:    ~/.hermes/iwork-venv/.venv/bin/python tests/make_chart_key_fixture.py
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEST = REPO / "tests" / "fixtures" / "chart.key"

JXA_MAKE = """ (() => {
  const app = Application('Keynote');
  const doc = app.Document();
  app.documents.push(doc);
  // one slide with a title so the deck is honest, then add a chart
  const slide = doc.slides[0];
  slide.textItems[0].objectText = 'مخططات الاختبار';
  app.addChart(slide, {columnNames: ['الربع الأول', 'الربع الثاني'],
                       rowNames: ['الإيرادات'],
                       data: [[10.0, 20.0]]});
  return 'created';
})()
"""


def jxa(script, timeout=300):
    r = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        DEST.unlink()

    rc, out, err = jxa(JXA_MAKE)
    print("add chart rc:", rc, out, err[:200] if err else "")
    if rc != 0:
        print("FAILED to create chart deck")
        return 1

    # The new untitled document: save in-place is impossible (no path yet),
    # so export is not applicable either. Keynote JXA: `save` an unsaved
    # document requires `save in`... which is the GATE-SAVE trap for
    # sandboxed saves to arbitrary paths. But this run is NOT inside the
    # Keynote sandbox: osascript runs as the user, and `save in` here is
    # the standard documented way to give an untitled document its path.
    # The GATE-SAVE trap (verified denial) applies to saves from WITHIN the
    # app sandbox. We save directly to tests/fixtures, then close.
    script = f"""
(() => {{
  const app = Application('Keynote');
  const doc = app.documents[0];
  app.save(doc, {{in: Path({str(DEST)!r})}});
  app.close(doc, {{saving: 'no'}});
  return 'saved';
}})()
"""
    rc, out, err = jxa(script)
    print("save rc:", rc, out, err[:300] if err else "")
    if rc != 0 or not DEST.exists():
        print("FAILED to save chart deck to", DEST)
        return 1
    print(f"saved: {DEST} ({DEST.stat().st_size} bytes)")

    sys.path.insert(0, str(REPO / "src"))
    from iwork_studio.keynote_io import contains_charts

    plain = REPO / "tests" / "fixtures" / "arabic.key"
    c1 = contains_charts(DEST)
    c2 = contains_charts(plain)
    print("contains_charts(chart_fixture):", c1)
    print("contains_charts(plain fixture):", c2)
    assert c1, "chart fixture does NOT trip the detector — FAIL"
    assert not c2, "plain fixture FALSELY trips the detector — FAIL"
    print("OK: chart fixture trips GATE-CHART; plain fixture does not")
    return 0


if __name__ == "__main__":
    sys.exit(main())