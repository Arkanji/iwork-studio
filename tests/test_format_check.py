"""PDF formatting check — headless, on PDFs drawn with PyMuPDF itself."""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf as fitz
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import format_check as fc  # noqa: E402


@pytest.fixture()
def pdf(tmp_path):
    p = tmp_path / "x.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text((72, 100), "Revenue", fontname="helv", fontsize=14, color=(0x1A / 255, 0x7F / 255, 0x79 / 255))
    page.insert_text((72, 140), "Notes", fontname="hebo", fontsize=10, color=(0, 0, 0))
    doc.save(p)
    return p


def test_inspect_lists_spans(pdf):
    info = fc.inspect_pdf_text(pdf)
    texts = {s["text"] for s in info["pages"][0]["spans"]}
    assert {"Revenue", "Notes"} <= texts and info["pages"][0]["width_pt"] == 595.0


def test_matching_format_passes(pdf):
    r = fc.check_pdf_format(pdf, "Revenue", font="Helvetica", size=14, color="#1A7F79", page_size=(595, 842))
    assert r["ok"] and r["span"]["size"] == 14.0


@pytest.mark.parametrize("kw", [{"size": 20}, {"color": "#FF0000"}, {"font": "Times"}, {"bold": True},
                                {"page_size": (612, 792)}])
def test_mismatch_is_reported(pdf, kw):
    with pytest.raises(fc.FormatMismatch):
        fc.check_pdf_format(pdf, "Revenue", **kw)


def test_bold_detected(pdf):
    assert fc.check_pdf_format(pdf, "Notes", bold=True)["ok"]


def test_missing_text(pdf):
    with pytest.raises(fc.FormatMismatch, match="not in the rendered"):
        fc.check_pdf_format(pdf, "Profit")
