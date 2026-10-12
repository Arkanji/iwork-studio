# Feature Specification: Front door

**Feature Branch**: `roadmap-2.7`

**Created**: 2026-10-12

**Status**: Draft

**Target release**: v2.6.2

**Input**: PM/CPO review. The product is far ahead of its reach. In 14 days: 2 stars, 59 unique visitors, 0 Desktop-extension downloads. The README leads with feature counts. The GitHub About box is stale. There are no sample files, no issue templates and no way to see traffic over time. A competitor ships a Numbers chart workaround that we claim is impossible.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A stranger understands it in 10 seconds (Priority: P1)

A Mac user lands on the README from a directory listing. The first screen tells them what it does for them: designed decks from their data, safely, Arabic-ready. It shows it in motion (the GIF from feature 004) and gives one install line for their app. Feature and tool counts move below the fold.

**Independent Test**: the first screen of the README holds an outcome headline, the demo, three messages (safe / designed / Arabic) and the install table. It doesn't mention tool or test counts.

**Acceptance Scenarios**:

1. **Given** the README, **When** read top to bottom, **Then** the first heading after the banner states the outcome, and the install table appears within the first screen.
2. **Given** any claim about Apple limits, **Then** it says "not reliably scriptable; we refuse rather than risk your file" or cites a probe. It never says "impossible" without evidence.

---

### User Story 2 - First success with zero files of their own (Priority: P1)

A new user has no Numbers or Keynote file handy. The capabilities tool and README offer three "try it now" prompts. A bundled sample (synthetic sales data) can be copied to a folder they choose. One prompt turns that sample into a designed deck.

**Independent Test**: from a clean install, one tool call copies the samples into a chosen folder (never overwriting). Following the "try it now" prompt produces a deck on a Mac.

**Acceptance Scenarios**:

1. **Given** a folder, **When** the agent calls the sample tool, **Then** `sample-sales.numbers` and `sample-outline.md` appear there, and existing files are never overwritten.
2. **Given** `iwork_capabilities`, **Then** it returns `try_it` prompts, the folder fence in force, whether Automation permission is known, app versions, and, on non-Mac systems, which toolsets can actually run.

---

### User Story 3 - The owner can see what's working (Priority: P2)

GitHub keeps only 14 days of traffic. A scheduled workflow saves weekly snapshots of views, referrers, clones and release downloads into a data branch. Issue templates make it easy for users to report a refusal, ask for a capability or show a deck.

**Acceptance Scenarios**:

1. **Given** the weekly workflow, **When** it runs, **Then** a dated JSON snapshot is committed to a `traffic-data` branch. It needs no secrets beyond the default token, or it documents the one it needs.
2. **Given** a user opens a new issue, **Then** three templates are offered: "It refused my file", "Request a capability", "Show your deck".

---

### User Story 4 - Listed where people look (Priority: P2)

A listing kit (one file) holds the title, short and long descriptions, tags, a screenshot list and the install lines. The owner can paste it into mcp.so, PulseMCP, Smithery, the Cursor directory, LobeHub, mcpservers.org and the GitHub About box. The README shows how to add the skill with `npx skills add`.

**Acceptance Scenarios**:

1. **Given** `docs/listing.md`, **Then** it has copy-ready text for each directory, within each one's length limits, and uses no personal names.

---

### User Story 5 - Settle the Numbers chart question (Priority: P3)

A probe script tests, on a throwaway copy, whether a chart can be added to a Numbers sheet through scripting (not UI scripting). The README wording then follows the result.

**Acceptance Scenarios**:

1. **Given** the probe run on a Mac, **Then** its result is recorded in `jxa-traps.md`, and the README claim matches it.

### Edge Cases

- Sample target folder outside the fence → refused.
- Sample files already exist → skipped and reported, never overwritten.
- Traffic API not permitted to the workflow token → the workflow fails loudly with a documented fix.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The README first screen MUST lead with the outcome and the three messages (safe, designed, Arabic). It MUST NOT lead with tool or test counts.
- **FR-002**: Apple-limit claims MUST be worded per Constitution II.
- **FR-003**: A `iwork_samples` tool (files toolset) MUST copy bundled synthetic samples to a fenced folder without overwriting.
- **FR-004**: `iwork_capabilities` MUST report `try_it` prompts, the fence, Automation status if known, app versions, and per-toolset runnability on this OS.
- **FR-005**: The repo MUST include issue templates (3) and a weekly traffic-snapshot workflow.
- **FR-006**: `docs/listing.md` MUST provide copy-ready directory listings and GitHub About text and topics.
- **FR-007**: A probe `scripts/probe_numbers_chart.py` MUST test chart creation via scripting on a temp copy only.

## Success Criteria *(mandatory)*

- **SC-001**: README first screen passes the 10-second test (owner review): outcome, demo, install.
- **SC-002**: A new user reaches a designed deck from the sample in ≤ 3 prompts (owner check on a Mac).
- **SC-003**: Traffic snapshots accumulate weekly without manual steps.
- **SC-004**: Listed on ≥ 6 directories within 2 weeks of release (owner action, tracked in ROADMAP).

## Assumptions

- Directory submissions and the GitHub About box are owner actions; we provide the copy.
- GitHub Discussions is a repo setting the owner turns on.
- The demo GIF comes from feature 004.
