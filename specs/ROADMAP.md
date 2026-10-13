# iWork Studio roadmap tracker

The working tracker for what's planned, done, waiting on a live Mac check, and what to
re-analyse. Specs live in `specs/NNN-*/`; the rules are in `.specify/memory/constitution.md`.
Priorities come from the Attractiveness Playbook (Vision Fit + Market Signals + Financial
Potential vs sprints). **Traps are out. Big Bets are parked for later.**

**Live board:** the private GitHub Project "iWork Studio roadmap" (created from `specs/roadmap.json` by the
Roadmap board workflow). Its Attractiveness and Quadrant columns are computed every hour from Vision Fit,
Market Signals, Financial Potential and Sprints. Edit scores on the board; this file keeps the specs and decisions.

Legend: ✅ done · 🔨 in progress · ⏳ waiting on the owner's live Mac check · 📋 specced · 💤 parked

## Now

| # | Feature | Release | Status | Spec |
|---|---|---|---|---|
| 001 | Trust patch: open-file guard, Pages per-paragraph replace, private bounded backups, deck fence, cell read-back, timeouts without leaks, PyPI install, honest docs | v2.6.1 | ✅ released 2026-10-13 (PyPI, Registry, GitHub .mcpb, plugin) | [spec](001-trust-patch/spec.md) · [plan](001-trust-patch/plan.md) · [tasks](001-trust-patch/tasks.md) |
| 004 | Show it: HyperFrames demo GIF/MP4 (gallery later) | v2.6.1 | ✅ released; GIF (3.2 MB, 15.5 s) + MP4 1080p; rebuild with `assets/demo/render.sh` | [spec](004-show-it/spec.md) |
| 002 | Front door: outcome-first README, samples + try-it, honest capabilities, issue templates, traffic snapshots, listing kit, Numbers chart probe | v2.6.1 | ✅ released (chart probe + owner actions pending) | [spec](002-front-door/spec.md) · [tasks](002-front-door/tasks.md) |

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
| Update the GitHub About box + topics (text in `docs/listing.md`) | now | 📋 |
| Directory listings: follow `docs/listing.md` (mcp.so, mcpservers.org, LobeHub CLI, cursor.directory; claim Glama) | now | 📋 |
| `npx skills add Arkanji/iwork-studio --skill iwork-studio` once (skills.sh listing; feeds the Hermes Skills Hub) | now | 📋 |
| Turn on GitHub Discussions | now | 📋 |
| Add the `TRAFFIC_TOKEN` secret (fine-grained, Administration: read) for the weekly traffic snapshot | now | 📋 |
| Live Mac check for each release (aqua tests + probes) | each release | — |
| Launch posts (Show HN, r/ClaudeAI, r/macapps, Arabic X/LinkedIn) | after 004 + 005 | 📋 |
| awesome-mcp-servers listing | — | ✅ merged 2026-10-08 |

## Waiting on a live check (⏳)

| What | Command (on the Mac, repo on the branch) | Proves | Result |
|---|---|---|---|
| 002 Numbers chart probe | `uv run python scripts/probe_numbers_chart.py` | whether Numbers' scripting dictionary can add a chart (no UI scripting) | — first run wrote no result file; re-run on its own. README now says "not reliably scriptable" until proven |
| 001 trust patch | `uv run --extra test pytest -m aqua -k "trust or pages or sort or formula or keynote_slides"` | open-file refusal on real Numbers; Pages replace keeps other paragraphs' formatting; app routes still pass with the new runner and backup folder | ✅ 2026-10-13: all pass. A first run hit -1712 on Pages template creation; same tests passed on old and new code once a Pages dialog was cleared (environmental). -1712 now maps to AppTimeoutError |

## Re-analyse (decisions to revisit with new evidence)

| Item | Why it's here | Revisit when |
|---|---|---|
| Pages per-paragraph replace keeps formatting (trap P3 "agrees, partly") | Whole feature 001-US2 rests on it; fallback is refuse-unless-`reset_formatting` | after the live check |
| Numbers chart creation | A competitor claims a workaround; we say it isn't reliably scriptable | after the 002 probe |
| Backup location moved out of synced folders | Users who look for `<file>.backups` in Finder | after a release cycle; consider a "show backups" helper |
| Open-document guard cost | One app query per write when the app runs | if users report slowness |
| Formula checks on comma-decimal locales | Untested; may false-fail | after a live check on such a locale |
| Hermes plugin vs skills.sh only | Small audience; skills.sh may be enough | after 30-day metrics |
| keynote_slides / pages_io runners on `safety.run_jxa` | They carry no secrets, so they kept their own timeout handling in 2.6.1 | next time those modules change |
| Same-second backup numbering | Found by the new prune test and fixed (never reuse a pruned name) | — (fixed, keep the test) |

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
- 2026-10-12: 001 built (36 regression tests); 002 mostly built. Examples made neutral, with a guard test. New bug found by the prune test: same-second backups reused pruned names (fixed).
- 2026-10-13: v2.6.1 released (trust patch + front door + demo).
