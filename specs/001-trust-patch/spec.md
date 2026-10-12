# Feature Specification: Trust patch

**Feature Branch**: `roadmap-2.7`

**Created**: 2026-10-12

**Status**: Draft

**Target release**: v2.6.1

**Input**: Gap audit and CPO review after v2.6.0: "make the safety promise true before
anything else". Edits made without the app can be silently overwritten; Pages find/replace
wipes formatting; backups grow without limit inside synced folders; one tool skips the folder
fence; the most-used write doesn't check the cell it edited; a timeout can leak an export
password; the installer runs unreleased code; docs overclaim dry_run; the README names an
employer.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An edit is never silently lost (Priority: P1)

A user has a spreadsheet open in Numbers and asks the agent to change a cell. Today the
tool edits the file on disk, reports success, and Numbers later saves its own open copy over
it, so the change disappears. After this feature, the tool sees the file is open and refuses
with a clear message asking the user to save and close it, exactly as the app-driven tools
already do.

**Why this priority**: the most likely real-world data loss; it breaks the core promise.

**Independent Test**: with the app reported as having the file open, every no-app write
refuses and the file is byte-identical afterwards.

**Acceptance Scenarios**:

1. **Given** a .numbers file open in Numbers, **When** the agent calls any no-app Numbers write
   (cell edit, formatting, structure, design), **Then** it refuses with `DocumentOpenError` and
   the file is unchanged.
2. **Given** a .key deck open in Keynote, **When** the agent calls `keynote_replace_text`,
   **Then** it refuses the same way.
3. **Given** a file open in its app, **When** the agent restores a backup, **Then** the
   restore refuses (the app would save over the restored file).
4. **Given** the app is not running or the file is not open, **When** the same writes run,
   **Then** they behave as before.

---

### User Story 2 - Find and replace keeps a Pages document's formatting (Priority: P1)

A user runs find/replace on a styled Pages report. Today every paragraph's formatting is
reset. After this feature, only paragraphs that contain the text are rewritten; every other
paragraph keeps its formatting, and the result says how many paragraphs were rewritten.

**Why this priority**: silent formatting loss on a common action is damage.

**Independent Test**: on a stubbed Pages document, only matching paragraphs are written; on
a Mac, a styled document keeps the formatting of untouched paragraphs.

**Acceptance Scenarios**:

1. **Given** a document where 2 of 40 paragraphs contain "2025", **When** replace "2025" →
   "2026" runs, **Then** exactly those 2 paragraphs are rewritten and the other 38 are untouched.
2. **Given** a find text that spans a paragraph break, **When** replace runs, **Then** it
   refuses with a hint (use `pages_set_body`), and nothing changes.
3. **Given** no paragraph contains the text, **When** replace runs, **Then** it reports zero
   replacements and does not write.

---

### User Story 3 - Backups are bounded and private (Priority: P1)

Every write leaves a backup. Today Numbers and Pages backups are never pruned and live next to
the file (often in iCloud-synced Desktop/Documents), so deleted content keeps syncing and disk
use grows. After this feature, backups go to a private local folder, the newest N per file are
kept for every file type, and older backups next to files are still listed and restorable.

**Why this priority**: privacy promise and disk/iCloud cost.

**Independent Test**: 15 writes leave exactly 10 backups for each of .numbers, .key and
.pages; no backup is created next to the file; legacy backups are listed and restorable.

**Acceptance Scenarios**:

1. **Given** 15 successive writes to one file, **When** listing backups, **Then** 10 remain.
2. **Given** a file in a synced folder, **When** it is written, **Then** no `<file>.backups`
   folder appears beside it.
3. **Given** an older `<file>.backups` folder from a previous version, **When** listing or
   restoring, **Then** those backups are found and restorable.
4. **Given** `IWORK_STUDIO_BACKUP_DIR` is set, **When** a write runs, **Then** backups go there.

---

### User Story 4 - The folder fence covers every path (Priority: P2)

A user fences the server to ~/Documents. Today a deck outline can pull images or data from
anywhere, and relative paths resolve against the server's working folder. After this feature,
every image, chart source and table source in a deck outline is resolved relative to the deck
and must be inside the fence.

**Independent Test**: an outline referencing a file outside the fence is refused before any
deck is created.

**Acceptance Scenarios**:

1. **Given** a fence and an outline with `image: /etc/hosts.png`, **When** building the deck,
   **Then** it refuses and no file is created.
2. **Given** an outline with `chart.from: "data.numbers"` (relative), **When** building a deck
   at `~/Documents/q3.key`, **Then** it reads `~/Documents/data.numbers`.

---

### User Story 5 - The edited cell is checked, and the result tells the truth (Priority: P2)

Today `numbers_edit_cell` checks every other cell but trusts the edited one, and reports the
requested value. After this feature it reads the edited cell back from the saved file, checks
it holds the requested value (with the type the request implies), and reports what it read.

**Independent Test**: a stub that stores a different value in the edited cell causes a
rollback; a normal edit returns the read-back value.

**Acceptance Scenarios**:

1. **Given** a request to set B2 = 1250, **When** the saved file holds 1250, **Then** the
   result reports `value: 1250` as read back.
2. **Given** the writer stored something else, **When** verifying, **Then** the write is
   rolled back with `WriteVerificationError`.

---

### User Story 6 - A slow app never leaks a secret or leaves a mess (Priority: P2)

Today when an app call times out, the error message contains the full script (including an
export password), the password is visible in the process list, and the document can be left
open in the app while the backup is restored under it. After this feature, timeouts become a
clear `AppTimeoutError` with no script text, passwords never appear on a command line, and the
document is closed before any rollback.

**Acceptance Scenarios**:

1. **Given** an export with a password that times out, **When** the error is returned,
   **Then** it contains neither the password nor the script.
2. **Given** a password export, **When** it runs, **Then** the password is not in the
   process arguments.
3. **Given** an app write that times out, **When** rolling back, **Then** the tool first asks
   the app to close that document without saving.

---

### User Story 7 - Installing runs released, tested code (Priority: P2)

Today the installer and README commands install from the GitHub main branch, which needs
Apple's developer tools for git and runs unreleased code. After this feature they install the
released package from PyPI.

**Acceptance Scenarios**:

1. **Given** a Mac without developer tools, **When** the user runs the installer, **Then** it
   completes without asking for them.
2. **Given** the installer writes the client config, **Then** the config pins the released
   version that wrote it.

---

### User Story 8 - The docs only promise what's true (Priority: P3)

The server instructions say every write takes `dry_run`, but some don't. The README uses an
employer's name in example prompts. After this feature, the docs name the writes without
`dry_run`, and examples use neutral names.

**Acceptance Scenarios**:

1. **Given** the server instructions, **Then** they list the writes that don't take `dry_run`.
2. **Given** the repository, **Then** no employer or personal name appears in examples.

### Edge Cases

- The app is running but scripting permission (Automation) is denied: the open check can't
  ask; the tool MUST refuse with a hint about Automation permission rather than write blind.
- Non-macOS machines: no app can have the file open; the check is skipped.
- Two documents with the same name in different folders: matching is by full resolved path.
- Backups of a file that is later renamed: old backups stay under the old name's folder.
- The private backup folder is not writable: the write refuses before touching the file.
- Pages paragraphs containing inline images or tables: only rewritten if they contain the
  find text; the result warns that inline formatting in rewritten paragraphs may reset.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every write that changes a file without the app MUST first check, on macOS,
  whether the owning app has that exact file open, and refuse with `DocumentOpenError` if so.
- **FR-002**: If the open check cannot run because Automation permission is denied, the
  write MUST refuse with a hint naming System Settings → Privacy & Security → Automation.
- **FR-003**: `pages_replace_all` MUST rewrite only the paragraphs that contain the find text,
  leave all other paragraphs untouched, refuse finds that contain a paragraph break, and
  report `replacements` and `paragraphs_rewritten`.
- **FR-004**: Backups MUST be written to a private local folder (default
  `~/.iwork-studio/backups/`, override `IWORK_STUDIO_BACKUP_DIR`), never beside the file.
- **FR-005**: Every write MUST keep at most `max_backups` (default 10) backups per file, for
  every file type.
- **FR-006**: Listing and restoring MUST include backups in both the new folder and the legacy
  `<file>.backups` folder; restore MUST still reject names that aren't backups of that file.
- **FR-007**: `keynote_build_deck` MUST resolve every image, `chart.from` and `table.from`
  relative to the deck's folder and refuse any outside `IWORK_STUDIO_ROOTS`, before creating
  anything.
- **FR-008**: `numbers_edit_cell` MUST read the edited cell back from the saved file, verify it
  matches the request, roll back on mismatch, and report the read-back value.
- **FR-009**: App calls that time out MUST raise `AppTimeoutError` whose message contains no
  script text or secrets, and MUST close the affected document without saving before rollback.
- **FR-010**: Export passwords MUST NOT be passed as command-line arguments.
- **FR-011**: The installer and documented install commands MUST install from PyPI; the
  installer MUST pin the version that wrote the config.
- **FR-012**: Server instructions MUST name the writes that don't take `dry_run`.
- **FR-013**: The repository MUST contain no employer or personal names in examples.

### Key Entities

- **Backup**: a copy of a file taken before a write; identified by file name + timestamp;
  stored per file in the private backup folder; bounded count.
- **Open-document check**: the answer to "does the app have this exact path open?"

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 no-app writes succeed while the app has the file open (headless tests cover
  every no-app write route).
- **SC-002**: A find/replace touching 2 of 40 paragraphs rewrites exactly 2 (headless) and
  untouched paragraphs keep their formatting on a Mac (live check).
- **SC-003**: After 15 writes, exactly 10 backups exist per file for each file type; 0 backups
  beside the file.
- **SC-004**: 0 paths outside the fence are read by deck building (tests).
- **SC-005**: 0 secrets appear in any error message or process argument (tests).
- **SC-006**: Install on a clean Mac completes without developer tools (owner check).
- **SC-007**: The headless suite and lint stay green; every fix has a regression test.

## Assumptions

- The app-driven tools' existing open-document check (by full path via scripting) is reliable
  and can be reused for no-app writes.
- Per-paragraph assignment in Pages keeps other paragraphs' formatting (trap P3, "agrees,
  partly"); this MUST be confirmed by the owner's live check before release. If it fails,
  `pages_replace_all` refuses formatted documents unless `reset_formatting=true`.
- Moving backups is backward-compatible because listing/restore read both locations.
- Out of scope: editing a document while it's open (Big Bet, later).
