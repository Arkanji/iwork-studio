"""App-driven ops (formula, sort, placeholders, transitions, images, slideshow, create)
— request validation and rollback, with the app stubbed."""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from numbers_parser import Document  # noqa: E402

from iwork_studio import app_ops, numbers_structure as ns  # noqa: E402
from iwork_studio import keynote_slides as ks, keynote_theme as kt, pages_io  # noqa: E402
from iwork_studio.numbers_io import CellRefError, WriteVerificationError  # noqa: E402


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture()
def book(tmp_path):
    p = tmp_path / "book.numbers"
    ns.create(p, [{"name": "S", "tables": [{"name": "T", "rows": [
        ["Name", "Amount"], ["ب", 30], ["أ", 10], ["ج", 20]]}]}])
    return p


def _rewrite(path, fn):
    doc = Document(str(path))
    fn(doc.sheets[0].tables[0])
    doc.save(str(path))


# ── Numbers: formula ─────────────────────────────────────────────────────────

def test_formula_must_start_with_equals(book):
    with pytest.raises(app_ops.AppOpError):
        app_ops.set_formula(book, "B5", "SUM(B2:B4)")


def test_formula_cell_out_of_range(book):
    with pytest.raises(CellRefError):
        app_ops.set_formula(book, "Z99", "=1")


def test_formula_not_applied_rolls_back(book, monkeypatch):
    before = _sha(book)
    # the "app" writes a plain value instead of a formula, and touches another cell
    monkeypatch.setattr(app_ops, "_edit_in_app",
                        lambda kind, path, body, params: _rewrite(path, lambda t: (t.write(1, 1, 999))))
    with pytest.raises(WriteVerificationError):
        app_ops.set_formula(book, "B4", "=SUM(B2:B3)")
    assert _sha(book) == before


def test_formula_body_targets_the_named_cell(book, monkeypatch):
    seen = {}

    def fake(kind, path, body, params):
        seen.update(params, kind=kind, body=body)
        raise RuntimeError("stop")

    monkeypatch.setattr(app_ops, "_edit_in_app", fake)
    with pytest.raises(RuntimeError):
        app_ops.set_formula(book, "R4C2", "=SUM(B2:B3)")
    assert seen["kind"] == "Numbers" and seen["ref"] == "B4" and seen["sheet"] == "S" and seen["table"] == "T"
    assert "byName(params.ref)" in seen["body"]


# ── Numbers: sort ────────────────────────────────────────────────────────────

def _sorted_rows(t, desc=False):
    rows = sorted([[t.cell(r, 0).value, t.cell(r, 1).value] for r in range(1, t.num_rows)],
                  key=lambda x: x[1], reverse=desc)
    for i, (a, b) in enumerate(rows, start=1):
        t.write(i, 0, a)
        t.write(i, 1, b)


def test_sort_ok(book, monkeypatch):
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda k, p, b, params: _rewrite(p, _sorted_rows))
    out = app_ops.sort_table(book, "B")
    assert out["rows_sorted"] == 3
    t = Document(str(book)).sheets[0].tables[0]
    assert [t.cell(r, 1).value for r in range(t.num_rows)] == ["Amount", 10, 20, 30]


def test_sort_wrong_order_rolls_back(book, monkeypatch):
    before = _sha(book)
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda k, p, b, params: _rewrite(p, lambda t: _sorted_rows(t, True)))
    with pytest.raises(WriteVerificationError, match="order"):
        app_ops.sort_table(book, "B")
    assert _sha(book) == before


def test_sort_that_alters_data_rolls_back(book, monkeypatch):
    before = _sha(book)
    monkeypatch.setattr(app_ops, "_edit_in_app", lambda k, p, b, params: _rewrite(p, lambda t: t.write(2, 0, "X")))
    with pytest.raises(WriteVerificationError):
        app_ops.sort_table(book, "B")
    assert _sha(book) == before


def test_sort_bad_column(book):
    with pytest.raises(CellRefError):
        app_ops.sort_table(book, "Q")


# ── Pages placeholders ───────────────────────────────────────────────────────

@pytest.fixture()
def letter(tmp_path, monkeypatch):
    p = tmp_path / "letter.pages"
    p.write_bytes(b"original")
    state = {"before": {"body": "Dear [Name],\rSee you on [Date].", "items": ["Sender [Name]", None]},
             "phs": [{"tag": "Name", "text": "[Name]"}, {"tag": "Date", "text": "[Date]"}],
             "after": None, "after_phs": []}
    reads = {"texts": 0, "phs": 0}

    def texts(path):
        reads["texts"] += 1
        return copy.deepcopy(state["before"] if reads["texts"] == 1 else state["after"])

    def phs(path):
        reads["phs"] += 1
        return copy.deepcopy(state["phs"] if reads["phs"] == 1 else state["after_phs"])

    class R:
        returncode, stderr = 0, ""

    def run(cmd, **kw):
        p.write_bytes(b"changed by app")
        return R()

    monkeypatch.setattr(pages_io, "preflight", lambda: {"ok": True})
    monkeypatch.setattr(app_ops, "_pages_texts", texts)
    monkeypatch.setattr(app_ops, "_pages_placeholders", phs)
    monkeypatch.setattr(app_ops.subprocess, "run", run)
    state["open_in_pages"] = False
    monkeypatch.setattr(app_ops, "_pages_open", lambda path, open_it=True: state["open_in_pages"])
    monkeypatch.setattr(app_ops, "_pages_close", lambda path: None)
    return p, state


def test_fill_placeholders_ok(letter):
    p, state = letter
    state["after"] = {"body": "Dear سارة,\rSee you on 3 Oct.", "items": ["Sender سارة", None]}
    out = app_ops.fill_placeholders(p, {"Name": "سارة", "Date": "3 Oct"})
    assert out["filled"] == ["Date", "Name"] and p.read_bytes() == b"changed by app"


def test_fill_placeholders_page_layout(letter):
    p, state = letter
    state["before"] = {"body": None, "items": ["[Name]", "Date: [Date]", "Footer"]}
    state["after"] = {"body": None, "items": ["سارة", "Date: 3 Oct", "Footer"]}
    assert app_ops.fill_placeholders(p, {"Name": "سارة", "Date": "3 Oct"})["ok"]


def test_fill_placeholders_unexpected_body_rolls_back(letter):
    p, state = letter
    state["after"] = {"body": "Dear سارة,\rSee you on 3 Oct. EXTRA", "items": ["Sender سارة", None]}
    with pytest.raises(pages_io.EditVerificationError):
        app_ops.fill_placeholders(p, {"Name": "سارة", "Date": "3 Oct"})
    assert p.read_bytes() == b"original"


def test_fill_placeholders_text_box_damage_rolls_back(letter):
    p, state = letter
    state["before"] = {"body": None, "items": ["[Name]", "Footer"]}
    state["after"] = {"body": None, "items": ["سارة", ""]}
    with pytest.raises(pages_io.EditVerificationError, match="text boxes"):
        app_ops.fill_placeholders(p, {"Name": "سارة"})
    assert p.read_bytes() == b"original"


def test_fill_placeholders_other_placeholder_changed_rolls_back(letter):
    p, state = letter
    state["after"] = {"body": "Dear سارة,\rSee you on [Date].", "items": ["Sender سارة", None]}
    state["after_phs"] = [{"tag": "Date", "text": "?"}]
    with pytest.raises(pages_io.EditVerificationError, match="other placeholders"):
        app_ops.fill_placeholders(p, {"Name": "سارة"})
    assert p.read_bytes() == b"original"


def test_fill_placeholders_refuses_document_open_in_pages(letter):
    p, state = letter
    state["open_in_pages"] = True
    with pytest.raises(ks.DocumentOpenError):
        app_ops.fill_placeholders(p, {"Name": "x"})
    assert p.read_bytes() == b"original" and not (p.parent / "letter.pages.backups").exists()


def test_placeholder_reader_opens_with_jxa_and_finds_by_path(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(pages_io, "_assert_aqua", lambda: None)
    monkeypatch.setattr(app_ops, "_pages_open", lambda path, open_it=True: calls.append("jxa-open") or False)

    class R:
        returncode, stderr, stdout = 0, "", "Name\x1f[Name]\x1e\x1f\x1e"

    def run(cmd, **kw):
        calls.append(cmd)
        return R()

    monkeypatch.setattr(app_ops.subprocess, "run", run)
    out = app_ops._pages_placeholders(tmp_path / "l.pages")
    assert out == [{"tag": "Name", "text": "[Name]"}, {"tag": "", "text": ""}]
    script = calls[1][2]
    assert calls[0] == "jxa-open" and "open (POSIX file" not in script and "front document" not in script
    assert calls[1][-1] == "close"


def test_fill_placeholders_unknown_tag(letter):
    p, _ = letter
    with pytest.raises(app_ops.AppOpError, match="Nope"):
        app_ops.fill_placeholders(p, {"Nope": "x"})
    assert p.read_bytes() == b"original"


def test_fill_placeholders_refuses_ambiguous_texts(letter):
    p, state = letter
    state["phs"] = [{"tag": "A", "text": "[Text]"}, {"tag": "B", "text": "[Text]"}]
    with pytest.raises(app_ops.AppOpError, match="same text"):
        app_ops.fill_placeholders(p, {"A": "x"})


def test_page_layout_has_no_body_text(monkeypatch, tmp_path):
    monkeypatch.setattr(pages_io, "_jxa", lambda script, timeout=180: "null")
    with pytest.raises(pages_io.PagesOutOfScopeError, match="page-layout"):
        pages_io.read_body_text(tmp_path / "x.pages")


# ── Keynote: transitions / images ────────────────────────────────────────────

STYLE = {"theme": "Basic White", "layouts": ["Title"], "slides": [
    {"slide": 1, "layout": "Title", "images": 0, "transition": {"effect": "no transition effect", "duration": 1.0,
                                                                 "delay": 0.0, "automatic": False},
     "items": [{"index": 0, "text": "عرض", "font": "HelveticaNeue", "size": 40.0, "color": "#000000"}]},
    {"slide": 2, "layout": "Title", "images": 1, "transition": {"effect": "no transition effect", "duration": 1.0,
                                                                 "delay": 0.0, "automatic": False},
     "items": [{"index": 0, "text": "Two", "font": "HelveticaNeue", "size": 40.0, "color": "#000000"}]},
]}


@pytest.fixture()
def deck(tmp_path, monkeypatch):
    d = tmp_path / "deck.key"
    d.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    state = {"after": None}
    reads = {"n": 0}

    def fake_read(path):
        reads["n"] += 1
        return copy.deepcopy(STYLE if reads["n"] == 1 else state["after"])

    def fake_jxa(body, params, timeout=None):
        Path(params["path"]).write_bytes(b"app wrote this")
        return {"ok": True}

    monkeypatch.delenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", raising=False)
    monkeypatch.setattr(kt, "read_style", fake_read)
    monkeypatch.setattr(ks, "_jxa", fake_jxa)
    monkeypatch.setattr(kt.keynote_io, "read_key", lambda p: {})
    return d, state


def _with(fn):
    a = copy.deepcopy(STYLE)
    fn(a)
    return a


def test_transition_ok(deck):
    d, state = deck
    state["after"] = _with(lambda a: a["slides"][0]["transition"].update(effect="dissolve", duration=2.0))
    out = app_ops.set_transition(d, 1, "Dissolve", duration=2)
    assert out["effect"] == "dissolve"


def test_transition_collateral_rolls_back(deck):
    d, state = deck
    before = _sha(d)

    def bad(a):
        a["slides"][0]["transition"]["effect"] = "dissolve"
        a["slides"][1]["transition"]["effect"] = "push"

    state["after"] = _with(bad)
    with pytest.raises(ks.SlideOpVerificationError):
        app_ops.set_transition(d, 1, "dissolve")
    assert _sha(d) == before


def test_transition_unknown_effect(deck):
    d, _ = deck
    with pytest.raises(app_ops.AppOpError, match="unknown effect"):
        app_ops.set_transition(d, 1, "explode")


def test_add_image_ok(deck, tmp_path):
    d, state = deck
    img = tmp_path / "logo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    state["after"] = _with(lambda a: a["slides"][0].update(images=1))
    assert app_ops.add_image(d, 1, img, width=200)["image"] == "logo.png"


def test_add_image_wrong_slide_rolls_back(deck, tmp_path):
    d, state = deck
    before = _sha(d)
    img = tmp_path / "logo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    state["after"] = _with(lambda a: a["slides"][1].update(images=2))
    with pytest.raises(ks.SlideOpVerificationError):
        app_ops.add_image(d, 1, img)
    assert _sha(d) == before


def test_add_image_rejects_non_images(deck, tmp_path):
    d, _ = deck
    f = tmp_path / "notes.txt"
    f.write_text("x")
    with pytest.raises(app_ops.AppOpError):
        app_ops.add_image(d, 1, f)


# ── slideshow / create ───────────────────────────────────────────────────────

def test_slideshow_bad_action():
    with pytest.raises(app_ops.AppOpError):
        app_ops.slideshow("dance")


def test_create_document_refuses_existing_and_bad_suffix(tmp_path):
    (tmp_path / "a.key").write_bytes(b"x")
    with pytest.raises(app_ops.AppOpError):
        app_ops.create_document(tmp_path / "a.key")
    with pytest.raises(app_ops.AppOpError):
        app_ops.create_document(tmp_path / "a.docx")


def test_create_document_moves_checked_file(tmp_path, monkeypatch):
    def fake(kind, body, params, timeout=300):
        Path(params["out"]).write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
        return {"template": "Basic White"}

    monkeypatch.setattr(app_ops, "_jxa", fake)
    out = app_ops.create_document(tmp_path / "new.key")
    assert out["template"] == "Basic White" and Path(out["file"]).exists()


def test_create_pages_document_checks_it_opens(tmp_path, monkeypatch):
    def fake(kind, body, params, timeout=300):
        Path(params["out"]).write_bytes(b"pages zip")
        return {"template": "Classic Letter"}

    monkeypatch.setattr(app_ops, "_jxa", fake)
    opened = []
    monkeypatch.setattr(pages_io, "document_info", lambda p: opened.append(p) or {"kind": "page layout"})
    out = app_ops.create_document(tmp_path / "l.pages", "Classic Letter")
    assert opened and Path(out["file"]).read_bytes() == b"pages zip"


def test_create_document_unknown_template(tmp_path, monkeypatch):
    monkeypatch.setattr(app_ops, "_jxa", lambda *a, **k: {"unknown": "Nope", "available": ["Blank"]})
    with pytest.raises(app_ops.AppOpError, match="Blank"):
        app_ops.create_document(tmp_path / "new.numbers", "Nope")
    assert not (tmp_path / "new.numbers").exists()


# ── live (macOS + the apps): pytest -m aqua ──────────────────────────────────

@pytest.mark.aqua
def test_live_numbers_sort_then_formula(book):
    assert app_ops.sort_table(book, "B")["ok"]
    t = Document(str(book)).sheets[0].tables[0]
    assert [t.cell(r, 1).value for r in range(1, 4)] == [10, 20, 30]
    ns.insert(book, "rows", values=[["المجموع", None]])
    out = app_ops.set_formula(book, "B5", "=SUM(B2:B4)")
    assert out["ok"] and out["result"] == 60


@pytest.mark.aqua
@pytest.mark.parametrize("ext", [".numbers", ".key", ".pages"])
def test_live_create_from_builtin_template(tmp_path, ext):
    out = app_ops.create_document(tmp_path / f"new{ext}")
    assert out["ok"] and Path(out["file"]).exists()


@pytest.mark.aqua
def test_live_keynote_transition_and_image(tmp_path):
    import pymupdf

    deck = tmp_path / "deck.key"
    deck.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    assert app_ops.set_transition(deck, 1, "dissolve", duration=1.5)["ok"]
    img = tmp_path / "dot.png"
    pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64), 0).save(str(img))
    assert app_ops.add_image(deck, 1, img, x=100, y=100, width=64)["ok"]


@pytest.mark.aqua
def test_live_pages_placeholders(tmp_path):
    from iwork_studio import helpers

    names = [n for n in helpers.list_templates("pages")["templates"] if "letter" in n.lower()]
    if not names:
        pytest.skip("no letter template in this Pages")
    for i, name in enumerate(names[:4]):
        doc = tmp_path / f"letter{i}.pages"
        app_ops.create_document(doc, name)  # page-layout templates must create fine too
        tags = app_ops.list_placeholders(doc)["tags"]
        if tags:
            out = app_ops.fill_placeholders(doc, {tags[0]: "تجربة"})
            assert out["ok"]
            return
    pytest.skip(f"no placeholders in {names[:4]}")


@pytest.mark.aqua
def test_live_slideshow_start_stop(tmp_path):
    deck = tmp_path / "deck.key"
    deck.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    assert app_ops.slideshow("start", deck)["ok"]
    assert app_ops.slideshow("stop")["playing"] is False
