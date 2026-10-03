---
name: iwork-studio
description: Create, read, edit, design and export Apple iWork files safely — build designed Keynote decks from an outline, style tables with design kits, in Numbers (.numbers), Keynote (.key), Pages (.pages). Use for any request that mentions a Numbers, Keynote or Pages file; spreadsheet cells, formulas, rows, tables, CSV import, cell formatting or currency; slides (add, duplicate, delete, move, hide), themes, layouts, fonts, transitions, images, presenter notes, slideshows; Pages text, template placeholders or tables; or exporting to PDF, Excel, Word, PowerPoint — including Arabic/RTL content and Arabic requests (كينوت، نمبرز، بيجز، شريحة، عرض تقديمي، جدول، تنسيق). Prefer the iwork-studio MCP tools when available; otherwise use the bundled scripts. Every write is backed up, verified and atomic, and can be undone.
license: MIT
metadata:
  version: 2.3.0
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
2. **Confirm destructive or broad changes** in one line before doing them (or
   show a preview: every write takes `dry_run=true` and returns what would change):
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
| What this machine can do | `iwork_capabilities` | anywhere — call it first when unsure |
| Read any iWork file to JSON · find files · metadata · thumbnail | `iwork_read` · `iwork_find` · `iwork_metadata` · `iwork_thumbnail` | anywhere (.pages read needs the Mac app) |
| New Numbers file from data / from a CSV | `numbers_create` · `numbers_import_csv` | anywhere |
| New file from Apple's templates / from the user's own file | `iwork_list_templates` + `iwork_create` · `iwork_create_from_template` | Mac + the app · anywhere |
| Set one Numbers cell (`ref` like `B2`, optional `sheet`/`table`) | `numbers_edit_cell` | anywhere |
| Insert/delete rows or columns · add a table or sheet | `numbers_insert` · `numbers_delete` · `numbers_add_table` | anywhere |
| Formula in a cell · recalculate formulas · sort a table | `numbers_set_formula` · `numbers_recalculate` · `numbers_sort` | Mac + Numbers, file closed |
| See / set Numbers formatting: style · number format · borders · widths/heights · headers · merge | `numbers_inspect_format` · `numbers_set_cell_style` · `numbers_set_number_format` · `numbers_set_borders` · `numbers_set_dimensions` · `numbers_set_headers` · `numbers_merge_cells` | anywhere |
| Find/replace text on every slide (literal; `regex=true` for patterns) | `keynote_replace_text` | anywhere |
| Build a designed deck from an outline · fill a slide's title/bullets | `keynote_build_deck` (with `kit=`) · `keynote_set_slide_text` | Mac + Keynote |
| Make a deck or table look designed | `iwork_list_design_kits` · `keynote_apply_design` · `numbers_apply_design` | Keynote: Mac · Numbers: anywhere |
| List slides · notes · hide/show · duplicate · delete · move · add | `keynote_list_slides` · `keynote_set_presenter_notes` · `keynote_skip_slide` · `keynote_duplicate_slide` · `keynote_delete_slide` · `keynote_move_slide` · `keynote_add_slide` | Mac + Keynote, deck closed |
| Theme · layout · text font/size/colour · transition · image · chart | `keynote_list_themes` · `keynote_inspect_style` · `keynote_set_theme` · `keynote_set_slide_layout` · `keynote_format_text` · `keynote_set_transition` · `keynote_add_image` · `keynote_add_chart` | Mac + Keynote, deck closed |
| Present (start/stop/next/previous) | `keynote_slideshow` | Mac + Keynote |
| Pages: replace text · replace the whole body · fill template fields · table cells | `pages_replace_all` · `pages_set_body` · `pages_list_placeholders` + `pages_fill_placeholders` · `pages_read_tables` + `pages_set_table_cells` | Mac + Pages; run `pages_preflight` first |
| Export: PDF, xlsx, csv, docx, epub, txt, rtf, pptx, slide images, movie | `iwork_export` | Mac + the app |
| Check the rendered PDF shows a word · uses a font/size/colour | `iwork_verify_render` · `iwork_verify_format` | Mac + the app |
| Undo | `iwork_list_backups` · `iwork_restore_backup` | anywhere |

Formatting tips: inspect first; ranges are `A1` or `A1:D9`; colours are `#RRGGBB`;
only the attributes you pass change. Merges are refused if they'd hide data. Numbers
has no scriptable table styles; Pages margins/page setup/paragraph styles and
Keynote shape fill/text alignment are not exposed — say so, don't improvise.

Building a spreadsheet: `numbers_create` (or `numbers_import_csv`) → format the
header with `numbers_set_cell_style` → `numbers_set_number_format` for money/% →
`numbers_set_dimensions` → `numbers_set_formula` for totals (Mac). After no-app edits
to a file with formulas (the result says `formulas_need_recalc`), run `numbers_recalculate`:
Numbers otherwise keeps showing the old totals. New files are
never overwritten. In a table with formulas, rows/columns can only be appended
headlessly.

Slide numbers are 1-based. `keynote_move_slide(slide, to)` puts the slide *at*
position `to`. `keynote_add_slide(after=0)` adds at the front, no `after` adds at
the end. The last slide can't be deleted.

## When a tool says no

| Error | What it means | Tell the user |
|---|---|---|
| `DocumentOpenError` | The deck is open in Keynote | "Please save and close it in Keynote, then I'll retry." |
| `ChartRefusalError` | The file has charts, and this tool works without the app (its rewrite could break chart links) | Say so plainly; app-driven tools still work on it. Don't look for a workaround |
| `PagesOutOfScopeError` | Pages only supports its text and table-cell operations — or the document is page layout (most letter/flyer templates), which has no body text | Offer `pages_replace_all` / `pages_set_body` / `pages_fill_placeholders` if they fit; page-layout documents only take placeholders |
| `StructureError` / `AppOpError` / `FormatError` / `ThemeError` | The request itself is invalid (exists already, out of range, unknown name) | Fix the request from the message; it lists the valid choices |
| `WriteVerificationError` / `EditVerificationError` | The result didn't match the request; rolled back | Nothing changed; report it |
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
- Numbers keeps values as typed (CSV import too): Arabic-Indic digits (`١٢٣`) and strings like
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

- `references/design-guide.md` — how to make decks and tables look designed (read before building a deck)
- `references/capability-matrix.md` — what each route supports and refuses
- `references/jxa-traps.md` — scripting traps, if you are extending this
- `references/sandbox-trap.md`, `references/keynote-1700-defect.md`, `references/tcc-preflight.md` — background on specific macOS/iWork behaviour
