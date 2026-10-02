"""Phase G — Keynote slide ops (app route) under the write protocol.

Headless tests prove the PROTOCOL with the app calls stubbed: the
verification gate, pre-flight validation (no backup churn), rollback to the
exact original bytes when the app does the wrong thing, and the manifest
entry on success. The aqua tests at the bottom are the live probe contract.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import keynote_io, keynote_slides as ks  # noqa: E402

KEY_SRC = REPO / "tests" / "fixtures" / "arabic.key"
CHART_SRC = REPO / "tests" / "fixtures" / "chart.key"

DECK = [
    {"skipped": False, "notes": "", "texts": ["Title A"]},
    {"skipped": False, "notes": "n2", "texts": ["Title B", "body"]},
    {"skipped": True, "notes": "", "texts": ["عنوان"]},
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture()
def key_file(tmp_path) -> Path:
    dest = tmp_path / "deck.key"
    dest.write_bytes(KEY_SRC.read_bytes())
    return dest


@pytest.fixture()
def unverified_ok(monkeypatch):
    monkeypatch.delenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", raising=False)


@pytest.fixture()
def fake_app(monkeypatch):
    """Stub the two app touch-points. `state["after"]` is what the 'app'
    leaves on disk; `state["mutate"]` lets a test corrupt the file."""
    state = {"calls": [], "after": None, "mutate": None}
    reads = {"n": 0}

    def fake_read(path):
        reads["n"] += 1
        if reads["n"] == 1 or state["after"] is None:
            return [dict(s) for s in DECK]
        return state["after"]

    def fake_apply(target, op, params):
        state["calls"].append((op, params))
        if state["mutate"]:
            state["mutate"](target)

    monkeypatch.setattr(ks, "read_slides", fake_read)
    monkeypatch.setattr(ks, "_apply", fake_apply)
    return state


class TestGate:
    def test_on_by_default(self, monkeypatch):
        monkeypatch.delenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", raising=False)
        assert ks.slide_ops_enabled()

    def test_off_switch_refuses_with_no_side_effects(self, key_file, monkeypatch, fake_app):
        monkeypatch.setenv("IWORK_STUDIO_DISABLE_SLIDE_OPS", "1")
        with pytest.raises(ks.SlideOpsDisabledError):
            ks.set_presenter_notes(key_file, 1, "hi")
        assert fake_app["calls"] == []
        assert not (key_file.parent / "deck.key.backups").exists()

    def test_nothing_observed_on_live_mac_yet(self):
        # flips only after scripts/probe_keynote_slides.py passes on the Mac
        assert ks.VERIFIED_OPS == frozenset()

    def test_non_key_refused(self, tmp_path, unverified_ok):
        f = tmp_path / "x.numbers"
        f.write_bytes(b"x")
        with pytest.raises(ks.SlideOpError):
            ks.delete_slide(f, 1)

    def test_chart_deck_refused(self, tmp_path, unverified_ok, fake_app):
        dest = tmp_path / "chart.key"
        dest.write_bytes(CHART_SRC.read_bytes())
        with pytest.raises(keynote_io.ChartRefusalError):
            ks.delete_slide(dest, 1)
        assert fake_app["calls"] == []


class TestPreflight:
    @pytest.mark.parametrize(
        "call",
        [
            lambda f: ks.delete_slide(f, 4),
            lambda f: ks.duplicate_slide(f, 0),
            lambda f: ks.move_slide(f, 1, 1),
            lambda f: ks.move_slide(f, 1, 9),
            lambda f: ks.add_slide(f, after=7),
            lambda f: ks.set_skipped(f, 5),
        ],
    )
    def test_bad_request_no_side_effects(self, key_file, unverified_ok, fake_app, call):
        before = _sha(key_file)
        with pytest.raises(ks.SlideOpError):
            call(key_file)
        assert fake_app["calls"] == []
        assert not (key_file.parent / "deck.key.backups").exists()
        assert _sha(key_file) == before

    def test_cannot_delete_only_slide(self, key_file, unverified_ok, monkeypatch):
        monkeypatch.setattr(ks, "read_slides", lambda p: [DECK[0]])
        with pytest.raises(ks.SlideOpError, match="only slide"):
            ks.delete_slide(key_file, 1)


class TestExpectationGate:
    def test_wrong_app_result_rolls_back_byte_exact(self, key_file, unverified_ok, fake_app):
        original = _sha(key_file)
        # the "app" scribbles on the file AND deletes the wrong slide
        fake_app["mutate"] = lambda t: t.write_bytes(b"corrupted")
        fake_app["after"] = [DECK[1], DECK[2]]  # asked to delete 2, it deleted 1
        with pytest.raises(ks.SlideOpVerificationError):
            ks.delete_slide(key_file, 2)
        assert _sha(key_file) == original
        backups = list((key_file.parent / "deck.key.backups").glob("*.key"))
        assert len(backups) == 1

    def test_collateral_change_rolls_back(self, key_file, unverified_ok, fake_app):
        original = _sha(key_file)
        after = [dict(s) for s in DECK]
        after[0] = {**after[0], "notes": "new"}
        after[2] = {**after[2], "texts": ["changed!"]}  # collateral damage
        fake_app["after"] = after
        with pytest.raises(ks.SlideOpVerificationError, match="slide 3"):
            ks.set_presenter_notes(key_file, 1, "new")
        assert _sha(key_file) == original

    def test_move_expectation(self, key_file, unverified_ok, fake_app):
        fake_app["after"] = [DECK[1], DECK[2], DECK[0]]
        result = ks.move_slide(key_file, 1, 3)
        assert result["ok"] and result["slides_after"] == 3

    def test_add_allows_any_new_slide_content(self, key_file, unverified_ok, fake_app):
        new = {"skipped": False, "notes": "", "texts": ["placeholder"]}
        fake_app["after"] = [DECK[0], new, DECK[1], DECK[2]]
        assert ks.add_slide(key_file, after=1)["slides_after"] == 4

    def test_notes_newline_normalised(self, key_file, unverified_ok, fake_app):
        after = [dict(s) for s in DECK]
        after[1] = {**after[1], "notes": "سطر\rline"}  # Keynote stores \r
        fake_app["after"] = after
        assert ks.set_presenter_notes(key_file, 2, "سطر\nline")["ok"]

    def test_success_writes_manifest(self, key_file, unverified_ok, fake_app):
        after = [dict(s) for s in DECK]
        after[2] = {**after[2], "skipped": False}
        fake_app["after"] = after
        ks.set_skipped(key_file, 3, False)
        entries = keynote_io.read_manifest(key_file)
        assert entries[-1]["op"] == "slide_skip"
        assert entries[-1]["route"] == "applescript"
        assert entries[-1]["verified_op"] is False


class TestSilentSuccess:
    """Failure class found in the wild (a fork of reichenbach/iwork_mcp):
    Keynote's scripting bridge reports success for writes that did nothing —
    writes to properties that don't exist, duplicates that land in another
    document, no-op moves. The app says ok; only the re-read from disk tells
    the truth. Each case must end in SlideOpVerificationError + byte-exact
    rollback, never in "ok"."""

    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda f: ks.duplicate_slide(f, 1), id="duplicate-landed-elsewhere"),
            pytest.param(lambda f: ks.set_presenter_notes(f, 1, "ملاحظات"), id="notes-write-ignored"),
            pytest.param(lambda f: ks.set_skipped(f, 1, True), id="skip-write-ignored"),
            pytest.param(lambda f: ks.move_slide(f, 1, 3), id="move-no-op"),
            pytest.param(lambda f: ks.add_slide(f), id="add-no-op"),
            pytest.param(lambda f: ks.delete_slide(f, 2), id="delete-no-op"),
        ],
    )
    def test_app_reports_ok_but_nothing_changed(self, key_file, unverified_ok, fake_app, call):
        original = _sha(key_file)
        fake_app["after"] = [dict(s) for s in DECK]  # deck on disk is unchanged
        with pytest.raises(ks.SlideOpVerificationError):
            call(key_file)
        assert _sha(key_file) == original

    def test_notes_landed_on_wrong_slide(self, key_file, unverified_ok, fake_app):
        after = [dict(s) for s in DECK]
        after[1] = {**after[1], "notes": "hello"}  # asked for slide 1
        fake_app["after"] = after
        with pytest.raises(ks.SlideOpVerificationError, match="slide 1"):
            ks.set_presenter_notes(key_file, 1, "hello")

    def test_notes_mangled_arabic_rejected(self, key_file, unverified_ok, fake_app):
        after = [dict(s) for s in DECK]
        after[0] = {**after[0], "notes": "????????"}  # encoding loss
        fake_app["after"] = after
        with pytest.raises(ks.SlideOpVerificationError):
            ks.set_presenter_notes(key_file, 1, "ملاحظات")


# ── live probe contract (Mac, Aqua, Keynote 15.4) ────────────────────────────


@pytest.mark.aqua
class TestLive:
    def test_notes_roundtrip_arabic(self, key_file, unverified_ok):
        n = len(ks.read_slides(key_file))
        assert ks.set_presenter_notes(key_file, 1, "ملاحظات المتحدث")["ok"]
        slides = ks.read_slides(key_file)
        assert len(slides) == n and slides[0]["notes"] == "ملاحظات المتحدث"

    def test_duplicate_then_delete_restores_count(self, key_file, unverified_ok):
        n = len(ks.read_slides(key_file))
        ks.duplicate_slide(key_file, 1)
        ks.delete_slide(key_file, 2)
        assert len(ks.read_slides(key_file)) == n
