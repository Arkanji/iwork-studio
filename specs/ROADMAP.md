# iWork Studio roadmap tracker

The working tracker for what's planned, done, waiting on a live Mac check, and what to
re-analyse. Specs live in `specs/NNN-*/`; the rules are in `.specify/memory/constitution.md`.
Priorities come from the Attractiveness Playbook (Vision Fit + Market Signals + Financial
Potential vs sprints). **Traps are out. Big Bets are parked for later.**

Legend: ✅ done · 🔨 in progress · ⏳ waiting on the owner's live Mac check · 📋 specced · 💤 parked

## Now

| # | Feature | Release | Status | Spec |
|---|---|---|---|---|
| 001 | Trust patch: open-file guard, Pages per-paragraph replace, private bounded backups, deck fence, cell read-back, timeouts without leaks, PyPI install, honest docs | v2.6.1 | 📋 | [spec](001-trust-patch/spec.md) · [plan](001-trust-patch/plan.md) · [tasks](001-trust-patch/tasks.md) |
| 004 | Show it: HyperFrames demo GIF/MP4 (gallery later) | v2.6.2 | 🔨 | [spec](004-show-it/spec.md) |
| 002 | Front door: outcome-first README, samples + try-it, honest capabilities, issue templates, traffic snapshots, listing kit, Numbers chart probe | v2.6.2 | 📋 | [spec](002-front-door/spec.md) |

## Next

| # | Feature | Release | Status | Spec |
|---|---|---|---|---|
| 003 | Agent efficiency: one-call slides, batch reorder, batch cells, paged reads, truthful formulas | v2.7.0 | 📋 | [spec](003-agent-efficiency/spec.md) |
| 004b | Gallery of generated decks (needs Mac renders) | v2.7.x | 📋 | [spec](004-show-it/spec.md) |
| 005 | Arabic README + 6 new kits + Pages RTL paragraphs (probe first) | v2.8.0 | 📋 | [spec](005-arabic-and-kits/spec.md) |
| 006 | Numbers breadth (dates, rename, clear, checkbox) + opt-in feedback + Hermes plugin | v2.8.x | 📋 | [spec](006-numbers-breadth/spec.md) |

## Owner actions (can't be done from code)

| Action | When | Status |
|---|---|---|
| Update the GitHub About box + topics (text in `docs/listing.md`) | after 002 | 📋 |
| Submit to mcp.so, PulseMCP, Smithery, Cursor directory, LobeHub, mcpservers.org | after 002 | 📋 |
| `npx skills add Arkanji/iwork-studio` once (skills.sh listing; feeds Hermes Skills Hub) | anytime | 📋 |
| Turn on GitHub Discussions | after 002 | 📋 |
| Live Mac check for each release (aqua tests + probes) | each release | — |
| Launch posts (Show HN, r/ClaudeAI, r/macapps, Arabic X/LinkedIn) | after 004 + 005 | 📋 |
| awesome-mcp-servers listing | — | ✅ merged 2026-10-08 |

## Waiting on a live check (⏳)

Nothing yet. Each entry: what to run, what it proves, the result once known.

## Re-analyse (decisions to revisit with new evidence)

| Item | Why it's here | Revisit when |
|---|---|---|
| Pages per-paragraph replace keeps formatting (trap P3 "agrees, partly") | Whole feature 001-US2 rests on it; fallback is refuse-unless-`reset_formatting` | after the live check |
| Numbers chart creation | A competitor claims a workaround; we say it isn't reliably scriptable | after the 002 probe |
| Backup location moved out of synced folders | Users who look for `<file>.backups` in Finder | after a release cycle; consider a "show backups" helper |
| Open-document guard cost | One app query per write when the app runs | if users report slowness |
| Formula checks on comma-decimal locales | Untested; may false-fail | after a live check on such a locale |
| Hermes plugin vs skills.sh only | Small audience; skills.sh may be enough | after 30-day metrics |

## Parked: Big Bets (later, probe first)

| Item | Why parked |
|---|---|
| Edit the document while it's open | Biggest friction remover, but needs careful app-state handling |
| Slide shapes, position, align, resize | Real design gap; needs probes for what Keynote scripts reliably |
| Anthropic directory submission (after a clean-Mac `.mcpb` test) | Owner deferred; prerequisite is a clean-Mac install test |

## Out: Traps (not doing)

UI scripting to fake Pages tables or Numbers charts · round-trip conversion to pptx/xlsx/docx
and back · Apple-blocked features (builds/animations, pivots, conditional formatting) ·
chasing the competitor's tool count · default-on telemetry.

## 30-day targets (from 2026-10-12)

| Metric | Baseline | Target | Latest |
|---|---|---|---|
| Damaged-file reports | 0 | 0 | — |
| GitHub stars | 2 | 50 | 2 |
| Unique visitors / 14 days | 59 | 400 | 59 |
| PyPI downloads / month | unknown | 500 | — |
| `.mcpb` downloads | 0 | 50 | 0 |
| Directory listings | 3 (Registry, Glama, awesome list) | 9+ | 3 |
| Issues/Discussions from others | 0 | 5 | 0 |

## Log

- 2026-10-12: Review by product engineer, PM and CPO agents; constitution 1.0.0; specs 001–006 written; GIF production started.
