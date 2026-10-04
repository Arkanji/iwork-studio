"""iWork Studio — toolsets: load only the tools a client needs.

Every connected client reads every tool's description, so a Keynote-only user
shouldn't carry 64. Pick toolsets with IWORK_STUDIO_TOOLSETS (or
`iwork-studio-mcp serve --toolsets keynote,design`); the default is all of them.
The core tools (capabilities, read, find, undo, the kit list) are always loaded.
"""

from __future__ import annotations

import re

__all__ = ["TOOLSETS", "CORE", "PROMPT_NEEDS", "parse", "selected", "describe"]

CORE = {"iwork_capabilities", "iwork_read", "iwork_find", "iwork_list_backups", "iwork_restore_backup",
        "iwork_list_design_kits"}

TOOLSETS: dict[str, str] = {
    "files": "new files from templates, export (PDF, Excel, Word, PowerPoint…), metadata, thumbnails, render checks",
    "numbers": "every Numbers tool: create, edit, structure, format, formulas, sort, design",
    "keynote": "every Keynote tool: build decks, slides, text, theming, images, charts, tables, review, present",
    "pages": "every Pages tool: replace text, body, placeholders, tables",
    "design": "design kits and brand kits, restyling, deck building and the design review",
}

_FILES = {"iwork_metadata", "iwork_thumbnail", "iwork_list_templates", "iwork_create", "iwork_create_from_template",
          "iwork_export", "iwork_verify_render", "iwork_verify_format"}
_DESIGN = {"iwork_extract_design_kit", "iwork_save_design_kit", "iwork_delete_design_kit", "numbers_apply_design",
           "keynote_apply_design", "keynote_build_deck", "keynote_review_deck", "keynote_slide_image"}

# A prompt is offered only when the tools it walks through are loaded.
PROMPT_NEEDS = {
    "pitch_deck": {"keynote_build_deck", "keynote_review_deck"},
    "report_from_numbers": {"keynote_build_deck", "keynote_review_deck"},
    "restyle_with_brand": {"iwork_extract_design_kit"},
    "style_table": {"numbers_apply_design"},
}


def _sets_of(tool: str) -> set[str]:
    out = set()
    if tool in _FILES:
        out.add("files")
    if tool in _DESIGN:
        out.add("design")
    prefix = tool.split("_", 1)[0]
    if prefix in ("numbers", "keynote", "pages"):
        out.add(prefix)
    return out


def parse(value: str | None) -> tuple[set[str] | None, list[str]]:
    """'keynote, design' → ({'keynote', 'design'}, unknown names). None/''/'all' → (None, [])."""
    names = [n for n in re.split(r"[,\s]+", (value or "").strip().lower()) if n]
    if not names or "all" in names:
        return None, []
    unknown = [n for n in names if n not in TOOLSETS]
    return {n for n in names if n in TOOLSETS}, unknown


def selected(tool: str, sets: set[str] | None) -> bool:
    return sets is None or tool in CORE or bool(_sets_of(tool) & sets)


def describe(sets: set[str] | None, unknown: list[str], loaded: int) -> dict:
    return {"active": "all" if sets is None else sorted(sets), "tools_loaded": loaded, "always_loaded": sorted(CORE),
            "available": TOOLSETS, "unknown_ignored": unknown,
            "how": 'set IWORK_STUDIO_TOOLSETS (e.g. "keynote,design") or run `iwork-studio-mcp serve --toolsets '
                   'keynote,design`; default all'}
