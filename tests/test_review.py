"""Design review: rendered text lines checked against their boxes (pure analysis + stubbed app)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import review  # noqa: E402


def _box(text, x, y, w, h, font="HelveticaNeue"):
    return {"text": text, "x": x, "y": y, "w": w, "h": h, "font": font, "size": 40.0}


def _line(text, x0, top, x1, bottom, size=40.0):
    return {"text": text, "x0": x0, "top": top, "x1": x1, "bottom": bottom, "size": size}


def _style(*slides, w=1920, h=1080):
    return {"width": w, "height": h, "slides": [dict(s, slide=i) for i, s in enumerate(slides, start=1)]}


def _page(*lines, w=1920, h=1080):
    return {"width": w, "height": h, "lines": list(lines)}


def kinds(findings):
    return sorted((f["slide"], f["kind"]) for f in findings)


def test_clean_slide_has_no_findings():
    st = _style({"items": [_box("Revenue doubled", 100, 80, 1700, 160), _box("Q1 up 20%", 100, 300, 1700, 600)],
                 "title_box": {"text": "Revenue doubled"}, "body_box": {"text": "Q1 up 20%"}})
    pg = _page(_line("Revenue doubled", 110, 100, 900, 180, 88), _line("Q1 up 20%", 110, 320, 500, 360, 32))
    assert review.analyse(st, [pg]) == []


def test_overflow_past_box_bottom():
    body = "one two three four five six seven eight"
    st = _style({"items": [_box(body, 100, 300, 800, 100)]})
    pg = _page(_line("one two three four", 110, 310, 800, 350, 32), _line("five six seven eight", 110, 400, 800, 460, 32))
    f = review.analyse(st, [pg])
    assert kinds(f) == [(1, "overflow")] and f[0]["severity"] == "error" and "60 pt" in f[0]["message"]


def test_off_slide_edge():
    st = _style({"items": [_box("Runs off the edge", 1800, 1000, 400, 60)]})
    pg = _page(_line("Runs off the edge", 1800, 998, 2115, 1038))
    assert (1, "off_slide") in kinds(review.analyse(st, [pg]))


def test_overlapping_boxes():
    st = _style({"items": [_box("Big headline here", 100, 100, 1000, 200), _box("Caption text", 120, 120, 900, 100)]})
    pg = _page(_line("Big headline here", 110, 110, 900, 190, 80), _line("Caption text", 130, 130, 700, 170, 30))
    assert kinds(review.analyse(st, [pg])) == [(1, "overlap")]


def test_small_text_scaled_to_page():
    st = _style({"items": [_box("Footnote", 100, 700, 600, 40)]}, w=1024, h=768)
    # 1024-wide slide: 18 pt on 1920 → 9.6 pt here
    assert kinds(review.analyse(st, [_page(_line("Footnote", 100, 700, 300, 710, 9.0), w=1024, h=768)])) == [(1, "small_text")]
    assert review.analyse(st, [_page(_line("Footnote", 100, 700, 300, 712, 12.0), w=1024, h=768)]) == []


def test_dense_slide_and_long_title():
    body = "\r".join(f"Point {i}" for i in range(8))
    title = "This title rambles on and on with far too many words to state one clear takeaway"
    st = _style({"items": [], "title_box": {"text": title}, "body_box": {"text": body}})
    assert kinds(review.analyse(st, [_page()])) == [(1, "dense"), (1, "dense")]


def test_arabic_lines_match_their_box_despite_reordering():
    text = "الإيرادات تضاعفت هذا العام"
    st = _style({"items": [_box(text, 100, 300, 800, 60)]})
    reordered = " ".join(reversed(text.split()))  # PDF text layers reorder RTL runs
    pg = _page(_line(reordered, 110, 310, 800, 350, 40), _line("العام", 110, 400, 300, 450, 40))
    f = review.analyse(st, [pg])
    assert kinds(f) == [(1, "overflow")]


def test_duplicate_placeholder_boxes_ignored():
    b = _box("Plan", 100, 80, 1700, 160)
    st = _style({"items": [b, dict(b)]})
    assert review.analyse(st, [_page(_line("Plan", 110, 100, 400, 180, 80))]) == []


def test_too_many_fonts_is_info():
    st = _style({"items": [_box("a", 0, 0, 10, 10, f) for f in ("HelveticaNeue", "AvenirNext-Regular", "Baskerville", "GeezaPro")]})
    f = review.analyse(st, [_page()])
    assert [(x["kind"], x["severity"]) for x in f] == [("fonts", "info")]


def test_review_deck_skipped_slides_lined_up(monkeypatch, tmp_path):
    from iwork_studio import keynote_applescript, keynote_slides as ks, keynote_theme as kt, pdf

    d = tmp_path / "d.key"
    d.write_bytes(b"deck")
    st = _style({"items": [_box("One", 100, 100, 500, 100)]}, {"items": [_box("Hidden", 100, 100, 500, 100)]},
                {"items": [_box("Three", 100, 100, 500, 100)]})
    monkeypatch.setattr(kt, "read_style", lambda p: st)
    monkeypatch.setattr(keynote_applescript, "render_pdf", lambda p, out_dir=None: Path(out_dir) / "x.pdf")
    monkeypatch.setattr(pdf, "lines", lambda p: [_page(_line("One", 110, 110, 300, 150)), _page(_line("Three", 110, 110, 300, 150))])
    monkeypatch.setattr(ks, "read_slides", lambda p: [{"skipped": False}, {"skipped": True}, {"skipped": False}])
    out = review.review_deck(d)
    assert out["ok"] and out["slides"] == 3 and out["slides_reviewed"] == 2 and d.read_bytes() == b"deck"


def test_slide_image_bad_args(tmp_path):
    with pytest.raises(review.ReviewError, match="1-based"):
        review.slide_image(tmp_path / "d.key", 0)
    with pytest.raises(review.ReviewError, match="width"):
        review.slide_image(tmp_path / "d.key", 1, width=5000)


@pytest.mark.aqua
def test_live_review_flags_overflow(tmp_path):
    from iwork_studio import keynote_deck as kd

    long = " ".join(["Programmable value for every business, everywhere, every day."] * 12)
    kd.build_deck(tmp_path / "r.key", [{"title": "Clean"}, {"title": "Too much", "body": long}])
    out = review.review_deck(tmp_path / "r.key")
    assert out["slides"] == 2 and any(f["slide"] == 2 for f in out["findings"])
    assert review.slide_image(tmp_path / "r.key", 1)[:2] == b"\xff\xd8"  # JPEG
