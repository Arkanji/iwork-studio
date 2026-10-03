<div align="center">

<img src="assets/banner.svg" alt="iWork Studio — read and edit Apple Numbers, Keynote and Pages with Python" width="100%">

[![CI](https://github.com/Arkanji/iwork-studio/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-2.0.0-1a7f79)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![iWork](https://img.shields.io/badge/iWork-classic%20%2B%20Creator%20Studio-black?logo=apple&logoColor=white)](#what-it-can-do)
[![MCP server](https://img.shields.io/badge/MCP-49%20tools-8A2BE2)](#all-49-tools)
[![Arabic safe](https://img.shields.io/badge/Arabic%2FRTL-exact%20round--trips-informational)](#arabic--rtl)
[![Undo](https://img.shields.io/badge/every%20write-backed%20up%20%2B%20undoable-success)](#the-safety-model)

### Give your AI the keys to Apple iWork.

Create, edit, format, theme and export **Numbers**, **Keynote** and **Pages** files from Claude or any AI agent.<br>
Every write is backed up, checked and swapped in atomically, and any change can be undone with one call.

[**Install**](#install) · [What it can do](#what-it-can-do) · [Safety](#the-safety-model) · [All 49 tools](#all-49-tools) · [For AI agents](#for-ai-agents) · [Changelog](CHANGELOG.md)

<br>

<a href="https://arkanji.com/images/posts/iwork-studio-film-v3.mp4">
  <img src="assets/iwork-studio-film.webp" alt="iWork Studio in action: an AI agent edits a Numbers cell and keeps its formula, updates every Keynote slide without touching the formatting, and writes an Arabic letter in Pages" width="100%">
</a>

<sub>▶ <a href="https://arkanji.com/images/posts/iwork-studio-film-v3.mp4"><b>Watch the film with sound</b></a> (46s) · <a href="https://arkanji.com/posts/iwork-studio-launch/">Read the launch story</a></sub>

</div>

---

## Install

| Your app | Do this |
|---|---|
| **Claude desktop app** (Mac) | Paste in Terminal: `curl -LsSf https://raw.githubusercontent.com/Arkanji/iwork-studio/main/install.sh \| sh`, then quit Claude (Cmd-Q) and reopen |
| **Claude Code** | `claude mcp add iwork-studio -- uvx --from git+https://github.com/Arkanji/iwork-studio iwork-studio-mcp` |
| **Cursor, VS Code, Codex, any MCP client** | `uvx --from git+https://github.com/Arkanji/iwork-studio iwork-studio-mcp config`, then paste the printed JSON into the client's MCP settings |

That's it. The installer sets up [`uv`](https://docs.astral.sh/uv/) if needed, and uv brings its own Python.

- **Fence it** (recommended): `… | sh -s -- --roots ~/Documents ~/Desktop` limits it to those folders. Other clients: set `IWORK_STUDIO_ROOTS` (`:`-separated).
- **First run:** macOS asks once whether Claude may control Keynote / Pages / Numbers. Click **OK**. (Missed it? System Settings → Privacy & Security → Automation.)
- **Check it:** ask *"what can iwork-studio do on this Mac?"*.
- **Remove:** `uvx --from git+https://github.com/Arkanji/iwork-studio iwork-studio-mcp uninstall`

> **AI agent setting this up for someone?** Pick the row for their app, run it, then call `iwork_capabilities`. Rules for using the tools are in [`AGENTS.md`](AGENTS.md).

## Just ask, in English or Arabic

> *"Turn sales.csv into a Numbers file, make the header bold on a teal fill, show column B as SAR with two decimals, and add a total row."*
>
> *"In pitch.key, switch to the Gradient theme, make the title on slide 1 white at 60 pt, add a dissolve between every slide, and put logo.png on the last slide."*
>
> *"Duplicate slide 3, move the copy to the front and add presenter notes: ملاحظات المتحدث"*
>
> *"Fill the Name and Date fields in offer-letter.pages, then export it as a password-protected PDF."*
>
> *"Find my Keynote decks from this week and export each one to PowerPoint."*
>
> *"Undo the last change to budget.numbers."*

## What it can do

| | **Numbers** | **Keynote** | **Pages** |
|---|---|---|---|
| **Read** | Every sheet, table, cell, formula and format | Every slide's text, notes, layout, theme and styling | Body text and placeholders |
| **Create** | From data or CSV ⚡ · from a built-in template · from your own file | From a built-in theme · from your own deck | From a built-in template · from your own file |
| **Edit content** | Cells ⚡ · formulas · insert/delete rows and columns ⚡ · add tables and sheets ⚡ · sort | Find/replace across the deck ⚡ · add, duplicate, delete, move, hide slides · presenter notes · images | Replace text everywhere · replace the body · fill placeholders |
| **Format** | Fonts, colours, fill, alignment, wrap ⚡ · currency, %, dates, decimals ⚡ · borders ⚡ · widths and heights ⚡ · headers ⚡ · merges ⚡ | Theme · slide layout · text font, size and colour · transitions | — |
| **Export** | PDF · Excel · CSV | PDF · PowerPoint · images · movie | PDF · Word · EPUB · text · RTF |
| **Present** | | Start, stop, next, previous | |

⚡ = works anywhere, no app needed (pure Python). Everything else drives the real app on a Mac with a logged-in session, classic iWork or the Creator Studio apps.

**Every file type:** look up metadata, pull the preview thumbnail, find files with Spotlight, check that a word is visibly rendered, check the rendered font/size/colour, list backups and undo.

### What it won't do

On purpose, so it never breaks a file:

- **Files with charts** are refused for writes. A text change can silently corrupt chart data.
- **Pages** is limited to text: replace, set body and placeholders (page-layout documents, like most letter templates, only take placeholders). There is no Pages file format parser anywhere, so it doesn't fake one.
- **Formulas and row shifts**: in a table that has formulas, rows and columns can only be appended without the app. Inserting in the middle would leave references pointing at the wrong cells.
- **Not scriptable by Apple**, so not offered: Numbers table styles, Keynote shape fill and text alignment, editing a theme's master slides. Page margins and page setup are planned.

## The safety model

An iWork app will happily say "saved" about a file it just broke. Nothing here trusts "saved".

```
backup → change a scratch copy → re-open it and compare → atomic swap
                       ↘ anything off: your file is untouched, the error says why
```

- **Backup first**, versioned, next to the file in `<file>.backups/`.
- **Re-read and compared**: exactly the requested change happened, and nothing else did. A cell edit checks every other cell. A row insert checks every cell at its new position. A slide op checks every other slide. A sort checks it's a pure reorder. An export is read back with a second, independent tool.
- **Atomic swap**: the file is replaced in one step, so a crash can't leave half a file.
- **The app's "ok" is never trusted.** App-driven writes are re-read from disk, and a write that "succeeded" but didn't land is rolled back.
- **Undo is one call**: `iwork_list_backups` → `iwork_restore_backup`. The restore backs up the current version first, so undo can be undone too.
- **New files never overwrite** an existing one.
- **Refuse, don't mangle.** The worst case is a clear "no", never a broken file.

## Arabic & RTL

- Arabic text round-trips exactly in all three apps, including presenter notes and Pages placeholders.
- Values are kept as typed: Arabic-Indic digits (`١٢٣`), `"$1,234.56"` and `=…` text stay text. Pass a real number when you want a number.
- When checking a rendered PDF, assert **one** Arabic word. PDF text layers reorder multi-word RTL text.

## All 49 tools

Writes are marked destructive and reads read-only, so clients can ask before writing.

<details open>
<summary><b>Any file</b> (13)</summary>

| Tool | What it does |
|---|---|
| `iwork_capabilities` | What this machine can do: apps, GUI session, which routes work |
| `iwork_read` | Any `.numbers` / `.key` / `.pages` → JSON |
| `iwork_find` | Find iWork files by kind and name (Spotlight on a Mac) |
| `iwork_metadata` · `iwork_thumbnail` | Template, app builds, format version, slide count · the stored preview image |
| `iwork_create` · `iwork_create_from_template` | New file from Apple's built-in templates · copy of your own file |
| `iwork_list_templates` | Built-in templates (Numbers, Pages) and themes (Keynote) |
| `iwork_export` | PDF, Excel, CSV, Word, EPUB, text, RTF, PowerPoint, slide images, movie; optional password |
| `iwork_verify_render` · `iwork_verify_format` | Rendered PDF shows this text · with this font, size, colour, page size |
| `iwork_list_backups` · `iwork_restore_backup` | Undo |

</details>

<details>
<summary><b>Numbers</b> (15)</summary>

| Tool | What it does |
|---|---|
| `numbers_create` · `numbers_import_csv` | New file from rows of data · from a CSV/TSV |
| `numbers_edit_cell` | Set one cell |
| `numbers_set_formula` | Put a formula in a cell; Numbers computes it |
| `numbers_insert` · `numbers_delete` | Rows or columns, anywhere |
| `numbers_add_table` | New table on a sheet, or on a new sheet |
| `numbers_sort` | Sort body rows by a column |
| `numbers_inspect_format` | Widths, heights, headers, merges, and every cell's style, number format and borders |
| `numbers_set_cell_style` | Font, size, bold/italic/underline/strike, colours, fill, alignment, wrap |
| `numbers_set_number_format` | Number, currency (any ISO code), %, scientific, fraction, date, text; decimals, separators, negatives |
| `numbers_set_borders` | All / outline / inner / one side; width, colour, style |
| `numbers_set_dimensions` · `numbers_set_headers` · `numbers_merge_cells` | Column widths and row heights · header rows/columns · merges |

</details>

<details>
<summary><b>Keynote</b> (16)</summary>

| Tool | What it does |
|---|---|
| `keynote_replace_text` | Find/replace on every slide, formatting untouched |
| `keynote_list_slides` | Every slide's text, notes and hidden state |
| `keynote_add_slide` · `keynote_duplicate_slide` · `keynote_delete_slide` · `keynote_move_slide` · `keynote_skip_slide` | Slide operations |
| `keynote_set_presenter_notes` | Presenter notes |
| `keynote_list_themes` · `keynote_inspect_style` | Available themes · a deck's theme, layouts and text styling |
| `keynote_set_theme` · `keynote_set_slide_layout` · `keynote_format_text` | Theme · one slide's layout · one text item's font, size, colour |
| `keynote_set_transition` | Effect, duration, delay, auto-advance |
| `keynote_add_image` | Place an image on a slide |
| `keynote_slideshow` | Start, stop, next, previous |

</details>

<details>
<summary><b>Pages</b> (5)</summary>

| Tool | What it does |
|---|---|
| `pages_preflight` | Checks Pages can answer (run once first) |
| `pages_replace_all` · `pages_set_body` | Replace text everywhere · replace the whole body (resets its formatting) |
| `pages_list_placeholders` · `pages_fill_placeholders` | Template fields like Name and Date |

</details>

Keynote slide, theme, transition and image tools refuse a deck that's open in Keynote (they never close a window that may hold unsaved work). To hide them all: `IWORK_STUDIO_DISABLE_SLIDE_OPS=1`.

## For AI agents

- **[`AGENTS.md`](AGENTS.md)**: setup and usage rules for any agent (Codex, Cursor, Copilot, Gemini; Claude Code reads it via `CLAUDE.md`).
- **MCP instructions**: the server sends its rules on connect, so the model has them even without this repo.
- **Skill**: [`skill-pack/SKILL.md`](skill-pack/SKILL.md), auto-discovered by Claude Code in this repo, or `bash skill-pack/install.sh` for other skill-based agents. It includes CLI scripts with JSON output for agents without MCP.
- **[`llms.txt`](llms.txt)**: a short machine-readable summary.

**The contract:** JSON in, JSON out. Errors are typed and say what to tell the user: `ChartRefusalError`, `DocumentOpenError`, `PagesOutOfScopeError`, `AquaSessionError` (no Mac GUI here) and so on. Don't retry a refused write with a trick.

## Python

```bash
pip install git+https://github.com/Arkanji/iwork-studio      # Python 3.12
```

```python
from iwork_studio import numbers_structure, numbers_format, numbers_io, keynote_io, keynote_slides, exporter, backups

numbers_structure.import_csv("sales.csv", "sales.numbers")
numbers_format.set_cell_style("sales.numbers", "A1:D1", bold=True, fill_color="#1A7F79", font_color="#FFFFFF")
numbers_format.set_number_format("sales.numbers", "B2:B99", "currency", currency_code="SAR", decimal_places=2)
numbers_io.edit_cell("sales.numbers", "B2", 2500)
keynote_io.edit_text("pitch.key", "2025", "2026")
keynote_slides.set_presenter_notes("pitch.key", 1, "ملاحظات")          # macOS + Keynote
exporter.export("pitch.key", "pptx")                                     # macOS + Keynote
backups.restore_backup("sales.numbers", backups.list_backups("sales.numbers")[0]["name"])
```

<details>
<summary><b>Traps we mapped so your agent doesn't hit them</b></summary>

1. **`save in <path>` is denied by the iWork sandbox.** In-place `save` and `export` work. → [`sandbox-trap.md`](skill-pack/references/sandbox-trap.md)
2. **Keynote's slide `title`/`body` properties throw `-1700`.** Use the text item's `object text`. → [`keynote-1700-defect.md`](skill-pack/references/keynote-1700-defect.md)
3. **Chart files corrupt quietly** when their text is edited, so writes refuse them.
4. **Byte-equal saves don't exist** in iWork's format. The real bar is semantic: it reopens, and the full model matches.
5. **First-run permission and template-chooser dialogs** block every script call. A preflight turns the hang into one clear prompt. → [`tcc-preflight.md`](skill-pack/references/tcc-preflight.md)
6. **"Creator Studio" apps have different names.** A hardcoded `Application("Numbers")` drives the wrong app; names are resolved per call. → [`apps.py`](src/iwork_studio/apps.py)
7. **stdout is the MCP wire.** Import-time warnings from libraries would corrupt it, so they go to stderr.
8. **Keynote's JavaScript insert and move are broken**; AppleScript `make new slide` and `move slide … to before slide …` work.
9. **Keynote master slides can't be reached from JavaScript** (`-1700`); layouts go through AppleScript.
10. **numbers-parser doesn't save in-place style edits.** Styles are registered first, then applied.
11. **numbers-parser stored 12 as 12.000000000000002.** Decimals are now encoded exactly.
12. **numbers-parser doesn't update formula references when rows move**, so mid-table inserts in formula tables are refused.
13. **Keynote colours are 0–65535 per channel**, not 0–255 or 0–1.
14. **Pages page-layout documents have no body text** (`bodyText()` is null), and most letter and flyer templates are page layout. Placeholders are filled and checked across every text box instead.
15. **Don't keep the repo in iCloud Drive.** Sync creates "main 2" copies inside `.git`.

More, each with its status: [`jxa-traps.md`](skill-pack/references/jxa-traps.md) (including traps borrowed from [reichenbach/iwork_mcp](https://github.com/reichenbach/iwork_mcp)).

</details>

<details>
<summary><b>How it's built</b></summary>

```
pure Python file parsers (headless, deterministic)  →  .numbers everything, .key text
the real app via AppleScript / JXA                   →  .key slides & theming, .pages, formulas, sort, export, render checks
MCP server · CLI scripts · skill                     →  thin wrappers over the same library and the same safety model
```

```
src/iwork_studio/   numbers_io · numbers_format · numbers_structure · keynote_io · keynote_slides · keynote_theme
                    pages_io · app_ops · exporter · helpers · format_check · render_verify · backups · apps · mcp_server
skill-pack/         SKILL.md · CLI scripts · references (capabilities, traps, pins)
tests/              headless suite (CI) · `pytest -m aqua` = live suite for a Mac with iWork
install.sh          one-line setup for the Claude desktop app
```

</details>

## Contributing

```bash
git clone https://github.com/Arkanji/iwork-studio.git && cd iwork-studio
uv run --extra test pytest -m "not aqua"      # headless suite, what CI runs
uv run --extra test pytest -m aqua            # live suite: a Mac with Numbers, Keynote and Pages
```

iWork changes between releases. If something breaks, check the [capabilities](skill-pack/references/capability-matrix.md) and [traps](skill-pack/references/jxa-traps.md), run the live suite, and pin what changed. New write routes must follow the safety model and come with tests that prove the rollback. Clone outside iCloud-synced folders.

## License

[MIT](LICENSE), traps included. Take them.
