# Feature Specification: Agent efficiency

**Feature Branch**: `roadmap-2.7`

**Created**: 2026-10-12

**Status**: Draft

**Target release**: v2.7.0

**Input**: Gap audit. Adding a slide takes 3 full open/save/verify cycles. Reordering is one slide per call. 50 cell edits take about 10 minutes on a large table. `iwork_read` returns 10.6 MB for a 3,000-row table and orders Keynote slides by internal file name. Formula errors read as "ok". Comma-decimal locales are untested.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One call per slide (Priority: P1)

An agent adds a slide with a chosen layout, title, body and notes in one call. It reorders several slides in one call.

**Independent Test**: `keynote_add_slide(layout=…, title=…, body=[…], notes=…)` produces the slide in one open/save cycle, verified. `keynote_move_slide(order=[3,1,2,…])` applies a full new order in one cycle.

**Acceptance Scenarios**:

1. **Given** a deck, **When** add_slide is called with layout + text, **Then** one slide is added with exactly that layout and text, and every other slide is unchanged.
2. **Given** a new order that is a permutation of 1..N, **When** move is called, **Then** the deck matches that order. A non-permutation is refused.

---

### User Story 2 - Many cells in one call (Priority: P1)

An agent writes many cells (values, or formulas through the app) in one call, with every cell verified and one backup.

**Acceptance Scenarios**:

1. **Given** `numbers_edit_cells(cells={"B2": 10, "C9": "text", …})` (no app), **Then** all cells are written in one swap, each is read back and every other cell is unchanged.
2. **Given** a batch containing one bad reference, **Then** nothing is written.
3. **Given** a batch of formulas, **When** `numbers_set_formula` gets `cells={…}`, **Then** Numbers sets them in one open/save and each is verified.

---

### User Story 3 - Reads that fit in context (Priority: P1)

`iwork_read` accepts sheet, table, range and a cell limit, skips empty cells and styles by default, and reports truncation. Keynote reads list slides in presentation order with slide numbers.

**Acceptance Scenarios**:

1. **Given** a 3,000×8 table, **When** read with defaults, **Then** the response is at most 200 KB and says how to page.
2. **Given** a .key file, **When** read, **Then** each slide has its 1-based number in deck order.

---

### User Story 4 - Formulas that tell the truth (Priority: P2)

A formula that produces an error (#DIV/0!, #REF!) is reported as an error, not as "ok, result None". Sort and recalculate detect new errors. On a Mac set to a comma-decimal locale, formulas written with commas or semicolons are verified correctly.

**Acceptance Scenarios**:

1. **Given** `=A1/0`, **Then** set_formula returns `ok` with `error: "#DIV/0!"` (as Numbers reports it), or refuses if requested with `allow_errors=false`.
2. **Given** a recalculate that turns a formula into #REF!, **Then** it rolls back.
3. **Given** a comma-decimal locale (live check), **Then** `=SUM(B2:B4)` and `=B2*0,1`-style formulas verify.

### Edge Cases

- A batch larger than the limit (e.g. 2,000 cells) is refused with a hint to split it.
- A read range outside the table is refused with the table's size.
- add_slide with a layout the theme lacks → refused with the layout list (silent-drop trap S5 checked).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `keynote_add_slide` MUST accept optional `layout`, `title`, `body`, `notes`, applied and verified in one cycle.
- **FR-002**: `keynote_move_slide` MUST accept a full `order` permutation.
- **FR-003**: A batch cell write (no app) MUST verify every written cell by read-back and every other cell unchanged, with a single backup.
- **FR-004**: `numbers_set_formula` MUST accept a batch of cells.
- **FR-005**: `iwork_read` MUST support sheet/table/range/limit, MUST omit empty cells and styles unless asked, and MUST report truncation. Keynote slides MUST be in deck order with numbers.
- **FR-006**: Formula results MUST surface errors explicitly. Sort and recalculate MUST roll back on new errors.
- **FR-007**: Formula comparison MUST accept locale separators (`;`, decimal `,`) equivalently.

## Success Criteria *(mandatory)*

- **SC-001**: A 6-slide deck edit (add 3 slides with text) takes 3 calls instead of 9.
- **SC-002**: 50 cells on a 3,000-row table take under 30 s instead of about 10 min.
- **SC-003**: Default read of a 3,000×8 table is ≤ 200 KB.
- **SC-004**: 0 formula errors reported as plain success (tests).

## Assumptions

- Keynote's `make new slide with properties {base slide: …}` works per the existing probe (trap S5 checked live).
- The parser can read Numbers error cells as a distinguishable type (to confirm; otherwise ask the app).
