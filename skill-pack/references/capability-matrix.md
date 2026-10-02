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

## .key slide ops — AppleScript via live Keynote (Phase G, PENDING PROBE)

Built 2026-10-02 (`src/iwork_studio/keynote_slides.py`), technique from
reichenbach/iwork_mcp (14.5 / 15.1.1, open-document only, no safety net).
Here each op runs: gates → inventory → backup → op + in-place save →
fresh-open readback → per-slide expectation gate → parser re-parse gate →
atomic restore on any failure. Protocol proven headless (tests/test_keynote_slides.py,
app stubbed: rollback byte-exact, collateral-change detection, no-churn
pre-flight). App behaviour on 15.4 NOT yet observed.

| Capability | Status | Evidence |
|---|---|---|
| set presenter notes (Arabic) | PENDING PROBE — refused (UnverifiedRouteError) | run scripts/probe_g_keynote_slides.py → evidence/g1/ |
| skip / unskip slide | PENDING PROBE — refused | same |
| duplicate slide | PENDING PROBE — refused | same |
| add slide (default layout; master-slide choice not offered: -1700 family) | PENDING PROBE — refused | same |
| move slide (`app.move … {to:}` before/after semantics unknown — gate decides) | PENDING PROBE — refused | same |
| delete slide (never the last one) | PENDING PROBE — refused | same |
| deck open in Keynote → DocumentOpenError (never closes a user's window) | BUILT, pending probe | same |
| chart decks | REFUSED (GATE-CHART) | same detector as C4 |

Promotion rule: an op moves to VERIFIED only by adding it to
`keynote_slides.VERIFIED_OPS` in the same commit as its PASS row in
evidence/g1/probe_results.json.

## App resolution (classic vs Creator Studio)

| Situation | Behaviour | Evidence |
|---|---|---|
| classic `<App>.app` installed (with or without Creator Studio) | classic used — the verified route | tests/test_apps.py |
| only `<App> Creator Studio.app` | REFUSED (CreatorStudioUnverifiedError) unless IWORK_STUDIO_ALLOW_CREATOR_STUDIO=1 | upstream: save hangs, export error 6 on 15.1.1 |
| `IWORK_STUDIO_<APP>_APP` set | exact operator pin | tests/test_apps.py |

## Agent surface + CI

| Capability | Status | Evidence |
|---|---|---|
| MCP server (stdio, mcp 2.2.0): 10 tools, read/destructive hints | VERIFIED headless | tests/test_mcp_server.py — real stdio subprocess |
| Undo: list + atomic restore of versioned backups (re-parse gated, restore itself backed up) | VERIFIED headless | tests/test_backups.py |
| Path fence IWORK_STUDIO_ROOTS | VERIFIED headless | tests/test_mcp_server.py |
| Headless CI (GitHub Actions, Linux, `-m "not aqua"`) | WIRED | .github/workflows/ci.yml |
| keynote_io YAML parse via libyaml CSafeLoader (3.4 s vs 12.4 s read) | VERIFIED parse-identical | both .key fixtures: identical objects + schema_hash |

## Cross-format rules

- NEVER author in docx/pptx/xlsx and convert to iWork — lossy, council-rejected.
- Every write: versioned backup → tmp write → re-parse gate → atomic swap →
  (optional) render-verify. Failure ⇒ target untouched.
- Headless (no Aqua): AppleScript routes hard-fail with guidance (SC4).
- Strict zip byte-equality is unachievable for .numbers/.key (IWA protobuf
  re-encode). GATE-1 = semantic equality. Operator-pinned; do not re-litigate.