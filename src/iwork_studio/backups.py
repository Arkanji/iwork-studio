"""iWork Studio — list and restore the versioned backups every write leaves.

Every writer (numbers_io / keynote_io / pages_io / keynote_slides) copies the
target to ``<file>.backups/<file>.<YYYYMMDD-HHMMSS>[.N].<ext>`` before it
touches anything. This module is the undo button over those copies.

restore_backup() rides the same protocol as a write:
  1. the backup must live in the target's own backups dir (no traversal)
  2. re-parse gate on the backup BEFORE it goes anywhere
     (.numbers → numbers-parser model, .key → keynote-parser tree,
      .pages → zip integrity only; a semantic .pages read needs the app)
  3. versioned backup of the CURRENT target (the restore is undoable too)
  4. copy backup → tmp in the target's directory → os.replace (atomic)
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

__all__ = ["backup_dir_for", "list_backups", "restore_backup", "BackupError"]

_EXTS = (".numbers", ".key", ".pages")


class BackupError(ValueError):
    """Bad restore request (unknown backup, wrong file, failed re-parse)."""


def backup_dir_for(target: str | os.PathLike) -> Path:
    target = Path(target).resolve()
    return target.parent / f"{target.name}.backups"


def _ext(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in _EXTS:
        raise BackupError(f"unsupported file type {ext!r}; expected one of {_EXTS}")
    return ext


def list_backups(target: str | os.PathLike) -> list[dict]:
    """Versioned backups of `target`, newest first."""
    target = Path(target).resolve()
    ext = _ext(target)
    bdir = backup_dir_for(target)
    if not bdir.is_dir():
        return []
    prefix = f"{target.name}."
    out = []
    for p in bdir.iterdir():
        if p.name.startswith(prefix) and p.name.endswith(ext) and p.is_file():
            st = p.stat()
            out.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "bytes": st.st_size,
                    "modified": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(
                        timespec="seconds"
                    ),
                }
            )
    # stamped names sort chronologically; mtime breaks .N ties
    out.sort(key=lambda b: (b["name"], b["modified"]), reverse=True)
    return out


def _reparse_gate(path: Path, ext: str) -> None:
    if not zipfile.is_zipfile(path):
        raise BackupError(f"{path.name} is not a valid iWork package (zip check failed)")
    if ext == ".numbers":
        from iwork_studio.numbers_io import read_numbers

        read_numbers(path)
    elif ext == ".key":
        from iwork_studio.keynote_io import read_key

        read_key(path)


def restore_backup(target: str | os.PathLike, backup: str) -> dict:
    """Atomically restore `backup` (a name from list_backups) over `target`."""
    target = Path(target).resolve()
    ext = _ext(target)
    bdir = backup_dir_for(target)
    name = Path(backup).name  # never trust a path from the caller
    src = (bdir / name).resolve()
    if src.parent != bdir.resolve() or not src.is_file():
        raise BackupError(f"backup {backup!r} not found in {bdir}")
    if not (name.startswith(f"{target.name}.") and name.endswith(ext)):
        raise BackupError(f"{name!r} is not a backup of {target.name}")

    _reparse_gate(src, ext)

    safety = None
    if target.exists():
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        n = 0
        while True:
            suffix = f".{stamp}.{n}" if n else f".{stamp}"
            safety = bdir / f"{target.name}{suffix}{ext}"
            if not safety.exists():
                break
            n += 1
        shutil.copy2(target, safety)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.restore", suffix=ext
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return {
        "ok": True,
        "file": str(target),
        "restored_from": str(src),
        "previous_version_saved_as": str(safety) if safety else None,
    }
