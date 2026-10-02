<div align="center">

<img src="assets/banner.svg" alt="iWork Studio — read and edit Apple Numbers, Keynote and Pages with Python" width="100%">

[![CI](https://github.com/arkanji/iwork-studio/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![macOS](https://img.shields.io/badge/macOS-27.2%20%2B%20iWork%2015.4-black?logo=apple&logoColor=white)](#verified-capability-matrix)
[![Arabic safe](https://img.shields.io/badge/Arabic%2FRTL-byte%20exact%20round--trips-informational?logo=languagetool&logoColor=white)](#arabic-round-trip-proof)
[![MCP server](https://img.shields.io/badge/MCP-one--line%20install-8A2BE2)](#mcp-server)
[![Agent skill](https://img.shields.io/badge/agent%20skill-drop--in%20SKILL.md-ff9f0a)](#for-ai-agents)
[![Zero repair prompts](https://img.shields.io/badge/iWork%20output-zero%20repair%20prompts-critical)](#the-real-story)

**Give your AI agent the keys to Apple iWork.** Read and edit **Numbers (`.numbers`)**, **Keynote (`.key`)** and **Pages (`.pages`)** files programmatically on macOS — with verified round-trips, atomic writes, versioned backups, and Arabic/RTL fidelity that actually holds. Ships as a Python library *and* a drop-in agent skill.

[Quick start](#quick-start) · [Capability matrix](#verified-capability-matrix) · [For AI agents](#for-ai-agents) · [The real story](#the-real-story) · [Traps we mapped so you don't die on them](#traps-we-mapped-so-you-dont-die-on-them)

<br>

<a href="https://arkanji.com/images/posts/iwork-studio-film-v3.mp4">
  <img src="assets/iwork-studio-film.webp" alt="iWork Studio in action: an AI agent edits a Numbers cell and keeps its formula, updates every Keynote slide without touching the formatting, and writes an Arabic letter in Pages" width="100%">
</a>

<sub>▶ <a href="https://arkanji.com/images/posts/iwork-studio-film-v3.mp4"><b>Watch the full film with sound</b></a> (46s) · <a href="https://arkanji.com/posts/iwork-studio-launch/">Read the launch story</a></sub>

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

Requires **Python 3.12**. `.numbers` and `.key` reads and edits are pure Python and run anywhere (CI runs them on Linux). `.pages`, render-verify and Keynote slide ops drive the real apps: macOS with iWork (validated against **15.4**) and a logged-in GUI session.

**As an MCP server** (Claude Code, Claude Desktop, Codex, any MCP client) — one line:

```bash
claude mcp add iwork-studio -- uvx --from git+https://github.com/arkanji/iwork-studio iwork-studio-mcp
```

**As a library:**

```bash
git clone https://github.com/Arkanji/iwork-studio.git
cd iwork-studio
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .            # pins come from pyproject.toml (== skill-pack/references/pins.txt)
```

Or just the CLI entry points (JSON on stdout, safe to pipe):

```bash
python skill-pack/scripts/read.py revenue.numbers            # .numbers / .key / .pages
python skill-pack/scripts/edit_numbers.py edit-cell revenue.numbers --ref B2 --value 2500
python skill-pack/scripts/edit_key.py replace pitch.key "2024" "2025"
python skill-pack/scripts/verify_render.py pitch.key --assert-text "الإيرادات"
```

## Verified capability matrix

Live-validated 2026-10-01, iWork 15.4 / macOS 27.2, with Arabic fixtures. Full table with per-row evidence: [`skill-pack/references/capability-matrix.md`](skill-pack/references/capability-matrix.md).

| Format | Route | Read | Write | Charts | Arabic/RTL | Render-verify |
|---|---|:---:|:---:|:---:|---|---|
| `.numbers` | `numbers-parser` 4.19.0 — pure Python, headless | ✅ full model (sheets→tables→cells, formulas, styles, formats) | ✅ cell edits, create, replace — atomic | 🚫 refused, not mangled | ✅ byte-exact codepoints | ✅ PDF → text-layer |
| `.key` | `keynote-parser` 1.14.5.0 — pure Python (+ AppleScript fallback in app) | ✅ slide/text-item tree (IWA→YAML) | ✅ deck-wide find/replace — atomic | 🚫 refused, not mangled | ✅ `\u06xx` escape-aware | ✅ PDF → text-layer |
| `.pages` | AppleScript via live Pages (Aqua session) | ✅ body text, export to `.docx`/PDF | ⚠️ `replace_all`, `set_body` only — richer ops raise `PagesOutOfScopeError` | n/a | ✅ preserved end-to-end | ✅ PDF → text-layer |

**Pending live probe (built, gated off):** Keynote slide ops via the app — add, duplicate, delete, move, skip, presenter notes ([`keynote_slides.py`](src/iwork_studio/keynote_slides.py)). Each runs the full write protocol plus a per-slide expectation gate. They stay refused (`UnverifiedRouteError`) until [`scripts/probe_g_keynote_slides.py`](scripts/probe_g_keynote_slides.py) passes on 15.4 and commits evidence.

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
7. **"Creator Studio" is a different app** — iWork 15.1+ can install as `Numbers Creator Studio.app` etc.; a hardcoded `Application("Numbers")` drives the wrong app. We resolve names at call time, prefer the verified classic app, and refuse a Creator-Studio-only machine until it is probed (upstream reports its save hangs and export fails). → [`src/iwork_studio/apps.py`](src/iwork_studio/apps.py)

Plus ~25 more scripting traps imported (with status, not as gospel) from [reichenbach/iwork_mcp](https://github.com/reichenbach/iwork_mcp): colour ranges per app, PostScript font names, Numbers auto-parsing `"$1,234"`, Pages tables only reachable from AppleScript, and more → [`skill-pack/references/jxa-traps.md`](skill-pack/references/jxa-traps.md)

## For AI agents

### MCP server

`iwork-studio-mcp` exposes the library over MCP (stdio). Every tool is a thin wrapper, so the write protocol is not optional: an agent cannot reach a write that skips the backup, the re-parse gate or the atomic swap.

| Tool | What it does |
|---|---|
| `iwork_capabilities` | What this machine can do right now (GUI session, installed apps, verified ops) |
| `iwork_read` | `.numbers` / `.key` / `.pages` → JSON model |
| `numbers_edit_cell` | One cell; every other cell verified unchanged |
| `keynote_replace_text` | Deck-wide find/replace; structure verified unchanged |
| `pages_preflight` · `pages_replace_all` · `pages_set_body` | The two verified Pages ops |
| `iwork_verify_render` | Export PDF via the app, assert the text is visibly there |
| `iwork_list_backups` · `iwork_restore_backup` | The undo button: every write's versioned backup, restored atomically |

Writes carry `destructiveHint`, reads carry `readOnlyHint`, so clients can ask before writing. Optional fence: `IWORK_STUDIO_ROOTS=~/Documents/Decks` keeps the server inside the folders you name. Keynote slide-op tools appear automatically once verified (`IWORK_STUDIO_ENABLE_UNVERIFIED=1` shows them early, for probing).

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
src/iwork_studio/     numbers_io · keynote_io · pages_io · keynote_applescript · keynote_slides · render_verify · backups · apps · mcp_server
skill-pack/           SKILL.md · install.sh · 6 CLI scripts · references/ (matrix, traps, pins)
scripts/              exploratory probes (phase evidence)
tests/                pytest — headless lane in CI (Linux) · `pytest -m aqua` = live GUI lane on the Mac
.github/workflows/    ci.yml — headless tests on every push/PR
evidence/             verbatim phase logs · probe scripts · fixtures · outputs
specs/                original build spec · data model · pins
```

## Contributing

iWork versions drift. If this breaks on a future macOS/iWork release: the failure mode is *documented renames* — check [`skill-pack/references/capability-matrix.md`](skill-pack/references/capability-matrix.md), re-run the probes in `scripts/`, and pin the new reality. PRs that add a verified route (with evidence) are the PRs we want.

## Star history, honestly

This started because an AI butler was asked to edit a Keynote slide and the ecosystem had nothing to offer him. If it saved your agent from corrupting a deck, consider starring — it helps others find the traps.

## License

[MIT](LICENSE) — including the traps. Take them.