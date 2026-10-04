# iWork scripting traps — imported catalog

Source: [reichenbach/iwork_mcp](https://github.com/reichenbach/iwork_mcp) (MIT),
`CLAUDE.md` "Critical JXA Bugs", tested there on iWork **14.5** and **15.1.1
Creator Studio**. Facts only, no code copied.

**Status legend**
- `UPSTREAM` — reported upstream, **not yet verified on our pin (15.4)**. Treat
  it as a strong hint, not evidence. A probe that confirms or refutes it moves
  it to one of the statuses below.
- `AGREES` — consistent with our own committed evidence (pointer given).
- `N/A` — does not affect any route iWork Studio offers today. Kept for when
  a route is added.

Rule (same as the capability matrix): a trap here never *enables* anything.
New routes still need a probe and evidence first.

## Cross-app

| # | Trap | Status | Notes |
|---|---|---|---|
| X1 | Export format strings: use `"PDF"`, not `"Numbers PDF"` / `"Keynote PDF"` / `"Pages PDF"` (the latter throw -1700) | AGREES | Our render routes already use `as: 'PDF'` (C7, D4) |
| X2 | Colours: **Numbers** takes 0–65535 ints (hex × 257); **Keynote and Pages** text colour takes 0–1 floats. Pages *reads* back 0–1 floats even after an int write | UPSTREAM | Relevant to any future formatting route |
| X3 | Fonts must be PostScript names (`HelveticaNeue-Bold`), never display names (`Helvetica Neue Bold` → -10000) | UPSTREAM | Arabic fonts too: e.g. `IBMPlexSansArabic-Bold` |
| X4 | JXA object refs can't be compared with `===`; `sheets().indexOf(sheet)` returns -1. Match by name | UPSTREAM | |
| X5 | Creator Studio bundles are separate apps (`"Numbers Creator Studio"`); `Application("Numbers")` drives the wrong app | AGREES (design) | Handled by `iwork_studio/apps.py`: classic preferred, Creator Studio refused until probed |
| X6 | Creator Studio 15.1–15.1.1: `doc.save()` hangs on a modal; `app.export()` fails with error 6 for every format | UPSTREAM | This is why `apps.py` refuses Creator Studio by default: both calls are load-bearing for us |
| X7 | Creator Studio auto-save renames docs (`"Untitled"` → `"Untitled.numbers"`), breaking `documents.byName()` | N/A | We address docs by the object `app.open()` returns, never by name |

## Numbers

| # | Trap | Status | Notes |
|---|---|---|---|
| N1 | `table.ranges["B2:C3"]` is broken in JXA ("Invalid index"). Iterate cells instead | N/A | Our Numbers route is numbers-parser, not JXA |
| N2 | Writing `"$1,234.56"` auto-converts to the number 1234.56; set `cell.format = "text"` first to keep a string | UPSTREAM | **App route only.** numbers-parser writes the type you pass. Watch for this if an app-driven Numbers write is ever added |
| N3 | Cell `format` value is `"percent"`, not `"percentage"`. Valid: automatic, number, currency, percent, fraction, scientific, text, checkbox, star rating | UPSTREAM | |
| N4 | Minimum table is 2×2: `Table({columnCount: 1})` throws -10000 | UPSTREAM | |
| N5 | New sheets auto-create "Table 1" | UPSTREAM | |
| N6 | Can't merge across header/non-header boundaries; zero the header counts first | UPSTREAM | |
| N7 | `rows.push()` always appends; inserting at the top needs a manual shift | UPSTREAM | |
| N8 | JXA can't bind data to charts; chart creation needs AppleScript (via `NSAppleScript`) on a selection | UPSTREAM | Input for the chart-files Big Bet, not for today |

## Keynote

| # | Trap | Status | Notes |
|---|---|---|---|
| K1 | `masterSlides()` / `.byName()` / `.name()` throw -1700 in JXA; use AppleScript via `NSAppleScript` | AGREES | Same -1700 family as our `title`/`body` defect ([keynote-1700-defect.md](keynote-1700-defect.md)). Slide ops avoid master slides entirely |
| K2 | Text colours are 0–1 floats (unlike Numbers) | UPSTREAM | See X2 |
| K3 | `shape.position = [x, y]` silently fails (reads back 0,0); use `{x: x, y: y}` | UPSTREAM | |
| K4 | No JXA API to set `shapeType`; fill/border colours not exposed | UPSTREAM | |
| K5 | A deck can't lose its last slide (`delete` fails) | AGREES (design) | `keynote_slides.delete_slide` refuses this before any backup |
| K6 | `doc.save({in: …})` fails -1728 from a different `osascript` process than the one that opened the doc | AGREES | Same family as our sandbox `save in` trap ([sandbox-trap.md](sandbox-trap.md)); we only ever save in place, in one process |
| K7 | Slide ops used upstream: `app.duplicate(slide)`, `app.delete(slide)`, `app.move(slide, {to: slide})`, `slide.skipped = bool`, `slide.presenterNotes = str` | UPSTREAM | Implemented in `keynote_slides.py` behind the probe gate. `move` semantics (before vs after target) **unknown**; the expectation gate catches either way |

## Pages

| # | Trap | Status | Notes |
|---|---|---|---|
| P1 | `doc.paragraphs` is completely broken (14.5); `doc.bodyText` (plain string) works | AGREES | Our D-phase reads/writes use `bodyText` |
| P2 | Per-paragraph access works via `doc.bodyText.paragraphs[i]`; properties are `font` / `size` / `color` only (no `bold`/`italic`; use a PostScript bold font) | UPSTREAM | Input for the Pages Big Bet |
| P3 | Setting `doc.bodyText = "…"` destroys ALL formatting; `bodyText.paragraphs[i] = "…"` preserves the other paragraphs' formatting | AGREES (partly) | Explains why our `set_body` resets formatting. The per-paragraph form is the Big Bet candidate |
| P4 | A paragraph containing `\n` becomes several real paragraphs; index bookkeeping must count them | UPSTREAM | |
| P5 | Tables are invisible to JXA (-2763 `TMAScriptTableInfoProxy`) but fully exposed to AppleScript: read, write cells (`=` → formula), resize | HANDLED | `pages_read_tables` / `pages_set_table_cells` use AppleScript on a JXA-opened document, bulk-reading `value/formatted value/formula of every cell` |
| P6 | 15.x: table *creation* broken in both JXA and AppleScript (-2763); upstream falls back to menu clicks via System Events (needs Accessibility) | UPSTREAM | UI scripting is out of our safety model; do not adopt |
| P7 | Paragraph styles (Title, Heading 1, …), alignment, indent, line spacing are not in the scripting dictionary | UPSTREAM | A hard wall: no route can offer these |
| P8 | Synthetic keystrokes are silently blocked while any app has secure keyboard entry (e.g. a focused password field) | UPSTREAM | Another reason to never rely on UI scripting |

## Silent success (found in a fork: lodgvideon/iwork_mcp, Sep 2026)

The scripting bridge can say "ok" for writes that did nothing. Never trust a
returned ok; re-read from disk. Every case below is a headless regression test
(`tests/test_keynote_slides.py::TestSilentSuccess`).

| # | Trap | Status | Notes |
|---|---|---|---|
| S1 | An ObjC `nil` is truthy in JXA: `if (!executeAndReturnError(...))` never fires, so every NSAppleScript failure reads as success | UPSTREAM | We don't use the NSAppleScript bridge; if added, check the error ref, not the return value |
| S2 | Keynote accepts writes to non-existent properties without error (e.g. `textAlignment`) | UPSTREAM | Covered: slide-op readback + expectation gate rolls back |
| S3 | Keynote `duplicate` can silently copy into another open document | UPSTREAM | Covered: count/order check; we also refuse decks already open in Keynote |
| S4 | Positions passed in a shape/image constructor are ignored (lands at 0,0); colour written 0–1 into a 0–65535 property → near-black | UPSTREAM | No such route today; any future one needs readback of the property |
| S5 | `add_slide` with an after-position silently drops the requested master slide | UPSTREAM | We don't offer master choice (-1700 family) |
| S6 | UI scripting by menu **title** fails (-1728) on non-English macOS — Arabic Macs included. Use AXIdentifier, or better, no UI scripting | UPSTREAM | We never click menus |
| S7 | Numbers app auto-parses `"$1,234.56"` and locale decimals into numbers | N/A (parser route) | `tests/test_value_fidelity.py`: strings, Arabic-Indic digits, `=…` text stay verbatim |
| S8 | Creator Studio auto-save drafts pile up until saves time out | UPSTREAM | Reason Creator Studio stays refused by default |
| S9 | Pages 15.x: `make new image` constructor gone (TMAScriptImageInfoProxy); table creation -2763 | UPSTREAM | Neither offered; Pages tables (existing) = Big Bet candidate |

## Creator Studio specifics (Keynote / Pages / Numbers 15.3)

| # | Trap | Status | Notes |
|---|---|---|---|
| L1 | In-place open → save → close of an on-disk deck works (upstream's "save hangs" not reproduced for Keynote) | CONFIRMED | |
| L2 | JXA `doc.slides.splice(i, 0, app.Slide({}))` fails: `-10002 Invalid key form` | CONFIRMED | add uses AppleScript `make new slide at end of slides` + `move` |
| L3 | JXA `app.move(slide, {to: slide})` produced a result the gate rejected | CONFIRMED | move uses AppleScript `move slide n to before/after slide t` |
| L4 | Text-item order inside a slide is not a stable identity — it changes across slide reorders and after filling a new slide's placeholders (an index read in one session can point at another box in the next) | HANDLED | slide signatures compare text as a multiset; deck building and design kits pick title/body boxes by position inside the writing session and verify by position |
| L5 | A repo inside an iCloud-synced folder (Desktop/Documents) gets "name 2" conflict copies inside `.git` → `fatal: bad object refs/heads/main 2` | CONFIRMED | keep clones in a non-synced folder, e.g. `~/Developer` |
| L6 | Numbers Creator Studio: AppleScript `open` + `delay` + `front document` + `export … as PDF` timed out (90 s) | CONFIRMED | replaced by JXA `export(doc_from_open, {as:'PDF'})` |
| L7 | Pages Creator Studio: in-place save + PDF export work (upstream's 15.1.1 "save hangs / export error 6" not reproduced) | CONFIRMED | |
| L8 | Keynote text colour (`objectText.color`) takes 0–65535 per channel; 0–1 floats (as some tools write) give near-black | CONFIRMED | `keynote_format_text` writes 0–65535 and reads the colour back |
| L9 | numbers-parser: assigning attributes on `cell.style` in place is accepted but silently not saved | CONFIRMED | styles are applied by deriving a registered style; readback catches any silent drop |
| L10 | Pages (Creator Studio) refuses AppleScript `open (POSIX file …)` for files outside its sandbox — a "can't be opened right now. Operation not permitted" dialog, and `open` returns `missing value` | CONFIRMED | open with JXA `app.open(Path(…))` (granted access), then have AppleScript find that open document by its exact file path — never `front document` |
| L11 | Pages page-layout documents (most letter/flyer templates) have no body text: `bodyText()` is null | CONFIRMED | body ops refuse them with a clear error; placeholders are checked across every text box |
| L12 | numbers-parser calls `sigfig.round(..., warn=False)`, which runs a global `filterwarnings("ignore")` then `resetwarnings()`: every warning filter in the process is wiped on save | CONFIRMED | `numbers_io` wraps it in a scoped `catch_warnings()`; a test checks filters survive a save |
| L13 | A new slide's text-item list repeats each placeholder box (title and body appear twice, same geometry), and also holds small footer boxes; so "top-most" or "largest other box" picks the wrong box. `slide.defaultTitleItem()` / `defaultBodyItem()` work (read and write) on Keynote Creator Studio | CONFIRMED | deck building and design kits write and verify through the default title/body boxes; fallback is by type size with duplicates ignored |
| L14 | Keynote tables: `tell slide n to make new table with properties {row count, column count, header row count}` works; `make new table at end of tables of slide n` and `delete` on a table fail with `-10000` (AppleEvent handler failed). One AppleScript verb Keynote lacks (`add row below`) fails the whole script at compile time | CONFIRMED | `keynote_add_table` uses the working form and never deletes: a failed add restores the backup. JXA reads cells (`rows()[r].cells()[c].value()`, `fontName`, `textColor`, `backgroundColor`, `alignment`) for verification |
| L15 | Keynote, like Pages, refuses AppleScript `open` on a temp path it hasn't been granted ("can't be opened right now. Operation not permitted"); a JXA `open` of that path first grants it for the session | CONFIRMED | every Keynote op reads the deck with JXA before any AppleScript step |
