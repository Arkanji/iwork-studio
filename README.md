<div align="center">

<img src="assets/banner.svg" alt="iWork Studio — read and edit Apple Numbers, Keynote and Pages with Python" width="100%">

[![Tests](https://img.shields.io/badge/tests-76%2F76%20green-brightgreen)](#verif)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![macOS](https://img.shields.io/badge/macOS-27.2%20%2B%20iWork%2015.4-black?logo=apple&logoColor=white)](#verified-capability-matrix)
[![Arabic safe](https://img.shields.io/badge/Arabic%2FRTL-byte%20exact%20round--trips-informational?logo=languagetool&logoColor=white)](#arabic-round-trip-proof)
[![Agent skill](https://img.shields.io/badge/agent%20skill-drop--in%20SKILL.md-ff9f0a)](#for-ai-agents)
[![Zero repair prompts](https://img.shields.io/badge/iWork%20output-zero%20repair%20prompts-critical)](#the-real-story)

**Give your AI agent the keys to Apple iWork.** Read and edit **Numbers (`.numbers`)**, **Keynote (`.key`)** and **Pages (`.pages`)** files programmatically on macOS — with verified round-trips, atomic writes, versioned backups, and Arabic/RTL fidelity that actually holds. Ships as a Python library *and* a drop-in agent skill.

[Quick start](#quick-start) · [Capability matrix](#verified-capability-matrix) · [For AI agents](#for-ai-agents) · [The real story](#the-real-story) · [Traps we mapped so you don't die on them](#traps-we-mapped-so-you-dont-die-on-them)

</div>

---

## Why this exists

Microsoft documents have great open tooling (python-docx, python-pptx, openpyxl — even official agent skills). **Apple iWork has none.** No public format spec, no maintained `.pages` parser, and AppleScript that quietly refuses to save outside its sandbox. AI agents asked to "fix slide 3" or "update cell B2" either hallucinate support or corrupt your files.

**iWork Studio is the missing piece**: honest capability boundaries, hard safety gates, and proof — every claim in this README is backed by committed, re-runnable evidence in [`evidence/`](evidence/). Where a route does *not* exist, we say so. Where one exists, it must pass gates before it's offered.

```python
from iwork_studio import numbers_io, keynote_io

model = numbers_io.read_numbers("revenue.numbers")          # full semantic model
numbers_io.edit_cell("revenue.numbers", "B2", 2500,
                     sheet="Budget")                         # backed up, atomic, verified
keynote_io.replace_text("pitch.key", "2024", "2025")         # deck-wide, escape-aware
```

## Quick start

Requires macOS with iWork installed (validated against **15.4**) and **Python 3.12**.

```bash
git clone https://github.com/Arkanji/iwork-studio.git
cd iwork-studio
python3.12 -m venv .venv && source .venv/bin/activate
pip install numbers-parser==4.19.0 keynote-parser==1.14.5.0 PyMuPDF==1.28.2 python-docx==1.2.0
```

Or just the CLI entry points (JSON on stdout, safe to pipe):

```bash
python skill-pack/scripts/read.py revenue.numbers            # .numbers / .key / .pages
python skill-pack/scripts/edit_numbers.py edit revenue.numbers --ref B2 --value 2500
python skill-pack/scripts/edit_key.py replace pitch.key --find "2024" --replace "2025"
python skill-pack/scripts/verify_render.py pitch.key --assert-text "الإيرادات"
```

## Verified capability matrix

Live-validated 2026-10-01, iWork 15.4 / macOS 27.2, with Arabic fixtures. Full table with per-row evidence: [`skill-pack/references/capability-matrix.md`](skill-pack/references/capability-matrix.md).

| Format | Route | Read | Write | Charts | Arabic/RTL | Render-verify |
|---|---|:---:|:---:|:---:|---|---|
| `.numbers` | `numbers-parser` 4.19.0 — pure Python, headless | ✅ full model (sheets→tables→cells, formulas, styles, formats) | ✅ cell edits, create, replace — atomic | 🚫 refused, not mangled | ✅ byte-exact codepoints | ✅ PDF → text-layer |
| `.key` | `keynote-parser` 1.14.5.0 — pure Python (+ AppleScript fallback in app) | ✅ slide/text-item tree (IWA→YAML) | ✅ deck-wide find/replace — atomic | 🚫 refused, not mangled | ✅ `\u06xx` escape-aware | ✅ PDF → text-layer |
| `.pages` | AppleScript via live Pages (Aqua session) | ✅ body text, export to `.docx`/PDF | ⚠️ `replace_all`, `set_body` only — richer ops raise `PagesOutOfScopeError` | n/a | ✅ preserved end-to-end | ✅ PDF → text-layer |

> **The `.pages` honesty clause:** there is *no* pure-Python `.pages` parser anywhere (we checked — the only candidate upstream is 1★/7 commits, watchlist only). Rather than fake it, we ship exactly the two verified app-driven ops and fail loudly on everything else. Inventing `.pages` support would be a corruption vector, not a feature.

### Arabic round-trip proof

- `.numbers`: `أحمد` written, saved, re-parsed → exact same codepoints ([`evidence/a3/probe_a_arabic_roundtrip.py`](evidence/a3/probe_a_arabic_roundtrip.py))
- `.key`: 17 `\u06xx` escape sequences survive find/replace intact ([`evidence/a3/probe_a_keypad_escapes.py`](evidence/a3/probe_a_keypad_escapes.py))
- Render level: single-word ligature-aware PDF assertions (multi-word fragments extract in visual bidi order and lie about mismatches — so we assert single-word by rule)
- RTL marks (U+200F) survive the full edit loop

### Write protocol — every write, every time

```
versioned backup → tmp write → re-parse gate → semantic diff → atomic swap → PDF render-verify
                                                    ↘ any failure: target untouched, forensic evidence kept
```

## Traps we mapped so you don't die on them

Hard-won on a live machine, so your agent doesn't learn them by corrupting something:

1. **The sandbox `save in` trap** — iWork apps are sandboxed; `save in <arbitrary path>` from AppleScript is **DENIED** ("You don't have permission"). In-place `save` works; `export` works. Rule shipped in-code: a script doing this is a bug, not a retry. → [`skill-pack/references/sandbox-trap.md`](skill-pack/references/sandbox-trap.md)
2. **Keynote 15.4 `-1700` defect** — the documented `title`/`body` slide properties throw `-1700`. Working form: `object text of first/second text item`. → [`skill-pack/references/keynote-1700-defect.md`](skill-pack/references/keynote-1700-defect.md)
3. **Hermes/Python-3.14 Pillow hijack** — broken Pillow leaking into venvs breaks `keynote-parser` with `PIL._imaging` errors; clean-env installs avoid it. → [`skill-pack/references/pins.txt`](skill-pack/references/pins.txt)
4. **Chart files are refused, not mangled** — editing chart decks via text-replacement risks corrupting chart data references (IWA chart message types verified against Apple's own templates before gating). Both writers detect and refuse.
5. **Strict byte-equality on save is a myth** — IWA protobuf re-encoding is opaque; the achievable bar is *semantic* equality (file reopens with zero repair prompts, full model compared). We enforce the real bar and name the fake one.
6. **TCC + template chooser first-run walls** — one-time permission prompts; documented preflight so agents fail with guidance instead of hanging. → [`skill-pack/references/tcc-preflight.md`](skill-pack/references/tcc-preflight.md)

## For AI agents

### Drop-in skill

This repo ships [`skill-pack/SKILL.md`](skill-pack/SKILL.md) — a structured, self-describing skill any agent framework can load (Hermes, Claude-style systems, anything with a `skills/` directory):

```bash
bash skill-pack/install.sh          # installs to $HERMES_HOME/skills/iwork-studio (default ~/.hermes/skills)
```

### For crawlers and LLMs (`llms.txt`)

Machine-readable project manifest for AI discovery: [`llms.txt`](llms.txt) — canonical summary, capability routes, install contract, honest limitations, links to evidence. Serve it from `/.well-known/llms.txt` if you're hosting docs for this.

### Agent contract (what your agent can rely on)

- **JSON in / JSON out** on every script — stderr is never part of the contract
- **Fail-loud errors**: `ChartRefusalError`, `PagesOutOfScopeError`, `NewerAppVersionError`, `SandboxSaveError` — typed, documented, never silent
- **Headless fails fast** with guidance (AppleScript routes need a GUI session — detected, not discovered the hard way)
- **Version pins enforced**: files from newer app versions degrade to read-only

## Architecture

```
file-level parsers (deterministic, headless, diffable)  →  .numbers, .key
app-level AppleScript (render-truth: PDF, RTL shaping)  →  render-verify, .pages, fallbacks
```

Hybrid by design — file-level where determinism wins, app-level only where the app *is* the renderer of record. Every write rides the atomic-swap protocol; every verified run leaves evidence, not assertions.

## Repository layout

```
assets/               banner + media
src/iwork_studio/     numbers_io · keynote_io · pages_io · keynote_applescript · render_verify
skill-pack/           SKILL.md · install.sh · 6 CLI scripts · references/ (matrix, traps, pins)
scripts/              exploratory probes (phase evidence)
tests/                pytest — 76/76 green (run twice, live GUI included)
evidence/             verbatim phase logs · probe scripts · fixtures · outputs
specs/                original build spec · data model · pins
```

## Contributing

iWork versions drift. If this breaks on a future macOS/iWork release: the failure mode is *documented renames* — check [`skill-pack/references/capability-matrix.md`](skill-pack/references/capability-matrix.md), re-run the probes in `scripts/`, and pin the new reality. PRs that add a verified route (with evidence) are the PRs we want.

## Star history, honestly

This started because an AI butler was asked to edit a Keynote slide and the ecosystem had nothing to offer him. If it saved your agent from corrupting a deck, consider starring — it helps others find the traps.

## License

[MIT](LICENSE) — including the traps. Take them.