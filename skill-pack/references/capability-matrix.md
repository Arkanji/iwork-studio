# iWork Studio — Capability Matrix

What each route does, what it refuses, and what it needs. Works with classic
iWork and the Creator Studio apps. Arabic/RTL content is supported throughout.

## .numbers — numbers-parser 4.19.0 (pure Python, no app needed)

| Capability | Status |
|---|---|
| Read full semantic model (sheets → tables → cells, formulas, styles, formats) | Supported |
| Create a new file | Supported |
| Edit one cell (backup → scratch copy → re-parse → atomic swap; every other cell checked unchanged) | Supported |
| Values stored verbatim (`"$1,234.56"`, Arabic-Indic digits, `=…` text stay strings) | Supported |
| Arabic round-trip, file level and rendered PDF | Supported |
| Cell style: font, size, bold/italic/underline/strike, font colour, fill, alignment, wrap (only requested attributes change) | Supported |
| Number format: number, currency (ISO code), percentage, scientific, fraction, datetime, text; decimals, separators, negative style | Supported |
| Borders: all / outline / inner / per side; width, colour, solid/dashes/dots | Supported |
| Column widths, row heights, header rows/columns | Supported |
| Merge a range (refused if it would hide data or cross the header edge) | Supported |
| Table styles (named table themes) | Not exposed — neither AppleScript nor the parser |
| Render-verify (export PDF via Numbers → text-layer check) | Supported — needs Numbers + GUI session |
| Format-verify (PDF font/size/colour/page size) | Supported — needs the app + GUI session |
| Files containing charts | REFUSED for writes (do not bypass) |

Equality bar is semantic (file reopens, full model identical); strict zip
byte-equality is impossible with IWA protobuf re-encoding.

numbers-parser 4.19 API notes: `d.sheets`/`s.tables` are ItemsList properties
(index by int, `.name` lookup); write with `t.write(r, c, val)`; read with
`t.cell(r, c).value`.

## .key text — keynote-parser 1.14.5.0 (pure Python) + AppleScript fallback

| Capability | Status |
|---|---|
| Read slide/text-item tree (IWA → YAML) + structural schema hash | Supported |
| Deck-wide find/replace, `\r`-paragraph aware, `\u06xx` escape-aware | Supported |
| Structure check on every write (rename-storm gate) + write manifest | Supported |
| File open/locked in Keynote | `FileLockedError` → AppleScript fallback (`object text` of a text item) |
| Render-verify (export PDF via Keynote) | Supported — needs Keynote + GUI session |
| Decks containing charts | REFUSED for writes |

Never use the slide `title`/`body` properties (throw -1700); use `object text`
(see keynote-1700-defect.md).

## .key slides — via Keynote (GUI session)

Each op: gates → slide inventory → backup → op + in-place save → fresh re-read
→ per-slide expectation check → parser re-parse → atomic restore on any
mismatch. On by default; off switch `IWORK_STUDIO_DISABLE_SLIDE_OPS=1`.

| Capability | Status |
|---|---|
| Set presenter notes (Arabic-safe) | Supported |
| Hide / unhide slide | Supported |
| Duplicate slide | Supported |
| Add slide at end or at a position (default layout; master choice not offered) | Supported — AppleScript `make new slide` + `move` |
| Move slide | Supported — AppleScript `move slide n to before/after slide t` |
| Delete slide (never the last one) | Supported |
| Change theme (refused/rolled back if any slide loses text) | Supported |
| Change a slide's layout (master) | Supported — AppleScript (JXA master access throws -1700) |
| Text item font (PostScript name), size, colour | Supported — colour read back after save |
| Text alignment, shape fill/border, editing a theme's masters | Not exposed by Apple's scripting |
| Deck open in Keynote | REFUSED (`DocumentOpenError`) — never closes a user's window |
| App reports "ok" but nothing (or the wrong thing) changed | Rolled back (`SlideOpVerificationError`) |
| Decks containing charts | REFUSED |

## .pages — via Pages (GUI session; no parser exists anywhere)

| Capability | Status |
|---|---|
| Read body text (+ export to .docx for structure) | Supported |
| `replace_all` across the body | Supported |
| `set_body` (replaces the whole body; resets body formatting) | Supported |
| Preflight for TCC / template-chooser dialogs (one prompt, never retry) | Supported |
| Render-verify (export PDF via Pages) | Supported |
| Anything richer (styles, tables, sections, regex) | OUT OF SCOPE (`PagesOutOfScopeError`) |

`save in <arbitrary path>` is banned for on-disk files (sandbox denial);
in-place save and export only.

## App resolution (classic vs Creator Studio)

| Situation | Behaviour |
|---|---|
| Classic `<App>.app` installed (with or without Creator Studio) | Classic is used |
| Only `Numbers` / `Pages` / `Keynote Creator Studio.app` | Supported |
| Any other, unknown Creator Studio app | REFUSED (`CreatorStudioUnverifiedError`); `IWORK_STUDIO_ALLOW_CREATOR_STUDIO=1` to try it |
| `IWORK_STUDIO_<APP>_APP` set | That exact app name is used |

## Agent surface

| Capability | Status |
|---|---|
| MCP server (stdio): 29 tools with read-only / destructive hints | Supported |
| Protocol stream kept clean (library output never reaches stdout) | Supported |
| Undo: list + atomic restore of versioned backups (restore is itself backed up) | Supported |
| Path fence `IWORK_STUDIO_ROOTS` | Supported |

## Cross-format rules

- Never author in docx/pptx/xlsx and convert to iWork — lossy.
- Every write: versioned backup → scratch write → re-parse check → atomic swap →
  (optional) render-verify. Failure ⇒ target untouched.
- No GUI session: app routes fail fast with guidance.
