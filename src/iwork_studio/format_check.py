"""iWork Studio — independent formatting check on the rendered PDF.

The writers verify formatting by re-reading the file with the same library
that wrote it. This module is the independent second opinion: export a PDF
through the real app and read what was actually drawn — the font, size and
colour of the text spans, and the page size — with PyMuPDF.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pymupdf as fitz  # PyMuPDF (`import fitz` prints to stdout)

__all__ = ["inspect_pdf_text", "check_pdf_format", "verify_format", "FormatMismatch"]

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


class FormatMismatch(AssertionError):
    """The rendered PDF does not show the expected formatting."""


def _norm_font(name: str) -> str:
    # PDF font names carry subset prefixes ("ABCDEF+HelveticaNeue-Bold") and no spaces
    name = name.split("+", 1)[-1]
    return re.sub(r"[\s_-]", "", name).lower()


def _hex(color_int: int) -> str:
    return f"#{color_int:06x}"


def inspect_pdf_text(pdf_path: str | os.PathLike, contains: str | None = None) -> dict:
    """Spans (text, font, size, colour) per page, optionally filtered."""
    out = {"pages": []}
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc, start=1):
            spans = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        t = span.get("text", "")
                        if not t.strip() or (contains and contains not in t):
                            continue
                        spans.append({"text": t, "font": span["font"], "size": round(span["size"], 1),
                                      "color": _hex(span["color"]), "bold": "bold" in span["font"].lower()})
            out["pages"].append({"page": i, "width_pt": round(page.rect.width, 1),
                                 "height_pt": round(page.rect.height, 1), "spans": spans})
    return out


def check_pdf_format(pdf_path: str | os.PathLike, text: str, *, font: str | None = None,
                     size: float | None = None, color: str | None = None, bold: bool | None = None,
                     page_size: tuple[float, float] | None = None, size_tolerance: float = 0.6) -> dict:
    """Assert some span containing `text` is drawn with the given attributes."""
    info = inspect_pdf_text(pdf_path, contains=text)
    candidates = [s for p in info["pages"] for s in p["spans"]]
    if not candidates:
        raise FormatMismatch(f"{text!r} is not in the rendered PDF's text layer")
    want_color = None
    if color is not None:
        m = _HEX.match(color)
        if not m:
            raise ValueError(f"colour {color!r} must be hex like #1A7F79")
        want_color = "#" + m.group(1).lower()

    def ok(s):
        return ((font is None or _norm_font(font) in _norm_font(s["font"]))
                and (size is None or abs(s["size"] - float(size)) <= size_tolerance)
                and (want_color is None or s["color"] == want_color)
                and (bold is None or s["bold"] == bool(bold)))

    match = next((s for s in candidates if ok(s)), None)
    if match is None:
        raise FormatMismatch(f"{text!r} is rendered, but not with the expected formatting; seen: {candidates[:5]}")
    result = {"ok": True, "text": text, "span": match}
    if page_size is not None:
        first = info["pages"][0]
        got = (first["width_pt"], first["height_pt"])
        if abs(got[0] - page_size[0]) > 1 or abs(got[1] - page_size[1]) > 1:
            raise FormatMismatch(f"page size is {got} pt, expected {tuple(page_size)}")
        result["page_size_pt"] = got
    return result


def verify_format(path: str | os.PathLike, text: str, **expect) -> dict:
    """Export via the app (macOS + GUI) and check the rendered formatting."""
    path = Path(path).resolve()
    ext = path.suffix.lower()
    out_dir = Path(tempfile.mkdtemp(prefix="iwork-fmtcheck-"))
    if ext == ".numbers":
        from iwork_studio.render_verify import render_pdf
    elif ext == ".key":
        from iwork_studio.keynote_applescript import render_pdf
    elif ext == ".pages":
        from iwork_studio.pages_io import render_pdf
    else:
        raise ValueError(f"unsupported file type {ext!r}")
    pdf = render_pdf(path, out_dir)
    result = check_pdf_format(pdf, text, **expect)
    result["pdf"] = str(pdf)
    return result
