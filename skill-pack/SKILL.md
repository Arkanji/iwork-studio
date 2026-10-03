---
name: iwork-studio
description: Read and edit Apple iWork files safely — Numbers (.numbers), Keynote (.key), Pages (.pages). Use for any request that mentions a Numbers, Keynote or Pages file, a spreadsheet cell, slide text, slides (add, duplicate, delete, move, hide), presenter notes, or Pages body text, including Arabic/RTL content and Arabic requests (كينوت، نمبرز، بيجز، شريحة، عرض تقديمي، جدول). Prefer the iwork-studio MCP tools when available; otherwise use the bundled scripts. Every write is backed up, verified and atomic, and can be undone.
license: MIT
metadata:
  version: 1.2.0
  author: iWork Studio
  homepage: https://github.com/Arkanji/iwork-studio
  tags: [iwork, numbers, keynote, pages, mcp, applescript, arabic, rtl]
---

# iWork Studio

Safe reads and edits of Numbers, Keynote and Pages files. Every write is backed
up first, applied to a scratch copy, re-read and checked, then swapped in
atomically. If anything doesn't match, the user's file is left untouched and
you get a typed error. Arabic/RTL text round-trips exactly.

## How to work (every request)

1. **Read before you write.** `iwork_read` the file and use what's actually there
   (real slide numbers, cell refs, exact text to replace).
2. **Confirm destructive or broad changes** in one line before doing them:
   deleting slides, `pages_set_body` (it resets the body's formatting), or a
   find/replace that hits many places.
3. **Write with one tool call per change.** Don't retry a failed write with a
   different trick; report the error (see the table below).
4. **Tell the user what changed** and that a backup exists. After an important
   change, offer `iwork_verify_render` (macOS) to confirm it's visibly there.
5. **Mistake? Undo** with `iwork_list_backups` → `iwork_restore_backup`.

## What you can do

| Task | MCP tool | Needs |
|---|---|---|
| Read any iWork file to JSON | `iwork_read` | anywhere (.pages needs the Mac app) |
| What this machine can do | `iwork_capabilities` | anywhere — call it first when unsure |
| Set one Numbers cell (`ref` like `B2`, optional `sheet`/`table`) | `numbers_edit_cell` | anywhere, no app needed |
| See a Numbers table's formatting | `numbers_inspect_format` | anywhere |
| Format Numbers: style · number format · borders · widths/heights · headers · merge | `numbers_set_cell_style` · `numbers_set_number_format` · `numbers_set_borders` · `numbers_set_dimensions` · `numbers_set_headers` · `numbers_merge_cells` | anywhere, no app needed |
| Check rendered font/size/colour/page size | `iwork_verify_format` | Mac + the app |
| Find/replace text on every slide (literal; `regex=true` for patterns) | `keynote_replace_text` | anywhere, no app needed |
| Presenter notes · hide/show · duplicate · delete · move · add slide | `keynote_set_presenter_notes` · `keynote_skip_slide` · `keynote_duplicate_slide` · `keynote_delete_slide` · `keynote_move_slide` · `keynote_add_slide` | Mac + Keynote, deck closed |
| Keynote theming: list themes · inspect styling · change theme · slide layout · text font/size/colour | `keynote_list_themes` · `keynote_inspect_style` · `keynote_set_theme` · `keynote_set_slide_layout` · `keynote_format_text` | Mac + Keynote, deck closed |
| Pages: replace text everywhere / replace the whole body | `pages_replace_all` · `pages_set_body` | Mac + Pages; run `pages_preflight` first |
| Check the rendered PDF shows a word | `iwork_verify_render` | Mac + the app |
| Undo | `iwork_list_backups` · `iwork_restore_backup` | anywhere |

Formatting tips: inspect first; ranges are `A1` or `A1:D9`; colours are `#RRGGBB`;
only the attributes you pass change. Merges are refused if they'd hide data. Numbers
has no scriptable table styles; Pages margins/page setup/paragraph styles and
Keynote shape fill/text alignment are not exposed by Apple — say so, don't improvise.

Slide numbers are 1-based. `keynote_move_slide(slide, to)` puts the slide *at*
position `to`. `keynote_add_slide(after=0)` adds at the front, no `after` adds at
the end. The last slide can't be deleted.

## When a tool says no

| Error | What it means | Tell the user |
|---|---|---|
| `DocumentOpenError` | The deck is open in Keynote | "Please save and close it in Keynote, then I'll retry." |
| `ChartRefusalError` | The file contains charts; writes are refused by design | Say so plainly; don't look for a workaround |
| `PagesOutOfScopeError` | Pages only supports the two text operations | Offer `pages_replace_all` / `pages_set_body` if they fit |
| `PagesUnavailableError` / -1712 | A dialog in Pages is blocking | "Please click away the dialog in Pages once." Don't loop |
| `AquaSessionError` | No Mac GUI here | The app-driven part can't run on this machine |
| `FileLockedError` | File locked or open | Ask the user to close it |
| `SlideOpVerificationError` / `SchemaDriftError` | The app did something other than asked; rolled back | Nothing changed; report it |
| `CreatorStudioUnverifiedError` | An unknown Creator Studio app version | Report it; don't set the override yourself |
| "outside IWORK_STUDIO_ROOTS" | The file is outside the folders the user allowed | Ask them to move it or widen the fence |

## Arabic / RTL

- Write Arabic exactly as given; it round-trips byte-exact.
- For `iwork_verify_render`, assert **one Arabic word**, not a phrase: PDF text
  layers reorder multi-word RTL text and the check would fail falsely.
- Numbers keeps values as typed: Arabic-Indic digits (`١٢٣`) and strings like
  `"$1,234.56"` stay text. Pass a real number (e.g. `2500`) when the user wants a number.

## Never

- Convert to docx/pptx/xlsx and back (lossy).
- Use AppleScript `save in <path>` on the user's files (the iWork sandbox denies it).
- Edit the files directly or with other tools while bypassing these routes.

## Install (if the tools aren't available yet)

- Claude desktop app (Mac): `curl -LsSf https://raw.githubusercontent.com/Arkanji/iwork-studio/main/install.sh | sh`, then quit Claude (Cmd-Q) and reopen.
- Claude Code: `claude mcp add iwork-studio -- uvx --from git+https://github.com/Arkanji/iwork-studio iwork-studio-mcp`
- Other MCP clients: `uvx --from git+https://github.com/Arkanji/iwork-studio iwork-studio-mcp config` prints the JSON entry.

No Python install needed; uv brings its own.

## No MCP? Use the scripts

Run from this skill's folder. Prefixing with `uvx --from git+https://github.com/Arkanji/iwork-studio`
needs no prior install (or use a Python 3.12 with the package installed). Output is JSON.

```bash
U="uvx --from git+https://github.com/Arkanji/iwork-studio"
$U python scripts/read.py <file.numbers|.key|.pages>
$U python scripts/edit_numbers.py edit-cell <file> --ref B3 --value "قيمة" [--sheet NAME] [--table NAME]
$U python scripts/edit_key.py replace <file.key> "old text" "new text" [--regex]
$U python scripts/edit_pages.py preflight
$U python scripts/edit_pages.py replace-all <file.pages> "old" "new"
$U python scripts/edit_pages.py set-body <file.pages> "new body"      # or '-' for stdin
$U python scripts/verify_render.py <file> --assert-text "word"
```

Slide ops and undo from Python (the MCP tools wrap exactly these):

```python
from iwork_studio import keynote_slides as ks, backups
ks.set_presenter_notes("deck.key", 1, "ملاحظات")
ks.duplicate_slide("deck.key", 2); ks.move_slide("deck.key", 3, 1)
ks.add_slide("deck.key", after=0); ks.set_skipped("deck.key", 4, True); ks.delete_slide("deck.key", 5)
backups.restore_backup("deck.key", backups.list_backups("deck.key")[0]["name"])
```

## References

- `references/capability-matrix.md` — what each route supports and refuses
- `references/jxa-traps.md` — scripting traps, if you are extending this
- `references/sandbox-trap.md`, `references/keynote-1700-defect.md`, `references/tcc-preflight.md` — background on specific macOS/iWork behaviour
