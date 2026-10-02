"""Phase B — .numbers writer test suite (B1–B6).

Gates:
- GATE-1: SEMANTIC byte-equality (content identical, file openable).
  Strict zip byte-equality is unachievable: numbers-parser re-encodes IWA
  protobuf on write (+1,632 B on unmodified save, verified evidence/a3).
  Interpretation pinned by operator directive — do not re-litigate.
- GATE-AR: Arabic round-trip ('أحمد') passes byte-exact on 4.19.0 (evidence/a3).
- GATE-CHART: writer refuses chart-container files (accepted scope cut).
- B6: render-verify loop runs only under Aqua; fails loud otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import numbers_io, render_verify  # noqa: E402

AR_VALUE = "أحمد"
AR_SHEET = "بيانات"
AR_TABLE = "جدول"


# ── B1: read_numbers semantic model ──────────────────────────────────────────


class TestReadNumbers:
    def test_model_shape(self, numbers_file):
        model = numbers_io.read_numbers(numbers_file)
        assert model["file"] == "fixture.numbers"
        assert [s["name"] for s in model["sheets"]] == [AR_SHEET]
        tables = model["sheets"][0]["tables"]
        assert [t["name"] for t in tables] == [AR_TABLE]
        t = tables[0]
        assert t["num_rows"] == 4 and t["num_cols"] == 3
        assert len(t["cells"]) == 12
        cell = t["cells"][0]
        assert cell["ref"] == "R1C1"
        assert cell["value"] == "الاسم"
        assert cell["format"]["type"] == "TextCell"

    def test_cells_carry_formula_style_format_keys(self, numbers_file):
        model = numbers_io.read_numbers(numbers_file)
        for sheet in model["sheets"]:
            for table in sheet["tables"]:
                for cell in table["cells"]:
                    assert set(("ref", "value", "format")) <= set(cell)
                    # formula/style present when populated
                    if cell.get("formula"):
                        assert isinstance(cell["formula"], str)

    def test_model_is_json_serialisable(self, numbers_file):
        import json

        json.dumps(numbers_io.read_numbers(numbers_file), ensure_ascii=False)

    def test_read_missing_file_raises(self, tmp_path):
        with pytest.raises(Exception):
            numbers_io.read_numbers(tmp_path / "nope.numbers")


# ── B2 + B3: edit_cell atomic swap + GATE-1 semantic round-trip ─────────────


class TestEditCell:
    def test_edit_cell_returns_result_and_writes(self, numbers_file):
        result = numbers_io.edit_cell(
            numbers_file, "R1C1", AR_VALUE, sheet=AR_SHEET, table=AR_TABLE
        )
        assert result["ok"] is True
        assert result["cell"]["before"] == "الاسم"
        assert result["cell"]["after"] == AR_VALUE
        model = numbers_io.read_numbers(numbers_file)
        assert model["sheets"][0]["tables"][0]["cells"][0]["value"] == AR_VALUE

    def test_excel_style_ref(self, numbers_file):
        numbers_io.edit_cell(numbers_file, "A2", "سارة", sheet=AR_SHEET, table=AR_TABLE)
        model = numbers_io.read_numbers(numbers_file)
        cells = model["sheets"][0]["tables"][0]["cells"]
        assert cells[3]["value"] == "سارة"  # R2C1

    def test_versioned_backup_created(self, numbers_file):
        result = numbers_io.edit_cell(numbers_file, "R2C2", 99)
        backup = Path(result["backup"])
        assert backup.exists()
        assert backup.suffix == ".numbers"  # openable by numbers-parser
        assert backup.parent.name == "fixture.numbers.backups"
        # backup is the PRE-write state
        from numbers_parser import Document

        d = Document(str(backup))
        t = d.sheets[0].tables[0]
        assert t.cell(1, 1).value == 34.0  # original value at R2C2

    def test_edit_number_cell(self, numbers_file):
        result = numbers_io.edit_cell(numbers_file, "R2C2", 123.5)
        assert result["cell"]["before"] == 34.0
        assert result["cell"]["after"] == 123.5

    def test_bad_ref_raises_and_leaves_file_intact(self, numbers_file):
        import hashlib

        before_hash = hashlib.sha256(numbers_file.read_bytes()).hexdigest()
        with pytest.raises(numbers_io.CellRefError):
            numbers_io.edit_cell(numbers_file, "ZZZ99", "x")
        with pytest.raises(numbers_io.CellRefError):
            numbers_io.edit_cell(numbers_file, "R99C1", "x")
        assert hashlib.sha256(numbers_file.read_bytes()).hexdigest() == before_hash

    def test_unknown_sheet_table_raises(self, numbers_file):
        with pytest.raises(numbers_io.CellRefError):
            numbers_io.edit_cell(numbers_file, "R1C1", "x", sheet="لا يوجد")
        with pytest.raises(numbers_io.CellRefError):
            numbers_io.edit_cell(numbers_file, "R1C1", "x", table="لا يوجد")

    def test_no_stray_tmp_files_after_edit(self, numbers_file):
        numbers_io.edit_cell(numbers_file, "R1C1", "تم")
        strays = [
            p.name
            for p in numbers_file.parent.iterdir()
            if p.name.startswith(".") and p.name.endswith(".numbers")
        ]
        assert strays == []


class TestGate1SemanticRoundTrip:
    """GATE-1: unmodified parse → write must preserve ALL observable content."""

    def test_unmodified_save_semantic_equality(self, numbers_file, tmp_path):
        import shutil

        from numbers_parser import Document

        out = tmp_path / "rt.numbers"
        doc = Document(str(numbers_file))  # no mutation at all
        doc.save(str(out))

        src_model = numbers_io.read_numbers(numbers_file)
        rt_model = numbers_io.read_numbers(out)
        assert numbers_io.read_model_tuples(src_model) == numbers_io.read_model_tuples(rt_model)
        # openable: reparse already succeeded above via read_numbers

    def test_edit_preserves_every_unchanged_cell(self, numbers_file):
        src_model = numbers_io.read_numbers(numbers_file)
        src_key = numbers_io._semantic_key(src_model)

        numbers_io.edit_cell(numbers_file, "R1C1", "جديد")

        after_model = numbers_io.read_numbers(numbers_file)
        after_key = numbers_io._semantic_key(after_model)
        edited = [k for k in after_key if k[2] == "R1C1"][0]
        expected = list(src_key)
        for idx, entry in enumerate(expected):
            if entry[2] == "R1C1":
                expected[idx] = (entry[0], entry[1], entry[2], edited[3])
        assert after_key == expected


# ── B4: GATE-AR Arabic round-trip ────────────────────────────────────────────


class TestGateArabic:
    def test_arabic_write_reparse_byte_exact_value(self, numbers_file):
        result = numbers_io.edit_cell(
            numbers_file, "R1C1", AR_VALUE, sheet=AR_SHEET, table=AR_TABLE
        )
        assert result["cell"]["after"] == AR_VALUE
        model = numbers_io.read_numbers(numbers_file)
        got = model["sheets"][0]["tables"][0]["cells"][0]["value"]
        assert got == AR_VALUE  # exact codepoint equality, no normalisation
        # every Arabic letter intact
        assert list(got) == list(AR_VALUE)

    def test_arabic_write_other_unchanged_arabic_cells_survive(self, numbers_file):
        numbers_io.edit_cell(numbers_file, "R2C1", "منيرة")
        model = numbers_io.read_numbers(numbers_file)
        cells = model["sheets"][0]["tables"][0]["cells"]
        assert cells[0]["value"] == "الاسم"      # R1C1 untouched Arabic
        assert cells[1]["value"] == "العمر"      # R1C2 untouched Arabic
        assert cells[3]["value"] == "منيرة"      # edited

    def test_rtl_preserved(self, numbers_file):
        """RTL mark + Arabic string round-trips exactly."""
        val = "مرحباً بكم\u200f"
        numbers_io.edit_cell(numbers_file, "R3C1", val)
        model = numbers_io.read_numbers(numbers_file)
        assert model["sheets"][0]["tables"][0]["cells"][6]["value"] == val


# ── B5: GATE-CHART refusal ───────────────────────────────────────────────────


class TestGateChart:
    def test_chart_file_refused(self, chart_file):
        with pytest.raises(numbers_io.ChartRefusalError, match="GATE-CHART"):
            numbers_io.edit_cell(chart_file, "R1C1", "x")

    def test_chart_file_read_reports_chart_flag(self, chart_file):
        """Reads via the raw detector are fine — only the writer refuses
        (scope cut is write-side). Full Document() read of a renamed
        template is not possible (templates lack DataList.iwa etc.), so
        the honest read-side check is the detector flag itself."""
        assert numbers_io.contains_charts(chart_file) is True

    def test_plain_file_not_flagged(self, numbers_file):
        assert numbers_io.contains_charts(numbers_file) is False


# ── B6: render-verify loop (Aqua only; fail loud) ───────────────────────────


class TestRenderVerify:
    @pytest.mark.aqua
    def test_aqua_assertion_detects_session(self):
        # On this dev box we run under Aqua; the check must pass here.
        # (On a headless box the same call raises AquaSessionError —
        #  fail-loud is the tested behaviour in the next test.)
        render_verify._assert_aqua()  # should not raise under Aqua

    def test_headless_raises_loud(self, monkeypatch):
        import subprocess as sp

        def fake_run(*a, **k):
            class R:
                returncode = 0
                stdout = "System"
                stderr = ""

            return R()

        monkeypatch.setattr(sp, "run", fake_run)
        with pytest.raises(render_verify.AquaSessionError):
            render_verify._assert_aqua()

    @pytest.mark.aqua
    def test_render_verify_numbers_pdf_text(self, numbers_file, tmp_path):
        """B6 live loop: Numbers → export PDF → PyMuPDF text-layer match."""
        evidence_pdf = REPO / "evidence" / "b6" / "render_verify_output.pdf"
        result = render_verify.verify_render(
            numbers_file,
            expected_fragment="الاسم",
            keep_pdf=evidence_pdf,
        )
        assert result["ok"] is True
        assert result["page_count"] == 1