# AGENTS.md — iWork Studio

Instructions for any AI agent (Claude Code, Codex, Cursor, Copilot, Gemini, …)
working **with** or **on** this repo.

## Setting this up for a user? (do this first)

| User's app | Command |
|---|---|
| Claude desktop app (Mac) | `curl -LsSf https://raw.githubusercontent.com/Arkanji/iwork-studio/main/install.sh \| sh`, then the user quits Claude (Cmd-Q) and reopens |
| Claude Code (plugin: tools + skill) | `claude plugin marketplace add Arkanji/iwork-studio` then `claude plugin install iwork-studio@iwork-studio` |
| Claude Code (tools only) | `claude mcp add iwork-studio -- uvx --from git+https://github.com/Arkanji/iwork-studio iwork-studio-mcp` |
| Any other MCP client | `uvx --from git+https://github.com/Arkanji/iwork-studio iwork-studio-mcp config` → paste the printed JSON into the client's MCP config |

- The installer installs `uv` if missing; uv brings its own Python. **Don't tell the user to install Python.**
- Recommend a folder fence: `… | sh -s -- --roots ~/Documents ~/Desktop` (or env `IWORK_STUDIO_ROOTS`, `:`-separated).
- If the user only needs some apps, load fewer tools: env `IWORK_STUDIO_TOOLSETS` = any of `files`, `numbers`, `keynote`, `pages`, `design` (comma-separated; default all). `iwork_capabilities` shows what's loaded.
- The desktop app needs the **absolute** uvx path in its config; the installer and `config` handle that. Never hand-write a bare `"command": "uvx"` for the desktop app.
- `.mcp.json` in this repo is for contributors working inside a clone; don't copy it elsewhere.
- First run: macOS asks once to let Claude control Keynote/Pages/Numbers → user clicks OK (fix later in System Settings → Privacy & Security → Automation). Logs: `~/Library/Logs/Claude/mcp-server-iwork-studio.log`.
- Verify: call `iwork_capabilities`.

## Using it: edit iWork files for a user

iWork Studio creates, reads, edits, formats, themes and exports Apple
**Numbers (`.numbers`)**, **Keynote (`.key`)** and **Pages (`.pages`)** files.
Use it whenever a request touches one of those.

**Pick your interface, in this order:**

1. **MCP tools** (names start with `iwork_`, `numbers_`, `keynote_`, `pages_`) — install
   as in the table above.
2. **Skill** — [`skill-pack/SKILL.md`](skill-pack/SKILL.md) (also at
   `.claude/skills/iwork-studio/`): CLI scripts with JSON output.
3. **Python** — `pip install -e .`, then `iwork_studio.numbers_io`, `numbers_format`,
   `numbers_structure`, `keynote_io`, `keynote_slides`, `keynote_theme`, `keynote_deck`,
   `design`, `preview`, `pages_io`, `app_ops`, `exporter`, `helpers`, `backups`.

**What each route needs**

| Task | Tools | Needs |
|---|---|---|
| Read any file · find files · metadata · thumbnail | `iwork_read`, `iwork_find`, `iwork_metadata`, `iwork_thumbnail` | Python only (`.pages` read needs the app) |
| Create `.numbers` from data / CSV · insert/delete rows & columns · add tables | `numbers_create`, `numbers_import_csv`, `numbers_insert`, `numbers_delete`, `numbers_add_table` | Python only |
| Edit / format `.numbers` (cells, style, number format, borders, sizes, headers, merge) | `numbers_edit_cell`, `numbers_inspect_format`, `numbers_set_*`, `numbers_merge_cells` | Python only |
| Formulas · recalculate · sort | `numbers_set_formula`, `numbers_recalculate`, `numbers_sort` | macOS + Numbers + GUI session |
| Find/replace `.key` text | `keynote_replace_text` | Python only |
| Keynote slides: add, duplicate, delete, move, hide, notes, images, charts, tables, transitions | `keynote_list_slides`, `keynote_*_slide`, `keynote_set_presenter_notes`, `keynote_add_image`, `keynote_add_chart`, `keynote_add_table`, `keynote_set_transition` | macOS + Keynote + GUI session |
| Build a deck from an outline (with chart and table slides, from data or a Numbers table) · slide titles/bullets | `keynote_build_deck`, `keynote_set_slide_text` | macOS + Keynote + GUI session |
| Check a deck's design as rendered · look at a slide | `keynote_review_deck`, `keynote_slide_image` | macOS + Keynote + GUI session |
| Keynote theming: theme, layout, text font/size/colour | `keynote_list_themes`, `keynote_inspect_style`, `keynote_set_theme`, `keynote_set_slide_layout`, `keynote_format_text` | macOS + Keynote + GUI session |
| Design kits: designed decks and tables | `iwork_list_design_kits`, `keynote_apply_design`, `numbers_apply_design` | Keynote: macOS + Keynote · Numbers: Python only |
| The user's brand kit: from their own file, saved by name | `iwork_extract_design_kit`, `iwork_save_design_kit`, `iwork_delete_design_kit` | from `.numbers` or saving: Python only · from `.key`: macOS + Keynote |
| Present | `keynote_slideshow` | macOS + Keynote + GUI session |
| Pages text and tables | `pages_preflight`, `pages_replace_all`, `pages_set_body`, `pages_list_placeholders`, `pages_fill_placeholders`, `pages_read_tables`, `pages_set_table_cells` | macOS + Pages + GUI session |
| New file from Apple's templates · from the user's own file | `iwork_list_templates`, `iwork_create` · `iwork_create_from_template` | the app · Python only |
| Export (PDF, xlsx, csv, docx, epub, pptx, images, movie…) | `iwork_export` | macOS + the app |
| Check the rendered result | `iwork_verify_render`, `iwork_verify_format` | macOS + the app + GUI session |
| Undo any write | `iwork_list_backups`, `iwork_restore_backup` | works anywhere |

**Rules — follow them, don't work around them**

- **Every write is backed up, checked and atomic.** If a tool errors, the file is
  untouched. Report the error to the user; do not retry with tricks.
- **Start with `iwork_capabilities`** when unsure what the machine can do.
  `AquaSessionError` = no macOS GUI here: say so, don't retry.
- **Charts**: the no-app routes refuse files with charts (`ChartRefusalError`); the
  app-driven routes work on them and check every chart is kept. Add Keynote
  charts with `keynote_add_chart`; Numbers/Pages charts can't be created. Never
  bypass a refusal.
- **Pages has four writes**: `pages_replace_all`, `pages_set_body`
  (resets body formatting — warn the user), `pages_fill_placeholders` and
  `pages_set_table_cells` (existing tables only; new tables can't be created).
  Anything richer is out of scope (`PagesOutOfScopeError`). Run
  `pages_preflight` first; a `PagesUnavailableError` / -1712 means a human must
  dismiss a dialog once. Page-layout documents (most letter/flyer templates)
  have no body text: only `pages_fill_placeholders` applies to them.
- **Preview broad changes**: every write on an existing file takes `dry_run=true`
  (real change on a throwaway copy, returns what would change). Use it before
  restyling, deleting or replacing widely, and show the user.
- **Make it look designed**: use a design kit (the user's saved brand kit if they have one) and follow
  [`skill-pack/references/design-guide.md`](skill-pack/references/design-guide.md)
  (one idea per slide, titles state the takeaway, right-aligned numbers; numbers go in
  chart or table slides, not bullets).
- **Check before you say done**: after building or restyling a deck, run
  `keynote_review_deck`, fix every error (shorten text or split the slide), and look at a
  slide with `keynote_slide_image`.
- **New files never overwrite.** Pick a new name if the tool says it exists.
- **Stale totals**: Numbers doesn't recalculate on open. When a no-app edit
  returns `formulas_need_recalc`, run `numbers_recalculate` (Mac) or tell the user.
- **Formula tables**: rows/columns can only be appended headlessly
  (`StructureError` otherwise); suggest doing mid-table inserts in Numbers.
- **Keynote slide/theme/image/transition ops** refuse a deck open in Keynote (`DocumentOpenError`): ask
  the user to save and close it. Slide numbers are 1-based. The last slide can't
  be deleted. Keynote tables can be added but not deleted (Keynote refuses);
  a failed add is undone from the backup.
- **Arabic/RTL**: text round-trips exactly. For `iwork_verify_render`, assert ONE
  Arabic word — multi-word RTL extracts reordered and fails falsely.
- **Never** convert to docx/pptx/xlsx and back (lossy), and never AppleScript
  `save in <path>` (sandbox denies it; in-place save + export only).
- After an important write, offer `iwork_verify_render`; after a mistake, offer
  `iwork_restore_backup`.

## Working on it: change this codebase

- Python 3.12. `uv run --extra test pytest -m "not aqua"` = the headless suite
  (what CI runs, with `ruff check src tests scripts`). `pytest -m aqua` (or `scripts/live.sh`, unattended: logs and quits
  the apps it opened) + `scripts/probe_keynote_slides.py` = the live lane;
  needs a Mac with iWork (classic or Creator Studio). Clone
  outside iCloud-synced folders.
- Dependency pins: `pyproject.toml` must equal `skill-pack/references/pins.txt`
  (a test enforces it).
- Every new write route must ride the write protocol: versioned backup → change
  a scratch copy → re-read + compare → atomic `os.replace` → rollback on failure.
  Add headless tests that stub the app and prove the rollback.
- `src/iwork_studio/mcp_server.py` must never print to stdout (it is the MCP
  wire); a test fails if anything does.
- Known scripting traps: [`skill-pack/references/jxa-traps.md`](skill-pack/references/jxa-traps.md),
  [`capability-matrix.md`](skill-pack/references/capability-matrix.md).
- Keep personal data out of the repo: no hostnames, home paths, names or
  machine logs. Live-probe output stays in `~/.iwork-studio/probes/`.
