"""Phase D tests — .pages read-mostly lane.

Two tiers:
- contract tests (always run): D2 out-of-scope enforcement, backup/
  rollback behaviour where simulable, error types, mode validation.
- aqua tests (marked `aqua`, live Pages): D1 read route, D2 both ops,
  D3 preflight, D4 Arabic render baseline. Skipped automatically when
  the fixture or a GUI session is missing.

Run:  ~/.hermes/iwork-venv/.venv/bin/python -m pytest tests/test_pages_writer.py -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import pages_io  # noqa: E402
from iwork_studio.pages_io import (  # noqa: E402
    AquaSessionError,
    EditVerificationError,
    OutOfScopeError,
    PagesOutOfScopeError,
    PagesUnavailableError,
)

PAGES_SRC = REPO / "tests" / "fixtures" / "arabic.pages"

ARABIC_BODY = "تقرير المشروع السنوي — Annual project report.\rSecond paragraph: السعر التقديري 42.\rEdited paragraph: تعديل جديد."


def _aqua_available() -> bool:
    try:
        out = subprocess.run(
            ["launchctl", "managername"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
        return out == "Aqua"
    except Exception:
        return False


@pytest.fixture()
def pages_file(tmp_path) -> Path:
    if not PAGES_SRC.exists():
        pytest.skip("pages fixture not built (requires Aqua; run scripts/d_preprobe.py)")
    dest = tmp_path / "fixture.pages"
    shutil.copy2(PAGES_SRC, dest)
    return dest


# ── D2: scope gate (pure, no app needed) ──────────────────────────────────────


class TestD2ScopeGate:
    def test_unknown_mode_rejected(self):
        with pytest.raises(PagesOutOfScopeError) as ei:
            pages_io.edit_pages_body("/nonexistent.pages", mode="format_text")
        assert "two verified ops" in str(ei.value)

    def test_replace_all_requires_find(self):
        with pytest.raises(PagesOutOfScopeError):
            pages_io.edit_pages_body("/nonexistent.pages", mode="replace_all", replace="x")

    def test_replace_all_requires_replace(self):
        with pytest.raises(PagesOutOfScopeError):
            pages_io.edit_pages_body("/nonexistent.pages", mode="replace_all", find="x")

    def test_empty_find_rejected(self):
        with pytest.raises(PagesOutOfScopeError):
            pages_io.edit_pages_body("/nonexistent.pages", find="", replace="x")

    def test_set_body_requires_new_body(self):
        with pytest.raises(PagesOutOfScopeError):
            pages_io.edit_pages_body("/nonexistent.pages", mode="set_body")

    def test_set_body_rejects_find(self):
        # per-fragment surgery is not one of the two ops
        with pytest.raises(PagesOutOfScopeError):
            pages_io.edit_pages_body(
                "/nonexistent.pages", find="a", replace="b", mode="set_body",
                new_body="c",
            )

    def test_missing_file_raises_before_any_side_effect(self):
        # FileNotFoundError precedes the scope gate write path entirely
        with pytest.raises(FileNotFoundError):
            pages_io.edit_pages_body(
                "/nonexistent/nowhere.pages", find="a", replace="b"
            )

    def test_out_of_scope_is_notimplemented_not_value(self):
        # deliberate contract: REJECTED scope, not bad input
        assert issubclass(OutOfScopeError, NotImplementedError)


# ── D3: preflight contract (pure where possible) ─────────────────────────────


class TestD3Preflight:
    def test_headless_raises_loud(self, monkeypatch):
        monkeypatch.setattr(pages_io, "_assert_aqua", lambda: (_ for _ in ()).throw(
            AquaSessionError("session manager is 'System', not 'Aqua' — refusing to fake it")
        ))
        with pytest.raises(AquaSessionError) as ei:
            pages_io.preflight()
        assert "refusing to fake it" in str(ei.value)

    def test_timeout_raises_pages_unavailable_with_one_prompt(self, monkeypatch):
        monkeypatch.setattr(pages_io, "_assert_aqua", lambda: None)
        def boom(script, timeout=180):
            raise subprocess.TimeoutExpired(cmd="osascript", timeout=timeout)
        monkeypatch.setattr(pages_io, "_jxa", boom)
        with pytest.raises(PagesUnavailableError) as ei:
            pages_io.preflight()
        msg = str(ei.value)
        assert "once" in msg.lower()
        assert "-1712" in msg or "timeout" in msg.lower()

    def test_1712_jxa_failure_maps_to_unavailable(self, monkeypatch):
        monkeypatch.setattr(pages_io, "_assert_aqua", lambda: None)
        def boom(script, timeout=180):
            raise RuntimeError(
                "JXA failed (rc=1): execution error: Pages got an error: "
                "AppleEvent timed out. (-1712)"
            )
        monkeypatch.setattr(pages_io, "_jxa", boom)
        with pytest.raises(PagesUnavailableError):
            pages_io.preflight()

    def test_unexpected_answer_raises(self, monkeypatch):
        monkeypatch.setattr(pages_io, "_assert_aqua", lambda: None)
        monkeypatch.setattr(pages_io, "_jxa", lambda s, timeout=180: "garbage")
        with pytest.raises(PagesUnavailableError):
            pages_io.preflight()

    def test_ok_preflight_returns_document_count(self, monkeypatch):
        monkeypatch.setattr(pages_io, "_assert_aqua", lambda: None)
        monkeypatch.setattr(pages_io, "_jxa", lambda s, timeout=180: "0")
        assert pages_io.preflight() == {"ok": True, "documents": 0}


# ── D2: rollback / verification contract (simulated write failure) ───────────


class TestD2RollbackContract:
    @pytest.fixture()
    def armed_file(self, tmp_path, monkeypatch):
        """A pages file + a readback double that fails on the post-save
        verification read, to prove the backup is restored."""
        if not _aqua_available():
            pytest.skip("no Aqua session (rollback contract reads real Pages)")
        if not PAGES_SRC.exists():
            pytest.skip("fixture missing")
        dest = tmp_path / "fixture.pages"
        shutil.copy2(PAGES_SRC, dest)

        real_read = pages_io.read_body_text
        state = {"reads": 0}

        def counting_read(p):
            state["reads"] += 1
            return real_read(p)

        monkeypatch.setattr(pages_io, "read_body_text", counting_read)
        return dest, state, monkeypatch

    def test_failed_write_restores_backup(self, armed_file):
        dest, state, monkeypatch = armed_file
        if not dest.exists():
            pytest.skip("fixture missing")

        before_bytes = dest.read_bytes()

        # Fail ONLY the write script (the one that sets bodyText + saves);
        # read scripts must still succeed, or the pre-check itself dies
        # before any backup is ever created (which is what this test is
        # NOT about).
        canned_body = json.dumps(ARABIC_BODY)  # contains '42'

        def selectively_failing_jxa(script, timeout=180):
            if "doc.bodyText = " in script:
                raise RuntimeError("JXA failed (rc=1): simulated app crash")
            return canned_body

        monkeypatch.setattr(pages_io, "_jxa", selectively_failing_jxa)
        monkeypatch.setattr(
            pages_io, "preflight", lambda timeout=20: {"ok": True, "documents": 0}
        )

        with pytest.raises(RuntimeError):
            pages_io.edit_pages_body(dest, find="42", replace="43")

        # file untouched (readback matched, no restore needed) or restored
        # — either way content identical to source
        assert dest.read_bytes() == before_bytes
        # backup was created (versioned, .pages suffix) and pruned dir exists
        backup_root = dest.parent / f"{dest.name}.backups"
        assert backup_root.is_dir()
        backups = list(backup_root.glob("*.pages"))
        assert len(backups) >= 1

    def test_verification_mismatch_restores_backup(self, armed_file):
        dest, state, monkeypatch = armed_file
        if not dest.exists():
            pytest.skip("fixture missing")

        real_read = pages_io.read_body_text
        original = real_read(dest)
        # first read: pre-check (returns real text)
        # write succeeds
        # verification read returns the WRONG text → mismatch → restore
        seq = {"n": 0}

        def misverifying_read(p):
            seq["n"] += 1
            if seq["n"] <= 1:
                return original
            return "wrong content that was never written"

        monkeypatch.setattr(pages_io, "read_body_text", misverifying_read)
        monkeypatch.setattr(
            pages_io, "preflight", lambda timeout=20: {"ok": True, "documents": 0}
        )

        with pytest.raises(EditVerificationError):
            pages_io.edit_pages_body(dest, find="42", replace="43")

        # restored: on-disk body equals the pre-edit content
        monkeypatch.setattr(pages_io, "read_body_text", real_read)
        assert real_read(dest) == original

    @pytest.mark.aqua  # reads the live body via Pages before deciding
    def test_missing_find_zero_side_effects(self, pages_file):
        # a missing find must NOT create backups or open the app:
        # monkeypatch the backup helper to prove it never runs
        calls = {"backup": 0}
        orig = pages_io._versioned_backup

        def spy(target, backup_dir):
            calls["backup"] += 1
            return orig(target, backup_dir)

        import iwork_studio.pages_io as pio

        pio._versioned_backup = spy
        try:
            with pytest.raises(ValueError) as ei:
                pages_io.edit_pages_body(
                    pages_file, find="هذا النص غير موجود أبداً XYZ", replace="no"
                )
            assert "not present" in str(ei.value)
        finally:
            pio._versioned_backup = orig
        assert calls["backup"] == 0


# ── Live Aqua tests (D1, D2 both ops, D3, D4) ─────────────────────────────────


@pytest.mark.aqua
class TestD1Read:
    def test_preflight_ok(self):
        if not _aqua_available():
            pytest.skip("no Aqua session")
        result = pages_io.preflight()
        assert result["ok"] is True
        assert isinstance(result["documents"], int)

    def test_read_body_text_arabic(self, pages_file):
        if not _aqua_available():
            pytest.skip("no Aqua session")
        body = pages_io.read_body_text(pages_file)
        assert "تقرير المشروع السنوي" in body
        assert "Annual project report" in body

    def test_read_pages_full_model(self, pages_file):
        if not _aqua_available():
            pytest.skip("no Aqua session")
        model = pages_io.read_pages(pages_file)
        assert model["ok"] if "ok" in model else True
        assert "تقرير المشروع السنوي" in model["body_text"]
        assert Path(model["docx"]).exists()
        assert model["docx_bytes"] > 1000
        joined = "\n".join(model["paragraphs"])
        assert "السعر التقديري" in joined
        assert "Annual project report" in joined

    def test_docx_export_preserves_arabic_wt_runs(self, pages_file):
        if not _aqua_available():
            pytest.skip("no Aqua session")
        docx_path = pages_io.export_docx(pages_file)
        texts = pages_io.extract_docx_text(docx_path)
        joined = "\n".join(texts)
        assert "تعديل جديد" in joined  # Arabic w:t run content


@pytest.mark.aqua
class TestD2VerifiedOps:
    def test_replace_all_arabic(self, pages_file):
        if not _aqua_available():
            pytest.skip("no Aqua session")
        result = pages_io.edit_pages_body(
            pages_file, find="السعر التقديري 42", replace="التكلفة النهائية 99"
        )
        assert result["ok"] is True
        assert "التكلفة النهائية 99" in result["after"]
        assert "السعر التقديري" not in result["after"]
        # on-disk truth: re-read
        body = pages_io.read_body_text(pages_file)
        assert "التكلفة النهائية 99" in body
        assert "تقرير المشروع السنوي" in body  # untouched Arabic survives
        # backup exists
        assert Path(result["backup"]).exists()

    def test_set_body(self, pages_file):
        if not _aqua_available():
            pytest.skip("no Aqua session")
        new_body = "مرحباً بكم في التقرير الجديد.\rWelcome to the new report."
        result = pages_io.edit_pages_body(
            pages_file, mode="set_body", new_body=new_body
        )
        assert result["ok"] is True
        assert result["after"] == new_body
        body = pages_io.read_body_text(pages_file)
        assert body == new_body

    def test_in_place_save_is_gatesave_compliant(self, pages_file):
        """The write path itself uses `save` (in-place), never `save in`
        on an on-disk file — verified by reading the module source."""
        src = (REPO / "src" / "iwork_studio" / "pages_io.py").read_text()
        assert "app.save(doc)" in src
        # 'save in' appears only in the docstring, never in a live script
        # for on-disk files (the fixture-maker d_preprobe uses it once to
        # NAME A NEW doc, which is not this module).
        write_section = src.split("D2: the two verified write ops")[1]
        assert "save(doc, {in:" not in write_section


@pytest.mark.aqua
class TestD4ArabicRenderBaseline:
    def test_render_pdf_arabic_text_layer(self, pages_file, tmp_path):
        if not _aqua_available():
            pytest.skip("no Aqua session")
        # ensure Arabic content is present via a set_body write, then
        # render-verify
        pages_io.edit_pages_body(
            pages_file,
            mode="set_body",
            new_body="السعر التقديري للتقرير العربي 42 ريالاً.\rRender baseline paragraph.",
        )
        result = pages_io.verify_render(
            pages_file,
            "تقديري",
            expected_pages=1,
            keep_pdf=tmp_path / "render_verify_output.pdf",
        )
        assert result["ok"] is True
        assert result["pages"] == 1
        assert Path(result["pdf"]).exists()

    def test_render_pdf_latin_fragment(self, pages_file):
        if not _aqua_available():
            pytest.skip("no Aqua session")
        # make the Latin content deterministic first
        pages_io.edit_pages_body(
            pages_file,
            mode="set_body",
            new_body="Render baseline paragraph for Latin text.\rفقرة عربية للتأكيد.",
        )
        result = pages_io.verify_render(pages_file, "baseline paragraph")
        assert result["ok"] is True

# ── paragraph direction (Arabic) — headless parts ────────────────────────────

def _docx_with(tmp_path, paras):
    import docx
    from docx.oxml import OxmlElement

    d = docx.Document()
    for text, rtl in paras:
        p = d.add_paragraph(text)
        if rtl:
            p._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
    out = tmp_path / "d.docx"
    d.save(str(out))
    return out


def test_docx_paragraph_directions(tmp_path):
    from iwork_studio import pages_io

    got = pages_io.docx_paragraph_directions(_docx_with(tmp_path, [("مرحبا", True), ("Hello", False)]))
    assert got == [{"text": "مرحبا", "rtl": True}, {"text": "Hello", "rtl": False}]


def test_replace_all_that_flips_rtl_is_damage():
    from iwork_studio import pages_io

    before = [{"text": "مرحبا", "rtl": True}, {"text": "x", "rtl": False}]
    after = [{"text": "أهلا", "rtl": False}, {"text": "x", "rtl": False}]
    with pytest.raises(pages_io.EditVerificationError, match="right-to-left"):
        pages_io._direction_report(before, after, "replace_all")


def test_set_body_reports_arabic_left_to_right():
    from iwork_studio import pages_io

    rep = pages_io._direction_report([], [{"text": "مرحبا", "rtl": False}, {"text": "Hi", "rtl": False}], "set_body")
    assert rep["arabic_paragraphs_left_to_right"] == [1] and "warning" in rep


def test_direction_check_is_skipped_when_unreadable():
    from iwork_studio import pages_io

    assert pages_io._direction_report(None, None, "replace_all") == {"checked": False}
