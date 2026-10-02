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

KEY_SRC = REPO / "evidence" / "a3" / "roundtrip_a3.key"
CHART_SRC = REPO / "evidence" / "c7" / "chart_fixture.key"

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
    monkeypatch.setenv("IWORK_STUDIO_ENABLE_UNVERIFIED", "1")


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
    def test_unverified_op_refused_by_default(self, key_file, monkeypatch, fake_app):
        monkeypatch.delenv("IWORK_STUDIO_ENABLE_UNVERIFIED", raising=False)
        with pytest.raises(ks.UnverifiedRouteError) as ei:
            ks.set_presenter_notes(key_file, 1, "hi")
        assert "probe_g_keynote_slides.py" in str(ei.value)
        assert fake_app["calls"] == []
        assert not (key_file.parent / "deck.key.backups").exists()

    def test_nothing_verified_yet(self):
        # flips only with committed evidence/g1/ — this test is the tripwire
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
