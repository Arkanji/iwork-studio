"""Deck building and slide text — the Keynote app stubbed."""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import app_ops, keynote_deck as kd, keynote_io, keynote_slides as ks, keynote_theme as kt  # noqa: E402


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _item(i, text, y, area):
    return {"index": i, "text": text, "font": "Helvetica", "size": 30.0, "color": "#000000", "y": y, "area": area}


STYLE = {"theme": "Basic White", "layouts": ["Title", "Title & Bullets", "Blank"], "slides": [
    {"slide": 1, "layout": "Title", "items": [_item(0, "Old title", 300, 9000), _item(1, "Sub", 420, 5000)]},
    {"slide": 2, "layout": "Title & Bullets", "items": [_item(0, "", 600, 90000), _item(1, "", 40, 8000)]},
]}


def test_pick_roles_by_position():
    assert kd.pick_roles(STYLE["slides"][1]["items"]) == {"title": 1, "body": 0}  # body box listed first
    assert kd.pick_roles([_item(0, "", 100, 10)]) == {"title": 0, "body": None}
    assert kd.pick_roles([]) == {"title": None, "body": None}


def test_one_box_layout_refuses_title_and_body():
    with pytest.raises(kd.DeckError, match="one text box"):
        kd._assign([_item(0, "", 100, 10)], "T", "B", "slide 1")
    assert kd._assign([_item(0, "", 100, 10)], None, "B", "slide 1") == {0: "B"}


@pytest.fixture()
def deck(tmp_path, monkeypatch):
    d = tmp_path / "deck.key"
    d.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    state = {"after": None, "reads": 0, "jxa": []}

    def read(path):
        state["reads"] += 1
        return copy.deepcopy(STYLE if state["reads"] == 1 else state["after"])

    def jxa(body, params, timeout=None):
        state["jxa"].append(params)
        Path(params["path"]).write_bytes(b"app wrote this")
        return {"ok": True}

    monkeypatch.delenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", raising=False)
    monkeypatch.setattr(kt, "read_style", read)
    monkeypatch.setattr(ks, "_jxa", jxa)
    monkeypatch.setattr(keynote_io, "read_key", lambda p: {})
    return d, state


def test_set_slide_text_ok(deck):
    d, state = deck
    after = copy.deepcopy(STYLE)
    after["slides"][1]["items"][1]["text"] = "الإيرادات"
    after["slides"][1]["items"][0]["text"] = "نمو\rربح"
    state["after"] = after
    out = kd.set_slide_text(d, 2, title="الإيرادات", body=["نمو", "ربح"])
    assert out["ok"]
    assert state["jxa"][0]["specs"] == [{"n": 2, "texts": {"1": "الإيرادات", "0": "نمو\nربح"}, "notes": None}]


def test_set_slide_text_wrong_box_rolls_back(deck):
    d, state = deck
    before = _sha(d)
    after = copy.deepcopy(STYLE)
    after["slides"][1]["items"][0]["text"] = "الإيرادات"  # landed in the body box
    state["after"] = after
    with pytest.raises(ks.SlideOpVerificationError):
        kd.set_slide_text(d, 2, title="الإيرادات")
    assert _sha(d) == before


def test_set_slide_text_other_slide_changed_rolls_back(deck):
    d, state = deck
    before = _sha(d)
    after = copy.deepcopy(STYLE)
    after["slides"][1]["items"][1]["text"] = "T"
    after["slides"][0]["items"][0]["text"] = "changed"
    state["after"] = after
    with pytest.raises(ks.SlideOpVerificationError):
        kd.set_slide_text(d, 2, title="T")
    assert _sha(d) == before


# ── build_deck ───────────────────────────────────────────────────────────────

@pytest.fixture()
def builder(tmp_path, monkeypatch):
    state = {"as": None, "specs": None, "notes_ok": True, "corrupt": False}
    blank = {"slide": 1, "layout": "Title", "items": [_item(0, "", 300, 9000), _item(1, "", 420, 5000)]}
    content = {"layout": "Title & Bullets", "items": [_item(0, "", 600, 90000), _item(1, "", 40, 8000)]}

    def create(path, template=None):
        Path(path).write_bytes(b"new deck")
        return {"ok": True, "file": str(path), "template": template or "Basic White"}

    def shaped(n, layouts):
        sl = [dict(copy.deepcopy(blank), layout=layouts[0])]
        sl += [dict(copy.deepcopy(content), slide=i, layout=layouts[i - 1]) for i in range(2, n + 1)]
        return {"theme": "Basic White", "layouts": ["Title", "Title & Bullets", "Blank"], "slides": sl}

    def read(path):
        if state["as"] is None:
            return {"theme": "Basic White", "layouts": ["Title", "Title & Bullets", "Blank"], "slides": [blank]}
        st = shaped(state["as"][0], state["as"][1:])
        if state["specs"]:
            for sp in state["specs"]:
                for k, v in sp["texts"].items():
                    st["slides"][sp["n"] - 1]["items"][int(k)]["text"] = v.replace("\n", "\r")
            if state["corrupt"]:
                st["slides"][-1]["items"][1]["text"] = "wrong"
        return st

    def run_as(target, body, args):
        state["as"] = args

    def jxa(body, params, timeout=None):
        state["specs"] = params["specs"]
        return {"ok": True}

    def notes(path):
        return [{"notes": sp["notes"] if state["notes_ok"] else ""} for sp in state["specs"]]

    monkeypatch.setattr(app_ops, "create_document", create)
    monkeypatch.setattr(kt, "read_style", read)
    monkeypatch.setattr(kt, "_applescript_op", run_as)
    monkeypatch.setattr(ks, "_jxa", jxa)
    monkeypatch.setattr(ks, "read_slides", notes)
    return tmp_path, state


OUTLINE = [{"title": "رسال", "body": "البنية التحتية للقيمة غير النقدية"},
           {"title": "Revenue", "body": ["Q1 up 20%", "Q2 up 35%"], "notes": "ملاحظات"},
           {"title": "Next", "body": ["Launch", "Scale"]}]


def test_build_deck_ok(builder):
    tmp, state = builder
    out = kd.build_deck(tmp / "pitch.key", OUTLINE, theme="Basic White")
    assert out["ok"] and out["layouts"] == ["Title", "Title & Bullets", "Title & Bullets"]
    assert state["as"] == [3, "Title", "Title & Bullets", "Title & Bullets"]
    assert state["specs"][1]["texts"] == {"1": "Revenue", "0": "Q1 up 20%\nQ2 up 35%"}


def test_build_deck_mismatch_removes_new_file(builder):
    tmp, state = builder
    state["corrupt"] = True
    with pytest.raises(ks.SlideOpVerificationError):
        kd.build_deck(tmp / "pitch.key", OUTLINE)
    assert not (tmp / "pitch.key").exists()


def test_build_deck_notes_checked(builder):
    tmp, state = builder
    state["notes_ok"] = False
    with pytest.raises(ks.SlideOpVerificationError, match="notes"):
        kd.build_deck(tmp / "pitch.key", OUTLINE)
    assert not (tmp / "pitch.key").exists()


@pytest.mark.parametrize("slides,kw,msg", [
    ([], {}, "1–200"),
    ([{}], {}, "at least"),
    ([{"title": "x", "image": "/nope.png"}], {}, "not found"),
    ([{"title": "x"}], {"transition": "explode"}, "transition"),
])
def test_build_deck_bad_outline(builder, slides, kw, msg):
    tmp, _ = builder
    with pytest.raises(kd.DeckError, match=msg):
        kd.build_deck(tmp / "x.key", slides, **kw)
    assert not (tmp / "x.key").exists()


def test_build_deck_refuses_existing(builder):
    tmp, _ = builder
    (tmp / "x.key").write_bytes(b"mine")
    with pytest.raises(kd.DeckError, match="exists"):
        kd.build_deck(tmp / "x.key", OUTLINE)
    assert (tmp / "x.key").read_bytes() == b"mine"


def test_unknown_layout(builder):
    tmp, _ = builder
    with pytest.raises(kd.DeckError, match="unknown layout"):
        kd.build_deck(tmp / "x.key", [{"title": "a", "layout": "Nope"}])
    assert not (tmp / "x.key").exists()


@pytest.mark.aqua
def test_live_build_deck_and_set_text(tmp_path):
    out = kd.build_deck(tmp_path / "pitch.key", OUTLINE, transition="dissolve")
    assert out["ok"] and out["slides"] == 3
    assert kd.set_slide_text(tmp_path / "pitch.key", 3, title="الخطوات التالية", body=["إطلاق", "توسع"])["ok"]
