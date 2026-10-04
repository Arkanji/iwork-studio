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


# When to use each tool, when not to, and what to use instead.
USAGE = {
    "iwork_capabilities": "Call first when unsure what this machine can do: which apps exist, whether a GUI session is "
                          "available, which toolsets are loaded. Not needed before plain reads of .numbers or .key files.",
    "iwork_read": "Use to see a file's content before editing it. Not for formatting details: use numbers_inspect_format "
                  "(Numbers) or keynote_inspect_style (Keynote). For file facts only, iwork_metadata is cheaper.",
    "iwork_find": "Use when the user names a file loosely (\"my sales deck\") or you don't know its path; then read it with "
                  "iwork_read. Not needed when you already have the path.",
    "iwork_metadata": "Use for file facts (template, app build, slide count) without reading content. For the content "
                      "itself use iwork_read.",
    "iwork_thumbnail": "Use for a quick look at the stored first-page preview with no app. It reflects the last save in the "
                       "app, not your latest edits: to see a slide as it renders now, use keynote_slide_image.",
    "iwork_list_templates": "Use before iwork_create to get valid template or theme names. Not needed for "
                            "iwork_create_from_template, which copies the user's own file.",
    "iwork_create": "Use for a new, empty file from Apple's templates. Instead: iwork_create_from_template to copy the "
                    "user's own file, numbers_create to make a Numbers file from data, keynote_build_deck for a "
                    "finished deck from an outline.",
    "iwork_create_from_template": "Use when the user has their own template or past file to start from. For Apple's "
                                  "built-in templates use iwork_create.",
    "iwork_export": "Use to hand the result over in another format (PDF, Excel, Word, PowerPoint, images). Never export to "
                    "docx/pptx/xlsx to edit and convert back: edit the iWork file directly.",
    "iwork_verify_render": "Use after an important write to prove the text really shows when rendered. To check font, size "
                           "or colour use iwork_verify_format; to check a deck's whole design use keynote_review_deck.",
    "iwork_verify_format": "Use to prove how a piece of text is drawn (font, size, colour, page size). To check text is "
                           "merely present use iwork_verify_render.",
    "iwork_list_backups": "Use when the user wants to undo or compare versions: it lists the backups, then "
                          "iwork_restore_backup restores one. Not needed after a failed tool call: failed writes never "
                          "change the file.",
    "iwork_restore_backup": "Use to undo a change, with a backup name from iwork_list_backups. The current version is "
                            "backed up first, so a restore can itself be undone.",
    "iwork_list_design_kits": "Use before any styling to pick a kit, and to see the user's saved brand kits. Pass the "
                              "name as kit= to keynote_build_deck, keynote_apply_design or numbers_apply_design.",
    "iwork_extract_design_kit": "Use when the user has a deck or table that already has their brand look. If they give "
                                "colours and fonts directly use iwork_save_design_kit instead.",
    "iwork_save_design_kit": "Use when the user gives brand colours and fonts directly. To capture them from an existing "
                             "file use iwork_extract_design_kit.",
    "iwork_delete_design_kit": "Use only when the user asks to remove a saved kit. To change a kit, save it again with "
                               "overwrite=true instead.",
    "numbers_create": "Use to make a new Numbers file when you have the rows. From a CSV file use numbers_import_csv; to "
                      "add a table to an existing file use numbers_add_table.",
    "numbers_import_csv": "Use when the data is in a CSV/TSV file. When you already have the rows use numbers_create.",
    "numbers_edit_cell": "Use to set one value. For a formula use numbers_set_formula; to add whole rows use numbers_insert "
                         "with values; for how a number displays use numbers_set_number_format.",
    "numbers_set_formula": "Use for a cell that calculates (=SUM…); Numbers computes the result. For a plain value use "
                           "numbers_edit_cell. Needs the Numbers app.",
    "numbers_recalculate": "Use only after a no-app edit returned formulas_need_recalc, so totals are current. Not needed "
                           "after numbers_set_formula, which recalculates itself.",
    "numbers_insert": "Use to add rows or columns to an existing table (optionally filled). For a separate table use "
                      "numbers_add_table. In tables with formulas only appending works; do mid-table inserts in Numbers.",
    "numbers_delete": "Use to remove rows or columns. Not for clearing values (use numbers_edit_cell with null). Refused "
                      "in tables with formulas or merges; undo with iwork_restore_backup.",
    "numbers_add_table": "Use for a new, separate table on a sheet or a new sheet. To grow an existing table use "
                         "numbers_insert.",
    "numbers_sort": "Use to reorder body rows by one column; header rows stay on top. Needs the Numbers app.",
    "numbers_inspect_format": "Use before formatting to see current styles, number formats, sizes, headers and merges. "
                              "For values use iwork_read.",
    "numbers_set_cell_style": "Use for fonts, colours, fill or alignment on a few cells. For a whole table that should "
                              "look designed use numbers_apply_design; for how numbers display use "
                              "numbers_set_number_format.",
    "numbers_set_number_format": "Use for how numbers display (currency, %, dates, decimals); the values don't change. For "
                                 "fonts and colours use numbers_set_cell_style.",
    "numbers_set_borders": "Use for lines around or inside a range. For fills and fonts use numbers_set_cell_style.",
    "numbers_set_dimensions": "Use for column widths and row heights. To change which rows count as headers use "
                              "numbers_set_headers.",
    "numbers_set_headers": "Use when the user wants a different number of header rows or columns, e.g. to freeze a title "
                           "row on top for sorting and styling. Not for sizes (numbers_set_dimensions) or header "
                           "colours (numbers_set_cell_style or numbers_apply_design).",
    "numbers_merge_cells": "Use to merge a range, e.g. a title across columns. Refused if it would hide values; avoid "
                           "merging inside data you will sort.",
    "numbers_apply_design": "Use to make a whole table look designed in one call (header band, fonts, banding, aligned "
                            "numbers). For a few cells use numbers_set_cell_style. Preview with dry_run.",
    "keynote_build_deck": "Use for a new deck from an outline, including chart and table slides; then run "
                          "keynote_review_deck. To change an existing deck use the slide and text tools instead.",
    "keynote_set_slide_text": "Use to fill or rewrite one slide's title and body. To change the same words across the "
                              "deck use keynote_replace_text; for speaker notes use keynote_set_presenter_notes.",
    "keynote_replace_text": "Use to change the same text everywhere in a deck (names, dates, numbers). To rewrite one "
                            "slide's title or body use keynote_set_slide_text.",
    "keynote_list_slides": "Use before slide operations to see slide numbers, text, notes and hidden state. For fonts and "
                           "layouts use keynote_inspect_style.",
    "keynote_add_slide": "Use for a new blank slide in an existing deck. To copy a slide use keynote_duplicate_slide; for a "
                         "whole new deck use keynote_build_deck.",
    "keynote_duplicate_slide": "Use to copy an existing slide (layout and content). For a blank slide use "
                               "keynote_add_slide.",
    "keynote_delete_slide": "Use to remove a slide for good (the last slide can't be deleted). To keep it but hide it "
                            "in the slideshow use keynote_skip_slide.",
    "keynote_move_slide": "Use to reorder slides. To copy a slide to a new position, duplicate it first with "
                          "keynote_duplicate_slide.",
    "keynote_skip_slide": "Use to hide or show a slide in the slideshow without deleting it. To remove it use "
                          "keynote_delete_slide.",
    "keynote_set_presenter_notes": "Use for speaker notes on an existing slide. For a new deck, put notes in "
                                   "keynote_build_deck's outline instead.",
    "keynote_list_themes": "Use before keynote_set_theme or keynote_build_deck to get valid theme names.",
    "keynote_inspect_style": "Use before formatting: theme, layouts, and each text item's font, size and colour. For "
                             "slide text and notes use keynote_list_slides.",
    "keynote_set_theme": "Use to switch the deck's theme only. For a full designed look (fonts, sizes, colours) use "
                         "keynote_apply_design, which can set the theme too.",
    "keynote_set_slide_layout": "Use to change one slide's layout (names from keynote_inspect_style). Not for text styling: "
                                "use keynote_format_text.",
    "keynote_format_text": "Use for one text item's font, size or colour. To restyle the whole deck consistently use "
                           "keynote_apply_design.",
    "keynote_set_transition": "Use for one slide's transition. For the same transition on every slide of a new deck, pass "
                              "transition= to keynote_build_deck.",
    "keynote_add_image": "Use to place a picture or logo on a slide. For data, use keynote_add_chart or keynote_add_table "
                         "rather than a picture of a chart.",
    "keynote_add_chart": "Use for a chart on an existing slide. In a new deck, put the chart in keynote_build_deck's "
                         "outline instead; for exact numbers use keynote_add_table.",
    "keynote_add_table": "Use for a table on an existing slide. In a new deck, put it in keynote_build_deck's outline; to "
                         "show a trend use keynote_add_chart.",
    "keynote_apply_design": "Use to restyle a whole deck from a kit. For one text item use keynote_format_text. Preview "
                            "with dry_run, then run keynote_review_deck.",
    "keynote_review_deck": "Use after building or restyling a deck, before saying it's done; fix every error. To look at "
                           "a flagged slide use keynote_slide_image; to check one word renders use iwork_verify_render.",
    "keynote_slide_image": "Use to look at a slide's real rendering, e.g. one keynote_review_deck flagged. For a quick "
                           "preview without Keynote use iwork_thumbnail (first slide, last saved state).",
    "keynote_slideshow": "Use to present the deck live; it doesn't change the file. To share it instead use iwork_export.",
    "pages_preflight": "Call once before other Pages tools. A -1712 error means a dialog in Pages needs a human; don't "
                       "retry until it's dismissed.",
    "pages_replace_all": "Use to change text everywhere while keeping formatting. To replace the whole body use "
                         "pages_set_body; for template fields use pages_fill_placeholders.",
    "pages_set_body": "Use only to replace the entire body text; it resets body formatting, so warn the user. Prefer "
                      "pages_replace_all or pages_fill_placeholders.",
    "pages_list_placeholders": "Use before pages_fill_placeholders to see the template's field tags.",
    "pages_fill_placeholders": "Use for template fields (Name, Date). It's the only write for page-layout documents like "
                               "letters and flyers, which have no body text.",
    "pages_read_tables": "Use before pages_set_table_cells to see the tables, their names and cell references.",
    "pages_set_table_cells": "Use to write into an existing Pages table. New tables can't be created in Pages; for text "
                             "outside tables use pages_replace_all.",
}
