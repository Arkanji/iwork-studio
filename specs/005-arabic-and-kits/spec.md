# Feature Specification: Arabic front door and more design kits

**Feature Branch**: `roadmap-2.7`

**Created**: 2026-10-12

**Status**: Draft

**Target release**: v2.8.0

**Input**: Arabic/RTL is the most defensible segment; no competitor serves it. Yet all the docs are English-only, there are only 6 design kits, and new Pages paragraphs come out left-to-right.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An Arabic speaker gets the whole story in Arabic (Priority: P1)

`README.ar.md` explains the product, install and three example prompts in natural Arabic. The English README links to it at the top.

**Acceptance Scenarios**:

1. **Given** the README, **Then** a link «العربية» sits next to the title.
2. **Given** README.ar.md, **Then** it covers what it does, install per app, try-it prompts and safety. Its direction renders right-to-left on GitHub (`<div dir="rtl">`).

---

### User Story 2 - Twelve kits, Arabic-first options (Priority: P1)

Six new kits join the existing six. At least two are Arabic-first, with an Arabic display font and RTL-friendly layouts. Every kit passes the contrast check and works for decks and tables.

**Acceptance Scenarios**:

1. **Given** `iwork_list_design_kits`, **Then** 12 kits are listed, each with a one-line "use it for".
2. **Given** each kit, **Then** its text/background contrast is ≥ 4.5:1 (existing check) and fonts fall back to fonts bundled with macOS.

---

### User Story 3 - Arabic paragraphs in Pages read right-to-left (Priority: P2)

When `pages_set_body` writes Arabic paragraphs, they come out right-aligned and right-to-left. A live probe must first confirm this can be scripted.

**Acceptance Scenarios**:

1. **Given** the probe confirms a scriptable paragraph-direction property, **Then** Arabic paragraphs are set RTL and verified on render.
2. **Given** the probe shows it can't be scripted, **Then** the limit is documented and the tool's result warns.

### Edge Cases

- Mixed Arabic/English paragraphs: direction follows the first strong character.
- A user's own kit with an Arabic font missing on the Mac: fall back and report.

## Requirements *(mandatory)*

- **FR-001**: README.ar.md MUST exist and be linked from README.md.
- **FR-002**: 6 new kits MUST be added. Each MUST pass contrast and have Latin + Arabic fonts that ship with macOS.
- **FR-003**: A probe MUST test Pages paragraph direction. The tool MUST use it only if the probe is proven.

## Success Criteria *(mandatory)*

- **SC-001**: 12 kits listed; 2+ Arabic-first.
- **SC-002**: Arabic README reviewed by a native speaker (owner).
- **SC-003**: Arabic-source referrers appear in the traffic snapshots after launch.

## Assumptions

- macOS ships Arabic fonts usable by kits (e.g. Geeza Pro, SF Arabic, Baghdad, Damascus); IBM Plex Sans Arabic is only used when installed, with a fallback.
