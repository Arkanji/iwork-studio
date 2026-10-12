"""iWork Studio — where backups live, how many are kept, and the undo button over them.

Every writer copies the target to ``<backup dir>/<file>.<YYYYMMDD-HHMMSS>[.N].<ext>``
before it touches anything (make_backup). The backup dir is private and local:
``~/.iwork-studio/backups/<file>-<hash of its path>/`` (or under
IWORK_STUDIO_BACKUP_DIR), never beside the file, so backups don't fill or sync a
Desktop/Documents folder in iCloud. The newest ``keep`` (10) per file are kept.
Older versions wrote ``<file>.backups/`` beside the file; those are still listed
and restorable.

restore_backup() rides the same protocol as a write:
  1. the backup must be in one of the target's own backup dirs (no traversal)
  2. the app must not have the target open (it would save over the restore)
  3. re-parse gate on the backup BEFORE it goes anywhere
     (.numbers → numbers-parser model, .key → keynote-parser tree,
      .pages → zip integrity only; a semantic .pages read needs the app)
  4. versioned backup of the CURRENT target (the restore is undoable too)
  5. copy backup → tmp in the target's directory → os.replace (atomic)
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

__all__ = ["backup_dir_for", "legacy_dir_for", "make_backup", "prune", "prune_dir", "list_backups", "restore_backup",
           "BackupError", "KEEP"]

_EXTS = (".numbers", ".key", ".pages")
KEEP = 10


class BackupError(ValueError):
    """Bad restore request (unknown backup, wrong file, failed re-parse)."""


def _root() -> Path:
    env = os.environ.get("IWORK_STUDIO_BACKUP_DIR")
    return Path(os.path.expanduser(env)) if env else Path.home() / ".iwork-studio" / "backups"


def backup_dir_for(target: str | os.PathLike) -> Path:
    """The private backup folder for this file (one folder per file path)."""
    target = Path(target).resolve()
    digest = hashlib.sha1(str(target).encode("utf-8")).hexdigest()[:10]
    return _root() / f"{target.name}-{digest}"


def legacy_dir_for(target: str | os.PathLike) -> Path:
    """Where versions before 2.6.1 put backups: beside the file."""
    target = Path(target).resolve()
    return target.parent / f"{target.name}.backups"


def _stamp_re(name: str, ext: str) -> re.Pattern:
    return re.compile(re.escape(name) + r"\.\d{8}-\d{6}(\.\d+)?" + re.escape(ext) + "$")


def prune(bdir: Path, name: str, ext: str, keep: int = KEEP) -> None:
    """Keep the newest `keep` backups of `name` in `bdir`; never touches anything else."""
    if keep <= 0 or not bdir.is_dir():
        return
    pat = _stamp_re(name, ext)

    def order(p: Path):
        m = re.search(r"\.(\d{8}-\d{6})(?:\.(\d+))?" + re.escape(ext) + "$", p.name)
        return (m.group(1), int(m.group(2) or 0)) if m else ("", 0)

    found = sorted((p for p in bdir.iterdir() if pat.match(p.name)), key=order)
    for old in found[:-keep]:
        try:
            shutil.rmtree(old) if old.is_dir() else old.unlink()
        except OSError:
            pass


def prune_dir(bdir: str | os.PathLike, keep: int = KEEP) -> None:
    """prune() for every file whose backups share `bdir`."""
    bdir = Path(bdir)
    if not bdir.is_dir():
        return
    groups = set()
    for p in bdir.iterdir():
        m = re.match(r"^(.+)\.\d{8}-\d{6}(?:\.\d+)?(\.numbers|\.key|\.pages)$", p.name)
        if m:
            groups.add((m.group(1), m.group(2)))
    for name, ext in groups:
        prune(bdir, name, ext, keep)


def make_backup(target: str | os.PathLike, backup_dir: str | os.PathLike | None = None, keep: int = KEEP,
                *, check_open: bool = True) -> Path:
    """Step 1 of every write: refuse if the app has the file open, then copy it to a
    timestamped backup and prune old ones. Returns the backup path."""
    target = Path(target).resolve()
    if check_open:
        from iwork_studio.safety import assert_not_open

        assert_not_open(target)
    ext = target.suffix.lower()
    bdir = Path(backup_dir) if backup_dir else backup_dir_for(target)
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    # within one second, number upward from the highest existing .N (never reuse a pruned
    # name: a reused low number would sort as the oldest and be pruned first)
    same = re.compile(re.escape(f"{target.name}.{stamp}") + r"(?:\.(\d+))?" + re.escape(ext) + "$")
    taken = [int(m.group(1) or 0) for p in bdir.iterdir() if (m := same.match(p.name))]
    n = max(taken) + 1 if taken else 0
    backup = bdir / f"{target.name}.{stamp}{f'.{n}' if n else ''}{ext}"
    (shutil.copytree if target.is_dir() else shutil.copy2)(target, backup)
    prune(bdir, target.name, ext, keep)
    return backup


def _ext(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in _EXTS:
        raise BackupError(f"unsupported file type {ext!r}; expected one of {_EXTS}")
    return ext


def list_backups(target: str | os.PathLike) -> list[dict]:
    """Versioned backups of `target` (private folder and the legacy beside-the-file one), newest first."""
    target = Path(target).resolve()
    ext = _ext(target)
    pat = _stamp_re(target.name, ext)
    out = []
    for bdir in (backup_dir_for(target), legacy_dir_for(target)):
        if not bdir.is_dir():
            continue
        for p in bdir.iterdir():
            if pat.match(p.name) and (p.is_file() or p.is_dir()):
                st = p.stat()
                out.append({"name": p.name, "path": str(p), "bytes": st.st_size,
                            "modified": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
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
    name = Path(backup).name  # never trust a path from the caller
    if not (name.startswith(f"{target.name}.") and name.endswith(ext)):
        raise BackupError(f"{name!r} is not a backup of {target.name}")
    src = None
    for bdir in (backup_dir_for(target), legacy_dir_for(target)):
        cand = (bdir / name).resolve()
        if bdir.is_dir() and cand.parent == bdir.resolve() and cand.exists():
            src = cand
            break
    if src is None:
        raise BackupError(f"backup {backup!r} not found; list them with iwork_list_backups")
    from iwork_studio.safety import assert_not_open

    assert_not_open(target)

    _reparse_gate(src, ext)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.restore", suffix=ext
    )
    os.close(fd)
    tmp = Path(tmp_name)
    safety = None
    try:
        # copy the backup out first: the safety backup below prunes old ones
        if src.is_dir():
            os.unlink(tmp)
            shutil.copytree(src, tmp)
        else:
            shutil.copy2(src, tmp)
        if target.exists():
            safety = make_backup(target, check_open=False)
        os.replace(tmp, target)
    except Exception:
        if tmp.is_dir():
            shutil.rmtree(tmp, ignore_errors=True)
        elif tmp.exists():
            tmp.unlink()
        raise
    return {
        "ok": True,
        "file": str(target),
        "restored_from": str(src),
        "previous_version_saved_as": str(safety) if safety else None,
    }
