"""iWork Studio — Keynote AppleScript fallback + render-verify (C6/C7).

C6 fallback (ONLY for files locked/open in Keynote — i.e. when the direct
keynote-parser route raises FileLockedError):
  - reads/writes via `object text of text item` (NEVER slide title/body
    props — they throw -1700 on Keynote 15.4, spec ground truth)
  - IN-PLACE `save` only (GATE-SAVE: `save in <arbitrary path>` is the
    sandbox denial trap). Keynote in-place save verified working live,
    2026-10-01, scripts/c_preprobe5.py: open → objectText write → save →
    close → parser re-read shows the edit, Arabic intact. This closes the
    "Keynote/Pages unverified" gap in the spec's GATE-SAVE table.

C7 render-verify: Keynote `export ... as PDF` → PyMuPDF text layer,
reusing render_verify.assert_text_layer (ligature-aware Arabic matching).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF

from iwork_studio.apps import app_name

__all__ = [
    "read_text_items",
    "write_text_item",
    "applescript_edit_text",
    "render_pdf",
    "verify_render",
    "AquaSessionError",
]

_APP = "Keynote"


class AquaSessionError(RuntimeError):
    """Headless machine or Keynote not installed — cannot run the fallback."""


def _assert_aqua() -> None:
    """Fail loud when there is no GUI session (SC4: never silently)."""
    try:
        manager = subprocess.run(
            ["launchctl", "managername"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AquaSessionError(
            f"cannot determine session manager: {exc!r}; the Keynote "
            "AppleScript fallback requires an Aqua (GUI) session"
        ) from exc
    if manager != "Aqua":
        raise AquaSessionError(
            f"session manager is {manager!r}, not 'Aqua' — the Keynote "
            "fallback cannot drive the app headless; refusing to fake it"
        )


def _jxa(script: str, timeout: int = 180) -> str:
    _assert_aqua()
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"JXA failed (rc={result.returncode}): {result.stderr.strip()[:500]}"
        )
    return result.stdout.strip()


def _js_path(p) -> str:
    return repr(str(Path(p).resolve()))


# ── C6: object-text reads/writes ──────────────────────────────────────────────


def read_text_items(path: str | os.PathLike) -> list[dict]:
    """Open the deck in Keynote and read every slide's text items via
    `object text` (the -1700-safe property). Returns
    [{"slide": 1-based, "item": 0-based, "text": ...}]."""
    script = f"""
(() => {{
  const app = Application({app_name(_APP)!r});
  const doc = app.open(Path({_js_path(path)}));
  const out = [];
  const slides = doc.slides();
  for (let s = 0; s < slides.length; s++) {{
    const tis = slides[s].textItems();
    for (let i = 0; i < tis.length; i++) {{
      out.push({{slide: s + 1, item: i, text: tis[i].objectText().toString()}});
    }}
  }}
  app.close(doc, {{saving: 'no'}});
  return JSON.stringify(out);
}})()
"""
    return json.loads(_jxa(script))


def write_text_item(
    path: str | os.PathLike,
    slide: int,
    item: int,
    text: str,
) -> dict:
    """Write one text item via `object text`, then IN-PLACE save (never
    `save in <path>` — GATE-SAVE). 1-based slide, 0-based item."""
    script = f"""
(() => {{
  const app = Application({app_name(_APP)!r});
  const doc = app.open(Path({_js_path(path)}));
  const ti = doc.slides[{slide - 1}].textItems[{item}];
  const before = ti.objectText().toString();
  ti.objectText = {text!r};
  app.save(doc);            // IN-PLACE save only — GATE-SAVE
  const after = ti.objectText().toString();
  app.close(doc, {{saving: 'no'}});
  return JSON.stringify({{before: before, after: after}});
}})()
"""
    return json.loads(_jxa(script))


def applescript_edit_text(
    path: str | os.PathLike,
    find: str,
    replace: str,
) -> dict:
    """C6 route: find/replace across every text item via object text.

    Only for files where the direct parser route is impossible
    (FileLockedError — file open/locked in Keynote). No backup/manifest
    side-effects here (Keynote owns the file while it is open; the caller
    should close the app-side copy and re-enter the parser route).
    """
    items = read_text_items(path)
    hits = [e for e in items if find in e["text"]]
    if not hits:
        raise ValueError(f"find {find!r} not found in any text item of {path}")
    changes = []
    for entry in hits:
        new_text = entry["text"].replace(find, replace)
        result = write_text_item(
            path, entry["slide"], entry["item"], new_text
        )
        changes.append(
            {
                "slide": entry["slide"],
                "item": entry["item"],
                "before": entry["text"],
                "after": result["after"],
            }
        )
    return {"ok": True, "file": str(Path(path).resolve()), "changes": changes}


# ── C7: render-verify (Keynote export → PyMuPDF) ──────────────────────────────


def render_pdf(key_path: str | os.PathLike, out_dir: str | os.PathLike | None = None) -> Path:
    """Open the deck in Keynote and export a PDF (never `save in <path>`;
    export is the verified-safe AppleScript surface for artifacts)."""
    _assert_aqua()
    key_path = Path(key_path).resolve()
    if not key_path.exists():
        raise FileNotFoundError(key_path)
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="iwork-render-"))
    else:
        out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / (key_path.stem + ".pdf")
    script = f"""
(() => {{
  const app = Application({app_name(_APP)!r});
  const doc = app.open(Path({_js_path(key_path)}));
  app.export(doc, {{to: Path({_js_path(pdf_path)}), as: 'PDF'}});
  app.close(doc, {{saving: 'no'}});
  return 'ok';
}})()
"""
    _jxa(script, timeout=300)
    if not pdf_path.exists():
        raise RuntimeError(
            f"Keynote export reported success but {pdf_path} does not exist"
        )
    return pdf_path


def verify_render(
    key_path: str | os.PathLike,
    expected_fragment: str,
    expected_slides: int | None = None,
    keep_pdf: str | os.PathLike | None = None,
) -> dict:
    """C7 full loop: Keynote → export PDF → PyMuPDF text-layer match
    (reuses render_verify.assert_text_layer — ligature-aware for Arabic)."""
    import shutil

    from iwork_studio.render_verify import assert_page_count, assert_text_layer

    pdf = render_pdf(key_path, out_dir=Path(tempfile.mkdtemp(prefix="iwork-krender-")))
    try:
        with fitz.open(pdf) as doc:
            pages = doc.page_count
        if expected_slides is not None:
            assert_page_count(pdf, expected_slides)
        assert_text_layer(pdf, expected_fragment)
    finally:
        if keep_pdf:
            shutil.copy2(pdf, keep_pdf)
    with fitz.open(pdf) as doc:
        text_sample = doc[0].get_text()[:400]
    return {
        "ok": True,
        "pdf": str(pdf),
        "pages": pages,
        "fragment": expected_fragment,
        "text_sample": text_sample,
    }