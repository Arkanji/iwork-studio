"""iWork Studio — .pages read-mostly lane (Phase D).

Verified ground truth (live, iWork 15.4):
- There is NO Python .pages parser (python-pages upstream 1-star, never
  vendored — watchlist only; numbers-parser and textutil both reject
  .pages — verified negatives).
- The ONLY route is AppleScript against Pages 15.4:
    read  = open → bodyText readback (op 2) and/or export to .docx →
            python-docx text extract (D1)
    write = set bodyText (op 1) — nothing else (D2)

D2 SCOPE (general Pages authoring is out of scope by design):
  edit_pages_body() accepts mode='replace_all' or mode='set_body' ONLY.
  Anything richer raises PagesOutOfScopeError — deliberately, not
  as a TODO.

D3 PREFLIGHT: first-launch TCC consent and the Pages "Open" file dialog /
template-chooser modal BLOCK AppleEvents (every event times out -1712,
verified live this phase). preflight() distinguishes:
  - Pages not answering at all (modal/TCC) → PagesUnavailableError with
    ONE actionable prompt (dismiss the dialog once / approve TCC), never
    a retry loop.

GATE-SAVE: in-place `save` of an on-disk .pages file is now VERIFIED
WORKING (live, scripts/d_preprobe.py, this phase — closes the last
UNVERIFIED row of the spec's GATE-SAVE table): open → bodyText write →
save → close → re-open readback shows the edit on disk, Arabic intact.
`save in <arbitrary path>` remains banned for on-disk files (sandbox
denial, verified Scout ground truth). An UNSAVED (new) document may be
given its path via `save in` — that is the documented way to name a new
doc and is NOT the sandbox trap (same interpretation as the Phase C
Keynote chart fixture save).

GATE-AR: Arabic must round-trip at RENDER level for shaping-sensitive
ops — verify_render() exports PDF and matches the text layer with the
ligature-aware matcher (shared render_verify.assert_text_layer).

Writes: versioned backup before any write; the app save is in-place
(Pages owns the file while open); rollback = restore backup if the
post-save readback disagrees with the requested edit.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from iwork_studio.apps import app_name

__all__ = [
    "read_pages",
    "read_body_text",
    "document_info",
    "export_docx",
    "extract_docx_text",
    "edit_pages_body",
    "preflight",
    "render_pdf",
    "verify_render",
    "AquaSessionError",
    "PagesUnavailableError",
    "PagesOutOfScopeError",
    "OutOfScopeError",
    "EditVerificationError",
]

_APP = "Pages"
_ALLOWED_MODES = frozenset({"replace_all", "set_body"})


class AquaSessionError(RuntimeError):
    """Headless machine or Pages not installed — the .pages lane cannot run."""


class PagesUnavailableError(AquaSessionError):
    """D3: Pages is installed but NOT answering AppleEvents — a TCC
    consent dialog or the open/template-chooser modal is blocking
    (verified live: every event times out -1712 while a modal is up).
    Prompt ONCE, fail loud; never retry-loop."""


class OutOfScopeError(NotImplementedError):
    """D2: the requested Pages operation is outside the two verified ops."""


# friendly alias
PagesOutOfScopeError = OutOfScopeError


class EditVerificationError(RuntimeError):
    """Post-save readback disagreed with the requested edit — rolled back."""


# ── D3: session + TCC preflight ───────────────────────────────────────────────


def _assert_aqua() -> None:
    try:
        manager = subprocess.run(
            ["launchctl", "managername"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AquaSessionError(
            f"cannot determine session manager: {exc!r}; the .pages lane "
            "requires an Aqua (GUI) session"
        ) from exc
    if manager != "Aqua":
        raise AquaSessionError(
            f"session manager is {manager!r}, not 'Aqua' — the .pages lane "
            "cannot drive Pages headless; refusing to fake it"
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


def preflight(timeout: int = 20) -> dict:
    """D3 preflight: can Pages answer AppleEvents at all?

    Live ground truth (this phase): with the first-launch TCC consent or
    the Pages "Open" file-dialog / template-chooser modal on screen, every
    AppleEvent — even `count of documents` — times out (-1712). Once the
    modal is dismissed (or TCC approved), the same events answer
    instantly. Therefore an event timeout here means "a human must look
    at the screen ONCE", not "retry harder".

    Returns {"ok": True, "documents": N} or raises PagesUnavailableError
    with the one-time prompt. Never retries.
    """
    _assert_aqua()
    try:
        out = _jxa(
            f"(() => {{ const a = Application({app_name(_APP)!r});"
            " return a.documents.length; })()",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PagesUnavailableError(
            "Pages is not answering AppleEvents (event timeout). A modal is "
            "almost certainly blocking: the first-launch TCC consent dialog "
            "or the Pages 'Open' / template-chooser window. ACTION (once): "
            "bring Pages frontmost, dismiss the dialog (or approve TCC for "
            "osascript/Hermes), then re-run. This error will keep firing "
            "until a human clears the modal — by design (SC4 fail-loud)."
        ) from exc
    except RuntimeError as exc:
        # -1712 AppleEvent timed out arrives as a JXA failure, same meaning
        if "-1712" in str(exc) or "timed out" in str(exc).lower():
            raise PagesUnavailableError(
                "Pages is not answering AppleEvents (-1712): TCC consent or "
                "the open-dialog/template-chooser modal is blocking. ACTION "
                "(once): dismiss it in the GUI / approve TCC, then re-run."
            ) from exc
        raise
    try:
        n = int(out)
    except ValueError as exc:
        raise PagesUnavailableError(
            f"unexpected Pages preflight answer {out!r}"
        ) from exc
    return {"ok": True, "documents": n}


# ── D1: read route (AppleScript readback + docx export) ───────────────────────


def read_body_text(path: str | os.PathLike) -> str:
    """Verified op 2: open the file in Pages, read `body text`, close
    without saving. Paragraph separator is \\r (same as Keynote)."""
    script = f"""
(() => {{
  const app = Application({app_name(_APP)!r});
  const doc = app.open(Path({_js_path(path)}));
  let txt = null;
  try {{ const b = doc.bodyText(); txt = (b === null || b === undefined) ? null : b.toString(); }} catch (e) {{}}
  app.close(doc, {{saving: 'no'}});
  return JSON.stringify(txt);
}})()
"""
    txt = json.loads(_jxa(script))
    if txt is None:
        raise OutOfScopeError(
            f"{Path(path).name} is a page-layout document: it has no body text, so "
            "replace_all / set_body don't apply. Its placeholders can still be filled."
        )
    return txt


def document_info(path: str | os.PathLike) -> dict:
    """Open → is it word-processing (has body text) or page layout, how many pages → close."""
    script = f"""
(() => {{
  const app = Application({app_name(_APP)!r});
  const doc = app.open(Path({_js_path(path)}));
  let body = null, pages = null;
  try {{ const b = doc.bodyText(); body = (b === null || b === undefined) ? null : b.toString().length; }} catch (e) {{}}
  try {{ pages = doc.pages().length; }} catch (e) {{}}
  app.close(doc, {{saving: 'no'}});
  return JSON.stringify({{body_characters: body, pages: pages}});
}})()
"""
    info = json.loads(_jxa(script))
    info["kind"] = "word processing" if info.get("body_characters") is not None else "page layout"
    return info


def export_docx(
    path: str | os.PathLike,
    out_path: str | os.PathLike | None = None,
) -> Path:
    """D1: export the .pages body to .docx via Pages AppleScript.

    Export (not `save in`) is the verified-safe AppleScript surface for
    artifacts (GATE-SAVE). Returns the docx path.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if out_path is None:
        out_path = Path(tempfile.mkdtemp(prefix="iwork-pages-")) / (path.stem + ".docx")
    else:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
(() => {{
  const app = Application({app_name(_APP)!r});
  const doc = app.open(Path({_js_path(path)}));
  app.export(doc, {{to: Path({_js_path(out_path)}), as: 'Microsoft Word'}});
  app.close(doc, {{saving: 'no'}});
  return 'ok';
}})()
"""
    _jxa(script, timeout=300)
    if not out_path.exists():
        raise RuntimeError(f"Pages export reported success but {out_path} missing")
    return out_path


def extract_docx_text(docx_path: str | os.PathLike) -> list[str]:
    """python-docx paragraph extraction (pinned 1.2.0)."""
    import docx  # python-docx

    d = docx.Document(str(docx_path))
    return [p.text for p in d.paragraphs]


def read_pages(path: str | os.PathLike) -> dict:
    """D1: full read — body text via AppleScript readback + docx export
    paragraph model. Returns a JSON-serialisable evidence dict."""
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    body = read_body_text(path)
    docx_path = export_docx(path)
    paragraphs = extract_docx_text(docx_path)
    return {
        "file": path.name,
        "path": str(path),
        "body_text": body,
        "docx": str(docx_path),
        "docx_bytes": docx_path.stat().st_size,
        "paragraphs": paragraphs,
    }


# ── D2: the two verified write ops ───────────────────────────────────────────


def _versioned_backup(target: Path, backup_dir: Path) -> Path:
    """Copy target to a timestamped, versioned backup (<name>.<stamp>
    [.N].pages) before any write. Keeps the .pages suffix so Pages can
    open the backup directly for restore."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    n = 0
    while True:
        suffix = f".{stamp}.{n}" if n else f".{stamp}"
        backup = backup_dir / f"{target.name}{suffix}.pages"
        if not backup.exists():
            break
        n += 1
    shutil.copy2(target, backup)
    return backup


def edit_pages_body(
    path: str | os.PathLike,
    find: str | None = None,
    replace: str | None = None,
    *,
    mode: str = "replace_all",
    new_body: str | None = None,
    backup_dir: str | os.PathLike | None = None,
    max_backups: int = 10,
) -> dict:
    """D2: apply ONE of the two verified body-text ops, in-place.

    mode='replace_all'  (op: find/replace across the whole body text)
        requires find (and replace, which may be '' to delete).
    mode='set_body'     (op: replace the entire body text)
        requires new_body.

    ANYTHING ELSE — styles, tables, sections, headers/footers, per-
    paragraph surgery, find-with-regex, … — is general Pages authoring,
    which is out of scope by design. Raise PagesOutOfScopeError, loudly.

    Safety: versioned backup BEFORE the write; in-place app save
    (GATE-SAVE, verified live); post-save readback must contain the
    requested edit or the backup is restored (rollback) and
    EditVerificationError raised.
    """
    target = Path(path).resolve()

    # ── D2 scope gate (FIRST — a rejected request must never touch the
    # filesystem or the app, regardless of whether the file exists) ────
    if mode not in _ALLOWED_MODES:
        raise PagesOutOfScopeError(
            f"mode {mode!r} is not one of the two verified ops "
            f"( {_ALLOWED_MODES} ). General Pages authoring is REJECTED "
            "scope (by design) — do not work around this error."
        )
    if mode == "replace_all":
        if not find:
            raise PagesOutOfScopeError(
                "mode 'replace_all' requires a non-empty `find`"
            )
        if replace is None:
            raise PagesOutOfScopeError(
                "mode 'replace_all' requires `replace` (use '' to delete)"
            )
    else:  # set_body
        if new_body is None:
            raise PagesOutOfScopeError(
                "mode 'set_body' requires `new_body`"
            )
        if find is not None:
            raise PagesOutOfScopeError(
                "mode 'set_body' does not take `find`/`replace` — per-"
                "fragment surgery is not one of the two verified ops"
            )

    if not target.exists():
        raise FileNotFoundError(target)

    preflight()

    # Pre-check (BEFORE any side effect — a missing find creates zero
    # backups, zero app opens):
    before = read_body_text(target)
    if mode == "replace_all":
        assert find is not None  # narrowed by the scope gate above
        assert replace is not None
        if find not in before:
            raise ValueError(f"find {find!r} not present in body text of {target}")

    if backup_dir is None:
        backup_dir = target.parent / f"{target.name}.backups"
    backup_dir = Path(backup_dir)
    backup_path = _versioned_backup(target, backup_dir)
    _prune_backups(backup_dir, max_backups)

    if mode == "replace_all":
        assert find is not None and replace is not None
        new_text = before.replace(find, replace)
    else:
        assert new_body is not None
        new_text = new_body

    # ── the write: open → set bodyText → IN-PLACE save (GATE-SAVE) ────
    script = f"""
(() => {{
  const app = Application({app_name(_APP)!r});
  const doc = app.open(Path({_js_path(target)}));
  doc.bodyText = {new_text!r};
  app.save(doc);            // IN-PLACE save only — GATE-SAVE
  app.close(doc, {{saving: 'no'}});
  return 'saved';
}})()
"""
    try:
        _jxa(script, timeout=300)
    except Exception:
        # App-side failure before/around save — the file may or may not
        # have been touched; verify and roll back if it moved.
        _rollback_if_changed(target, backup_path, before)
        raise

    # ── verification: post-save readback must show the edit ───────────
    after = read_body_text(target)
    if after != new_text:
        _restore(target, backup_path)
        raise EditVerificationError(
            "post-save readback disagrees with the requested edit; "
            f"backup restored. expected={new_text!r} readback={after!r}"
        )

    return {
        "ok": True,
        "file": str(target),
        "mode": mode,
        "before": before,
        "after": after,
        "changed": before != after,
        "backup": str(backup_path),
    }


def _rollback_if_changed(target: Path, backup: Path, before_text: str) -> None:
    """After a failed JXA write: restore the backup only if the file
    actually moved (compare content via readback; fall back to mtime)."""
    try:
        now_text = read_body_text(target)
        if now_text != before_text:
            _restore(target, backup)
    except Exception:
        # cannot read — restore unconditionally, safest
        _restore(target, backup)


def _restore(target: Path, backup: Path) -> None:
    if backup.exists():
        shutil.copy2(backup, target)


def _prune_backups(backup_dir: Path, max_backups: int) -> None:
    try:
        backups = sorted(
            (
                p
                for p in backup_dir.iterdir()
                if p.name.endswith(".pages") and p.name != backup_dir.name
            ),
            key=lambda p: p.name,
        )
        stamp_marker = tuple(".0123456789-")
        backups = [
            b
            for b in backups
            if len(b.name.split(".")) >= 3 and b.name.split(".")[-2].isdigit()
        ]
        for old in backups[:-max_backups] if max_backups > 0 else []:
            old.unlink()
    except OSError:
        pass


# ── D4: render-verify (Pages export → PyMuPDF) ────────────────────────────────


def render_pdf(
    pages_path: str | os.PathLike,
    out_dir: str | os.PathLike | None = None,
) -> Path:
    """Open the .pages file in Pages and export a PDF (export, not save —
    GATE-SAVE). Returns the exported PDF path."""
    _assert_aqua()
    pages_path = Path(pages_path).resolve()
    if not pages_path.exists():
        raise FileNotFoundError(pages_path)
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="iwork-pages-render-"))
    else:
        out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / (pages_path.stem + ".pdf")
    script = f"""
(() => {{
  const app = Application({app_name(_APP)!r});
  const doc = app.open(Path({_js_path(pages_path)}));
  app.export(doc, {{to: Path({_js_path(pdf_path)}), as: 'PDF'}});
  app.close(doc, {{saving: 'no'}});
  return 'ok';
}})()
"""
    _jxa(script, timeout=300)
    if not pdf_path.exists():
        raise RuntimeError(
            f"Pages export reported success but {pdf_path} does not exist"
        )
    return pdf_path


def verify_render(
    pages_path: str | os.PathLike,
    expected_fragment: str,
    expected_pages: int | None = None,
    keep_pdf: str | os.PathLike | None = None,
) -> dict:
    """D4 full loop: Pages → export PDF → PyMuPDF text-layer match
    (ligature-aware Arabic matcher shared with Phases B/C —
    render_verify.assert_text_layer)."""
    import pymupdf as fitz

    from iwork_studio.render_verify import assert_page_count, assert_text_layer

    pdf = render_pdf(pages_path, out_dir=Path(tempfile.mkdtemp(prefix="iwork-prender-")))
    try:
        with fitz.open(pdf) as doc:
            pages = doc.page_count
        if expected_pages is not None:
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
        "pages": pages,
        "fragment": expected_fragment,
        "text_sample": text_sample,
    }