"""iWork Studio — MCP server (stdio).

Every tool is a thin wrapper over the library: the write protocol
(versioned backup → tmp write → re-parse gate → semantic diff → atomic swap)
lives in the library, so an agent cannot reach a write without it.

Install (Claude Code):
    claude mcp add iwork-studio -- uvx --from git+https://github.com/arkanji/iwork-studio iwork-studio-mcp

Environment:
    IWORK_STUDIO_ROOTS              os.pathsep-separated folders the server may
                                    touch (unset = any path the user can reach)
    IWORK_STUDIO_DISABLE_SLIDE_OPS  "1" hides and refuses the Keynote slide ops
"""

from __future__ import annotations

import contextlib
import os
import platform
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

# stdout IS the protocol wire. Libraries that print at import time must not
# reach it (the SDK only diverts fd 1 once serving starts), so imports go to
# stderr. keynote-parser's "Reading from …" prints during calls are covered by
# the SDK's diversion while serving.
with contextlib.redirect_stdout(sys.stderr):
    from iwork_studio import __version__, apps, backups, keynote_slides
    from iwork_studio import keynote_applescript, keynote_io, numbers_io, pages_io, render_verify  # noqa: F401

INSTRUCTIONS = """\
iWork Studio reads and edits Apple Numbers (.numbers), Keynote (.key) and Pages
(.pages) files with hard safety gates. Rules:

- Every write makes a versioned backup and only swaps the file in after it
  re-parses and matches the requested change exactly. If a tool errors, the
  file is untouched. Use iwork_list_backups / iwork_restore_backup to undo.
- Call iwork_capabilities first when unsure what this machine can do.
  .numbers and .key reads/edits are pure Python (no app needed). .pages, render
  verification and Keynote slide ops drive the real app and need a logged-in
  macOS GUI session.
- Keynote slide ops refuse a deck that is open in Keynote: ask the user to save
  and close it. Slide numbers are 1-based.
- Files containing charts are REFUSED for writes (ChartRefusalError). Do not try
  to work around it; tell the user.
- Pages supports exactly two writes: pages_replace_all and pages_set_body.
  Anything richer is out of scope by design. Run pages_preflight first; a -1712 /
  PagesUnavailableError means a human must dismiss a dialog once. Never retry.
- After a write the user cares about, call iwork_verify_render with a word that
  must appear. For Arabic, assert ONE word: PDF text layers reorder multi-word
  RTL text and produce false failures.
- Never convert to docx/pptx/xlsx and back; it is lossy.
"""

mcp = MCPServer(
    name="iwork-studio",
    title="iWork Studio",
    version=__version__,
    instructions=INSTRUCTIONS,
    website_url="https://github.com/arkanji/iwork-studio",
)

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)
APP_READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False, idempotent_hint=True)


# ── helpers ───────────────────────────────────────────────────────────────────


def _path(path: str, *exts: str) -> Path:
    p = Path(os.path.expanduser(path)).resolve()
    if exts and p.suffix.lower() not in exts:
        raise ToolError(f"{p.name}: expected a {' / '.join(exts)} file")
    roots = os.environ.get("IWORK_STUDIO_ROOTS")
    if roots:
        allowed = [Path(os.path.expanduser(r)).resolve() for r in roots.split(os.pathsep) if r]
        if not any(p == r or r in p.parents for r in allowed):
            raise ToolError(f"{p} is outside IWORK_STUDIO_ROOTS; refusing to touch it")
    if not p.exists():
        raise ToolError(f"file not found: {p}")
    return p


_HINTS = {
    "AquaSessionError": "needs a logged-in macOS GUI session; .numbers/.key reads and edits work without one",
    "PagesUnavailableError": "a dialog is blocking Pages: ask the user to dismiss it once, then retry once",
    "ChartRefusalError": "chart files are refused for writes by design; tell the user",
    "OutOfScopeError": "Pages supports only pages_replace_all and pages_set_body",
    "FileLockedError": "the file is locked or open in Keynote; ask the user to close it",
    "DocumentOpenError": "ask the user to save and close the deck in Keynote first",
    "CreatorStudioUnverifiedError": "only the Creator Studio app is installed and it is not verified yet",
    "SlideOpsDisabledError": "slide ops are switched off on this machine",
}


def _call(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        result = fn(*args, **kwargs)
    except ToolError:
        raise
    except Exception as exc:  # typed library errors → readable tool errors
        name = type(exc).__name__
        hint = _HINTS.get(name)
        raise ToolError(f"{name}: {exc}" + (f" (hint: {hint})" if hint else "")) from exc
    return result if isinstance(result, dict) else {"result": result}


def _aqua_status() -> dict:
    from iwork_studio.keynote_applescript import AquaSessionError, _assert_aqua

    if platform.system() != "Darwin":
        return {"available": False, "reason": f"{platform.system()} is not macOS"}
    try:
        _assert_aqua()
        return {"available": True}
    except AquaSessionError as exc:
        return {"available": False, "reason": str(exc)}


def _app_status() -> dict:
    out = {}
    for app in apps.IWORK_APPS:
        try:
            out[app] = {"scripting_name": apps.app_name(app), **apps.app_bundle_candidates(app)}
        except apps.CreatorStudioUnverifiedError as exc:
            out[app] = {"scripting_name": None, "error": str(exc), **apps.app_bundle_candidates(app)}
    return out


# ── read-only tools ───────────────────────────────────────────────────────────


@mcp.tool(annotations=READ)
def iwork_capabilities() -> dict[str, Any]:
    """What this machine can do right now: routes, GUI session, installed apps, which slide ops are verified."""
    return {
        "version": __version__,
        "platform": platform.platform(),
        "gui_session": _aqua_status(),
        "apps": _app_status(),
        "routes": {
            ".numbers": "read full model + edit one cell, pure Python (no app needed)",
            ".key": "read text model + deck-wide find/replace, pure Python (no app needed)",
            ".pages": "read body + replace_all + set_body, via the Pages app (GUI session)",
            "render_verify": "export PDF via the app and assert visible text (GUI session)",
            "keynote_slide_ops": "add/duplicate/delete/move/skip/notes via the Keynote app (GUI session)",
        },
        "keynote_slide_ops": {
            "enabled": keynote_slides.slide_ops_enabled(),
            "observed_on_live_mac": sorted(keynote_slides.VERIFIED_OPS),
            "not_yet_observed": sorted(set(keynote_slides.SLIDE_OPS) - keynote_slides.VERIFIED_OPS),
            "safety_net": "backup + per-slide readback + rollback on any mismatch",
        },
        "refused_by_design": [
            "writes to files containing charts",
            "Pages edits beyond replace_all / set_body",
            "docx/pptx/xlsx round-trip conversion",
        ],
    }


@mcp.tool(annotations=READ)
def iwork_read(path: str) -> dict[str, Any]:
    """Read a .numbers, .key or .pages file into JSON (.pages needs the Pages app and a GUI session)."""
    p = _path(path, ".numbers", ".key", ".pages")
    ext = p.suffix.lower()
    if ext == ".numbers":
        from iwork_studio import numbers_io

        return _call(numbers_io.read_numbers, p)
    if ext == ".key":
        from iwork_studio import keynote_io

        return _call(keynote_io.read_key, p)
    from iwork_studio import pages_io

    return _call(pages_io.read_pages, p)


@mcp.tool(annotations=READ)
def iwork_list_backups(path: str) -> dict[str, Any]:
    """List the versioned backups (newest first) every write left for this file, plus the Keynote write manifest."""
    p = _path(path, ".numbers", ".key", ".pages")
    out: dict[str, Any] = {"file": str(p), "backups": _call(backups.list_backups, p)["result"]}
    if p.suffix.lower() == ".key":
        from iwork_studio import keynote_io

        out["manifest"] = keynote_io.read_manifest(p)
    return out


@mcp.tool(annotations=APP_READ)
def pages_preflight() -> dict[str, Any]:
    """Check Pages can answer AppleEvents. Run once before any Pages op; never loop on failure."""
    from iwork_studio import pages_io

    return _call(pages_io.preflight)


@mcp.tool(annotations=APP_READ)
def iwork_verify_render(path: str, assert_text: str, expected_pages: int | None = None) -> dict[str, Any]:
    """Export the file to PDF through its app and assert `assert_text` is visibly rendered. For Arabic, use one word."""
    p = _path(path, ".numbers", ".key", ".pages")
    ext = p.suffix.lower()
    if ext == ".numbers":
        from iwork_studio import render_verify

        return _call(render_verify.verify_render, p, assert_text, expected_pages=expected_pages or 1)
    if ext == ".key":
        from iwork_studio import keynote_applescript

        return _call(keynote_applescript.verify_render, p, assert_text, expected_slides=expected_pages)
    from iwork_studio import pages_io

    return _call(pages_io.verify_render, p, assert_text, expected_pages=expected_pages)


# ── write tools (all ride the library's write protocol) ──────────────────────


@mcp.tool(annotations=WRITE)
def numbers_edit_cell(
    path: str,
    ref: str,
    value: str | int | float | bool,
    sheet: str | None = None,
    table: str | None = None,
) -> dict[str, Any]:
    """Set one cell (e.g. ref "B2") in a .numbers file. Backed up, verified, atomic; every other cell is checked unchanged."""
    from iwork_studio import numbers_io

    p = _path(path, ".numbers")
    return _call(numbers_io.edit_cell, p, ref, value, sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def keynote_replace_text(path: str, find: str, replace: str, regex: bool = False) -> dict[str, Any]:
    """Find/replace text across every slide of a .key deck (literal unless regex=true). Formatting and structure are verified unchanged."""
    from iwork_studio import keynote_io

    p = _path(path, ".key")
    return _call(keynote_io.edit_text, p, find, replace, regex=regex)


@mcp.tool(annotations=WRITE)
def pages_replace_all(path: str, find: str, replace: str) -> dict[str, Any]:
    """Replace every occurrence of `find` in a .pages body (needs Pages + GUI session). Rolled back if the readback disagrees."""
    from iwork_studio import pages_io

    p = _path(path, ".pages")
    return _call(pages_io.edit_pages_body, p, find, replace, mode="replace_all")


@mcp.tool(annotations=WRITE)
def pages_set_body(path: str, body: str) -> dict[str, Any]:
    """Replace the entire body text of a .pages document (needs Pages + GUI session). Body formatting is reset."""
    from iwork_studio import pages_io

    p = _path(path, ".pages")
    return _call(pages_io.edit_pages_body, p, mode="set_body", new_body=body)


@mcp.tool(annotations=WRITE)
def iwork_restore_backup(path: str, backup: str) -> dict[str, Any]:
    """Undo: atomically restore a backup (a name from iwork_list_backups). The current version is backed up first."""
    p = _path(path, ".numbers", ".key", ".pages")
    return _call(backups.restore_backup, p, backup)


# ── Keynote slide ops (on unless IWORK_STUDIO_DISABLE_SLIDE_OPS=1) ───────────


def _slide_tool(op: str) -> bool:
    return keynote_slides.slide_ops_enabled()


if _slide_tool("add"):

    @mcp.tool(annotations=WRITE)
    def keynote_add_slide(path: str, after: int | None = None) -> dict[str, Any]:
        """Insert a slide after slide number `after` (0 = first, omit = end). Every other slide is verified unchanged."""
        return _call(keynote_slides.add_slide, _path(path, ".key"), after=after)


if _slide_tool("duplicate"):

    @mcp.tool(annotations=WRITE)
    def keynote_duplicate_slide(path: str, slide: int) -> dict[str, Any]:
        """Duplicate slide number `slide` (1-based); the copy lands right after it."""
        return _call(keynote_slides.duplicate_slide, _path(path, ".key"), slide)


if _slide_tool("delete"):

    @mcp.tool(annotations=WRITE)
    def keynote_delete_slide(path: str, slide: int) -> dict[str, Any]:
        """Delete slide number `slide` (1-based). Recoverable with iwork_restore_backup."""
        return _call(keynote_slides.delete_slide, _path(path, ".key"), slide)


if _slide_tool("move"):

    @mcp.tool(annotations=WRITE)
    def keynote_move_slide(path: str, slide: int, to: int) -> dict[str, Any]:
        """Move slide number `slide` so it ends up at position `to` (both 1-based)."""
        return _call(keynote_slides.move_slide, _path(path, ".key"), slide, to)


if _slide_tool("skip"):

    @mcp.tool(annotations=WRITE)
    def keynote_skip_slide(path: str, slide: int, skipped: bool = True) -> dict[str, Any]:
        """Hide (skipped=true) or show a slide in the slideshow."""
        return _call(keynote_slides.set_skipped, _path(path, ".key"), slide, skipped)


if _slide_tool("notes"):

    @mcp.tool(annotations=WRITE)
    def keynote_set_presenter_notes(path: str, slide: int, notes: str) -> dict[str, Any]:
        """Set the presenter notes of slide number `slide` (1-based). Arabic-safe."""
        return _call(keynote_slides.set_presenter_notes, _path(path, ".key"), slide, notes)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
