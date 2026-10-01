# iWork Studio — Verified Capability Matrix

Machine: macOS 27.2, iWork 15.4 (build 7051.0.79)
Validated: 2026-10-01, live, with Arabic content. Evidence per row.
Re-verify on any newer app version before trusting these rows.

## .numbers — numbers-parser 4.19.0 (pure Python, no GUI)

| Capability | Status | Evidence |
|---|---|---|
| Read full semantic model (sheets/tables/cells + style/format) | VERIFIED | Phase B, `numbers_io.read_numbers` |
| Create new file (Document + write + save) | VERIFIED | A3-probe-2, `scripts/edit_numbers.py demo` |
| Edit single cell, AtomicSwap (backup→tmp→re-parse→swap) | VERIFIED | B2, 29 pytest cases |
| GATE-1 semantic byte-equality (strict zip equality impossible) | VERIFIED | A3-probe-1/6: +1,632 B IWA re-encode, semantic equal |
| Arabic round-trip byte-exact at file level | VERIFIED | A3-probe-2: 'أحمد' re-parsed exact |
| Arabic render-level (PDF text layer) | VERIFIED | B6: ligature-aware match PASS |
| Chart-container files | REFUSED (GATE-CHART) | B4; accepted scope cut, do not bypass |
| Render-verify (AppleScript export PDF → PyMuPDF) | VERIFIED | B6, live Aqua loop |

API drift on 4.19 vs docs: `d.sheets`/`s.tables` are ItemsList properties
(index by int, `.name` lookup); `t.set_value` → `t.write(r,c,val)`; read
via `t.cell(r,c).value` (evidence/a3/discover_api.py).

## .key — keynote-parser 1.14.5.0 (pure Python) + AppleScript fallback

| Capability | Status | Evidence |
|---|---|---|
| Read: unpack IWA→YAML tree, slide text model + schema_hash | VERIFIED | C1 |
| Deck-wide find/replace, AtomicSwap, \r-paragraph aware | VERIFIED | C2; upstream Replacement bug patched via _FixedReplacement |
| Arabic `\u06xx` escape-aware find/replace | VERIFIED | A3-probe-4, C2 |
| Schema-hash manifest + rename-storm gate | VERIFIED | C5 |
| Chart decks | REFUSED (GATE-CHART) | C4, live chart fixture |
| File locked/open in Keynote → FileLockedError | DETECTED | C2; use AppleScript fallback |
| AppleScript fallback: `object text of Nth text item` | VERIFIED | C6; in-place save verified |
| Render-verify (export PDF → PyMuPDF) | VERIFIED | C7 |

Keynote 15.4 defect: slide `title`/`body` props throw -1700. Never use
them; use `object text` (see keynote-1700-defect.md).

## .pages — AppleScript only (no parser exists)

| Capability | Status | Evidence |
|---|---|---|
| Read body text (bodyText readback) | VERIFIED | D1 |
| Read via export → docx → python-docx (Arabic in w:t runs) | VERIFIED | D1; export 7,697 B |
| Write op 1: replace_all across body text | VERIFIED | D2 |
| Write op 2: set_body (full body replacement) | VERIFIED | D2 |
| Anything richer (styles, tables, sections, regex) | OUT OF SCOPE — raises PagesOutOfScopeError | D2; council-rejected, never fake parity |
| In-place `save` of on-disk .pages | VERIFIED | Phase D GATE-SAVE (mtime + readback + Arabic intact) |
| TCC / template-chooser preflight (one prompt, never retry) | VERIFIED | D3; -1712 = modal blocking, human dismisses once |
| Render-verify (export PDF → PyMuPDF, Arabic) | VERIFIED | D4; 'تقديري' ligature-aware PASS |

`save in <arbitrary path>` stays BANNED for on-disk files (sandbox denial).
Naming a NEW unsaved doc with `save in` is not the trap (same as C fixture).

## Cross-format rules

- NEVER author in docx/pptx/xlsx and convert to iWork — lossy, council-rejected.
- Every write: versioned backup → tmp write → re-parse gate → atomic swap →
  (optional) render-verify. Failure ⇒ target untouched.
- Headless (no Aqua): AppleScript routes hard-fail with guidance (SC4).
- Strict zip byte-equality is unachievable for .numbers/.key (IWA protobuf
  re-encode). GATE-1 = semantic equality. Operator-pinned; do not re-litigate.