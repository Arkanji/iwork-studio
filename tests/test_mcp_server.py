"""MCP server — end-to-end over real stdio (the same wire Claude Code uses)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CHART_SRC = REPO / "tests" / "fixtures" / "chart.numbers"

from mcp import Client, StdioServerParameters  # noqa: E402

CORE_TOOLS = {
    "iwork_capabilities",
    "iwork_read",
    "iwork_list_backups",
    "iwork_restore_backup",
    "iwork_verify_render",
    "numbers_edit_cell",
    "keynote_replace_text",
    "pages_preflight",
    "pages_replace_all",
    "pages_set_body",
    "numbers_inspect_format",
    "numbers_set_dimensions",
    "numbers_set_number_format",
    "numbers_set_cell_style",
    "numbers_set_borders",
    "numbers_set_headers",
    "numbers_merge_cells",
    "iwork_verify_format",
    "iwork_export",
    "iwork_metadata",
    "iwork_thumbnail",
    "iwork_find",
    "iwork_list_templates",
    "iwork_list_design_kits", "iwork_extract_design_kit", "iwork_save_design_kit",
    "iwork_delete_design_kit",
    "numbers_apply_design",
    "numbers_create",
    "numbers_import_csv",
    "numbers_insert",
    "numbers_delete",
    "numbers_add_table",
    "iwork_create_from_template",
    "iwork_create",
    "numbers_set_formula",
    "numbers_sort",
    "numbers_recalculate",
    "pages_list_placeholders",
    "pages_fill_placeholders",
    "pages_read_tables",
    "pages_set_table_cells",
    "keynote_slideshow",
}
SLIDE_TOOLS = {
    "keynote_add_slide",
    "keynote_duplicate_slide",
    "keynote_delete_slide",
    "keynote_move_slide",
    "keynote_skip_slide",
    "keynote_set_presenter_notes",
    "keynote_list_slides",
    "keynote_list_themes",
    "keynote_inspect_style",
    "keynote_set_theme",
    "keynote_set_slide_layout",
    "keynote_format_text",
    "keynote_set_transition",
    "keynote_add_image",
    "keynote_add_chart",
    "keynote_add_table",
    "keynote_review_deck",
    "keynote_slide_image",
    "keynote_build_deck",
    "keynote_set_slide_text",
    "keynote_apply_design",
}


def _params(**env) -> StdioServerParameters:
    base = {k: v for k, v in os.environ.items() if not k.startswith("IWORK_STUDIO_")}
    base["PYTHONPATH"] = str(REPO / "src") + os.pathsep + base.get("PYTHONPATH", "")
    base.update(env)
    return StdioServerParameters(command=sys.executable, args=["-m", "iwork_studio.mcp_server"], env=base)


def _session(steps, **env):
    wire_errors: list = []

    async def on_message(msg):
        if isinstance(msg, Exception):  # a non-JSON-RPC line reached stdout
            wire_errors.append(msg)

    async def go():
        async with Client(_params(**env), message_handler=on_message) as client:
            return await steps(client)

    result = asyncio.run(go())
    assert not wire_errors, f"stdout polluted (breaks strict MCP clients): {wire_errors[0]}"
    return result


def _payload(result) -> dict:
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def test_tools_listed_with_safety_annotations():
    async def steps(c):
        return (await c.list_tools()).tools

    tools = {t.name: t for t in _session(steps)}
    assert set(tools) == CORE_TOOLS | SLIDE_TOOLS  # slide ops on by default
    assert tools["iwork_read"].annotations.read_only_hint is True
    assert tools["numbers_edit_cell"].annotations.destructive_hint is True


def test_slide_tools_hidden_by_off_switch():
    async def steps(c):
        return {t.name for t in (await c.list_tools()).tools}

    assert _session(steps, IWORK_STUDIO_DISABLE_SLIDE_OPS="1") == CORE_TOOLS


def test_capabilities_reports_slide_ops_on():
    async def steps(c):
        return _payload(await c.call_tool("iwork_capabilities", {}))

    caps = _session(steps)
    assert caps["keynote_slide_ops"]["enabled"] is True


def test_read_edit_backup_restore_roundtrip(numbers_file):
    async def steps(c):
        p = str(numbers_file)
        read = _payload(await c.call_tool("iwork_read", {"path": p}))
        edit = _payload(await c.call_tool("numbers_edit_cell", {"path": p, "ref": "B2", "value": "مرحبا"}))
        listed = _payload(await c.call_tool("iwork_list_backups", {"path": p}))
        restored = _payload(
            await c.call_tool("iwork_restore_backup", {"path": p, "backup": listed["backups"][0]["name"]})
        )
        reread = _payload(await c.call_tool("iwork_read", {"path": p}))
        return read, edit, listed, restored, reread

    read, edit, listed, restored, reread = _session(steps)
    assert read["sheets"]
    assert edit["ok"] and edit["cell"]["after"] == "مرحبا"
    assert len(listed["backups"]) == 1
    assert restored["ok"]
    assert reread["sheets"] == read["sheets"]


def test_chart_refusal_surfaces_as_typed_tool_error(tmp_path):
    if not CHART_SRC.exists():
        pytest.skip("chart fixture not built")
    dest = tmp_path / "chart.numbers"
    shutil.copy2(CHART_SRC, dest)

    async def steps(c):
        return await c.call_tool("numbers_edit_cell", {"path": str(dest), "ref": "A1", "value": 1})

    result = _session(steps)
    assert result.is_error
    assert "ChartRefusalError" in result.content[0].text


def test_roots_fence(numbers_file, tmp_path):
    fenced = tmp_path / "allowed"
    fenced.mkdir()

    async def steps(c):
        return await c.call_tool("iwork_read", {"path": str(numbers_file)})

    result = _session(steps, IWORK_STUDIO_ROOTS=str(fenced))
    assert result.is_error and "outside IWORK_STUDIO_ROOTS" in result.content[0].text


def test_keynote_read_keeps_the_wire_clean(tmp_path):
    # keynote-parser prints "Reading from …" and other libraries may print on stdout;
    # _session fails if either reaches the protocol stream
    deck = tmp_path / "deck.key"
    shutil.copy2(REPO / "tests" / "fixtures" / "arabic.key", deck)

    async def steps(c):
        return _payload(await c.call_tool("iwork_read", {"path": str(deck)}))

    assert _session(steps)["slides"]


def test_wrong_extension_rejected(numbers_file):
    async def steps(c):
        return await c.call_tool("keynote_replace_text", {"path": str(numbers_file), "find": "a", "replace": "b"})

    assert _session(steps).is_error


def test_format_tools_end_to_end(numbers_file):
    async def steps(c):
        p = str(numbers_file)
        await c.call_tool("numbers_set_cell_style", {"path": p, "cells": "A1:C1", "bold": True, "fill_color": "#1A7F79"})
        fmt = _payload(await c.call_tool("numbers_set_number_format",
                                         {"path": p, "cells": "B2", "format": "currency", "currency_code": "SAR"}))
        lay = _payload(await c.call_tool("numbers_inspect_format", {"path": p}))
        bad = await c.call_tool("numbers_set_borders", {"path": p, "cells": "Z9"})
        return fmt, lay, bad

    fmt, lay, bad = _session(steps)
    assert fmt["now_shown_as"]["B2"].startswith("SAR")
    a1 = next(c for c in lay["cells"] if c["ref"] == "A1")
    assert a1["style"]["bold"] and a1["style"]["bg_color"] == "#1a7f79"
    assert bad.is_error and "CellRefError" in bad.content[0].text


def test_readonly_helpers_over_mcp(tmp_path):
    deck = tmp_path / "d.key"
    shutil.copy2(REPO / "tests" / "fixtures" / "arabic.key", deck)

    async def steps(c):
        meta = _payload(await c.call_tool("iwork_metadata", {"path": str(deck)}))
        thumb = _payload(await c.call_tool("iwork_thumbnail", {"path": str(deck)}))
        found = _payload(await c.call_tool("iwork_find", {"folder": str(tmp_path), "kind": "keynote"}))
        fenced = await c.call_tool("iwork_export", {"path": str(deck), "format": "pdf", "out": "/etc/x.pdf"})
        return meta, thumb, found, fenced

    meta, thumb, found, fenced = _session(steps, IWORK_STUDIO_ROOTS=str(tmp_path))
    assert meta["kind"] == "Keynote" and meta["slides"] == 1
    assert Path(thumb["thumbnail"]).exists() and thumb["width"] > 0
    assert found["files"] == [str(deck.resolve())]
    assert fenced.is_error and "outside IWORK_STUDIO_ROOTS" in fenced.content[0].text


def test_prompts_listed_and_rendered():
    async def steps(c):
        names = {p.name for p in (await c.list_prompts()).prompts}
        got = await c.get_prompt("report_from_numbers", {"numbers_file": "/r/تقرير.numbers", "path": "/r/deck.key"})
        brand = await c.get_prompt("restyle_with_brand", {"path": "/r/t.numbers", "brand_file": "/r/brand.key"})
        return names, got.messages[0].content.text, brand.messages[0].content.text

    names, text, brand = _session(steps)
    assert names == {"pitch_deck", "report_from_numbers", "restyle_with_brand", "style_table"}
    assert '"from": "/r/تقرير.numbers"' in text and "keynote_review_deck" in text
    assert "numbers_apply_design(dry_run=true)" in brand and "iwork_extract_design_kit" in brand
