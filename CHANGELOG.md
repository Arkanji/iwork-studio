# Changelog

Versions follow [semantic versioning](https://semver.org). Every write in every
version follows the same safety model: backup → scratch copy → re-read and
compare → atomic swap.

## 2.4.0

Data to deck, on brand.

- **Chart and table slides:** a slide in `keynote_build_deck` can carry a chart or a table, from data or straight from a Numbers table (the header row gives the columns, the first column the rows; pick columns by name, cap the rows). Everything is validated before the deck is created.
- **Tables on Keynote slides:** `keynote_add_table` adds a table, styled from a design kit: header band, Arabic-aware fonts, banding, numbers right-aligned. Every cell's value, font and colours are read back; text Keynote would turn into a number rolls back with a hint. Every other Keynote write now checks that no table changed.
- **Your brand kit:** `iwork_extract_design_kit` reads the fonts (Latin and Arabic) and colours from a deck or table that already has your look; `iwork_save_design_kit` / `iwork_delete_design_kit` keep kits by name, usable anywhere a kit goes. Contrast is still checked; presets can't be shadowed; nothing is replaced without `overwrite`.
- **Design review:** `keynote_review_deck` renders the deck through Keynote and compares every drawn line with its text box. Errors: text off the slide or past the bottom of its box. Warnings: text Keynote had to shrink to fit, overlapping boxes, text under 18 pt, crowded slides, long titles. `keynote_slide_image` returns a slide as an image so an agent can look at it.
- **Prompts:** *Pitch deck from an outline*, *Report deck from a Numbers table*, *Restyle with my brand*, *Make this table look designed* — ready-made workflows in clients that show MCP prompts.
- **Claude Code plugin:** the repo is a plugin marketplace (`/plugin marketplace add Arkanji/iwork-studio`); the plugin brings the MCP server and the skill together. Every tool now has a title, the extension and plugin carry an icon, and there's a privacy policy (`PRIVACY.md`: everything stays on your Mac).
- **Fixed:** `iwork_export` slide images with `image_format` failed in Keynote (`-1700`); slides now export in Keynote's format and are converted with macOS `sips`.
- **Live runs:** `scripts/live.sh` runs the Mac suite unattended, so it can run on a schedule; `scripts/probe_keynote_tables.py` maps what Keynote's table scripting can do.

## 2.3.0

Reach + decks: designed documents, previews, one-click install.

- **Build a deck from an outline:** `keynote_build_deck` makes a new deck from a theme and a list of slides (title, bullets, notes, image, layout), with an optional transition and design kit. Every slide is read back; a mismatch removes the new file. `keynote_set_slide_text` fills an existing slide's title and body.
- **Design kits:** six kits (executive, banking, classic, teal, analytics, midnight) — a Latin + Arabic font pair bundled with macOS, a WCAG-checked palette and a type scale. `keynote_apply_design` and `numbers_apply_design` restyle a deck or a table; custom brand kits are contrast-checked. A design guide tells agents how to write slides and tables that look designed.
- **Dry run everywhere:** every write that changes an existing file takes `dry_run=true` — the real change on a throwaway copy, with every check, returning exactly what would change.
- **Install anywhere:** packaged for PyPI (`pip install iwork-studio`), listed for the MCP Registry, and shipped as a one-click Claude Desktop extension (`.mcpb`, with a folder picker). Releases publish automatically from a tag.
- **Unattended live runs:** `scripts/live.sh` runs the Mac test suite, logs it, and quits the iWork apps the run opened (never an app with your documents).
- `iwork_capabilities` describes the current routes.
- **PDF checks now use pdfminer.six (MIT)** instead of PyMuPDF (AGPL), so the whole package is permissively licensed. Arabic text layers are normalised (NFKC), so shaped letters and the lam-alef ligature match plain text.

## 2.2.0

Pages tables, Arabic direction, formula safety.

- **Pages tables:** `pages_read_tables` reads every table (values, shown text, formulas, dates); `pages_set_table_cells` writes text, numbers and formulas into an existing table. Every other cell, every table's size and the body text are checked; text that Pages would silently turn into a number is caught and rolled back. New tables can't be created (Pages 15 doesn't script it).
- **Arabic paragraph direction in Pages:** replace-all rolls back if a right-to-left paragraph flips to left-to-right. Pages writes new paragraphs left-to-right, even Arabic ones (not scriptable), so set-body flags them.
- **Formula safety:** a save that breaks a formula (`#REF!`) is refused, and formulas made in Numbers survive every no-app write.
- **`numbers_recalculate`:** Numbers doesn't recalculate when it opens a file changed without it, so totals kept their old results. No-app edits on files with formulas now say so (`formulas_need_recalc`), this tool has Numbers recompute every formula, and `numbers_set_formula` recalculates first so its result is current.
- The harmless "unsupported version" warning from numbers-parser is silenced. Along the way: numbers-parser's rounding helper (sigfig) wiped every warning filter in the process on each save; it's now wrapped so it can't.

## 2.1.0

Charts.

- **`keynote_add_chart`**: add a bar, stacked bar, horizontal bar, line, area, pie or scatter chart (2D or 3D) to a slide from data. Checked: one new chart on that slide, nothing else changed.
- **App-driven tools now work on files with charts.** Keynote slide ops, theming, transitions and images, and Numbers formulas and sort, used to refuse them. The app makes the change and keeps its charts linked; every slide's (or sheet's) chart count is checked before and after, and any difference rolls back.
- The tools that work without the app still refuse files with charts: their rewrite can break a chart's link to its data.
- Numbers and Pages charts can't be created: Apple doesn't make them scriptable.

## 2.0.0

The "do the whole job" release: create, structure, format, theme, present and
export, not just edit text. 49 MCP tools (was 16).

### Numbers
- **Create** a file from rows of data (`numbers_create`) or a CSV/TSV (`numbers_import_csv`); plain numbers become numbers, everything else stays text exactly as written.
- **Structure:** insert/delete rows and columns anywhere (`numbers_insert`, `numbers_delete`), add tables and sheets (`numbers_add_table`). Every existing cell is checked at its new position.
- **Formulas and sorting** through the Numbers app (`numbers_set_formula`, `numbers_sort`).
- **Formatting:** cell style, number formats (currency with any ISO code, %, dates, decimals, negatives), borders, column widths and row heights, header rows/columns, merges, plus `numbers_inspect_format` to read it all back.
- Numbers are now stored exactly: numbers-parser wrote 12 as 12.000000000000002; decimals are encoded and decoded exactly.

### Keynote
- **Theming:** list themes, inspect a deck's styling, change the theme, change a slide's layout, set a text item's font, size and colour.
- **Transitions** (`keynote_set_transition`), **images** (`keynote_add_image`) and **slideshow control** (`keynote_slideshow`).
- `keynote_list_slides`: every slide's text, notes and hidden state.

### Pages
- **Placeholders:** `pages_list_placeholders`, `pages_fill_placeholders` (template fields such as Name and Date), alongside replace-all and set-body. Works on page-layout documents too; the body and every text box are checked.
- Page-layout documents (no body text) now get a clear error from replace-all / set-body instead of a script crash.

### Every file type
- **Export** (`iwork_export`): PDF, Excel, CSV, Word, EPUB, text, RTF, PowerPoint, slide images, movie; optional password. Each export is read back with a second tool and compared with the source, and the source is checked unchanged.
- **New documents** from Apple's built-in templates (`iwork_create`) or from your own file (`iwork_create_from_template`). Never overwrites.
- **Helpers:** `iwork_find` (Spotlight), `iwork_metadata`, `iwork_thumbnail`, `iwork_list_templates`.
- **Format check:** `iwork_verify_format` confirms the rendered font, size, colour, bold and page size.

### Changed
- Pages now has three writes: replace all, set body, fill placeholders.
- README rewritten; tool reference grouped by app.

## 1.1.0

- **MCP server** (`iwork-studio-mcp`) with read-only / destructive hints and a clean protocol stream.
- **One-line install** for the Claude desktop app (`install.sh`), Claude Code, and any MCP client (`iwork-studio-mcp config`); optional folder fence.
- **Undo:** `iwork_list_backups`, `iwork_restore_backup`.
- **Keynote slide ops:** add, duplicate, delete, move, hide, presenter notes, each checked slide by slide and rolled back on any mismatch.
- **Creator Studio** versions of Numbers, Keynote and Pages supported; app names resolved per call.
- `AGENTS.md`, `CLAUDE.md`, `llms.txt` and a skill any agent can pick up.

## 1.0.0

- Numbers: read the full model, edit cells (pure Python).
- Keynote: read slides and text, find/replace across the deck (pure Python).
- Pages: read body text, replace all, set body (through Pages).
- Render check: export a PDF through the app and confirm the text is visible.
- Chart files refused for writes; Arabic/RTL round-trips exactly.
