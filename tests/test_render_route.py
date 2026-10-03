"""Numbers render route — the exact command sent to the app (headless).

The AppleScript `front document` form timed out on Numbers Creator Studio
(live, 2026-10-02); the JXA open → export → close form passed for Keynote
and Pages Creator Studio. Pin the Numbers route to that form.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import render_verify  # noqa: E402


@pytest.fixture()
def captured(monkeypatch, tmp_path):
    calls = []

    class R:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        Path(cmd[-1]).write_bytes(b"%PDF-1.4\n")  # the "export"
        return R()

    monkeypatch.setattr(render_verify, "_assert_aqua", lambda: None)
    monkeypatch.setattr(render_verify.subprocess, "run", fake_run)
    monkeypatch.setattr(render_verify, "app_name", lambda app: "Numbers Creator Studio")
    return calls


def test_numbers_export_uses_jxa_document_object(numbers_file, tmp_path, captured):
    pdf = render_verify.render_pdf(numbers_file, out_dir=tmp_path / "out")
    cmd, kw = captured[0]
    assert cmd[:4] == ["osascript", "-l", "JavaScript", "-e"]
    script = cmd[4]
    assert 'Application("Numbers Creator Studio")' in script
    assert "app.open(Path(argv[0]))" in script
    assert "as: 'PDF'" in script and "saving: 'no'" in script and "finally" in script
    assert "front document" not in script and "save in" not in script
    assert cmd[5:] == [str(numbers_file.resolve()), str(pdf)]  # paths via argv, not interpolated
    assert kw["timeout"] >= 90


def test_export_failure_is_loud(numbers_file, tmp_path, monkeypatch, captured):
    class Bad:
        returncode = 1
        stdout = ""
        stderr = "Error: The document could not be exported. (6)"

    monkeypatch.setattr(render_verify.subprocess, "run", lambda cmd, **kw: Bad())
    with pytest.raises(RuntimeError, match=r"\(6\)"):
        render_verify.render_pdf(numbers_file, out_dir=tmp_path / "out")


# ── text-layer matching on pdfminer.six output ───────────────────────────────

def _pdf_with(tmp_path, *lines):
    from reportlab.pdfgen import canvas

    p = tmp_path / "t.pdf"
    c = canvas.Canvas(str(p))
    for i, line in enumerate(lines):
        c.drawString(72, 720 - 20 * i, line)
    c.save()
    return p


def test_text_layer_found_in_real_pdf(tmp_path):
    from iwork_studio import render_verify as rv

    pdf = _pdf_with(tmp_path, "Revenue 2026", "Notes")
    rv.assert_text_layer(pdf, "Revenue")
    rv.assert_page_count(pdf, 1)
    with pytest.raises(AssertionError):
        rv.assert_text_layer(pdf, "Profit")


@pytest.mark.parametrize("layer", [
    "ﺍﻟﺎﺳﻤ",   # الاسم as shaped presentation forms (visual order)
    "مسالا",                              # reversed logical letters
    "ﻻﺳﻤ x",              # lam-alef ligature form
])
def test_arabic_matches_shaped_text_layers(monkeypatch, layer):
    from iwork_studio import pdf as _pdf
    from iwork_studio import render_verify as rv

    monkeypatch.setattr(_pdf, "page_texts", lambda p, password="": [layer])
    rv.assert_text_layer("x.pdf", "الاسم" if "x" not in layer else "لاسم")
