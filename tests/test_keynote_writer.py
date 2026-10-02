"""Phase C — .key writer test suite (C1–C7).

Gates:
- GATE-1 (semantic): YAML-tree content digest stable across repack
  (verified scripts/c_preprobe.py P3); .key bytes byte-stable from the
  first repack on; strict source-byte equality unachievable (protobuf
  re-encode, evidence/a3) — pinned interpretation, do not re-litigate.
- GATE-CHART: writer refuses chart decks (live Keynote-built fixture,
  evidence/c7/chart_fixture.key).
- GATE-AR: Arabic round-trips escape-aware (backslash-u06xx) and codepoint-exact.
- C5: schema-hash manifest on every write; skeleton invariant under
  text-only edits.
- C6/C7 (aqua marker): AppleScript fallback + render-verify loop.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import keynote_io, keynote_applescript  # noqa: E402

KEY_SRC = REPO / "evidence" / "a3" / "roundtrip_a3.key"
CHART_SRC = REPO / "evidence" / "c7" / "chart_fixture.key"

AR_TITLE = "عرض تجريبي"
AR_BODY = "مرحباً بكم في التحليل"


@pytest.fixture()
def key_file(tmp_path) -> Path:
    dest = tmp_path / "fixture.key"
    dest.write_bytes(KEY_SRC.read_bytes())
    return dest


@pytest.fixture()
def chart_key_file(tmp_path) -> Path:
    if not CHART_SRC.exists():
        pytest.skip("chart .key fixture not built (requires Aqua + Keynote)")
    dest = tmp_path / "chart_fixture.key"
    dest.write_bytes(CHART_SRC.read_bytes())
    return dest


# ── C1: read_key semantic model ──────────────────────────────────────────────


class TestReadKey:
    def test_model_shape(self, key_file):
        model = keynote_io.read_key(key_file)
        assert model["file"] == "fixture.key"
        assert model["parser_version"] == "1.14.5.0"
        assert model["contains_charts"] is False
        assert len(model["schema_hash"]) == 64
        slides = model["slides"]
        sources = [s["source"] for s in slides]
        assert any("Slide" in s for s in sources)
        joined = "\n".join(t for s in slides for t in s["texts"])
        assert AR_TITLE in joined
        assert AR_BODY in joined
        assert "English bullet" in joined

    def test_model_json_serialisable(self, key_file):
        json.dumps(keynote_io.read_key(key_file), ensure_ascii=False)

    def test_read_missing_file_raises(self, tmp_path):
        with pytest.raises(Exception):
            keynote_io.read_key(tmp_path / "nope.key")

    def test_texts_of_tree_stable_order(self, key_file, tmp_path):
        t1 = keynote_io.texts_of_tree(keynote_io.unpack_key(key_file, tmp_path / "t1"))
        t2 = keynote_io.texts_of_tree(keynote_io.unpack_key(key_file, tmp_path / "t2"))
        assert [e["source"] for e in t1] == [e["source"] for e in t2]


# ── C3: GATE-1 semantic round-trip ───────────────────────────────────────────


class TestGate1SemanticRoundTrip:
    def test_unmodified_repack_tree_hash_stable(self, key_file, tmp_path):
        d1 = keynote_io.unpack_key(key_file, tmp_path / "u1")
        o1 = tmp_path / "rt1.key"
        keynote_io.unpack_key  # process-based
        from keynote_parser.file_utils import process

        process(str(key_file), str(o1), replacements=[])
        d2 = keynote_io.unpack_key(o1, tmp_path / "u2")
        assert keynote_io.tree_hash(d1) == keynote_io.tree_hash(d2)

    def test_repack_byte_stable_from_first_repack(self, key_file, tmp_path):
        from keynote_parser.file_utils import process

        o1, o2 = tmp_path / "rt1.key", tmp_path / "rt2.key"
        process(str(key_file), str(o1), replacements=[])
        process(str(o1), str(o2), replacements=[])
        assert hashlib.sha256(o1.read_bytes()).hexdigest() == hashlib.sha256(
            o2.read_bytes()
        ).hexdigest()

    def test_unmodified_repack_same_size(self, key_file, tmp_path):
        from keynote_parser.file_utils import process

        o1 = tmp_path / "rt1.key"
        process(str(key_file), str(o1), replacements=[])
        assert o1.stat().st_size == key_file.stat().st_size


# ── C2: edit_text ────────────────────────────────────────────────────────────


class TestEditText:
    def test_edit_latin_text(self, key_file):
        result = keynote_io.edit_text(key_file, "English", "الإنجليزية")
        assert result["ok"] is True
        assert result["occurrences"] >= 1
        model = keynote_io.read_key(key_file)
        joined = "\n".join(t for s in model["slides"] for t in s["texts"])
        assert "الإنجليزية bullet" in joined
        assert "English bullet" not in joined

    def test_edit_arabic_literal(self, key_file):
        result = keynote_io.edit_text(key_file, "عرض", "تقرير")
        assert result["ok"] is True
        model = keynote_io.read_key(key_file)
        joined = "\n".join(t for s in model["slides"] for t in s["texts"])
        assert "تقرير تجريبي" in joined
        assert AR_TITLE not in joined

    def test_edit_arabic_escape_form(self, key_file):
        """GATE-AR escape-awareness: caller may pass \\u06xx escape form."""
        find_esc = "\\u0639\\u0631\\u0636"  # عرض
        replace_esc = "\\u062A\\u0642\\u0631\\u064A\\u0631"  # تقرير
        result = keynote_io.edit_text(key_file, find_esc, replace_esc)
        assert result["ok"] is True
        model = keynote_io.read_key(key_file)
        joined = "\n".join(t for s in model["slides"] for t in s["texts"])
        assert "تقرير تجريبي" in joined

    def test_literal_find_is_not_regex(self, key_file):
        """A literal 'a.b' must not match 'axb' (regex escaping honest)."""
        # literal 'E.glish' does not occur; regex 'E.glish' WOULD match
        with pytest.raises(keynote_io.EditTextError):
            keynote_io.edit_text(key_file, "E.glish", "ENGLISH")
        # ...and the SAME pattern as regex DOES match 'English'
        result = keynote_io.edit_text(key_file, "E.glish", "ENGLISH", regex=True)
        assert result["occurrences"] >= 1

    def test_edit_creates_backup(self, key_file):
        result = keynote_io.edit_text(key_file, "English", "EN")
        backup = Path(result["backup"])
        assert backup.exists()
        assert backup.suffix == ".key"
        assert backup.parent.name == "fixture.key.backups"
        # backup is the PRE-write state
        assert "English bullet" in _all_texts(backup)
        assert "English bullet" not in _all_texts(key_file)

    def test_missing_find_raises_no_side_effects(self, key_file):
        before = hashlib.sha256(key_file.read_bytes()).hexdigest()
        with pytest.raises(keynote_io.EditTextError):
            keynote_io.edit_text(key_file, "لا يوجد هذا النص", "س")
        assert hashlib.sha256(key_file.read_bytes()).hexdigest() == before
        backups = key_file.parent / "fixture.key.backups"
        assert not backups.exists()  # pre-flight runs BEFORE any backup

    def test_no_stray_tmp_files(self, key_file):
        keynote_io.edit_text(key_file, "English", "EN")
        strays = [p.name for p in key_file.parent.iterdir() if p.name.startswith(".")]
        assert strays == []

    def test_multiline_paragraph_fix(self, key_file):
        """Library defect workaround: edit on \r-separated multi-paragraph
        text must not raise NotImplementedError (upstream does)."""
        # body is 'مرحباً بكم في التحليل\rEnglish bullet' — \r-separated
        result = keynote_io.edit_text(key_file, "التحليل", "الجديدة")
        assert result["ok"] is True
        model = keynote_io.read_key(key_file)
        joined = "\n".join(t for s in model["slides"] for t in s["texts"])
        assert "مرحباً بكم في الجديدة" in joined


def _all_texts(p) -> str:
    model = keynote_io.read_key(p)
    return "\n".join(t for s in model["slides"] for t in s["texts"])


# ── C5: schema-hash manifest ────────────────────────────────────────────────


class TestSchemaHashManifest:
    def test_manifest_written_on_every_write(self, key_file):
        keynote_io.edit_text(key_file, "English", "EN")
        keynote_io.edit_text(key_file, "EN", "English")
        manifest = keynote_io.read_manifest(key_file)
        assert len(manifest) == 2
        assert manifest[0]["op"] == "edit_text"
        assert manifest[0]["parser_version"] == "1.14.5.0"
        assert manifest[1]["schema_hash_after"] == manifest[0]["schema_hash_before"]

    def test_schema_hash_invariant_under_text_edit(self, key_file):
        before = keynote_io.read_key(key_file)["schema_hash"]
        keynote_io.edit_text(key_file, "English", "EN")
        after = keynote_io.read_key(key_file)["schema_hash"]
        assert before == after  # text-only edit must NOT move the skeleton

    def test_manifest_records_schema_hash_before_after(self, key_file):
        keynote_io.edit_text(key_file, "English", "EN")
        entry = keynote_io.read_manifest(key_file)[-1]
        assert entry["schema_hash_before"] == entry["schema_hash_after"]
        assert entry["changed_texts"] >= 1
        assert len(entry["sha256_after"]) == 64

    def test_parser_repack_between_writes_is_not_a_shift(self, key_file):
        """A skeleton-preserving repack between writes is NOT an external
        edit — byte-stable from first repack (P3), so no shift is flagged."""
        keynote_io.edit_text(key_file, "English", "EN")
        from keynote_parser.file_utils import process

        tmp = key_file.parent / "external.key"
        process(str(key_file), str(tmp), replacements=[])
        tmp.replace(key_file)
        r = keynote_io.edit_text(key_file, "EN", "English")
        assert r["baseline_shift"] is False

    @pytest.mark.aqua
    def test_app_save_between_writes_flags_baseline_shift(self, key_file):
        """A REAL Keynote app save between writes restructures the tree
        (verified scripts/c_preprobe5.py) and must be recorded as a
        schema baseline shift — the Keynote-16 rename-storm audit trail."""
        keynote_io.edit_text(key_file, "English", "EN")  # baseline manifest
        # real external edit: open in Keynote, write, in-place save, close
        result = keynote_applescript.write_text_item(key_file, 1, 0, "عنوان جديد")
        assert result["after"] == "عنوان جديد"
        # the manifest baseline is now stale — a write must flag the shift
        r = keynote_io.edit_text(key_file, "EN", "ENGLISH")
        assert r["baseline_shift"] is True
        manifest = keynote_io.read_manifest(key_file)
        assert manifest[-1]["schema_hash_before"] != manifest[0]["schema_hash_after"]
        # the new skeleton becomes the baseline: a further parser write
        # must NOT re-flag (no false alarms)
        r2 = keynote_io.edit_text(key_file, "ENGLISH", "EN")
        assert r2["baseline_shift"] is False


# ── C4: GATE-CHART refusal ───────────────────────────────────────────────────


class TestGateChart:
    def test_chart_deck_refused(self, chart_key_file):
        with pytest.raises(keynote_io.ChartRefusalError, match="GATE-CHART"):
            keynote_io.edit_text(chart_key_file, "A", "B")

    def test_chart_deck_read_reports_flag(self, chart_key_file):
        assert keynote_io.contains_charts(chart_key_file) is True

    def test_plain_deck_not_flagged(self, key_file):
        assert keynote_io.contains_charts(key_file) is False


# ── C6: AppleScript fallback (aqua) ─────────────────────────────────────────


class TestApplescriptFallback:
    @pytest.mark.aqua
    def test_read_text_items(self, key_file):
        items = keynote_applescript.read_text_items(key_file)
        assert len(items) >= 3
        joined = "\n".join(e["text"] for e in items)
        assert AR_TITLE in joined or AR_BODY in joined

    @pytest.mark.aqua
    def test_write_text_item_in_place_save(self, key_file):
        result = keynote_applescript.write_text_item(key_file, 1, 0, "عنوان جديد")
        assert result["after"] == "عنوان جديد"
        # change is ON DISK (in-place save landed)
        assert "عنوان جديد" in _all_texts(key_file)

    @pytest.mark.aqua
    def test_applescript_edit_text(self, key_file):
        result = keynote_applescript.applescript_edit_text(key_file, "English", "EN")
        assert result["ok"] is True
        assert result["changes"]
        assert "EN bullet" in _all_texts(key_file)

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="root ignores file modes, so chmod 0o444 is not a lock proxy",
    )
    def test_locked_file_routes_to_fallback(self, key_file):
        """C6 contract: an unwritable file raises FileLockedError naming
        the AppleScript fallback route — never a silent write attempt."""
        key_file.chmod(0o444)  # read-only: the honest, portable lock proxy
        try:
            with pytest.raises(keynote_io.FileLockedError) as ei:
                keynote_io.edit_text(key_file, "English", "EN")
            assert "keynote_applescript" in str(ei.value)
        finally:
            key_file.chmod(0o644)
        # nothing was written and no backup churn happened
        backups = key_file.parent / "fixture.key.backups"
        assert not backups.exists()
        assert "English bullet" in _all_texts(key_file)


# ── C7: render-verify (aqua) ─────────────────────────────────────────────────


class TestRenderVerify:
    @pytest.mark.aqua
    def test_render_verify_key_pdf_text(self, key_file):
        evidence_pdf = REPO / "evidence" / "c7" / "render_verify_output.pdf"
        evidence_pdf.parent.mkdir(exist_ok=True, parents=True)
        keynote_io.edit_text(key_file, "English", "السعر")
        result = keynote_applescript.verify_render(
            key_file, expected_fragment="السعر", keep_pdf=evidence_pdf
        )
        assert result["ok"] is True
        assert result["pages"] >= 1

    @pytest.mark.aqua
    def test_chart_fixture_render(self, chart_key_file):
        """The chart deck itself must still render (read/refusal path
        never touched the file — the deck stays valid)."""
        result = keynote_applescript.verify_render(
            chart_key_file, expected_fragment="مخططات", expected_slides=1
        )
        assert result["ok"] is True