# Feature Specification: Show it (demo GIF + gallery)

**Feature Branch**: `roadmap-2.7`

**Created**: 2026-10-12

**Status**: In progress (GIF in production)

**Target release**: v2.6.2 (GIF) / v2.7.x (gallery)

**Input**: The design quality only sells if people see it. There is no demo GIF at the top of the README and no gallery of decks the tool made.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See it in 15 seconds (Priority: P1)

A visitor sees a short, premium animation at the top of the README: a prompt becomes a designed deck from a table, a write is verified and rolled back safely, and the slide flips to Arabic RTL. It ends on the install line.

**Independent Test**: `assets/demo.gif` (≤ 4 MB, sharp text, loops cleanly) and `assets/demo.mp4` exist. The GIF is built from source in `assets/demo/` with HyperFrames and can be rebuilt with one documented command.

**Acceptance Scenarios**:

1. **Given** the README on GitHub, **Then** the GIF loads at the top and reads clearly at 800 px.
2. **Given** the source, **When** the documented render command runs, **Then** the GIF and MP4 are regenerated.
3. **Given** the frames, **Then** they contain no real company or person names and no Apple logos.

---

### User Story 2 - A gallery that proves the design (Priority: P2)

A `gallery/` page shows 4–6 decks and tables made by the tool from synthetic data. It includes an Arabic one and a before/after restyle, each with the outline or prompt that made it.

**Acceptance Scenarios**:

1. **Given** the gallery, **Then** every image has the prompt or outline that produced it and the kit used.
2. **Given** the scripts, **When** the owner runs them on a Mac, **Then** the gallery images regenerate.

### Edge Cases

- GIF too large → reduce fps or width, never text sharpness below legibility.
- Arabic shaping must render correctly (no broken ligatures, correct RTL order).

## Requirements *(mandatory)*

- **FR-001**: The demo GIF and MP4 MUST be reproducible from `assets/demo/` with a documented command.
- **FR-002**: The README MUST show the GIF above the fold.
- **FR-003**: `scripts/make_gallery.py` MUST build the gallery decks from synthetic data and export slide images (Mac).

## Success Criteria *(mandatory)*

- **SC-001**: GIF ≤ 4 MB, 12–15 s, legible at 800 px.
- **SC-002**: Gallery with ≥ 4 items, including one Arabic and one restyle.

## Assumptions

- Gallery rendering needs the owner's Mac (Keynote export).
