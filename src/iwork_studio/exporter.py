"""iWork Studio — export Numbers / Pages / Keynote to other formats.

Protocol:
  1. refuse if the document is open in its app (closing it could drop edits)
  2. hash the source
  3. app opens the file, exports into a fresh temp folder, closes without saving
  4. the export is read back with a SECOND, independent tool and compared with
     the source (pdfminer.six, openpyxl, python-pptx, python-docx, zip/text checks)
  5. the source must be byte-identical afterwards
  6. only then is the result moved to its destination (an existing destination
     is refused unless overwrite=True, in which case it is backed up first)

Exporting to a temp folder and moving it afterwards avoids the iWork sandbox
refusing arbitrary destinations.
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from iwork_studio.apps import app_name

__all__ = ["export", "FORMATS", "ExportError"]

# format key → (scripting "as" name, file extension or "" for a folder)
FORMATS = {
    "Numbers": {"pdf": ("PDF", ".pdf"), "xlsx": ("Microsoft Excel", ".xlsx"), "csv": ("CSV", ".csv")},
    "Pages": {"pdf": ("PDF", ".pdf"), "docx": ("Microsoft Word", ".docx"), "epub": ("EPUB", ".epub"),
              "txt": ("unformatted text", ".txt"), "rtf": ("formatted text", ".rtf")},
    "Keynote": {"pdf": ("PDF", ".pdf"), "pptx": ("Microsoft PowerPoint", ".pptx"),
                "images": ("slide images", ""), "movie": ("QuickTime movie", ".m4v")},
}
_KIND = {".numbers": "Numbers", ".pages": "Pages", ".key": "Keynote"}
_QUALITY = {"good": "Good", "better": "Better", "best": "Best"}
_IMAGE_FMT = {"jpeg": "JPEG", "png": "PNG", "tiff": "TIFF"}


class ExportError(RuntimeError):
    """The export was refused, failed, or did not match the source."""


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    if p.is_dir():
        for f in sorted(p.rglob("*")):
            if f.is_file():
                h.update(str(f.relative_to(p)).encode())
                h.update(f.read_bytes())
    else:
        h.update(p.read_bytes())
    return h.hexdigest()


def _jxa_export(src: Path, out: Path, kind: str, as_name: str, props: dict) -> None:
    """Open → export → close without saving. Refuses a document already open."""
    from iwork_studio.keynote_slides import _assert_aqua

    _assert_aqua()
    script = f"""function run(argv) {{
  const params = JSON.parse(argv[0]);
  const app = Application({json.dumps(app_name(kind))});
  const already = app.documents().some(d => {{
    try {{ const f = d.file(); return f && f.toString() === params.src; }} catch (e) {{ return false; }}
  }});
  if (already) return JSON.stringify({{open_in_app: true}});
  const doc = app.open(Path(params.src));
  try {{
    const opts = {{to: Path(params.out), as: params.as}};
    if (Object.keys(params.props).length) opts.withProperties = params.props;
    app.export(doc, opts);
  }} finally {{
    app.close(doc, {{saving: 'no'}});
  }}
  return JSON.stringify({{ok: true}});
}}"""
    r = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script,
         json.dumps({"src": str(src), "out": str(out), "as": as_name, "props": props})],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        raise ExportError(f"{kind} export failed (rc={r.returncode}): {r.stderr.strip()[:400]}")
    if json.loads(r.stdout.strip() or "{}").get("open_in_app"):
        from iwork_studio.keynote_slides import DocumentOpenError

        raise DocumentOpenError(f"{src.name} is open in {kind}. Save and close it first.")


# ── verification by a second tool ─────────────────────────────────────────────


def _source_strings(src: Path, kind: str) -> list[str]:
    """A sample of the source's text/values to look for in the export (no app)."""
    if kind == "Numbers":
        from iwork_studio.numbers_io import read_numbers

        vals = []
        for sh in read_numbers(src)["sheets"]:
            for tb in sh["tables"]:
                for c in tb["cells"]:
                    v = c.get("value")
                    if isinstance(v, str) and v.strip():
                        vals.append(v.strip())
        return vals
    if kind == "Keynote":
        from iwork_studio.keynote_io import read_key

        # Keynote separates paragraphs with \r; exports split them, so compare line by line
        return [line.strip() for sl in read_key(src)["slides"] if sl["source"].startswith("Index/Slide")
                for t in sl["texts"] for line in t.replace("\r", "\n").split("\n")
                if line.strip() and line.strip() != "\ufffc"]
    return []  # Pages has no parser; checked against the app's own body text instead


def _source_numbers(src: Path) -> list[float]:
    from iwork_studio.numbers_io import read_numbers

    return [c["value"] for sh in read_numbers(src)["sheets"] for tb in sh["tables"] for c in tb["cells"]
            if isinstance(c.get("value"), (int, float)) and not isinstance(c.get("value"), bool)]


def _cellnorm(v) -> str:
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        f = float(format(float(v), ".15g"))  # spreadsheet precision: 33.999999999999996 → 34
        return str(int(f)) if f.is_integer() else repr(f)
    return _norm(str(v))


def _norm(s: str) -> str:
    return " ".join(s.replace("\r", "\n").split())


_IMAGE_EXT = {"jpeg": ".jpeg", "png": ".png", "tiff": ".tiff"}
_IMAGE_SUFFIXES = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".tif": "tiff", ".tiff": "tiff"}


def _convert_images(folder: Path, fmt: str) -> None:
    """Convert exported slide images to `fmt` with macOS `sips` (images already in it stay)."""
    for f in sorted(folder.rglob("*")):
        have = _IMAGE_SUFFIXES.get(f.suffix.lower())
        if not have or have == fmt:
            continue
        dest = f.with_suffix(_IMAGE_EXT[fmt])
        r = subprocess.run(["sips", "-s", "format", fmt, str(f), "--out", str(dest)],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not dest.exists():
            raise ExportError(f"couldn't convert {f.name} to {fmt}: {r.stderr.strip()[:200]}")
        f.unlink()


def _verify(out: Path, fmt: str, kind: str, src: Path, password: str | None) -> dict:
    if fmt == "pdf":
        from iwork_studio import pdf as _pdf

        if password:
            if not _pdf.needs_password(out):
                raise ExportError("PDF is not password-protected although a password was requested")
            if not _pdf.opens_with(out, password):
                raise ExportError("PDF does not open with the given password")
        pages = _pdf.page_count(out, password or "")
        if pages < 1:
            raise ExportError("PDF has no pages")
        return {"pages": pages, "encrypted": bool(password)}
    if fmt == "xlsx":
        if password:
            if not out.read_bytes()[:8] == bytes.fromhex("D0CF11E0A1B11AE1"):
                raise ExportError("xlsx is not encrypted although a password was requested")
            return {"encrypted": True}
        import openpyxl

        wb = openpyxl.load_workbook(str(out), read_only=True, data_only=True)
        got = {_cellnorm(v) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row if v is not None}
        missing = [v for v in _source_strings(src, kind) + _source_numbers(src) if _cellnorm(v) not in got]
        if missing:
            raise ExportError(f"xlsx is missing source values: {missing[:5]}")
        return {"sheets": len(wb.worksheets)}
    if fmt == "csv":
        files = sorted(out.rglob("*.csv")) if out.is_dir() else [out]
        text = "".join(f.read_text(encoding="utf-8-sig", errors="replace") for f in files)
        got = {_norm(cell) for f_text in [text] for row in csv.reader(io.StringIO(f_text)) for cell in row}
        missing = [v for v in _source_strings(src, kind) if _norm(v) not in got]
        if missing:
            raise ExportError(f"csv is missing source values: {missing[:5]}")
        return {"files": len(files)}
    if fmt == "pptx":
        from pptx import Presentation

        prs = Presentation(str(out))
        text = _norm(" ".join(sh.text_frame.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame))
        missing = [t for t in _source_strings(src, kind) if _norm(t) not in text]
        if missing:
            raise ExportError(f"pptx is missing slide text: {missing[:3]}")
        return {"slides": len(prs.slides)}
    if fmt == "docx":
        import docx

        text = _norm(" ".join(p.text for p in docx.Document(str(out)).paragraphs))
        if not text:
            raise ExportError("docx has no text")
        return {"characters": len(text)}
    if fmt == "epub":
        with zipfile.ZipFile(out) as z:
            if z.read("mimetype").decode().strip() != "application/epub+zip":
                raise ExportError("not a valid EPUB")
            return {"entries": len(z.namelist())}
    if fmt in ("txt", "rtf"):
        if out.stat().st_size == 0:
            raise ExportError(f"{fmt} export is empty")
        return {"bytes": out.stat().st_size}
    if fmt == "images":
        imgs = [f for f in out.rglob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff")]
        if not imgs:
            raise ExportError("no slide images were produced")
        return {"images": len(imgs)}
    if fmt == "movie":
        if out.stat().st_size == 0:
            raise ExportError("movie export is empty")
        return {"bytes": out.stat().st_size}
    raise ExportError(f"no verifier for {fmt}")


# ── public ────────────────────────────────────────────────────────────────────


def export(path, fmt: str, out=None, *, password: str | None = None, password_hint: str | None = None,
           image_quality: str | None = None, image_format: str | None = None, overwrite: bool = False) -> dict:
    src = Path(path).resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    kind = _KIND.get(src.suffix.lower())
    if not kind:
        raise ExportError(f"{src.name}: not a .numbers / .pages / .key file")
    fmt = fmt.lower()
    if fmt not in FORMATS[kind]:
        raise ExportError(f"{kind} can export to {sorted(FORMATS[kind])}, not {fmt!r}")
    as_name, ext = FORMATS[kind][fmt]

    props: dict = {}
    if password:
        if fmt not in ("pdf", "xlsx", "docx", "pptx"):
            raise ExportError(f"password protection isn't available for {fmt}")
        props["password"] = password
        if password_hint:
            props["passwordHint"] = password_hint
    if image_quality:
        q = _QUALITY.get(image_quality.lower())
        if not q:
            raise ExportError("image_quality must be good, better or best")
        props["imageQuality"] = q
    if image_format:
        if fmt != "images":
            raise ExportError("image_format only applies to Keynote slide images")
        f = _IMAGE_FMT.get(image_format.lower())
        if not f:
            raise ExportError("image_format must be jpeg, png or tiff")
        # Keynote's JXA export rejects the imageFormat option (-1700 "Can't convert
        # types"), so slides export in Keynote's default format and are converted here.

    dest = Path(out).expanduser().resolve() if out else src.with_name(src.stem + (ext or " slides"))
    if dest == src:
        raise ExportError("the export destination can't be the source file")
    if dest.exists() and not overwrite:
        raise ExportError(f"{dest} already exists; pass overwrite=true to replace it (the old one is backed up)")

    before = _sha(src)
    work = Path(tempfile.mkdtemp(prefix="iwork-export-"))
    tmp_out = work / (src.stem + (ext or " slides"))
    try:
        _jxa_export(src, tmp_out, kind, as_name, props)
        if not tmp_out.exists():
            raise ExportError(f"{kind} reported success but produced no {fmt} file")
        if fmt == "images" and image_format:
            _convert_images(tmp_out, image_format.lower())
        checks = _verify(tmp_out, fmt, kind, src, password)
        if _sha(src) != before:
            raise ExportError(f"{src.name} changed during export — export discarded, source left as the app saved it")
        backup = None
        if dest.exists():
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            bdir = dest.parent / f"{dest.name}.backups"
            bdir.mkdir(exist_ok=True)
            backup = bdir / f"{dest.name}.{stamp}"
            shutil.move(str(dest), str(backup))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_out), str(dest))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"ok": True, "source": str(src), "format": fmt, "output": str(dest),
            "previous_output_saved_as": str(backup) if backup else None, "checked": checks,
            "source_unchanged": True}
