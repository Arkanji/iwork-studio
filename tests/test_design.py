"""Design kits: contrast-checked palettes, Arabic-aware fonts, applied under the write protocol."""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import design, keynote_io, keynote_slides as ks, keynote_theme as kt, numbers_structure as ns  # noqa: E402
from iwork_studio.numbers_format import read_layout  # noqa: E402


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.mark.parametrize("name", sorted(design.KITS))
def test_every_kit_meets_wcag_aa(name):
    k = design.KITS[name]
    c, bg = k["colors"], k["background"]
    assert design.contrast(c["title"], bg) >= 4.5
    assert design.contrast(c["body"], bg) >= 4.5
    assert design.contrast(c["header_text"], c["header_fill"]) >= 4.5
    assert design.contrast(c.get("table_text", c["body"]), c["band"]) >= 4.5
    assert {"heading", "body", "heading_ar", "body_ar", "family", "family_ar"} <= set(k["fonts"])


def test_numbers_knows_every_kit_family():
    from numbers_parser.model import FONT_FAMILY_TO_NAME

    for k in design.KITS.values():
        assert k["fonts"]["family"] in FONT_FAMILY_TO_NAME and k["fonts"]["family_ar"] in FONT_FAMILY_TO_NAME


def test_contrast_values():
    assert design.contrast("#000000", "#FFFFFF") == 21.0
    assert design.contrast("#777777", "#777777") == 1.0


def test_custom_kit_is_contrast_checked():
    with pytest.raises(design.DesignError, match="contrast"):
        design.get_kit({"colors": {"title": "#EEEEEE"}})
    with pytest.raises(design.DesignError, match="#RRGGBB"):
        design.get_kit({"colors": {"accent": "teal"}})
    k = design.get_kit({"name": "brand", "colors": {"title": "#0B1F3A", "accent": "#2DD4BF"}})
    assert k["colors"]["title"] == "#0B1F3A" and k["fonts"]["family"] == "Helvetica Neue"


def test_unknown_kit():
    with pytest.raises(design.DesignError, match="unknown kit"):
        design.get_kit("neon")


@pytest.fixture()
def table(tmp_path):
    p = tmp_path / "t.numbers"
    ns.create(p, [{"name": "S", "tables": [{"name": "T", "rows": [
        ["المنطقة", "Revenue", "Growth"], ["الرياض", 1200, 0.1], ["Jeddah", 950.5, 0.2], ["الدمام", 700, 0.3]]}]}])
    return p


def test_numbers_design_applied(table):
    out = design.apply_to_numbers(table, "banking")
    assert out["number_columns"] == ["B", "C"] and Path(out["backup"]).exists()
    cells = {c["ref"]: c for c in read_layout(table)["cells"]}
    assert cells["B1"]["style"]["bold"] and cells["B1"]["style"]["bg_color"] == "#1e3a8a"
    assert cells["A2"]["style"]["font_name"] == "Damascus"  # Arabic cell → Arabic family
    assert cells["A3"]["style"]["font_name"] == "Avenir Next" and cells["A3"]["style"]["bg_color"] == "#f8fafc"
    assert cells["B2"]["style"]["align"] == "right"
    assert [cells[r]["value"] for r in ("A2", "B2", "C3")] == ["الرياض", 1200, 0.2]  # values untouched


def test_numbers_design_no_banding(table):
    design.apply_to_numbers(table, "executive", banding=False)
    cells = {c["ref"]: c for c in read_layout(table)["cells"]}
    assert "bg_color" not in cells["A3"]["style"]


# ── Keynote (app stubbed) ────────────────────────────────────────────────────

def _item(i, text, y, area, font="Helvetica", size=30.0, color="#000000"):
    return {"index": i, "text": text, "font": font, "size": size, "color": color, "y": y, "area": area}


STYLE = {"theme": "Basic White", "layouts": ["Title", "Title & Bullets"], "slides": [
    {"slide": 1, "layout": "Title", "items": [_item(0, "رسال", 300, 9000), _item(1, "Programmable value", 420, 5000)]},
    {"slide": 2, "layout": "Title & Bullets", "items": [_item(0, "Growth\rScale", 600, 90000), _item(1, "Plan", 40, 8000)]},
]}


def _designed(kit="executive", break_font=False):
    k = design.get_kit(kit)
    a = copy.deepcopy(STYLE)
    fill = {(1, 0): ("GeezaPro-Bold", 88, "title"), (1, 1): ("HelveticaNeue", 32, "body"),
            (2, 0): ("HelveticaNeue", 28, "body"), (2, 1): ("HelveticaNeue-Bold", 52, "title")}
    for s in a["slides"]:
        for it in s["items"]:
            f, size, role = fill[(s["slide"], it["index"])]
            it.update(font=f, size=float(size), color=k["colors"][role].lower())
    if break_font:
        a["slides"][1]["items"][1]["font"] = "Helvetica"
    return a


@pytest.fixture()
def deck(tmp_path, monkeypatch):
    d = tmp_path / "d.key"
    d.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    state = {"after": None, "reads": 0, "params": None}

    def read(path):
        state["reads"] += 1
        return copy.deepcopy(STYLE if state["reads"] == 1 else state["after"])

    def jxa(body, params, timeout=None):
        state["params"] = params
        Path(params["path"]).write_bytes(b"app wrote this")
        return {"ok": True}

    monkeypatch.delenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", raising=False)
    monkeypatch.setattr(kt, "read_style", read)
    monkeypatch.setattr(ks, "_jxa", jxa)
    monkeypatch.setattr(keynote_io, "read_key", lambda p: {})
    return d, state


def test_keynote_design_ok(deck):
    d, state = deck
    state["after"] = _designed()
    out = design.apply_to_keynote(d, "executive", set_theme=False)
    assert out["ok"] and out["text_boxes"] == 4
    sp1, sp2 = state["params"]["specs"]
    assert sp1["title_ar"] == {"font": "GeezaPro-Bold", "size": 88, "rgb": kt._rgb16("#0F172A")}  # title slide
    assert sp2["title_lat"]["font"] == "HelveticaNeue-Bold" and sp2["title_lat"]["size"] == 52
    assert sp2["body_lat"]["size"] == 28 and sp2["other_lat"]["size"] is None


def test_keynote_design_survives_text_box_reordering(deck):
    d, state = deck
    a = _designed()
    for sl in a["slides"]:  # Keynote lists the boxes in another order next session (trap L4)
        sl["items"].reverse()
        for n, it in enumerate(sl["items"]):
            it["index"] = n
    state["after"] = a
    assert design.apply_to_keynote(d, "executive", set_theme=False)["ok"]


def test_keynote_design_missing_font_rolls_back(deck):
    d, state = deck
    before = _sha(d)
    state["after"] = _designed(break_font=True)
    with pytest.raises(ks.SlideOpVerificationError, match="installed"):
        design.apply_to_keynote(d, "executive", set_theme=False)
    assert _sha(d) == before


def test_keynote_design_text_change_rolls_back(deck):
    d, state = deck
    before = _sha(d)
    a = _designed()
    a["slides"][1]["items"][0]["text"] = "lost"
    state["after"] = a
    with pytest.raises(ks.SlideOpVerificationError):
        design.apply_to_keynote(d, "executive", set_theme=False)
    assert _sha(d) == before


@pytest.mark.aqua
def test_live_designed_deck(tmp_path):
    from iwork_studio import keynote_deck

    out = keynote_deck.build_deck(tmp_path / "designed.key", [
        {"title": "رسال", "body": "البنية التحتية البرمجية للقيمة غير النقدية"},
        {"title": "Why now", "body": ["Programmable value", "Trust by design", "Access for everyone"]},
    ], kit="midnight")
    assert out["ok"] and out["kit"] == "midnight"


@pytest.mark.aqua
def test_live_designed_table(table):
    assert design.apply_to_numbers(table, "teal")["ok"]


def _with_boxes(a, title_font="HelveticaNeue-Bold"):
    """Keynote reports its own title/body boxes (the normal case on a Mac)."""
    k = design.get_kit("executive")
    a["slides"][1]["title_box"] = {"text": "Plan", "font": title_font, "size": 52.0, "color": k["colors"]["title"].lower()}
    a["slides"][1]["body_box"] = {"text": "Growth\rScale", "font": "HelveticaNeue", "size": 28.0,
                                  "color": k["colors"]["body"].lower()}
    return a


def test_keynote_design_checks_keynotes_own_boxes(deck):
    d, state = deck
    state["after"] = _with_boxes(_designed())
    assert design.apply_to_keynote(d, "executive", set_theme=False)["ok"]


def test_keynote_design_title_box_wrong_rolls_back(deck):
    d, state = deck
    before = _sha(d)
    state["after"] = _with_boxes(_designed(), title_font="Helvetica")
    with pytest.raises(ks.SlideOpVerificationError, match="title"):
        design.apply_to_keynote(d, "executive", set_theme=False)
    assert _sha(d) == before


# ── Brand kits: extract from your own file, save by name ──────────────────────


@pytest.fixture()
def kits_dir(tmp_path, monkeypatch):
    d = tmp_path / "kits"
    monkeypatch.setenv("IWORK_STUDIO_KITS_DIR", str(d))
    return d


def test_extract_kit_from_styled_table(table, kits_dir):
    design.apply_to_numbers(table, "banking")
    before = _sha(table)
    out = design.extract_kit(table, name="Brand")
    k = out["kit"]
    assert _sha(table) == before  # the file is never changed
    assert k["colors"]["header_fill"] == "#1E3A8A" and k["colors"]["title"] == "#1E3A8A"
    assert k["fonts"]["family"] == "Avenir Next" and k["fonts"]["family_ar"] == "Damascus"
    assert k["fonts"]["heading"].startswith("AvenirNext") and "Bold" in k["fonts"]["heading"]
    assert out["contrast_ok"] and not out["notes"]
    assert design.contrast(k["colors"]["header_text"], k["colors"]["header_fill"]) >= 4.5


def test_extracted_kit_saves_and_applies_by_name(table, kits_dir):
    design.apply_to_numbers(table, "teal")
    out = design.extract_kit(table, name="Resal", save=True)
    assert Path(out["saved"]).parent == kits_dir
    assert "Resal" in [k["name"] for k in design.list_kits() if k.get("saved")]
    applied = design.apply_to_numbers(table, "Resal")
    assert applied["kit"] == "Resal"


def test_save_kit_never_overwrites_or_shadows_presets(kits_dir):
    kit = {"colors": {"title": "#0B1F3A", "accent": "#2DD4BF"}}
    design.save_kit("Brand", kit)
    with pytest.raises(design.DesignError, match="already saved"):
        design.save_kit("Brand", kit)
    design.save_kit("Brand", {"colors": {"title": "#1E3A8A"}}, overwrite=True)
    assert design.get_kit("Brand")["colors"]["title"] == "#1E3A8A"
    with pytest.raises(design.DesignError, match="preset"):
        design.save_kit("Banking", kit)
    with pytest.raises(design.DesignError, match="kit name"):
        design.save_kit("../evil", kit)


def test_save_kit_checks_contrast(kits_dir):
    with pytest.raises(design.DesignError, match="contrast"):
        design.save_kit("Pale", {"colors": {"title": "#EEEEEE"}})
    assert not list(kits_dir.glob("*.json")) if kits_dir.exists() else True


def test_delete_kit_returns_contents(kits_dir):
    design.save_kit("Brand", {"colors": {"title": "#0B1F3A"}})
    out = design.delete_kit("Brand")
    assert out["kit"]["colors"]["title"] == "#0B1F3A"
    with pytest.raises(design.DesignError, match="unknown kit"):
        design.get_kit("Brand")
    with pytest.raises(design.DesignError, match="no saved kit"):
        design.delete_kit("Brand")


def test_damaged_saved_kit_is_skipped(kits_dir):
    kits_dir.mkdir()
    (kits_dir / "broken.json").write_text("{not json")
    assert [k["name"] for k in design.list_kits()] == sorted(design.KITS, key=list(design.KITS).index)


def test_custom_kit_base_preset():
    k = design.get_kit({"base": "midnight", "colors": {"accent": "#22D3EE"}})
    assert k["background"] == "#000000" and k["colors"]["title"] == "#F8FAFC"
    with pytest.raises(design.DesignError, match="base kit"):
        design.get_kit({"base": "neon"})


def test_extract_kit_from_deck(monkeypatch, tmp_path, kits_dir):
    d = tmp_path / "d.key"
    d.write_bytes(b"deck")
    style = {"theme": "Basic Black", "slides": [
        {"slide": 1, "items": [], "title_box": {"text": "Resal", "font": "AvenirNext-Bold", "size": 80, "color": "#ffffff"},
         "body_box": {"text": "Programmable value", "font": "AvenirNext-Regular", "size": 30, "color": "#cbd5e1"}},
        {"slide": 2, "items": [_item(3, "Note", 900, 100, font="AvenirNext-Regular", color="#34d399")],
         "title_box": {"text": "رسال", "font": "DamascusBold", "size": 52, "color": "#ffffff"},
         "body_box": {"text": "قيمة قابلة للبرمجة", "font": "Damascus", "size": 28, "color": "#cbd5e1"}},
    ]}
    monkeypatch.setattr(kt, "read_style", lambda p: copy.deepcopy(style))
    out = design.extract_kit(d)
    k = out["kit"]
    assert k["background"] == "#000000" and k["base"] == "midnight" and k["theme"] == "Basic Black"
    assert k["colors"]["title"] == "#FFFFFF" and k["colors"]["accent"] == "#34D399"
    assert k["fonts"]["heading"] == "AvenirNext-Bold" and k["fonts"]["heading_ar"] == "DamascusBold"
    assert k["fonts"]["family"] == "Avenir Next" and k["fonts"]["family_ar"] == "Damascus"
    assert any("background judged" in n for n in out["notes"]) and out["contrast_ok"]
    assert design.contrast(k["colors"]["header_text"], k["colors"]["header_fill"]) >= 4.5


def test_extract_kit_rejects_other_files(tmp_path):
    p = tmp_path / "x.pages"
    p.write_bytes(b"")
    with pytest.raises(design.DesignError, match=".key or .numbers"):
        design.extract_kit(p)
