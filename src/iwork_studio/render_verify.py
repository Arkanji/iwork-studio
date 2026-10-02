"""iWork Studio — render verification loop (B6): Numbers → PDF → PyMuPDF.

Protocol (data-model.md VerificationLoop):
  render_pdf(path) → PyMuPDF doc
  assert_page_count(expected)
  assert_text_layer(expected_fragment, page=None)

Requires an Aqua (GUI) session: Numbers is driven via AppleScript to export
a PDF. If headless, this module FAILS LOUD — never silently (SC4).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf as fitz  # PyMuPDF (`import fitz` prints a deprecation warning to stdout)

from iwork_studio.apps import app_name

__all__ = [
    "render_pdf",
    "assert_page_count",
    "assert_text_layer",
    "verify_render",
    "AquaSessionError",
]


class AquaSessionError(RuntimeError):
    """Headless machine or Numbers not installed — render-verify cannot run."""


def _assert_aqua() -> None:
    """Fail loud when there is no GUI session (SC4: never silently)."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        # SSH sessions can still forward a Aqua session on macOS; the
        # launchd check below is the authoritative one.
        pass
    if not os.path.exists("/System/Library/LaunchDaemons/com.apple.launchd.plist"):
        pass  # non-macOS guard; kept harmless
    session = os.environ.get("SECURE_SERVER_SESSION")  # unused, informational
    # Authoritative check: Aqua session exists iff /System/Library/Session
    # has a console owner or `launchctl managername` says "Aqua".
    try:
        manager = subprocess.run(
            ["launchctl", "managername"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AquaSessionError(
            f"cannot determine session manager: {exc!r}; "
            "render-verify requires an Aqua (GUI) session — failing loud"
        ) from exc
    if manager != "Aqua":
        raise AquaSessionError(
            f"session manager is {manager!r}, not 'Aqua' — render-verify "
            "requires an Aqua (GUI) session; refusing to fake verification"
        )


def render_pdf(numbers_path: str | os.PathLike, out_dir: str | os.PathLike | None = None) -> Path:
    """Open `numbers_path` in Numbers via AppleScript and export a PDF.

    Returns the exported PDF path. Uses a tmp export path inside out_dir
    (or a temp dir), never `save in <arbitrary path>` inside Numbers
    (GATE-SAVE: sandbox denial is verified ground truth — export, not save).
    """
    _assert_aqua()
    numbers_path = Path(numbers_path).resolve()
    if not numbers_path.exists():
        raise FileNotFoundError(numbers_path)

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="iwork-render-"))
    else:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / (numbers_path.stem + ".pdf")

    script = f"""
tell application "{app_name('Numbers')}"
    open POSIX file "{numbers_path}"
    delay 1
    set theDoc to front document
    set docName to name of theDoc
    with timeout of 30 seconds
        export theDoc to POSIX file "{pdf_path}" as PDF
    end timeout
    close theDoc saving no
end tell
"""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"AppleScript PDF export failed (rc={result.returncode}): "
            f"{result.stderr.strip()}"
        )
    if not pdf_path.exists():
        raise RuntimeError(
            f"AppleScript reported success but PDF {pdf_path} does not exist"
        )
    return pdf_path


def assert_page_count(pdf_path: str | os.PathLike, expected: int) -> None:
    with fitz.open(pdf_path) as doc:
        actual = doc.page_count
    if actual != expected:
        raise AssertionError(f"page count: expected {expected}, got {actual}")


def assert_text_layer(
    pdf_path: str | os.PathLike,
    expected_fragment: str,
    page: int | None = None,
) -> None:
    """Assert `expected_fragment` appears in the PDF text layer.

    Arabic: the text layer of a Numbers-exported PDF stores visual-order
    glyphs with shaped ligatures, so extraction can decompose/reorder:
    verified live, 'الاسم' extracts as 'االسم' (lam-alef ligature split and
    bidi-reordered). A match on ANY of three candidates is a pass:
      1. the logical string itself
      2. its reversed (visual-order) form
      3. a ligature-aware pass: some token in the text layer is a
         character-multiset match for the fragment (same letters, any
         order/ligature decomposition). Arabic-only, never applied to
         Latin fragments, so it cannot mask a wrong-language render.
    """
    with fitz.open(pdf_path) as doc:
        if page is None:
            text = "\n".join(p.get_text() for p in doc)
        else:
            text = doc[page].get_text()
    candidates = [expected_fragment]
    is_arabic = any("\u0600" <= ch <= "\u06FF" for ch in expected_fragment)
    if is_arabic:
        candidates.append(expected_fragment[::-1])
    text_c = text
    for cand in candidates:
        if cand in text_c:
            return
    if is_arabic:
        # Ligature-aware pass: the fragment's character multiset must
        # match some whitespace-separated token exactly (no substring
        # loosening — token-level, so neighbouring cells can't satisfy it).
        frag_set = sorted(ch for ch in expected_fragment if not ch.isspace())
        for token in text_c.split():
            tok_set = sorted(ch for ch in token if not ch.isspace())
            if tok_set == frag_set:
                return
    raise AssertionError(
        f"fragment {expected_fragment!r} not found in PDF text layer"
    )


def verify_render(
    numbers_path: str | os.PathLike,
    expected_fragment: str,
    expected_pages: int = 1,
    keep_pdf: str | os.PathLike | None = None,
) -> dict:
    """Full B6 render-verify loop for a .numbers file.

    Returns a JSON-serialisable evidence dict. On Aqua absence raises
    AquaSessionError (fail-loud, SC4).
    """
    pdf = render_pdf(numbers_path)
    try:
        assert_page_count(pdf, expected_pages)
        assert_text_layer(pdf, expected_fragment)
    finally:
        if keep_pdf:
            shutil.copy2(pdf, keep_pdf)
    with fitz.open(pdf) as doc:
        text_sample = doc[0].get_text()[:400]
    return {
        "ok": True,
        "pdf": str(pdf),
        "page_count": expected_pages,
        "fragment": expected_fragment,
        "text_sample": text_sample,
    }