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
}
SLIDE_TOOLS = {
    "keynote_add_slide",
    "keynote_duplicate_slide",
    "keynote_delete_slide",
    "keynote_move_slide",
    "keynote_skip_slide",
    "keynote_set_presenter_notes",
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


def test_capabilities_reports_slide_ops_on_but_not_yet_observed():
    async def steps(c):
        return _payload(await c.call_tool("iwork_capabilities", {}))

    caps = _session(steps)
    assert caps["keynote_slide_ops"]["enabled"] is True
    assert caps["keynote_slide_ops"]["observed_on_live_mac"] == []
    assert "notes" in caps["keynote_slide_ops"]["not_yet_observed"]


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
    # keynote-parser prints "Reading from …" and PyMuPDF warns on stdout;
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
