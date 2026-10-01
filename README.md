# iWork Studio

Read and edit Apple iWork files (**.numbers**, **.key**, **.pages**) programmatically on macOS — with verified round-trips, Arabic (RTL) fidelity, atomic writes, and hard safety gates. Ships as both a Python library (`src/iwork_studio/`) and a drop-in agent skill (`skill-pack/`).

## The real story

No official public format documentation exists for iWork files. Everything in this repo was established by live probing on a real machine (macOS 27.2, iWork 15.4, CPython 3.12.7), and every capability claim below is backed by committed evidence you can re-run or read yourself in [`evidence/`](evidence/).

Three honest constraints shape the whole design:

1. **There is no pure-Python .pages parser.** The .pages format is a zip of IWA protobufs plus a QuickLook preview — no maintained third-party parser exists. All .pages access is done via AppleScript against the Pages app (requires a GUI session / Aqua, plus a one-time TCC approval).
2. **Strict byte-equality on save is unachievable for .numbers/.key.** Both formats store IWA protobufs; any parser re-encodes them (e.g. numbers-parser 4.19.0 adds ~1.6 KB and rewrites protobuf wire data on an unmodified round-trip). So the fidelity gate here is **semantic equality** (GATE-1): open the written file, compare the full content model, byte-exact at the *text* level.
3. **Chart-containing files are refused, not mangled.** Editing chart decks through text-replacement risks corrupting chart data references. Both writers detect charts and refuse with a clear error (GATE-CHART). This is a deliberate scope cut, not a limitation we plan to silently lift.

## Verified capability matrix

Validated live 2026-10-01 with Arabic content. Evidence per row; see [`skill-pack/references/capability-matrix.md`](skill-pack/references/capability-matrix.md) for the full table.

| Format | Route | Read | Write | Charts | Arabic | Render-verify |
|---|---|---|---|---|---|---|
| `.numbers` | numbers-parser 4.19.0 (pure Python, no GUI) | Full model (sheets/tables/cells) | Cell edits, create, find/replace — atomic swap | Refused (detected) | Byte-exact round-trip; ligature-aware PDF match | PDF export → text-layer assert |
| `.key` | keynote-parser 1.14.5.0 (pure Python) + AppleScript fallback | Slide/text-item tree | Deck-wide find/replace, atomic swap | Refused (detected) | `\u06xx` escape-aware, round-trip verified | PDF export → text-layer assert |
| `.pages` | AppleScript only (needs Aqua + one-time TCC) | Body text (2 routes) | `replace_all`, `set_body` only — anything richer raises `PagesOutOfScopeError` | n/a | Preserved through read/export/PDF | PDF export → text-layer assert |

### Arabic round-trip proof

- `.numbers`: writing `'أحمد'`, saving, and re-parsing yields the exact same codepoints (`evidence/a3/probe_a_arabic_roundtrip.py`).
- `.key`: 17 `\u06xx` escape sequences survive a find/replace round-trip intact (`evidence/a3/probe_a_keypad_escapes.py`).
- PDF render verification asserts single Arabic words (ligature-aware): multi-word fragments extract in visual bidi order and produce spurious mismatches, so assertions are single-word by rule (`skill-pack/SKILL.md` rule 7).

### The sandbox `save in` trap

iWork apps are sandboxed. From AppleScript:

- `save in <arbitrary path>` → **DENIED** (sandbox refuses to write outside its container). Never use. A script doing this is a bug — fix it, don't retry it.
- `save` (in-place, file already on disk) → **works**, verified live for all three apps.
- `export ... to <path> as "PDF"/"Microsoft Word"` → **works** — the safe route for artifacts.

Full ground truth and helper lint functions: [`skill-pack/references/sandbox-trap.md`](skill-pack/references/sandbox-trap.md).

### Keynote 15.4 `-1700` defect

On Keynote 15.4, the AppleScript slide properties `title` and `body` throw error -1700 even on slides that have them. The verified workaround is reading/writing via each slide's text items and their `object text`: [`skill-pack/references/keynote-1700-defect.md`](skill-pack/references/keynote-1700-defect.md).

### Write protocol

Every write: versioned backup → tmp write → re-parse gate → atomic swap → optional render-verify. On any failure the target file is left untouched.

## Install

Requires macOS with iWork installed (validated against 15.4) and Python 3.12.

```bash
git clone https://github.com/Arkanji/iwork-studio.git
cd iwork-studio
python3.12 -m venv .venv && source .venv/bin/activate
pip install numbers-parser==4.19.0 keynote-parser==1.14.5.0 PyMuPDF==1.28.2 python-docx==1.2.0
```

Pins and rationale: [`skill-pack/references/pins.txt`](skill-pack/references/pins.txt). Note: keynote-parser is CLI-locked at 1.14.5.0; numbers-parser pinned to 4.19.0 where `d.sheets`/`s.tables` are `ItemsList` (index by int, lookup by `.name`), and `t.set_value` is `t.write(r, c, v)`.

## Usage

Library:

```python
from iwork_studio import numbers_io, keynote_io, pages_io

model = numbers_io.read_numbers("budget.numbers")     # semantic model
numbers_io.edit_cell("budget.numbers", "B2", 2500,
                     sheet="Budget")                   # atomic, backed up
model = keynote_io.read_key("deck.key")               # YAML-tree model
```

Scripts (JSON on stdout; they auto-locate a pinned interpreter at `~/.hermes/iwork-venv/.venv` if present, otherwise run under the current Python):

```bash
python skill-pack/scripts/read.py file.numbers   # or .key / .pages
python skill-pack/scripts/edit_numbers.py edit file.numbers --ref B2 --value 2500
python skill-pack/scripts/edit_key.py --help
python skill-pack/scripts/edit_pages.py --help
python skill-pack/scripts/verify_render.py file.key --assert-text "Expected text"
```

As an agent skill (any skill system with a `skills/` dir, e.g. Hermes): `bash skill-pack/install.sh` assembles a self-contained copy under `$HERMES_HOME/skills/iwork-studio` (default `~/.hermes/skills/`). See [`skill-pack/SKILL.md`](skill-pack/SKILL.md).

## Headless / CI caveats

- AppleScript routes (all .pages work, .key fallback, render-verify) need a GUI session; headless they fail fast with guidance.
- First AppleScript run triggers a TCC permission prompt (one-time, per app).
- TCC and the AppleScript `-1712` timeout (a modal blocking the app) are documented in [`skill-pack/references/tcc-preflight.md`](skill-pack/references/tcc-preflight.md).

## Repository layout

```
src/iwork_studio/    numbers_io.py, keynote_io.py, pages_io.py,
                     keynote_applescript.py, render_verify.py
skill-pack/          SKILL.md, install.sh, six scripts (the CLI entry
                     points), references/
scripts/             exploratory probe scripts (phase evidence)
tests/               pytest suite — 76/76 green (run twice, live GUI included)
evidence/            verbatim phase logs + probe scripts + fixtures + outputs
specs/               the original build spec, data model, pins
```

## License

[MIT](LICENSE)