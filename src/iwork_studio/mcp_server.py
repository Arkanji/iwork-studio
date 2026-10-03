"""iWork Studio — MCP server (stdio).

Every tool is a thin wrapper over the library: the write protocol
(versioned backup → tmp write → re-parse gate → semantic diff → atomic swap)
lives in the library, so an agent cannot reach a write without it.

Install:
    Claude desktop app:  curl -LsSf https://raw.githubusercontent.com/Arkanji/iwork-studio/main/install.sh | sh
    Claude Code:         claude mcp add iwork-studio -- uvx --from git+https://github.com/Arkanji/iwork-studio iwork-studio-mcp
    Anything else:       iwork-studio-mcp config   (prints the JSON entry)

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
    from iwork_studio import format_check, numbers_format  # noqa: F401
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
- Charts: tools that work without the app refuse files containing charts
  (ChartRefusalError) — their rewrite could break chart links. Tools that drive
  the app (Keynote slide/theme/image/transition ops, Numbers formulas and sort)
  work on them and check every chart is kept. keynote_add_chart adds a chart;
  Numbers and Pages charts can't be created (Apple doesn't script them). Never
  work around a refusal; tell the user.
- Numbers doesn't recalculate formulas when it opens a file changed without it.
  If a no-app edit returns formulas_need_recalc, call numbers_recalculate (Mac)
  so totals are current, or tell the user to.
- New files: numbers_create / numbers_import_csv (no app), iwork_create (from
  Apple's built-in templates, needs the app), iwork_create_from_template (copy
  the user's own document). They never overwrite an existing file.
- Pages writes: pages_replace_all, pages_set_body (resets body formatting),
  pages_fill_placeholders and pages_set_table_cells (existing tables only). Anything richer is out of scope by design. Run
  pages_preflight first; a -1712 / PagesUnavailableError means a human must
  dismiss a dialog once. Never retry.
- After a write the user cares about, call iwork_verify_render with a word that
  must appear. For Arabic, assert ONE word: PDF text layers reorder multi-word
  RTL text and produce false failures.
- Every write tool takes dry_run=true: it runs the change on a temporary copy,
  with all checks, and returns what would change. Use it to show the user a
  preview before a broad or destructive change.
- Never convert to docx/pptx/xlsx and back; it is lossy.
"""

mcp = MCPServer(
    name="iwork-studio",
    title="iWork Studio",
    version=__version__,
    instructions=INSTRUCTIONS,
    website_url="https://github.com/Arkanji/iwork-studio",
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


def _fenced(p: Path) -> Path:
    roots = os.environ.get("IWORK_STUDIO_ROOTS")
    if roots:
        allowed = [Path(os.path.expanduser(r)).resolve() for r in roots.split(os.pathsep) if r]
        if not any(p == r or r in p.parents for r in allowed):
            raise ToolError(f"{p} is outside IWORK_STUDIO_ROOTS; refusing to touch it")
    return p


def _out_path(path: str | None) -> Path | None:
    return None if not path else _fenced(Path(os.path.expanduser(path)).resolve())


def _search_folders(folder: str | None) -> list[str]:
    if folder:
        return [str(_fenced(Path(os.path.expanduser(folder)).resolve()))]
    roots = os.environ.get("IWORK_STUDIO_ROOTS")
    if roots:
        return [r for r in roots.split(os.pathsep) if r]
    return [str(Path.home() / d) for d in ("Documents", "Desktop", "Downloads") if (Path.home() / d).exists()] or [str(Path.home())]


_HINTS = {
    "AquaSessionError": "needs a logged-in macOS GUI session; .numbers/.key reads and edits work without one",
    "PagesUnavailableError": "a dialog is blocking Pages: ask the user to dismiss it once, then retry once",
    "ChartRefusalError": "files with charts are refused by the no-app tools (they could break chart links); app-driven tools work on them — tell the user",
    "OutOfScopeError": "Pages supports pages_replace_all, pages_set_body, pages_fill_placeholders and pages_set_table_cells only",
    "StructureError": "fix the request (positions are 1-based; new files must not exist yet)",
    "AppOpError": "fix the request; the message lists the valid choices",
    "WriteVerificationError": "the result didn't match the request, so nothing was changed",
    "EditVerificationError": "the result didn't match the request; the backup was restored",
    "SlideOpVerificationError": "Keynote did something other than asked; the backup was restored",
    "FileLockedError": "the file is locked or open in Keynote; ask the user to close it",
    "DocumentOpenError": "ask the user to save and close the deck in Keynote first",
    "CreatorStudioUnverifiedError": "only the Creator Studio app is installed and it is not verified yet",
    "SlideOpsDisabledError": "slide ops are switched off on this machine",
    "FormatError": "fix the request (range, colour as #RRGGBB, option names) and try again",
    "CellRefError": "the cell/range is outside the table; check with numbers_inspect_format",
    "FormatMismatch": "the rendered file does not show that formatting",
    "ThemeError": "fix the request: check names with keynote_list_themes / keynote_inspect_style",
    "ExportError": "the export was refused or didn't match the source; nothing was written",
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


def _write(dry_run: bool, fn, path, *args, **kwargs) -> dict[str, Any]:
    """Every write tool goes through here; dry_run runs it on a throwaway copy."""
    if dry_run:
        from iwork_studio import preview

        return _call(preview.dry_run, fn, path, *args, **kwargs)
    return _call(fn, path, *args, **kwargs)


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
    """What this machine can do right now: routes, GUI session, installed apps, Keynote slide-op status. Call first when unsure."""
    return {
        "version": __version__,
        "platform": platform.platform(),
        "gui_session": _aqua_status(),
        "apps": _app_status(),
        "routes": {
            "no_app_needed": "read any .numbers/.key; create Numbers files (data, CSV); edit, format and restructure "
                             "Numbers tables; Keynote find/replace; metadata, thumbnails, find files; undo",
            "needs_the_app": "Pages text, placeholders and tables; Numbers formulas, recalculate, sort; Keynote slides, "
                             "theming, transitions, images, charts, slideshow; new files from Apple templates; "
                             "export; render and format checks",
        },
        "keynote_slide_ops": {"enabled": keynote_slides.slide_ops_enabled()},
        "refused_by_design": [
            "no-app writes to files containing charts (app-driven tools work on them)",
            "Pages edits beyond replace / set body / placeholders / table cells; creating Pages tables",
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
def iwork_verify_format(
    path: str,
    text: str,
    font: str | None = None,
    size: float | None = None,
    color: str | None = None,
    bold: bool | None = None,
    page_width: float | None = None,
    page_height: float | None = None,
) -> dict[str, Any]:
    """Independent check of formatting: export a PDF through the app and confirm `text` is drawn with the given font (name contains), size (pt), color (#RRGGBB), bold, and page size (pt). Needs macOS + the app."""
    from iwork_studio import format_check as fc

    page = (page_width, page_height) if page_width and page_height else None
    return _call(fc.verify_format, _path(path, ".numbers", ".key", ".pages"), text, font=font, size=size,
                 color=color, bold=bold, page_size=page)


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
    dry_run: bool = False,
) -> dict[str, Any]:
    """Set one cell (e.g. ref "B2") in a .numbers file. Backed up, verified, atomic; every other cell is checked unchanged. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_io

    p = _path(path, ".numbers")
    return _write(dry_run, numbers_io.edit_cell, p, ref, value, sheet=sheet, table=table)


# ── Numbers formatting (file-level, no app needed) ───────────────────────────


@mcp.tool(annotations=READ)
def numbers_inspect_format(path: str, sheet: str | None = None, table: str | None = None) -> dict[str, Any]:
    """Current formatting of a Numbers table: column widths, row heights, header rows/cols, merges, and per-cell font/colour/fill/alignment, number format (shown_as) and borders. Read this before formatting."""
    from iwork_studio import numbers_format as nf

    return _call(nf.read_layout, _path(path, ".numbers"), sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def numbers_set_dimensions(
    path: str,
    columns: dict[str, float] | None = None,
    rows: dict[str, float] | None = None,
    sheet: str | None = None,
    table: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Set column widths and/or row heights in points, e.g. columns={"A": 160, "C": 90}, rows={"1": 32} (rows are 1-based). Nothing else changes. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_format as nf

    return _write(dry_run, nf.set_dimensions, _path(path, ".numbers"), columns=columns, rows=rows, sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def numbers_set_number_format(
    path: str,
    cells: str,
    format: str,
    decimal_places: int | None = None,
    thousands_separator: bool | None = None,
    negative_style: str | None = None,
    currency_code: str | None = None,
    accounting: bool | None = None,
    date_format: str | None = None,
    sheet: str | None = None,
    table: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """How numbers display in a range ("B2:B9"): format = number | currency | percentage | scientific | fraction | datetime | text. Options: decimal_places, thousands_separator, negative_style (minus|red|parentheses|red_parentheses), currency_code (ISO, e.g. SAR, USD), accounting, date_format (e.g. "d MMM yyyy"). Values are not changed; the result shows how each cell now displays. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_format as nf

    return _write(dry_run, nf.set_number_format, _path(path, ".numbers"), cells, format, decimal_places=decimal_places,
                 thousands_separator=thousands_separator, negative_style=negative_style,
                 currency_code=currency_code, accounting=accounting, date_format=date_format,
                 sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def numbers_set_cell_style(
    path: str,
    cells: str,
    font_name: str | None = None,
    font_size: float | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    strikethrough: bool | None = None,
    font_color: str | None = None,
    fill_color: str | None = None,
    align: str | None = None,
    valign: str | None = None,
    wrap: bool | None = None,
    sheet: str | None = None,
    table: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Style a range ("A1:D1"): font_name, font_size, bold, italic, underline, strikethrough, font_color / fill_color as "#RRGGBB", align (left|center|right|justify|auto), valign (top|middle|bottom), wrap. Only the attributes you pass change; every other cell is verified untouched. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_format as nf

    return _write(dry_run, nf.set_cell_style, _path(path, ".numbers"), cells, font_name=font_name, font_size=font_size,
                 bold=bold, italic=italic, underline=underline, strikethrough=strikethrough,
                 font_color=font_color, fill_color=fill_color, align=align, valign=valign, wrap=wrap,
                 sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def numbers_set_borders(
    path: str,
    cells: str,
    sides: str = "all",
    width: float = 1.0,
    color: str = "#000000",
    style: str = "solid",
    sheet: str | None = None,
    table: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Cell borders on a range: sides = all | outline | inner | top | right | bottom | left; width in points; color "#RRGGBB"; style = solid | dashes | dots | none. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_format as nf

    return _write(dry_run, nf.set_borders, _path(path, ".numbers"), cells, sides=sides, width=width, color=color,
                 style=style, sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def numbers_set_headers(
    path: str,
    header_rows: int | None = None,
    header_columns: int | None = None,
    sheet: str | None = None,
    table: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Set how many header rows / header columns a table has (0–5). dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_format as nf

    return _write(dry_run, nf.set_headers, _path(path, ".numbers"), header_rows=header_rows,
                 header_columns=header_columns, sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def numbers_merge_cells(path: str, cells: str, sheet: str | None = None, table: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Merge a rectangular range ("A1:C1"). Refused if any cell other than the top-left holds data (it would be hidden) or the range crosses the header edge. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_format as nf

    return _write(dry_run, nf.merge_cells, _path(path, ".numbers"), cells, sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def keynote_replace_text(path: str, find: str, replace: str, regex: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Find/replace text across every slide of a .key deck (literal unless regex=true). Formatting and structure are verified unchanged. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import keynote_io

    p = _path(path, ".key")
    return _write(dry_run, keynote_io.edit_text, p, find, replace, regex=regex)


@mcp.tool(annotations=WRITE)
def pages_replace_all(path: str, find: str, replace: str, dry_run: bool = False) -> dict[str, Any]:
    """Replace every occurrence of `find` in a .pages body (needs Pages + GUI session). Rolled back if the readback disagrees. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import pages_io

    p = _path(path, ".pages")
    return _write(dry_run, pages_io.edit_pages_body, p, find, replace, mode="replace_all")


@mcp.tool(annotations=WRITE)
def pages_set_body(path: str, body: str, dry_run: bool = False) -> dict[str, Any]:
    """Replace the entire body text of a .pages document (needs Pages + GUI session). Body formatting is reset. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import pages_io

    p = _path(path, ".pages")
    return _write(dry_run, pages_io.edit_pages_body, p, mode="set_body", new_body=body)


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
    def keynote_add_slide(path: str, after: int | None = None, dry_run: bool = False) -> dict[str, Any]:
        """Insert a slide after slide number `after` (0 = first, omit = end). Every other slide is verified unchanged. dry_run=true previews the change on a copy without touching the file."""
        return _write(dry_run, keynote_slides.add_slide, _path(path, ".key"), after=after)


if _slide_tool("duplicate"):

    @mcp.tool(annotations=WRITE)
    def keynote_duplicate_slide(path: str, slide: int, dry_run: bool = False) -> dict[str, Any]:
        """Duplicate slide number `slide` (1-based); the copy lands right after it. dry_run=true previews the change on a copy without touching the file."""
        return _write(dry_run, keynote_slides.duplicate_slide, _path(path, ".key"), slide)


if _slide_tool("delete"):

    @mcp.tool(annotations=WRITE)
    def keynote_delete_slide(path: str, slide: int, dry_run: bool = False) -> dict[str, Any]:
        """Delete slide number `slide` (1-based). Recoverable with iwork_restore_backup. dry_run=true previews the change on a copy without touching the file."""
        return _write(dry_run, keynote_slides.delete_slide, _path(path, ".key"), slide)


if _slide_tool("move"):

    @mcp.tool(annotations=WRITE)
    def keynote_move_slide(path: str, slide: int, to: int, dry_run: bool = False) -> dict[str, Any]:
        """Move slide number `slide` so it ends up at position `to` (both 1-based). dry_run=true previews the change on a copy without touching the file."""
        return _write(dry_run, keynote_slides.move_slide, _path(path, ".key"), slide, to)


if _slide_tool("skip"):

    @mcp.tool(annotations=WRITE)
    def keynote_skip_slide(path: str, slide: int, skipped: bool = True, dry_run: bool = False) -> dict[str, Any]:
        """Hide (skipped=true) or show a slide in the slideshow. dry_run=true previews the change on a copy without touching the file."""
        return _write(dry_run, keynote_slides.set_skipped, _path(path, ".key"), slide, skipped)


if _slide_tool("notes"):

    @mcp.tool(annotations=WRITE)
    def keynote_set_presenter_notes(path: str, slide: int, notes: str, dry_run: bool = False) -> dict[str, Any]:
        """Set the presenter notes of slide number `slide` (1-based). Arabic-safe. dry_run=true previews the change on a copy without touching the file."""
        return _write(dry_run, keynote_slides.set_presenter_notes, _path(path, ".key"), slide, notes)


# ── export (via the app; output verified by a second tool) ───────────────────


@mcp.tool(annotations=WRITE)
def iwork_export(
    path: str,
    format: str,
    out: str | None = None,
    password: str | None = None,
    password_hint: str | None = None,
    image_quality: str | None = None,
    image_format: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Export to another format. Numbers: pdf | xlsx | csv. Pages: pdf | docx | epub | txt | rtf. Keynote: pdf | pptx | images | movie. Optional password (+hint) for pdf/xlsx/docx/pptx, image_quality (good|better|best), image_format for slide images (jpeg|png|tiff). Default output sits next to the source. The export is checked against the source with a second tool and the source is verified unchanged. Needs macOS + the app."""
    from iwork_studio import exporter

    return _call(exporter.export, _path(path, ".numbers", ".pages", ".key"), format, _out_path(out),
                 password=password, password_hint=password_hint, image_quality=image_quality,
                 image_format=image_format, overwrite=overwrite)


# ── read-only helpers ─────────────────────────────────────────────────────────


@mcp.tool(annotations=READ)
def iwork_metadata(path: str) -> dict[str, Any]:
    """What a file says about itself, without the app: kind, size, modified, template it was made from, app builds that saved it, file format version, slide count (Keynote), embedded media count."""
    from iwork_studio import helpers

    return _call(helpers.metadata, _path(path, ".numbers", ".pages", ".key"))


@mcp.tool(annotations=READ)
def iwork_thumbnail(path: str, out_dir: str | None = None) -> dict[str, Any]:
    """Extract the preview image stored in the file (first page/slide) to a JPEG and return its path — a quick look without opening the app. Reflects the app's last save."""
    from iwork_studio import helpers

    return _call(helpers.thumbnail, _path(path, ".numbers", ".pages", ".key"), _out_path(out_dir))


@mcp.tool(annotations=READ)
def iwork_find(folder: str | None = None, kind: str | None = None, name: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Find Numbers / Keynote / Pages files (newest first). kind: numbers | keynote | pages; name: part of the file name. Searches `folder`, else the allowed folders, else Documents/Desktop/Downloads. Uses Spotlight on macOS."""
    from iwork_studio import helpers

    return _call(helpers.find_files, _search_folders(folder), kind=kind, name=name, limit=max(1, min(limit, 500)))


@mcp.tool(annotations=APP_READ)
def iwork_list_templates(app: str) -> dict[str, Any]:
    """Built-in templates for Numbers or Pages, or themes for Keynote (app: numbers | pages | keynote). Needs macOS + the app."""
    from iwork_studio import helpers

    return _call(helpers.list_templates, app)


# ── create & structure (Numbers: no app needed) ──────────────────────────────


@mcp.tool(annotations=WRITE)
def numbers_create(path: str, sheets: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a new .numbers file from data. sheets = [{"name": "Sales", "tables": [{"name": "Q1", "rows": [["Region", "Revenue"], ["Riyadh", 1200]], "header_rows": 1}]}]. Numbers stay numbers, text stays text exactly (Arabic included). Refuses to overwrite. No app needed."""
    from iwork_studio import numbers_structure as ns

    return _call(ns.create, _out_path(path), sheets)


@mcp.tool(annotations=WRITE)
def numbers_import_csv(
    csv_path: str,
    path: str,
    delimiter: str | None = None,
    header_rows: int = 1,
    sheet: str = "Sheet 1",
    table: str = "Table 1",
    numbers: bool = True,
) -> dict[str, Any]:
    """Turn a CSV/TSV into a new .numbers file (UTF-8, delimiter auto-detected). Plain numbers become numbers (numbers=false keeps everything as text); dates, "$1,234" and Arabic-Indic digits stay text exactly as written. Refuses to overwrite."""
    from iwork_studio import numbers_structure as ns

    return _call(ns.import_csv, _path(csv_path, ".csv", ".tsv", ".txt"), _out_path(path), delimiter=delimiter,
                 header_rows=header_rows, sheet=sheet, table=table, numbers=numbers)


@mcp.tool(annotations=WRITE)
def numbers_insert(
    path: str,
    what: str,
    count: int = 1,
    at: int | None = None,
    values: list[list[Any]] | None = None,
    sheet: str | None = None,
    table: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Insert rows or columns (what = rows | columns) before 1-based position `at`; omit `at` to append. Optional `values`: one list per new row (or column). Every existing cell is verified at its new position. In tables with formulas, only appending is allowed (shifting would break references). dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_structure as ns

    return _write(dry_run, ns.insert, _path(path, ".numbers"), what, count, at, values, sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def numbers_delete(path: str, what: str, at: int, count: int = 1, sheet: str | None = None,
                   table: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Delete `count` rows or columns (what = rows | columns) starting at 1-based position `at`. Remaining cells are verified. Refused in tables with formulas or merged cells. Undo with iwork_restore_backup. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_structure as ns

    return _write(dry_run, ns.delete, _path(path, ".numbers"), what, at, count, sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def numbers_add_table(
    path: str,
    table_name: str,
    rows: list[list[Any]],
    sheet: str | None = None,
    new_sheet: str | None = None,
    header_rows: int = 1,
    header_columns: int = 0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add a table with data to an existing sheet (`sheet`, default the first) or to a new sheet (`new_sheet`). Every existing table is verified unchanged. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import numbers_structure as ns

    return _write(dry_run, ns.add_table, _path(path, ".numbers"), table_name, rows, sheet=sheet, new_sheet=new_sheet,
                 header_rows=header_rows, header_columns=header_columns)


@mcp.tool(annotations=WRITE)
def iwork_create_from_template(template: str, path: str) -> dict[str, Any]:
    """Start a new document from one of the user's own files (any .numbers / .key / .pages): copies it to `path` and checks it opens. Refuses to overwrite."""
    from iwork_studio import numbers_structure as ns

    return _call(ns.create_from_template, _path(template, ".numbers", ".key", ".pages"), _out_path(path))


# ── app-driven (macOS + the app) ──────────────────────────────────────────────


@mcp.tool(annotations=WRITE)
def iwork_create(path: str, template: str | None = None) -> dict[str, Any]:
    """New .numbers / .key / .pages from Apple's built-in templates (Keynote: themes); names from iwork_list_templates. Omit template for Blank / Basic White. Refuses to overwrite. Needs macOS + the app."""
    from iwork_studio import app_ops

    return _call(app_ops.create_document, _out_path(path), template)


@mcp.tool(annotations=WRITE)
def numbers_set_formula(path: str, ref: str, formula: str, sheet: str | None = None,
                        table: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Put a formula in one cell, e.g. ref "D10", formula "=SUM(D2:D9)"; Numbers computes it and the result is returned. Every other cell's input is verified unchanged. Needs macOS + Numbers, file closed. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import app_ops

    return _write(dry_run, app_ops.set_formula, _path(path, ".numbers"), ref, formula, sheet=sheet, table=table)


@mcp.tool(annotations=WRITE)
def numbers_recalculate(path: str, dry_run: bool = False) -> dict[str, Any]:
    """Make Numbers recompute every formula from the current values. Numbers keeps showing a formula's old result after edits made without it (numbers_edit_cell, numbers_insert…), so run this after those when the file has formulas — their result says so (formulas_need_recalc). Formulas and inputs are verified unchanged. Needs macOS + Numbers, file closed. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import app_ops

    return _write(dry_run, app_ops.recalculate, _path(path, ".numbers"))


@mcp.tool(annotations=WRITE)
def numbers_sort(path: str, column: str, descending: bool = False, sheet: str | None = None,
                 table: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Sort a table's body rows by a column letter (header rows stay on top). Verified as a pure reorder. Needs macOS + Numbers, file closed. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import app_ops

    return _write(dry_run, app_ops.sort_table, _path(path, ".numbers"), column, descending=descending, sheet=sheet,
                 table=table)


@mcp.tool(annotations=APP_READ)
def pages_list_placeholders(path: str) -> dict[str, Any]:
    """Template placeholders in a .pages document (tag + current text), e.g. a letter's "Name" or "Date" fields. Needs macOS + Pages."""
    from iwork_studio import app_ops

    return _call(app_ops.list_placeholders, _path(path, ".pages"))


@mcp.tool(annotations=WRITE)
def pages_fill_placeholders(path: str, values: dict[str, str], dry_run: bool = False) -> dict[str, Any]:
    """Fill template placeholders by tag, e.g. {"Name": "Sara", "Date": "3 October"}. Formatting is kept; the body is verified to change only there. Needs macOS + Pages. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import app_ops

    return _write(dry_run, app_ops.fill_placeholders, _path(path, ".pages"), values)


@mcp.tool(annotations=APP_READ)
def pages_read_tables(path: str) -> dict[str, Any]:
    """Every table in a .pages document: name, size, and each cell's value, shown text and formula. Needs macOS + Pages."""
    from iwork_studio import app_ops

    return _call(app_ops.read_tables, _path(path, ".pages"))


@mcp.tool(annotations=WRITE)
def pages_set_table_cells(path: str, table: str, cells: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    """Write cells of an existing table in a .pages document. table = its name or number (from pages_read_tables); cells = {"B2": 1200, "C3": "تم", "D9": "=SUM(D2:D8)"} — numbers stay numbers, "=…" makes a formula, null clears. Every other cell and the body text are verified unchanged. New tables can't be created (Pages 15 doesn't script it). Needs macOS + Pages, document closed. dry_run=true previews the change on a copy without touching the file."""
    from iwork_studio import app_ops

    return _write(dry_run, app_ops.set_table_cells, _path(path, ".pages"), table, cells)


@mcp.tool(annotations=APP_READ)
def keynote_slideshow(action: str, path: str | None = None, from_slide: int = 1) -> dict[str, Any]:
    """Present: action = start (needs path; from_slide 1-based) | stop | next | previous. Doesn't change the file. Needs macOS + Keynote."""
    from iwork_studio import app_ops

    return _call(app_ops.slideshow, action, _path(path, ".key") if path else None, from_slide=from_slide)


# ── Keynote theming (via the app) ────────────────────────────────────────────

if keynote_slides.slide_ops_enabled():

    @mcp.tool(annotations=APP_READ)
    def keynote_list_slides(path: str) -> dict[str, Any]:
        """Every slide with its text, presenter notes and whether it is hidden (via Keynote). Use slide numbers from here for slide operations."""
        def run(p):
            return {"slides": [{"slide": i, **s} for i, s in enumerate(keynote_slides.read_slides(p), start=1)]}

        return _call(run, _path(path, ".key"))

    @mcp.tool(annotations=APP_READ)
    def keynote_list_themes() -> dict[str, Any]:
        """Themes available in Keynote on this Mac (names to pass to keynote_set_theme)."""
        from iwork_studio import keynote_theme as kt

        return _call(lambda: {"themes": kt.list_themes()})

    @mcp.tool(annotations=APP_READ)
    def keynote_inspect_style(path: str) -> dict[str, Any]:
        """A deck's styling: current theme, available slide layouts, and per slide its layout plus each text item's text, font, size and colour. Read this before theming."""
        from iwork_studio import keynote_theme as kt

        return _call(kt.read_style, _path(path, ".key"))

    @mcp.tool(annotations=WRITE)
    def keynote_set_theme(path: str, theme: str, dry_run: bool = False) -> dict[str, Any]:
        """Apply a different Keynote theme to the whole deck. Rolled back if any slide loses text. dry_run=true previews the change on a copy without touching the file."""
        from iwork_studio import keynote_theme as kt

        return _write(dry_run, kt.set_theme, _path(path, ".key"), theme)

    @mcp.tool(annotations=WRITE)
    def keynote_set_slide_layout(path: str, slide: int, layout: str, dry_run: bool = False) -> dict[str, Any]:
        """Change one slide's layout (master), e.g. "Title & Bullets". Other slides are verified untouched. dry_run=true previews the change on a copy without touching the file."""
        from iwork_studio import keynote_theme as kt

        return _write(dry_run, kt.set_slide_layout, _path(path, ".key"), slide, layout)

    @mcp.tool(annotations=WRITE)
    def keynote_format_text(
        path: str,
        slide: int,
        item: int | None = None,
        match: str | None = None,
        font: str | None = None,
        size: float | None = None,
        color: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Font (PostScript name, e.g. "HelveticaNeue-Bold"), size (pt) and/or colour ("#RRGGBB") of one text item on a slide — pick it by item index (from keynote_inspect_style) or by a unique piece of its text (match). Alignment and shape fill are not scriptable. dry_run=true previews the change on a copy without touching the file."""
        from iwork_studio import keynote_theme as kt

        return _write(dry_run, kt.format_text, _path(path, ".key"), slide, item=item, match=match, font=font,
                     size=size, color=color)


    @mcp.tool(annotations=WRITE)
    def keynote_set_transition(
        path: str,
        slide: int,
        effect: str,
        duration: float | None = None,
        delay: float | None = None,
        automatic: bool | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Transition into a slide: effect such as dissolve, push, wipe, magic move, cube, flip, move in, reveal, "none"; duration/delay in seconds; automatic=true advances on its own. Other slides verified untouched. dry_run=true previews the change on a copy without touching the file."""
        from iwork_studio import app_ops

        return _write(dry_run, app_ops.set_transition, _path(path, ".key"), slide, effect, duration=duration, delay=delay,
                     automatic=automatic)

    @mcp.tool(annotations=WRITE)
    def keynote_add_chart(
        path: str,
        slide: int,
        rows: list[str],
        columns: list[str],
        data: list[list[float]],
        type: str = "bar",
        group_by: str = "row",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add a chart to a slide from data. rows = series names, columns = category names, data = one list of numbers per row (rows × columns). type: bar | stacked_bar | horizontal_bar | stacked_horizontal_bar | line | area | stacked_area | pie | scatter (or *_3d). group_by: row | column. Text and other charts are verified untouched. dry_run=true previews the change on a copy without touching the file."""
        from iwork_studio import app_ops

        return _write(dry_run, app_ops.add_chart, _path(path, ".key"), slide, rows, columns, data, type=type, group_by=group_by)

    @mcp.tool(annotations=WRITE)
    def keynote_add_image(path: str, slide: int, image: str, x: float | None = None, y: float | None = None,
                          width: float | None = None, dry_run: bool = False) -> dict[str, Any]:
        """Place an image file (png, jpg, heic, pdf…) on a slide; optional x/y position and width in points. All text verified untouched. dry_run=true previews the change on a copy without touching the file."""
        from iwork_studio import app_ops

        return _write(dry_run, app_ops.add_image, _path(path, ".key"), slide, _path(image), x=x, y=y, width=width)


def main() -> None:
    # `iwork-studio-mcp install|uninstall|config` = set-up helpers; no args = serve.
    if len(sys.argv) > 1:
        from iwork_studio.installer import main as installer_main

        raise SystemExit(installer_main(sys.argv[1:]))
    mcp.run("stdio")


if __name__ == "__main__":
    main()
