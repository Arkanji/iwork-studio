"""iWork Studio — parameter descriptions and "when to use it" guidance for every MCP tool.

Clients and directories read a tool's parameter descriptions and decide between
sibling tools from its description, so both live here in one place:

  param_doc(tool, name)   the description of one parameter
  USAGE[tool]             one or two sentences: when to use this tool, and which to use instead

mcp_server applies them to every registered tool; a test checks nothing is missing.
"""

from __future__ import annotations

_FILE = {"numbers": "the .numbers file", "keynote": "the .key deck", "pages": "the .pages document",
         "iwork": "the .numbers, .key or .pages file"}

# Parameters that mean the same thing everywhere.
COMMON = {
    "dry_run": "true = make the change on a throwaway copy, run every check, and return what would change; "
               "the file itself is not touched. Use it before broad or risky edits and show the user.",
    "sheet": "Sheet name. Omit when the file has one sheet (iwork_read lists sheets and tables).",
    "table": "Table name on that sheet. Omit when the sheet has one table.",
    "slide": "Slide number, 1-based (keynote_list_slides lists them).",
    "cells": 'A cell or range in A1 notation, e.g. "B2" or "A1:D1".',
    "kit": 'A design kit: a name from iwork_list_design_kits (preset or saved, e.g. "executive", "Resal") or '
           'your own {"fonts": {...}, "colors": {"title": "#RRGGBB", ...}}. Contrast is checked.',
    "ref": 'One cell in A1 notation, e.g. "B2".',
    "overwrite": "true = replace an existing output (the old one is kept as a backup or returned). Default false.",
    "header_rows": "How many rows at the top are headers (styled and kept on top).",
    "header_columns": "How many columns on the left are headers.",
    "color": 'Colour as "#RRGGBB".',
    "width": "Width in points.",
    "x": "Left edge in points from the slide's top-left corner (give with y).",
    "y": "Top edge in points from the slide's top-left corner (give with x).",
}

# Tool-specific parameters (and overrides of COMMON).
PARAMS: dict[str, dict[str, str]] = {
    "iwork_verify_format": {
        "text": "Text that must appear in the rendered PDF; for Arabic, one word (multi-word RTL text is reordered).",
        "font": 'Expected font; matches when the drawn font name contains it, e.g. "Avenir".',
        "size": "Expected size in points (±0.6).",
        "color": 'Expected text colour "#RRGGBB".',
        "bold": "Expected bold (true) or not bold (false).",
        "page_width": "Expected page width in points.",
        "page_height": "Expected page height in points.",
    },
    "iwork_verify_render": {
        "assert_text": "Text that must be visibly rendered; for Arabic, one word.",
        "expected_pages": "Expected page (or slide) count; omit to skip that check.",
    },
    "numbers_edit_cell": {"value": "New value: a number stays a number, text stays text exactly (Arabic too); null clears. "
                                   "For a formula use numbers_set_formula."},
    "numbers_set_dimensions": {
        "columns": 'Column widths in points by letter, e.g. {"A": 160, "C": 90}.',
        "rows": 'Row heights in points by 1-based row number, e.g. {"1": 32}.',
    },
    "numbers_set_number_format": {
        "format": "number | currency | percentage | scientific | fraction | datetime | text.",
        "decimal_places": "Digits after the decimal point.",
        "thousands_separator": "true = group thousands (1,234).",
        "negative_style": "minus | red | parentheses | red_parentheses.",
        "currency_code": 'ISO currency code for format=currency, e.g. "SAR" or "USD".',
        "accounting": "true = accounting style (symbol aligned left) for currency.",
        "date_format": 'Date pattern for format=datetime, e.g. "d MMM yyyy".',
    },
    "numbers_set_cell_style": {
        "font_name": 'Font family, e.g. "Helvetica Neue" or "Geeza Pro".',
        "font_size": "Font size in points.",
        "bold": "true/false; omit to leave as is.",
        "italic": "true/false; omit to leave as is.",
        "underline": "true/false; omit to leave as is.",
        "strikethrough": "true/false; omit to leave as is.",
        "font_color": 'Text colour "#RRGGBB".',
        "fill_color": 'Cell fill "#RRGGBB".',
        "align": "Horizontal: left | center | right | justify | auto.",
        "valign": "Vertical: top | middle | bottom.",
        "wrap": "true = wrap text in the cell.",
    },
    "numbers_set_borders": {
        "sides": "all | outline | inner | top | right | bottom | left.",
        "width": "Line width in points.",
        "color": 'Line colour "#RRGGBB".',
        "style": "solid | dashes | dots | none (none removes the border).",
    },
    "numbers_set_headers": {"header_rows": "Number of header rows (0 for none).",
                            "header_columns": "Number of header columns (0 for none)."},
    "numbers_merge_cells": {"cells": 'The range to merge, e.g. "A1:C1". Refused if it would hide values.'},
    "numbers_insert": {
        "what": "rows | columns.",
        "count": "How many to insert.",
        "at": "1-based position to insert before; omit to append at the end.",
        "values": "Optional contents: one list per new row (or column), e.g. [[\"Riyadh\", 1200]].",
    },
    "numbers_delete": {"what": "rows | columns.", "at": "1-based position of the first one to delete.",
                       "count": "How many to delete."},
    "numbers_add_table": {
        "table_name": "Name of the new table (must not exist on that sheet).",
        "rows": 'The data, header first: [["Region", "Revenue"], ["Riyadh", 1200]].',
        "sheet": "Existing sheet to add it to; omit for the first sheet.",
        "new_sheet": "Name of a new sheet to create for the table instead.",
    },
    "numbers_create": {
        "path": "Where to create the new .numbers file; it must not exist yet.",
        "sheets": 'Sheets with their tables: [{"name": "Sales", "tables": [{"name": "Q1", "rows": [["Region", "Revenue"], '
                  '["Riyadh", 1200]], "header_rows": 1}]}].',
    },
    "numbers_import_csv": {
        "csv_path": "The CSV or TSV file to read (UTF-8).",
        "path": "Where to create the new .numbers file; it must not exist yet.",
        "delimiter": 'Column separator, e.g. "," or "\\t"; omit to detect it.',
        "sheet": "Name for the new sheet.",
        "table": "Name for the new table.",
        "numbers": "true = plain numbers become numbers; false = keep every cell as text.",
    },
    "numbers_set_formula": {"formula": 'The formula, starting with "=", e.g. "=SUM(B2:B9)".'},
    "numbers_sort": {"column": 'Column letter to sort by, e.g. "C".', "descending": "true = largest/last first."},
    "keynote_replace_text": {"find": "Text to find (literal unless regex=true).", "replace": "Replacement text.",
                             "regex": "true = treat find as a regular expression."},
    "pages_replace_all": {"find": "Text to find, exactly.", "replace": "Replacement text."},
    "pages_set_body": {"body": "The new body text; paragraphs separated by newlines. Resets body formatting."},
    "iwork_restore_backup": {"backup": "Backup name from iwork_list_backups."},
    "keynote_add_slide": {"after": "Insert after this slide number; 0 = make it the first slide; omit = at the end."},
    "keynote_move_slide": {"slide": "The slide to move, 1-based.", "to": "Where it should end up, 1-based."},
    "keynote_skip_slide": {"skipped": "true = hide the slide in the slideshow; false = show it again."},
    "keynote_set_presenter_notes": {"notes": "The presenter notes text (replaces existing notes)."},
    "iwork_export": {
        "format": "Numbers: pdf | xlsx | csv. Pages: pdf | docx | epub | txt | rtf. Keynote: pdf | pptx | images | movie.",
        "out": "Output path (a folder for images); omit to write next to the source.",
        "password": "Optional password for pdf, xlsx, docx or pptx.",
        "password_hint": "Optional hint shown with the password prompt.",
        "image_quality": "good | better | best.",
        "image_format": "Slide images only: jpeg | png | tiff.",
    },
    "iwork_thumbnail": {"out_dir": "Folder for the extracted JPEG; omit for a temporary folder."},
    "iwork_find": {
        "folder": "Folder to search; omit to search the allowed folders, else Documents, Desktop and Downloads.",
        "kind": "numbers | keynote | pages; omit for all three.",
        "name": "Part of the file name to match (case-insensitive).",
        "limit": "Maximum results (1–500).",
    },
    "iwork_extract_design_kit": {
        "path": "A .key deck or .numbers table that already has the look to capture.",
        "name": 'Name for the kit, e.g. "Resal" (required with save=true).',
        "save": "true = save it under name for reuse; contrast must pass.",
        "overwrite": "true = replace a saved kit with the same name.",
        "sheet": "For .numbers: the sheet holding the styled table.",
        "table": "For .numbers: the styled table.",
    },
    "iwork_save_design_kit": {
        "name": 'Name to save under, e.g. "Resal" (letters, digits, spaces, - or _; not a preset name).',
        "kit": '{"fonts": {...}, "colors": {...}, "theme": "...", "background": "#RRGGBB", "base": "<preset>"} '
               "or a preset name to copy.",
        "overwrite": "true = replace a saved kit with the same name.",
    },
    "iwork_delete_design_kit": {"name": "Name of the saved kit to delete (presets can't be deleted)."},
    "numbers_apply_design": {"banding": "true = tint alternate body rows."},
    "iwork_list_templates": {"app": "numbers | pages | keynote."},
    "iwork_create_from_template": {"template": "The user's own .numbers, .key or .pages file to copy.",
                                   "path": "Where to create the new file; it must not exist yet."},
    "iwork_create": {"path": "Where to create the new file (.numbers, .key or .pages); it must not exist yet.",
                     "template": "Template or theme name from iwork_list_templates; omit for Blank / Basic White."},
    "pages_fill_placeholders": {"values": 'Placeholder tag → text, e.g. {"Name": "Sara", "Date": "3 October"} '
                                          "(tags from pages_list_placeholders)."},
    "pages_set_table_cells": {
        "table": "The table's name or number (from pages_read_tables).",
        "cells": '{"B2": 1200, "C3": "تم", "D9": "=SUM(D2:D8)"}: numbers stay numbers, "=…" is a formula, null clears.',
    },
    "keynote_slideshow": {"action": "start | stop | next | previous.",
                          "path": "The deck to present (needed for start).",
                          "from_slide": "Slide to start from, 1-based."},
    "keynote_set_theme": {"theme": "Theme name from keynote_list_themes."},
    "keynote_set_slide_layout": {"layout": "Layout (master slide) name from keynote_inspect_style."},
    "keynote_format_text": {
        "item": "Text item index on the slide (from keynote_inspect_style); or use match.",
        "match": "A unique piece of the item's text, to pick it instead of item.",
        "font": 'PostScript font name, e.g. "HelveticaNeue-Bold".',
        "size": "Font size in points.",
        "color": 'Text colour "#RRGGBB".',
    },
    "keynote_set_transition": {
        "effect": 'Transition effect, e.g. "dissolve", "push", "magic move", or "none".',
        "duration": "Duration in seconds.",
        "delay": "Delay before it starts, in seconds.",
        "automatic": "true = advance to the next slide on its own.",
    },
    "keynote_build_deck": {
        "path": "Where to create the new .key deck; it must not exist yet.",
        "slides": 'The outline: [{"title": "…", "body": ["bullet", …], "notes": "…", "layout": "…", "image": "/path.png", '
                  '"chart": {…}, "table": {…}}, …]; see the tool description for chart and table.',
        "theme": "Theme name from keynote_list_themes; the kit's theme is used when omitted.",
        "transition": 'Transition for every slide, e.g. "dissolve".',
    },
    "keynote_add_table": {
        "rows": 'The table, header first: [["Region", "Q1"], ["Riyadh", 1200]]; text, numbers or null; "=…" is a formula.',
        "x": "Left edge in points (give with y); omit to let Keynote place it.",
        "y": "Top edge in points (give with x).",
        "width": "Table width in points; omit for Keynote's default.",
    },
    "keynote_slide_image": {"width": "Image width in pixels (320–2560)."},
    "keynote_apply_design": {"set_theme": "true = also switch to the kit's theme first."},
    "keynote_set_slide_text": {"title": "New title text; omit to leave it.",
                               "body": "New body: a string, or a list of bullets; omit to leave it."},
    "keynote_add_chart": {
        "rows": 'Row names, e.g. ["2025", "2026"] (series when group_by="row").',
        "columns": 'Column names, e.g. ["Q1", "Q2", "Q3"].',
        "data": "One list of numbers per row name, each as long as columns.",
        "type": "bar | stacked_bar | horizontal_bar | stacked_horizontal_bar | line | area | stacked_area | pie | "
                "scatter (or a *_3d variant).",
        "group_by": 'row (each row is a series) | column.',
    },
    "keynote_add_image": {"image": "Image file to place (png, jpg, heic, pdf…).",
                          "x": "Left edge in points (give with y); omit to let Keynote place it.",
                          "width": "Image width in points; height keeps the aspect ratio."},
}


def param_doc(tool: str, name: str) -> str | None:
    if name in PARAMS.get(tool, {}):
        return PARAMS[tool][name]
    if name == "path":
        return f"Path to {_FILE.get(tool.split('_', 1)[0], 'the file')} (absolute, or starting with ~)."
    return COMMON.get(name)


# When to use each tool, and what to use instead.
USAGE = {
    "iwork_capabilities": "Call first when unsure what this machine can do (Mac apps, GUI session, which routes work).",
    "iwork_read": "Use to see a file's content before editing it. For Numbers formatting use numbers_inspect_format; "
                  "for Keynote styling, keynote_inspect_style.",
    "iwork_find": "Use when the user names a file loosely (\"my sales deck\"); then read it with iwork_read.",
    "iwork_metadata": "Use for file facts (template, app build, slide count) without reading content; use iwork_read for content.",
    "iwork_thumbnail": "Use for a quick look at the stored preview with no app; for the real rendering of a slide use keynote_slide_image.",
    "iwork_list_templates": "Use before iwork_create to pick a template or theme name.",
    "iwork_create": "Use for a new file from Apple's templates; for a copy of the user's own file use iwork_create_from_template; "
                    "for a Numbers file from data use numbers_create; for a designed deck use keynote_build_deck.",
    "iwork_create_from_template": "Use when the user has their own template file; use iwork_create for Apple's built-in ones.",
    "iwork_export": "Use to hand the result over as PDF, Excel, Word or PowerPoint; never convert back into iWork.",
    "iwork_verify_render": "Use after an important write to confirm the text really shows; use iwork_verify_format to check font, size or colour.",
    "iwork_verify_format": "Use to confirm how text is drawn (font, size, colour); use iwork_verify_render to check text is present.",
    "iwork_list_backups": "Use to find a version to undo to, then restore it with iwork_restore_backup.",
    "iwork_restore_backup": "Use to undo a change: pick the backup with iwork_list_backups first.",
    "iwork_list_design_kits": "Use before styling to pick a kit (presets and the user's saved kits).",
    "iwork_extract_design_kit": "Use when the user has a deck or table with their brand look; use iwork_save_design_kit when they give colours and fonts directly.",
    "iwork_save_design_kit": "Use when the user gives brand colours and fonts; use iwork_extract_design_kit to take them from a file.",
    "iwork_delete_design_kit": "Use only when the user asks to remove a saved kit.",
    "numbers_create": "Use to make a new Numbers file from data; use numbers_import_csv for a CSV file.",
    "numbers_import_csv": "Use for a CSV/TSV file; use numbers_create when you already have the rows.",
    "numbers_edit_cell": "Use for one value; for a formula use numbers_set_formula, for many rows numbers_insert with values.",
    "numbers_set_formula": "Use for a formula cell (Numbers computes it); use numbers_edit_cell for plain values.",
    "numbers_recalculate": "Use when a no-app edit returned formulas_need_recalc, so totals are current.",
    "numbers_insert": "Use to add rows or columns (optionally with values); use numbers_add_table for a separate table.",
    "numbers_delete": "Use to remove rows or columns; undo with iwork_restore_backup.",
    "numbers_add_table": "Use for a new, separate table; use numbers_insert to grow an existing one.",
    "numbers_sort": "Use to reorder body rows by a column.",
    "numbers_inspect_format": "Use before formatting to see current styles, formats, sizes and merges.",
    "numbers_set_cell_style": "Use for fonts, colours, fill and alignment of a range; for a whole designed table use numbers_apply_design.",
    "numbers_set_number_format": "Use for how numbers display (currency, %, dates); values don't change.",
    "numbers_set_borders": "Use for cell borders on a range.",
    "numbers_set_dimensions": "Use for column widths and row heights.",
    "numbers_set_headers": "Use to change how many header rows/columns a table has.",
    "numbers_merge_cells": "Use to merge a range, e.g. a title across columns.",
    "numbers_apply_design": "Use to make a whole table look designed in one call; use numbers_set_cell_style for a few cells.",
    "keynote_build_deck": "Use for a new deck from an outline; then run keynote_review_deck. To change an existing deck use the slide tools.",
    "keynote_set_slide_text": "Use to fill or rewrite a slide's title and body; use keynote_replace_text for find/replace across the deck.",
    "keynote_replace_text": "Use to change the same text everywhere; use keynote_set_slide_text for one slide's title or body.",
    "keynote_list_slides": "Use to see slides, notes and hidden state before slide operations.",
    "keynote_add_slide": "Use for a blank slide; use keynote_duplicate_slide to copy one; use keynote_build_deck for a whole deck.",
    "keynote_duplicate_slide": "Use to copy an existing slide; use keynote_add_slide for a blank one.",
    "keynote_delete_slide": "Use to remove a slide (the last one can't be deleted); to hide it instead use keynote_skip_slide.",
    "keynote_move_slide": "Use to reorder slides.",
    "keynote_skip_slide": "Use to hide or show a slide in the slideshow without deleting it.",
    "keynote_set_presenter_notes": "Use for speaker notes on an existing slide (keynote_build_deck sets notes for new decks).",
    "keynote_list_themes": "Use before keynote_set_theme or keynote_build_deck to pick a theme name.",
    "keynote_inspect_style": "Use before formatting: theme, layouts, and each text item's font, size and colour.",
    "keynote_set_theme": "Use to switch the deck's theme; for a full designed look use keynote_apply_design.",
    "keynote_set_slide_layout": "Use to change one slide's layout (names from keynote_inspect_style).",
    "keynote_format_text": "Use for one text item; to restyle the whole deck use keynote_apply_design.",
    "keynote_set_transition": "Use for one slide's transition (keynote_build_deck can set one for every slide).",
    "keynote_add_image": "Use to place a picture or logo on a slide.",
    "keynote_add_chart": "Use for a chart on an existing slide; in a new deck put it in keynote_build_deck's outline.",
    "keynote_add_table": "Use for a table on an existing slide; in a new deck put it in keynote_build_deck's outline.",
    "keynote_apply_design": "Use to restyle a whole deck from a kit; preview with dry_run, then run keynote_review_deck.",
    "keynote_review_deck": "Use after building or restyling a deck, before saying it's done; fix errors, then look with keynote_slide_image.",
    "keynote_slide_image": "Use to look at a slide's real design (e.g. one keynote_review_deck flagged).",
    "keynote_slideshow": "Use to present the deck; it doesn't change the file.",
    "pages_preflight": "Call once before other Pages tools; a -1712 error means a dialog needs a human.",
    "pages_replace_all": "Use to change text everywhere and keep formatting; pages_set_body replaces the whole body.",
    "pages_set_body": "Use only to replace the whole body (resets its formatting); prefer pages_replace_all or pages_fill_placeholders.",
    "pages_list_placeholders": "Use before pages_fill_placeholders to see the template's fields.",
    "pages_fill_placeholders": "Use for template fields (Name, Date); the only write for page-layout documents like letters.",
    "pages_read_tables": "Use before pages_set_table_cells to see tables and cell references.",
    "pages_set_table_cells": "Use to write into an existing Pages table (new tables can't be created).",
}
