"""iWork Studio — reading PDFs for verification (pdfminer.six, MIT).

Every render check, format check and PDF-export check reads PDFs through here:
page count, page size, password protection, text per page, and text spans with
their font, size and fill colour.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["page_count", "page_sizes", "page_texts", "needs_password", "opens_with", "spans", "PdfError"]


class PdfError(RuntimeError):
    """The PDF can't be read (damaged, or locked with a password)."""


def _open(path, password: str = ""):
    from pdfminer.pdfdocument import PDFDocument, PDFPasswordIncorrect
    from pdfminer.pdfparser import PDFParser

    fh = open(path, "rb")
    try:
        return fh, PDFDocument(PDFParser(fh), password=password)
    except PDFPasswordIncorrect:
        fh.close()
        raise
    except Exception as exc:  # noqa: BLE001
        fh.close()
        raise PdfError(f"can't read {Path(path).name}: {exc}") from exc


def needs_password(path: str | os.PathLike) -> bool:
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    try:
        fh, _ = _open(path)
        fh.close()
        return False
    except PDFPasswordIncorrect:
        return True


def opens_with(path: str | os.PathLike, password: str) -> bool:
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    try:
        fh, _ = _open(path, password)
        fh.close()
        return True
    except PDFPasswordIncorrect:
        return False


def _pages(path, password: str = ""):
    from pdfminer.pdfpage import PDFPage

    fh, doc = _open(path, password)
    try:
        return fh, list(PDFPage.create_pages(doc))
    except Exception:
        fh.close()
        raise


def page_count(path: str | os.PathLike, password: str = "") -> int:
    fh, pages = _pages(path, password)
    fh.close()
    return len(pages)


def page_sizes(path: str | os.PathLike, password: str = "") -> list[tuple[float, float]]:
    fh, pages = _pages(path, password)
    fh.close()
    out = []
    for p in pages:
        x0, y0, x1, y1 = p.mediabox
        w, h = abs(x1 - x0), abs(y1 - y0)
        out.append((round(h, 1), round(w, 1)) if (p.rotate or 0) % 180 else (round(w, 1), round(h, 1)))
    return out


def _layouts(path, password: str = ""):
    from pdfminer.layout import LAParams
    from pdfminer.high_level import extract_pages

    return extract_pages(str(path), password=password, laparams=LAParams())


def page_texts(path: str | os.PathLike, password: str = "") -> list[str]:
    from pdfminer.layout import LTTextContainer

    return ["".join(el.get_text() for el in page if isinstance(el, LTTextContainer))
            for page in _layouts(path, password)]


def _hex(color) -> str | None:
    """pdfminer fill colour (gray, RGB or CMYK, 0–1 floats or a pattern name) → #rrggbb."""
    if color is None or isinstance(color, str):
        return None
    vals = list(color) if isinstance(color, (list, tuple)) else [color]
    try:
        vals = [float(v) for v in vals]
    except (TypeError, ValueError):
        return None
    if len(vals) == 1:
        r = g = b = vals[0]
    elif len(vals) == 3:
        r, g, b = vals
    elif len(vals) == 4:
        c, m, y, k = vals
        r, g, b = (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)
    else:
        return None
    scale = 255.0 if max(r, g, b) > 1.0 else 1.0
    return "#" + "".join(f"{max(0, min(255, round(v / scale * 255))):02x}" for v in (r, g, b))


def spans(path: str | os.PathLike, password: str = "") -> list[dict]:
    """Pages with size and text spans: runs of characters sharing font, size and colour."""
    from pdfminer.layout import LTChar, LTTextContainer, LTTextLine

    out = []
    sizes = page_sizes(path, password)
    for n, page in enumerate(_layouts(path, password), start=1):
        runs: list[dict] = []
        for el in page:
            if not isinstance(el, LTTextContainer):
                continue
            for line in el:
                if not isinstance(line, LTTextLine):
                    continue
                cur = None
                for ch in line:
                    if not isinstance(ch, LTChar):
                        if cur is not None and ch.get_text() == " ":
                            cur["text"] += " "
                        continue
                    key = (ch.fontname, round(ch.size, 1), _hex(ch.graphicstate.ncolor))
                    if cur is None or cur["_key"] != key:
                        cur = {"_key": key, "text": "", "font": ch.fontname.split("+", 1)[-1], "size": key[1],
                               "color": key[2]}
                        runs.append(cur)
                    cur["text"] += ch.get_text()
        for r in runs:
            r.pop("_key")
            r["bold"] = "bold" in r["font"].lower()
        w, h = sizes[n - 1] if n - 1 < len(sizes) else (None, None)
        out.append({"page": n, "width_pt": w, "height_pt": h, "spans": [r for r in runs if r["text"].strip()]})
    return out
