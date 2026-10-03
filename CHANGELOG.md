# Changelog

Versions follow [semantic versioning](https://semver.org). Every write in every
version follows the same safety model: backup → scratch copy → re-read and
compare → atomic swap.

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
