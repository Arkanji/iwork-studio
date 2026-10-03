"""iWork Studio — read-only helpers: metadata, thumbnail, find, templates.

Nothing here writes to the user's files.
"""

from __future__ import annotations

import datetime as _dt
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

__all__ = ["metadata", "thumbnail", "find_files", "list_templates", "IWORK_EXTS"]

IWORK_EXTS = {".numbers": "Numbers", ".key": "Keynote", ".pages": "Pages"}
_UTI = {
    "Numbers": "com.apple.iwork.numbers.sffnumbers",
    "Keynote": "com.apple.iwork.keynote.sffkey",
    "Pages": "com.apple.iwork.pages.sffpages",
}


class _Package:
    """An iWork document is a zip file (current format) or a folder (older)."""

    def __init__(self, path: Path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.is_file() else None

    def names(self) -> list[str]:
        if self.zip:
            return self.zip.namelist()
        return [str(p.relative_to(self.path)) for p in self.path.rglob("*") if p.is_file()]

    def read(self, name: str) -> bytes | None:
        try:
            return self.zip.read(name) if self.zip else (self.path / name).read_bytes()
        except (KeyError, FileNotFoundError):
            return None


def _kind(path: Path) -> str:
    kind = IWORK_EXTS.get(path.suffix.lower())
    if not kind:
        raise ValueError(f"{path.name}: not a .numbers / .key / .pages file")
    return kind


def metadata(path) -> dict:
    """What the file says about itself — no app, works anywhere."""
    p = Path(path).resolve()
    kind = _kind(p)
    pkg = _Package(p)
    names = pkg.names()
    props = plistlib.loads(pkg.read("Metadata/Properties.plist") or plistlib.dumps({}))
    history = plistlib.loads(pkg.read("Metadata/BuildVersionHistory.plist") or plistlib.dumps([]))
    template = next((h.split(":", 1)[1].strip() for h in history if isinstance(h, str) and h.startswith("Template:")), None)
    builds = [h for h in history if isinstance(h, str) and not h.startswith("Template:")]
    st = p.stat()
    out = {
        "file": str(p),
        "kind": kind,
        "bytes": st.st_size,
        "modified": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "file_format_version": props.get("fileFormatVersion"),
        "template": template,
        "saved_by_builds": builds,
        "multi_page": props.get("isMultiPage"),
        "has_missing_data": props.get("hasExternalReferenceOrMissingData"),
        "previews": sorted(n for n in names if n.startswith("preview") and n.endswith(".jpg")),
        "embedded_media": len([n for n in names if n.startswith("Data/")]),
    }
    if kind == "Keynote":
        out["slides"] = len([n for n in names if n.startswith("Index/Slide") and n.endswith(".iwa")])
    elif kind == "Numbers":
        out["sheets_hint"] = len([n for n in names if n.startswith("Index/Tables/") or n.startswith("Index/CalculationEngine")])
    return out


def thumbnail(path, out_dir=None) -> dict:
    """Extract the preview image the app stored in the file (first page/slide).
    Note: it reflects the last save by the app, not edits made without it."""
    p = Path(path).resolve()
    _kind(p)
    pkg = _Package(p)
    for name in ("preview.jpg", "preview-web.jpg", "preview-micro.jpg"):
        data = pkg.read(name)
        if data:
            break
    else:
        raise FileNotFoundError(f"{p.name} has no embedded preview image")
    dest_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="iwork-thumb-"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{p.stem}-preview.jpg"
    dest.write_bytes(data)
    import pymupdf as fitz

    pix = fitz.Pixmap(str(dest))
    return {"file": str(p), "thumbnail": str(dest), "width": pix.width, "height": pix.height,
            "note": "made by the app at its last save; edits made without the app aren't reflected"}


def find_files(folders: list[str], *, kind: str | None = None, name: str | None = None, limit: int = 50) -> dict:
    """Find iWork files under `folders` (Spotlight on macOS, a folder walk elsewhere)."""
    kinds = [kind.capitalize()] if kind else list(_UTI)
    for k in kinds:
        if k not in _UTI:
            raise ValueError(f"kind must be numbers, keynote or pages, not {kind!r}")
    exts = {e for e, k in IWORK_EXTS.items() if k in kinds}
    results: list[str] = []
    used = "walk"
    if sys.platform == "darwin" and shutil.which("mdfind"):
        used = "spotlight"
        q = " || ".join(f"kMDItemContentType == '{_UTI[k]}'" for k in kinds)
        for folder in folders:
            r = subprocess.run(["mdfind", "-onlyin", os.path.expanduser(folder), q],
                               capture_output=True, text=True, timeout=30)
            results += [line for line in r.stdout.splitlines() if line]
    if not results:
        used = "walk" if used == "walk" else "spotlight+walk"
        for folder in folders:
            for root, dirs, files in os.walk(os.path.expanduser(folder)):
                dirs[:] = [d for d in dirs if not d.startswith(".") and not d.endswith(".backups")
                           and Path(d).suffix.lower() not in IWORK_EXTS]
                for f in files:
                    if Path(f).suffix.lower() in exts:
                        results.append(os.path.join(root, f))
                for d in list(os.listdir(root)):  # folder-format documents
                    if Path(d).suffix.lower() in exts and os.path.isdir(os.path.join(root, d)):
                        results.append(os.path.join(root, d))
    seen, out = set(), []
    for r in results:
        rp = str(Path(r).resolve())
        if rp in seen or ".backups" in rp or (name and name.lower() not in Path(rp).name.lower()):
            continue
        seen.add(rp)
        out.append(rp)
    out.sort(key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0, reverse=True)
    return {"found": len(out), "files": out[:limit], "method": used}


def list_templates(app: str) -> dict:
    """Built-in templates (Numbers, Pages) or themes (Keynote) — needs the app."""
    from iwork_studio.apps import app_name
    from iwork_studio.keynote_slides import _assert_aqua

    app = app.capitalize()
    if app not in _UTI:
        raise ValueError("app must be numbers, pages or keynote")
    _assert_aqua()
    collection = "themes" if app == "Keynote" else "templates"
    import json

    script = f"JSON.stringify(Application({json.dumps(app_name(app))}).{collection}().map(t => t.name()))"
    r = subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"JXA failed: {r.stderr.strip()[:300]}")
    return {"app": app, collection: json.loads(r.stdout)}
