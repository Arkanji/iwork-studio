---
name: iwork-studio
description: Read and edit Apple iWork files safely — Numbers (.numbers), Keynote (.key), Pages (.pages). Use for any request that mentions a Numbers, Keynote or Pages file, a spreadsheet cell, slide text, slides (add, duplicate, delete, move, hide), presenter notes, or Pages body text, including Arabic/RTL content. Prefer the iwork-studio MCP tools when available; otherwise use the bundled scripts. Every write is backed up, verified and atomic, and can be undone.
license: MIT
metadata:
  version: 1.1.0
  author: iWork Studio
  homepage: https://github.com/arkanji/iwork-studio
  tags: [iwork, numbers, keynote, pages, mcp, applescript, arabic, rtl]
---

# iWork Studio — verified .numbers / .key / .pages read-write

One skill pack, three verified routes, zero repair prompts. Everything below was
built and live-verified against iWork 15.4 (build 7051.0.79) on macOS 27.2,
including Arabic round-trips at file level AND render level.

## Route matrix (follow exactly; never freelance)

| Format | Read | Write | Engine |
|--------|------|-------|--------|
| `.numbers` | full semantic model | create + per-cell edit | `numbers-parser` 4.19.0, pure Python, no GUI |
| `.key` | full text model (YAML tree) | find/replace text | `keynote-parser` 1.14.5.0; AppleScript fallback ONLY for file locked in Keynote |
| `.key` slides | per-slide inventory | add / duplicate / delete / move / skip / presenter notes | AppleScript via Keynote (`iwork_studio.keynote_slides`), per-slide expectation gate + rollback |
| `.pages` | body text (AppleScript + docx export) | the TWO verified body ops ONLY | AppleScript `bodyText`; richer edits = out of scope by design |

## Pick your interface (in this order)

1. **iwork-studio MCP tools are available** (tool names start with `iwork_`,
   `numbers_`, `keynote_`, `pages_`) → use them. Call `iwork_capabilities`
   first if unsure what this machine can do.
2. **No MCP, but you can run shell commands** → the scripts in the
   Commands section below (JSON on stdout).
3. **Writing Python** → `pip install -e <repo>` and import `iwork_studio`
   (`numbers_io`, `keynote_io`, `keynote_slides`, `pages_io`, `backups`).

What needs what: `.numbers` and `.key` text reads/edits are pure Python and
work anywhere. Pages, render-verify and Keynote slide ops drive the real app:
macOS + iWork + a logged-in GUI session. Elsewhere they fail fast with
`AquaSessionError` — tell the user, don't retry.

## MCP server


```bash
claude mcp add iwork-studio -- uvx --from git+https://github.com/arkanji/iwork-studio iwork-studio-mcp
```

Tools: `iwork_capabilities`, `iwork_read`, `numbers_edit_cell`,
`keynote_replace_text`, `pages_preflight`, `pages_replace_all`,
`pages_set_body`, `iwork_verify_render`, `iwork_list_backups`,
`iwork_restore_backup`, plus the Keynote slide ops `keynote_add_slide`,
`keynote_duplicate_slide`, `keynote_delete_slide`, `keynote_move_slide`,
`keynote_skip_slide`, `keynote_set_presenter_notes`. Same library, same gates
as the scripts below. Slide ops are ON (off switch:
IWORK_STUDIO_DISABLE_SLIDE_OPS=1); they refuse a deck open in Keynote, never
delete the last slide, and roll back if Keynote does anything unexpected.

## Commands (run from this skill's directory)

Run with a Python 3.12 that has the package installed (`pip install -e <repo>`).
If a pinned venv exists at `~/.hermes/iwork-venv/.venv`, the scripts re-exec
into it automatically. Scripts print JSON results.

```bash
# READ any iWork file (dispatches on extension)
python scripts/read.py <file.numbers|.key|.pages>

# NUMBERS: read / edit a cell / create demo file (self-test)
python scripts/edit_numbers.py read <file>
python scripts/edit_numbers.py edit-cell <file> --ref B3 --value "قيمة" [--sheet NAME] [--table NAME]
python scripts/edit_numbers.py demo --out /tmp/demo.numbers

# KEYNOTE: read / find-replace across the deck
python scripts/edit_key.py read <file.key>
python scripts/edit_key.py replace <file.key> "old text" "new text" [--regex]

# PAGES: TCC preflight / read / the two verified body ops
python scripts/edit_pages.py preflight
python scripts/edit_pages.py read <file.pages>
python scripts/edit_pages.py replace-all <file.pages> "old" "new"
python scripts/edit_pages.py set-body <file.pages> "full new body text"   # or '-' to read stdin

# RENDER VERIFY any format (needs Aqua): export PDF -> PyMuPDF text-layer match
python scripts/verify_render.py <file> --assert-text "expected visible text" [--pages N]
```

Keynote slide ops and undo (Python; the MCP tools wrap exactly these):

```python
from iwork_studio import keynote_slides as ks, backups
ks.set_presenter_notes("deck.key", 1, "ملاحظات")   # 1-based slide numbers
ks.duplicate_slide("deck.key", 2); ks.move_slide("deck.key", 3, 1)
ks.add_slide("deck.key", after=0); ks.set_skipped("deck.key", 4, True); ks.delete_slide("deck.key", 5)
backups.restore_backup("deck.key", backups.list_backups("deck.key")[0]["name"])   # undo last write
```

## Hard rules (every job)

1. **GATE-SAVE**: NEVER AppleScript `save in <arbitrary path>` — iWork sandbox denies
   it (verified denial). In-place `save` of an on-disk file is verified working for
   Numbers, Keynote, Pages. For artifacts, always `export ... as ...`, never save.
   Helpers: `scripts/save_paths.sh` (source it).
2. **Keynote -1700 defect**: slide `title`/`body` properties throw -1700 on
   Keynote 15.4. Use `object text of Nth text item` (see
   references/keynote-1700-defect.md). The library already handles this.
3. **Preflight before ANY Pages op** (`edit_pages.py preflight`): first-launch TCC
   consent and the Pages template-chooser/Open dialog block ALL AppleEvents with
   -1712. That means "a human must look at the screen ONCE" — never retry, never
   loop. See references/tcc-preflight.md.
4. **GATE-CHART**: the writers REFUSE chart-container files (.numbers/.key) until a
   probe proves them. Accepted scope cut — do not bypass.
5. **Headless = hard fail**: all AppleScript routes require an interactive Aqua
   session. Without one they raise `AquaSessionError` with guidance — by design (SC4).
6. **Every write** already does: versioned backup → tmp write → re-parse verify →
   atomic swap (os.replace) → optional render-verify. On any gate failure the
   target rolls back untouched. "File saved" is never proof — re-read to confirm.
7. **Arabic**: round-trips are verified byte-exact at file level and ligature-aware
   at render level ('الاسم' extracts from PDF text layers as 'ااسمل' — lam-alef
   split + bidi, an extraction artifact the matcher tolerates, not a defect).
   For render-verify assertions use SINGLE Arabic words — bidi reorders words in
   extracted text layers, so multi-word Arabic fragments fail spuriously.
8. **Creator Studio**: Keynote Creator Studio is supported (live-tested on
   15.3.1). If only Numbers/Pages Creator Studio is installed, those routes raise
   `CreatorStudioUnverifiedError` (upstream: save hangs, export fails). Never set
   IWORK_STUDIO_ALLOW_CREATOR_STUDIO=1 except to probe.
9. **Strict zip byte-equality is unachievable** (IWA protobuf re-encode, +1,632 B
   on unmodified .numbers save). GATE-1 is SEMANTIC equality — pinned,
   do not re-litigate. See references/pins.txt.

## Scope walls (by design)

- Pages: ONLY `replace_all` and `set_body` body-text ops. Anything richer
  (styles, tables, sections, per-paragraph surgery) raises PagesOutOfScopeError.
- No pptx/docx/xlsx → iWork conversion (lossy, rejected).
- No iCloud concurrent-edit handling (local files only).

## References

- `references/capability-matrix.md` — per-route verified ops
- `references/pins.txt` — dependency pins, single source of truth
- `references/sandbox-trap.md` — GATE-SAVE: the `save in` denial playbook
- `references/keynote-1700-defect.md` — the Keynote 15.4 text-property defect
- `references/tcc-preflight.md` — TCC / template-chooser / -1712 playbook
- `references/jxa-traps.md` — ~25 upstream scripting traps (reichenbach/iwork_mcp), each marked UPSTREAM / AGREES / N/A
- Undo: `iwork_studio.backups.list_backups(path)` / `restore_backup(path, name)`

## Source of truth

Project repo: https://github.com/arkanji/iwork-studio (library source, pytest
suite, fixtures). This installed skill = pack sources + vendored copy
of `src/iwork_studio` at install time (`skill-pack/install.sh`). Re-run install
after library changes.