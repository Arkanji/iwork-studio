# AGENTS.md — iWork Studio

Instructions for any AI agent (Claude Code, Codex, Cursor, Copilot, Gemini, …)
working **with** or **on** this repo.

## Using it: edit iWork files for a user

iWork Studio reads and edits Apple **Numbers (`.numbers`)**, **Keynote (`.key`)**
and **Pages (`.pages`)** files. Use it whenever a request touches one of those.

**Pick your interface, in this order:**

1. **MCP tools** (names start with `iwork_`, `numbers_`, `keynote_`, `pages_`).
   This repo ships [`.mcp.json`](.mcp.json); elsewhere install with
   `claude mcp add iwork-studio -- uvx --from git+https://github.com/arkanji/iwork-studio iwork-studio-mcp`
   (any MCP client: command `uvx`, args `--from git+https://github.com/arkanji/iwork-studio iwork-studio-mcp`).
2. **Skill** — [`skill-pack/SKILL.md`](skill-pack/SKILL.md) (also at
   `.claude/skills/iwork-studio/`): CLI scripts with JSON output.
3. **Python** — `pip install -e .`, then `iwork_studio.numbers_io`, `keynote_io`,
   `keynote_slides`, `pages_io`, `backups`.

**What each route needs**

| Task | Tools | Needs |
|---|---|---|
| Read / edit `.numbers` cells | `iwork_read`, `numbers_edit_cell` | Python only — works anywhere |
| Read / find-replace `.key` text | `iwork_read`, `keynote_replace_text` | Python only — works anywhere |
| Keynote slides: add, duplicate, delete, move, hide, presenter notes | `keynote_*_slide`, `keynote_set_presenter_notes` | macOS + Keynote + logged-in GUI session |
| Pages body text | `pages_preflight`, `pages_replace_all`, `pages_set_body` | macOS + Pages + GUI session |
| Check the rendered result | `iwork_verify_render` | macOS + the app + GUI session |
| Undo any write | `iwork_list_backups`, `iwork_restore_backup` | works anywhere |

**Rules — follow them, don't work around them**

- **Every write is backed up, checked and atomic.** If a tool errors, the file is
  untouched. Report the error to the user; do not retry with tricks.
- **Start with `iwork_capabilities`** when unsure what the machine can do.
  `AquaSessionError` = no macOS GUI here: say so, don't retry.
- **Charts are refused** (`ChartRefusalError`). Tell the user; never bypass.
- **Pages has exactly two writes**: `pages_replace_all`, `pages_set_body`
  (`set_body` resets body formatting — warn the user). Anything richer is out of
  scope (`PagesOutOfScopeError`). Run `pages_preflight` first; a
  `PagesUnavailableError` / -1712 means a human must dismiss a dialog once.
- **Keynote slide ops** refuse a deck open in Keynote (`DocumentOpenError`): ask
  the user to save and close it. Slide numbers are 1-based. The last slide can't
  be deleted.
- **Arabic/RTL**: text round-trips exactly. For `iwork_verify_render`, assert ONE
  Arabic word — multi-word RTL extracts reordered and fails falsely.
- **Never** convert to docx/pptx/xlsx and back (lossy), and never AppleScript
  `save in <path>` (sandbox denies it; in-place save + export only).
- After an important write, offer `iwork_verify_render`; after a mistake, offer
  `iwork_restore_backup`.

## Working on it: change this codebase

- Python 3.12. `uv run --extra test pytest -m "not aqua"` = the headless suite
  (what CI runs). `pytest -m aqua` + `scripts/probe_keynote_slides.py` = the live lane;
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
