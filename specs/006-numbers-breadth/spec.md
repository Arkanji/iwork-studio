# Feature Specification: Numbers breadth and opt-in feedback

**Feature Branch**: `roadmap-2.7`

**Created**: 2026-10-12

**Status**: Draft

**Target release**: v2.8.x

**Input**: Gap audit. The parser already supports real dates and durations, sheet and table renames, checkbox/star/pop-up cells, captions and true cell clearing, but our tools don't expose them. The owner can't learn what fails for users without telemetry. Hermes users would benefit from a portable plugin.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Real dates, renames, clear (Priority: P1)

An agent writes a real date (not text) into a cell, renames a sheet or table, and clears a cell. Each change is verified and can be undone.

**Acceptance Scenarios**:

1. **Given** `numbers_edit_cell(value="2026-10-12", type="date")`, **Then** the cell is a date and reads back as one.
2. **Given** `numbers_rename(sheet="Sheet 1", to="Q3")`, **Then** only that name changes. Formulas that reference the old name are checked, and the rename is refused if they would break.
3. **Given** `value=null`, **Then** the cell is empty, not an empty string.

---

### User Story 2 - Interactive cells (Priority: P3)

Checkbox and star-rating cells can be set where the parser supports them.

---

### User Story 3 - Feedback without telemetry (Priority: P2)

A user who hits a refusal can run `iwork_feedback`. It shows a local summary of recent tool errors (counts and error types only; no file names or contents) and opens a pre-filled GitHub issue. Nothing is sent automatically.

**Acceptance Scenarios**:

1. **Given** errors occurred, **When** `iwork_feedback` runs, **Then** it returns the summary and an issue URL with that summary pre-filled. No network call is made by the tool.
2. **Given** `IWORK_STUDIO_STATS=0`, **Then** nothing is recorded.

---

### User Story 4 - Hermes portable plugin (Priority: P3)

`plugin.json`, `mcp.json` and `skills/iwork-studio` at the repo root let `hermes plugins install Arkanji/iwork-studio` install the tools and the skill. A catalog entry draft is prepared for the owner.

### Edge Cases

- Renaming to a name that already exists → refused.
- Stats file unwritable → feedback still works with no history.

## Requirements *(mandatory)*

- **FR-001**: Date/duration typed writes, rename, clear, and checkbox/star cells (where the parser supports them) MUST ride the write protocol.
- **FR-002**: `iwork_feedback` MUST be opt-out-able, local-only, and contain no file names, paths or content.
- **FR-003**: Hermes portable plugin files MUST validate with `hermes plugins validate` (owner or CI).

## Success Criteria *(mandatory)*

- **SC-001**: Dates round-trip as dates (tests).
- **SC-002**: The feedback summary contains no paths or content (tests).

## Assumptions

- Homebrew tap and docs site stay deferred until there are users (tracked in ROADMAP, not specced).
