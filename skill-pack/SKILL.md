---
name: iwork-studio
description: Use when reading, creating, or editing Apple iWork files — Numbers spreadsheets (.numbers), Keynote decks (.key), Pages documents (.pages). Triggers on any Pages/Keynote/Numbers file mention, iWork authoring request, spreadsheet cell edit, slide text change, or Pages body-text task. Routes through the verified iWork Studio library: versioned backup + atomic swap on every write, Arabic-safe round-trips, chart refusal, PDF render verification.
version: 1.0.0
author: iWork Studio
license: MIT
metadata:
  hermes:
    tags: [iwork, numbers, keynote, pages, applescript, arabic]
    related_skills: [apple-iwork-automation, apple-iwork-files]
---

# iWork Studio — verified .numbers / .key / .pages read-write

One skill pack, three verified routes, zero repair prompts. Everything below was
built and live-verified against iWork 15.4 (build 7051.0.79) on macOS 27.2,
including Arabic round-trips at file level AND render level. Evidence:
`the project repo`.

## Route matrix (follow exactly; never freelance)

| Format | Read | Write | Engine |
|--------|------|-------|--------|
| `.numbers` | full semantic model | create + per-cell edit | `numbers-parser` 4.19.0, pure Python, no GUI |
| `.key` | full text model (YAML tree) | find/replace text only | `keynote-parser` 1.14.5.0; AppleScript fallback ONLY for file locked in Keynote |
| `.pages` | body text (AppleScript + docx export) | the TWO verified body ops ONLY | AppleScript `bodyText`; richer edits = out of scope by council |

## Commands (run from this skill's directory)

All scripts auto-locate the pinned interpreter (`~/.hermes/iwork-venv/.venv/bin/python`)
and re-exec into it if started with a bare python3. Scripts print JSON results.

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
8. **Strict zip byte-equality is unachievable** (IWA protobuf re-encode, +1,632 B
   on unmodified .numbers save). GATE-1 is SEMANTIC equality — operator-pinned,
   do not re-litigate. See references/pins.txt.

## Scope walls (council-validated)

- Pages: ONLY `replace_all` and `set_body` body-text ops. Anything richer
  (styles, tables, sections, per-paragraph surgery) raises PagesOutOfScopeError.
- No pptx/docx/xlsx → iWork conversion (lossy, rejected).
- No iCloud concurrent-edit handling (local files only).

## References

- `references/capability-matrix.md` — per-route verified ops + evidence pointers
- `references/pins.txt` — dependency pins, single source of truth
- `references/sandbox-trap.md` — GATE-SAVE: the `save in` denial playbook
- `references/keynote-1700-defect.md` — the Keynote 15.4 text-property defect
- `references/tcc-preflight.md` — TCC / template-chooser / -1712 playbook

## Source of truth

Project repo: `the project repo` (specs, library source,
pytest suite, evidence logs). This installed skill = pack sources + vendored copy
of `src/iwork_studio` at install time (`skill-pack/install.sh`). Re-run install
after library changes.