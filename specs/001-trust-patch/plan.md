# Implementation Plan: Trust patch

**Branch**: `roadmap-2.7` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-trust-patch/spec.md`

## Summary

Close every gap between the "never damages your file" promise and the code: one shared
backup/safety module used by every writer (private bounded backups, legacy-aware listing,
open-document guard), per-paragraph Pages replace, a fenced deck outline, a read-back check on
the edited cell, timeout handling that leaks nothing, PyPI installs, honest docs.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: numbers-parser 4.19, keynote-parser, FastMCP; osascript (JXA) on macOS

**Storage**: files on disk; backups under `~/.iwork-studio/backups/` (override `IWORK_STUDIO_BACKUP_DIR`)

**Testing**: pytest headless suite (app stubbed) + aqua live tests on the owner's Mac

**Target Platform**: macOS (app routes); any OS for the parser routes

**Project Type**: library + MCP server + agent skill

**Performance Goals**: the open-document check adds ≤ 0.5 s per write, and only when the app is running

**Constraints**: no stdout from the server; no secrets on command lines; every change has a regression test

**Scale/Scope**: about 12 backup call sites, 7 no-app write routes, 3 app runners

## Constitution Check

| Principle | How this plan complies |
|---|---|
| I. Never damage a file | Open-document guard, bounded backups, per-paragraph replace, read-back cell check |
| II. Honest claims | dry_run exceptions documented; results report read-back values |
| III. Tests prove it | Headless tests for every fix; Pages per-paragraph replace and open guard need the owner's live check |
| IV. Agent-first | New errors are typed with hints (`DocumentOpenError`, `AutomationDeniedError`, `AppTimeoutError`) |
| V. Privacy | Backups leave synced folders; secrets never on command lines; examples use made-up names; fence covers deck inputs |
| VI. Arabic | Paragraph rewrite keeps Arabic text exact (tests with Arabic paragraphs) |

Result: PASS. No exceptions.

## Project Structure

### Documentation (this feature)

```text
specs/001-trust-patch/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
src/iwork_studio/
├── backups.py          # backup_dir_for (new location), legacy_dir_for, make_backup, prune, list/restore both dirs
├── safety.py           # NEW: assert_not_open(path), AutomationDeniedError, AppTimeoutError, run_osascript (stdin script, timeout)
├── numbers_io.py       # edit_cell read-back; use backups.make_backup + safety guard
├── numbers_format.py   # guard + shared backups
├── numbers_structure.py# guard + shared backups
├── keynote_io.py       # guard + shared backups
├── keynote_slides.py / keynote_theme.py / keynote_table.py / app_ops.py / pages_io.py / exporter.py
│                       # shared backups; timeouts via safety; exporter script on stdin
├── pages_io.py         # replace_all per paragraph
├── mcp_server.py       # deck outline fencing; instructions name non-dry_run writes; new hints
└── installer.py        # PyPI source pinned to __version__
install.sh, README.md, AGENTS.md, CHANGELOG.md, skill-pack docs
tests/test_trust_patch.py   # NEW: regression tests for every requirement
```

**Structure Decision**: Keep the existing module layout. Add one small `safety.py` and grow
`backups.py` into the single owner of backup location, naming and pruning, so the bug can't
recur in one module only.

## Design notes

- **Backup location**: `backup_dir_for(target)` → `<root>/<name>-<sha1(resolved path)[:10]>/`,
  where `<root>` is `$IWORK_STUDIO_BACKUP_DIR` or `~/.iwork-studio/backups`. File names are
  unchanged (`<name>.<YYYYMMDD-HHMMSS>[.N].<ext>`). `legacy_dir_for(target)` is
  `<file>.backups`. Listing merges both; restore looks a name up in both and keeps the
  "must be a backup of this file" rule. Pruning matches `^<name>\.\d{8}-\d{6}(\.\d+)?<ext>$`
  and only touches the new folder.
- **Open guard**: on macOS only. A JXA call checks `Application(app).running()` first, which
  doesn't launch the app; if it's running, the call compares every open document's file path
  with the target. An error code of -1743 raises `AutomationDeniedError`. The guard runs inside
  `make_backup()` (every write takes a backup first, before it opens anything), so no route can
  miss it. App routes call it before they open the document.
- **Pages replace**: one JXA call reads paragraphs, rewrites only those whose text contains
  `find` (`doc.bodyText.paragraphs[i] = new`), saves, and returns the indexes it rewrote. The
  check re-reads the body and compares it with the expected full text, and also checks that the
  paragraph count is unchanged.
- **Timeouts**: `safety.run_osascript(script, params, timeout)` passes the script on stdin and
  the params as the one argv JSON with no secrets. Exporter params carry the password on stdin
  inside the script payload, never in argv. `TimeoutExpired` is turned into `AppTimeoutError`
  ("<App> didn't answer within N s; nothing was changed") followed by a best-effort close of
  that path without saving.
- **Deck fence**: `mcp_server` walks the outline before the call. It resolves `image`,
  `chart.from` and `table.from` against the deck's folder, applies `_fenced`, and substitutes
  the absolute paths.

## Complexity Tracking

None.
