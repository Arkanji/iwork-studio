"""Keynote theming (theme / layout / text format) — protocol with the app stubbed."""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import keynote_slides as ks, keynote_theme as kt  # noqa: E402

STYLE = {
    "theme": "Basic White",
    "layouts": ["Title", "Title & Bullets", "Blank"],
    "slides": [
        {"slide": 1, "layout": "Title", "items": [
            {"index": 0, "text": "عرض تجريبي", "font": "HelveticaNeue-Bold", "size": 60.0, "color": "#000000"},
            {"index": 1, "text": "Subtitle عرض", "font": "HelveticaNeue", "size": 28.0, "color": "#333333"}]},
        {"slide": 2, "layout": "Title & Bullets", "items": [
            {"index": 0, "text": "Revenue", "font": "HelveticaNeue-Bold", "size": 44.0, "color": "#000000"}]},
    ],
}


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture()
def deck(tmp_path):
    d = tmp_path / "deck.key"
    d.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    return d


@pytest.fixture()
def app(monkeypatch):
    """state["after"] = what the 'app' leaves on disk; calls recorded."""
    state = {"after": None, "calls": [], "mutate": None}
    reads = {"n": 0}

    def fake_read(path):
        reads["n"] += 1
        return copy.deepcopy(STYLE if reads["n"] == 1 or state["after"] is None else state["after"])

    def fake_jxa(body, params, timeout=None):
        state["calls"].append(("jxa", body, params))
        if state["mutate"]:
            state["mutate"](Path(params["path"]))
        return {"ok": True}

    def fake_as(target, body, args):
        state["calls"].append(("as", body, args))
        if state["mutate"]:
            state["mutate"](target)

    monkeypatch.delenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", raising=False)
    monkeypatch.setattr(kt, "read_style", fake_read)
    monkeypatch.setattr(kt, "list_themes", lambda: ["Basic White", "Basic Black", "Gradient"])
    monkeypatch.setattr(ks, "_jxa", fake_jxa)
    monkeypatch.setattr(kt, "_applescript_op", fake_as)
    return state


def _after(**edits):
    a = copy.deepcopy(STYLE)
    for fn in edits.values():
        fn(a)
    return a


# ── theme ────────────────────────────────────────────────────────────────────

def test_set_theme_ok(deck, app):
    app["after"] = _after(t=lambda a: a.update(theme="Basic Black"))
    r = kt.set_theme(deck, "Basic Black")
    assert r["ok"] and r["previous_theme"] == "Basic White"


def test_unknown_theme_refused_before_backup(deck, app):
    with pytest.raises(kt.ThemeError, match="available"):
        kt.set_theme(deck, "Neon")
    assert app["calls"] == [] and not (deck.parent / "deck.key.backups").exists()


def test_theme_that_loses_text_rolls_back(deck, app):
    original = _sha(deck)

    def lose(a):
        a["theme"] = "Basic Black"
        a["slides"][1]["items"] = []

    app["after"] = _after(x=lose)
    app["mutate"] = lambda p: p.write_bytes(b"garbage")
    with pytest.raises(ks.SlideOpVerificationError, match="text lost"):
        kt.set_theme(deck, "Basic Black")
    assert _sha(deck) == original


def test_theme_silently_not_applied_rolls_back(deck, app):
    app["after"] = copy.deepcopy(STYLE)  # app said ok, nothing changed
    with pytest.raises(ks.SlideOpVerificationError, match="theme reads"):
        kt.set_theme(deck, "Basic Black")


# ── layout ───────────────────────────────────────────────────────────────────

def test_set_layout_goes_through_applescript(deck, app):
    app["after"] = _after(l=lambda a: a["slides"][1].update(layout="Blank"))
    r = kt.set_slide_layout(deck, 2, "Blank")
    kind, body, args = app["calls"][0]
    assert kind == "as" and "set base slide of slide" in body and args == [2, "Blank"]
    assert r["previous_layout"] == "Title & Bullets"


def test_layout_collateral_change_rolls_back(deck, app):
    def both(a):
        a["slides"][1]["layout"] = "Blank"
        a["slides"][0]["layout"] = "Blank"  # touched slide 1 too

    app["after"] = _after(x=both)
    with pytest.raises(ks.SlideOpVerificationError, match="slide 1 changed"):
        kt.set_slide_layout(deck, 2, "Blank")


@pytest.mark.parametrize("args", [(9, "Blank"), (1, "Nope")])
def test_layout_bad_request(deck, app, args):
    with pytest.raises(kt.ThemeError):
        kt.set_slide_layout(deck, *args)
    assert app["calls"] == []


# ── text format ──────────────────────────────────────────────────────────────

def test_format_text_by_match(deck, app):
    app["after"] = _after(f=lambda a: a["slides"][1]["items"][0].update(color="#1a7f79", size=48.0))
    r = kt.format_text(deck, 2, match="Revenue", color="#1A7F79", size=48)
    _, body, params = app["calls"][0]
    assert "ot.color = params.rgb" in body and params["rgb"] == [0x1A * 257, 0x7F * 257, 0x79 * 257]
    assert r["item"] == 0 and r["color"] == "#1a7f79"


def test_colour_written_on_wrong_scale_is_caught(deck, app):
    """The trap from the field: 0–1 floats into a 0–65535 property → near-black."""
    app["after"] = _after(f=lambda a: a["slides"][1]["items"][0].update(color="#000000"))
    with pytest.raises(ks.SlideOpVerificationError, match="colour reads"):
        kt.format_text(deck, 2, item=0, color="#1A7F79")


def test_format_other_item_touched_rolls_back(deck, app):
    def both(a):
        a["slides"][0]["items"][0]["size"] = 30.0
        a["slides"][0]["items"][1]["size"] = 30.0

    app["after"] = _after(x=both)
    with pytest.raises(ks.SlideOpVerificationError, match="another text item"):
        kt.format_text(deck, 1, item=0, size=30)


def test_arabic_match_and_ambiguity(deck, app):
    app["after"] = _after(f=lambda a: a["slides"][0]["items"][0].update(font="IBMPlexSansArabic-Bold"))
    assert kt.format_text(deck, 1, match="تجريبي", font="IBMPlexSansArabic-Bold")["ok"]
    app["after"] = None
    with pytest.raises(kt.ThemeError, match="need exactly one"):
        kt.format_text(deck, 1, match="عرض", size=20)  # in both items


@pytest.mark.parametrize("kw", [{}, {"color": "teal"}, {"size": 1000}])
def test_format_bad_request(deck, app, kw):
    with pytest.raises(kt.ThemeError):
        kt.format_text(deck, 1, item=0, **kw)


def test_colour_normalisation():
    assert kt._color_hex([0x1A * 257, 0x7F * 257, 0x79 * 257]) == "#1a7f79"
    assert kt._color_hex([0x1A / 255, 0x7F / 255, 0x79 / 255]) == "#1a7f79"
    assert kt._color_hex(None) is None


@pytest.mark.aqua
def test_live_theme_layout_format(deck, monkeypatch):
    monkeypatch.delenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", raising=False)
    style = kt.read_style(deck)
    other = next(t for t in kt.list_themes() if t != style["theme"])
    assert kt.set_theme(deck, other)["ok"]
    style = kt.read_style(deck)
    target = next(name for name in style["layouts"] if name != style["slides"][0]["layout"])
    assert kt.set_slide_layout(deck, 1, target)["ok"]
    assert kt.format_text(deck, 1, item=0, color="#1A7F79", size=40)["ok"]
