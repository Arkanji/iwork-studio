# Tasks: Trust patch (v2.6.1)

**Input**: `specs/001-trust-patch/` (spec.md, plan.md)

**Tests**: required by the constitution (headless regression test per fix; live check where app-driven)

## Phase 1: Foundation (blocks all stories)

- [ ] T001 Create `src/iwork_studio/safety.py`: `run_osascript` (script on stdin, timeout → `AppTimeoutError`, no script text in errors), `assert_not_open(path)`, `AutomationDeniedError`
- [ ] T002 Grow `src/iwork_studio/backups.py`: `backup_dir_for` (private root), `legacy_dir_for`, `make_backup(target, bdir=None, keep=10, check_open=True)`, `prune(bdir, name, ext, keep)`
- [ ] T003 Tests for T001–T002 in `tests/test_trust_patch.py` (prune for every extension, naming, location, env override, no secrets in timeout errors)

## Phase 2: US1 + US3, open guard and bounded private backups (P1)

- [ ] T004 [US3] Route every writer's backup through `backups.make_backup` (numbers_io, numbers_format, numbers_structure, keynote_io, keynote_slides, keynote_theme, keynote_table, app_ops, pages_io, exporter); delete per-module `_prune_backups` and `_versioned_backup` (or keep them as thin delegates)
- [ ] T005 [US3] `list_backups` and `restore_backup` read both the new and the legacy folder; restore keeps its name rule; restore calls `assert_not_open`
- [ ] T006 [US1] Tests: every no-app write route refuses when `assert_not_open` raises, and the file stays byte-identical
- [ ] T007 [US3] Tests: 15 writes leave 10 backups for each extension; nothing created beside the file; legacy backups listed and restorable

## Phase 3: US2, Pages per-paragraph replace (P1)

- [ ] T008 [US2] `pages_io.replace_all`: refuse a find containing a newline, then per-paragraph JXA rewrite plus verification; result includes `replacements` and `paragraphs_rewritten`
- [ ] T009 [US2] Headless tests with stubbed JXA: only matching paragraphs are written; zero matches means no write; a newline in find is refused; Arabic paragraphs stay exact
- [ ] T010 [US2] Live aqua test: a styled document keeps the formatting of untouched paragraphs (owner runs it)

## Phase 4: US4–US6 (P2)

- [ ] T011 [US4] `mcp_server.keynote_build_deck`: resolve and fence `image`, `chart.from` and `table.from` relative to the deck; tests
- [ ] T012 [US5] `numbers_io.edit_cell`: read the edited cell back, compare it with the request, roll back on mismatch, report the read-back value; tests (stubbed writer stores the wrong value)
- [ ] T013 [US6] Use `safety.run_osascript` in app_ops, exporter, keynote_slides and pages_io; close the document best-effort on timeout before restoring; tests that no password appears in argv or errors

## Phase 5: US7–US8 (P2/P3)

- [ ] T014 [US7] `installer.SOURCE` → `iwork-studio==<version>`; `install.sh` → `uvx --from iwork-studio@latest`; README, AGENTS, mcp_server docstring and llms.txt install lines use PyPI; test
- [ ] T015 [US8] Server instructions name the writes without `dry_run`; hints for `AutomationDeniedError` and `AppTimeoutError`; remove the employer name from README examples (neutral "Acme"); a test fails if it reappears

## Phase 6: Polish and release

- [ ] T016 Docs: CHANGELOG 2.6.1, README safety section (backup location and env), capability matrix, jxa-traps (P3 confirmed or not), AGENTS rules
- [ ] T017 Bump to 2.6.1 in every version file; ruff and the headless suite green
- [ ] T018 Owner live check on the Mac: aqua tests (`-k "trust or pages or sort or formula"`), then record the result in `specs/ROADMAP.md`
- [ ] T019 Merge, tag v2.6.1, verify PyPI, Registry, GitHub release and plugin

## Dependencies

T001–T003 come first. T004–T007, T008–T010 and T011–T013 can then proceed in parallel. T016–T019 come last. T010 and T018 need the owner's Mac.
