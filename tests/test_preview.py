"""Dry run: the real operation on a throwaway copy; the original is never touched."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import keynote_io, numbers_format, numbers_io, numbers_structure as ns, pages_io, preview  # noqa: E402


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _no_backups(p):
    return not (Path(p).parent / f"{Path(p).name}.backups").exists()


def test_cell_edit_preview(numbers_file):
    before = _sha(numbers_file)
    out = preview.dry_run(numbers_io.edit_cell, numbers_file, "B2", "مرحبا")
    assert out["dry_run"] and out["file_untouched"]
    assert _sha(numbers_file) == before and _no_backups(numbers_file)
    cells = out["would_change"]["cells"]
    assert len(cells) == 1 and cells[0]["cell"].endswith("› B2") and cells[0]["after"] == "مرحبا"
    assert str(numbers_file) in out["result"]["file"] and "backup" not in out["result"]


def test_style_preview_names_the_aspect(numbers_file):
    out = preview.dry_run(numbers_format.set_cell_style, numbers_file, "B2", italic=True)
    assert out["would_change"]["cells"][0]["changed"] == ["style"]


def test_structure_preview(tmp_path):
    p = tmp_path / "b.numbers"
    ns.create(p, [{"name": "S", "tables": [{"name": "T", "rows": [["a", 1], ["b", 2]]}]}])
    before = _sha(p)
    out = preview.dry_run(ns.insert, p, "rows", 1, None, [["c", 3]])
    assert _sha(p) == before
    assert out["would_change"]["layout"][0]["size"] == {"before": (2, 2), "after": (3, 2)}


def test_keynote_replace_preview(tmp_path):
    deck = tmp_path / "d.key"
    deck.write_bytes((REPO / "tests" / "fixtures" / "arabic.key").read_bytes())
    texts = [t for s in keynote_io.read_key(deck)["slides"] for t in s["texts"] if t.strip() and t != "￼"]
    word = next(w for t in texts for w in t.split() if len(w) > 2)
    before = _sha(deck)
    out = preview.dry_run(keynote_io.edit_text, deck, word, "XYZ")
    assert _sha(deck) == before
    assert any("XYZ" in t for t in out["would_change"]["text_added"])


def test_no_op_preview_says_so(numbers_file):
    out = preview.dry_run(numbers_format.set_cell_style, numbers_file, "A1", bold=True)  # header: already bold
    assert out["would_change"] == "nothing visible in the content"


def test_failed_preview_raises_and_cleans_up(numbers_file):
    before = _sha(numbers_file)
    with pytest.raises(numbers_io.CellRefError):
        preview.dry_run(numbers_io.edit_cell, numbers_file, "ZZ999", 1)
    assert _sha(numbers_file) == before


def test_pages_body_diff(monkeypatch, tmp_path):
    a, b = tmp_path / "a.pages", tmp_path / "b.pages"
    monkeypatch.setattr(pages_io, "read_body_text", lambda p: "سطر\rقديم" if p == a else "سطر\rجديد")
    assert preview.diff_files(a, b)["body_diff"] == ["-قديم", "+جديد"]


def test_mcp_tools_take_dry_run(numbers_file):
    import asyncio

    from iwork_studio import mcp_server as m

    tools = {t.name: t for t in asyncio.run(m.mcp.list_tools())}
    schema = lambda t: getattr(t, "input_schema", None) or t.inputSchema  # noqa: E731
    with_dry = {n for n, t in tools.items() if "dry_run" in schema(t)["properties"]}
    writes = {n for n, t in tools.items() if t.annotations and t.annotations.destructive_hint}
    no_preview = {"iwork_restore_backup", "iwork_export", "numbers_create", "numbers_import_csv",
                  "iwork_create", "iwork_create_from_template", "keynote_build_deck"}  # undo / new files
    assert writes - no_preview <= with_dry
    before = _sha(numbers_file)
    out = m._write(True, numbers_io.edit_cell, numbers_file, "B2", 7)
    assert out["dry_run"] and _sha(numbers_file) == before
