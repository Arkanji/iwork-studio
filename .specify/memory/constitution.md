<!--
Sync Impact Report
- Version change: template (unfilled) → 1.0.0
- Principles defined: I. Never Damage a User's File; II. Verified, Honest Claims; III. Tests Prove It;
  IV. Agent-First Ergonomics; V. Privacy and Local-Only; VI. Arabic/RTL First-Class
- Added sections: Additional Constraints; Development Workflow; Governance
- Removed sections: none
- Templates: plan/spec/tasks templates read this file at runtime; no template edits needed
- Deferred TODOs: none
-->

# iWork Studio Constitution

## Core Principles

### I. Never Damage a User's File (NON-NEGOTIABLE)

Every write MUST ride the write protocol: versioned backup → change a scratch copy → re-read and
compare that exactly the requested change happened and nothing else changed → atomic `os.replace`
→ rollback on any mismatch. A tool that cannot prove its result MUST refuse rather than guess.
Risky workarounds are forbidden: no UI scripting, no lossy round-trip conversion (docx/pptx/xlsx
and back), no AppleScript `save in`, and never bypass a `ChartRefusalError` or other refusal.
A write MUST NOT be silently undone by the app (e.g. an open document saved over our change).
Rationale: safety is the product's reason to exist; one damaged file costs more trust than any
feature earns.

### II. Verified, Honest Claims

Tools MUST report what they read back from the file, not what was requested. README, tool
descriptions, server instructions and listings MUST only claim behaviour that is tested. Apple
limits MUST be stated precisely ("not reliably scriptable; we refuse rather than risk your file"),
never overstated. Rationale: agents and users act on our words; a wrong claim is a bug.

### III. Tests Prove It

Every write route MUST have headless tests that stub the app and prove the rollback. CI runs
`uv run --extra test pytest -m "not aqua"` and `ruff check src tests scripts`; both MUST pass.
App-driven behaviour MUST have a live `aqua` test or a probe run on a Mac before release; probe
scripts live in `scripts/probe_*.py` and write results only to `~/.iwork-studio/probes/`.
A bug found in the field MUST get a regression test that would have caught it.

### IV. Agent-First Ergonomics

A job MUST take as few tool calls as practical (batch where a loop of calls would be slow).
Every tool and parameter MUST be described with when to use it and its sibling alternatives.
Errors MUST be typed and carry a hint the agent can act on. Every write on an existing file
SHOULD take `dry_run`; where it doesn't, the docs MUST say so. Toolsets MUST let a client load
only what it needs. Large reads MUST be bounded (paging/limits) so they never flood a context.

### V. Privacy and Local-Only

Nothing leaves the machine by default: no telemetry; any feedback mechanism is opt-in and shows
the user what it would send. The repository MUST contain no personal data: no names, employers,
hostnames, home paths or machine logs; examples use neutral names. The folder fence
(`IWORK_STUDIO_ROOTS`) MUST be enforced on every path a tool reads or writes, including indirect
ones (images, data sources, outputs). Backups MUST be bounded and kept out of synced folders.

### VI. Arabic/RTL First-Class

Arabic text MUST round-trip exactly through every route. RTL output MUST be checked as rendered
(assert one Arabic word in render checks). Design kits and docs MUST treat Arabic as a primary
audience, not an afterthought.

## Additional Constraints

- Python 3.12; dependency pins in `pyproject.toml` MUST equal `skill-pack/references/pins.txt`.
- `src/iwork_studio/mcp_server.py` MUST never print to stdout (it is the MCP wire).
- The version MUST agree across pyproject, `__init__`, server.json, mcpb/manifest.json, the
  plugin manifest and pin, SKILL.md metadata, llms.txt and uv.lock (a test enforces it).
- README, CHANGELOG, AGENTS.md and the capability matrix MUST be updated before every release.
- Known scripting traps are recorded in `skill-pack/references/jxa-traps.md`; new traps found
  by probes MUST be added there.

## Development Workflow

1. Feature branch off `main`; the spec lives in `specs/NNN-name/` (spec → plan → tasks).
2. Tests first for every write route, then implementation; lint and the headless suite green.
3. App-driven changes: the owner runs the live check on a Mac (aqua tests or a probe) and the
   result is recorded in the roadmap tracker before release.
4. Merge to `main`, CI green, release by tag (`vX.Y.Z`); delete the merged branch.
5. The roadmap tracker (`specs/ROADMAP.md`) records what is done, what is waiting on a live
   check, and what must be re-analysed.

## Governance

This constitution supersedes other practice in this repository; AGENTS.md is the runtime guide
and MUST stay consistent with it. Amendments are made by editing this file with a version bump:
MAJOR for removing or redefining a principle, MINOR for a new principle or materially expanded
guidance, PATCH for clarifications. Every spec's plan MUST include a Constitution Check against
these principles, and any justified exception MUST be recorded in that plan's Complexity Tracking.

**Version**: 1.0.0 | **Ratified**: 2026-10-12 | **Last Amended**: 2026-10-12
