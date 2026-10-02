"""Backup listing + atomic restore (the undo button) — headless."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import backups, numbers_io  # noqa: E402


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_no_backups_yet(numbers_file):
    assert backups.list_backups(numbers_file) == []


def test_edit_then_restore_roundtrip(numbers_file):
    original = _sha(numbers_file)
    numbers_io.edit_cell(numbers_file, "B2", "تعديل")
    listed = backups.list_backups(numbers_file)
    assert len(listed) == 1
    result = backups.restore_backup(numbers_file, listed[0]["name"])
    assert result["ok"]
    assert _sha(numbers_file) == original
    # the restore saved the edited version first, so it is undoable too
    assert Path(result["previous_version_saved_as"]).exists()
    assert len(backups.list_backups(numbers_file)) == 2


def test_restore_rejects_path_traversal(numbers_file, tmp_path):
    numbers_io.edit_cell(numbers_file, "B2", "x")
    evil = tmp_path / "evil.numbers"
    evil.write_bytes(numbers_file.read_bytes())
    with pytest.raises(backups.BackupError):
        backups.restore_backup(numbers_file, str(evil))
    with pytest.raises(backups.BackupError):
        backups.restore_backup(numbers_file, "../evil.numbers")


def test_restore_rejects_corrupt_backup_target_untouched(numbers_file):
    numbers_io.edit_cell(numbers_file, "B2", "x")
    before = _sha(numbers_file)
    bdir = backups.backup_dir_for(numbers_file)
    bad = bdir / f"{numbers_file.name}.20990101-000000.numbers"
    bad.write_bytes(b"not a zip")
    with pytest.raises(backups.BackupError):
        backups.restore_backup(numbers_file, bad.name)
    assert _sha(numbers_file) == before


def test_unsupported_extension(tmp_path):
    with pytest.raises(backups.BackupError):
        backups.list_backups(tmp_path / "file.docx")
