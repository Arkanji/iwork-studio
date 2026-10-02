# iWork scripting traps — imported catalog

Source: [reichenbach/iwork_mcp](https://github.com/reichenbach/iwork_mcp) (MIT),
`CLAUDE.md` "Critical JXA Bugs", tested there on iWork **14.5** and **15.1.1
Creator Studio**. Imported 2026-10-02. Facts only, no code copied.

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
| P5 | Tables are invisible to JXA (-2763 `TMAScriptTableInfoProxy`) but fully exposed to AppleScript: read, write cells (`=` → formula), resize | UPSTREAM | Input for the Pages Big Bet |
| P6 | 15.x: table *creation* broken in both JXA and AppleScript (-2763); upstream falls back to menu clicks via System Events (needs Accessibility) | UPSTREAM | UI scripting is out of our safety model; do not adopt |
| P7 | Paragraph styles (Title, Heading 1, …), alignment, indent, line spacing are not in the scripting dictionary | UPSTREAM | A hard wall: no route can offer these |
| P8 | Synthetic keystrokes are silently blocked while any app has secure keyboard entry (e.g. a focused password field) | UPSTREAM | Another reason to never rely on UI scripting |
