# GATE-SAVE — The AppleScript `save in` Sandbox Trap

## Ground truth

iWork apps (Numbers/Keynote/Pages 15.4) are sandboxed. From AppleScript/JXA:

| Save form | Result |
|---|---|
| `save in <arbitrary path>` | **DENIED** — sandbox refuses to write outside its container. Exact error text captured in Scout probe transcript. NEVER USE. |
| `save` (no path — in-place, file already on disk) | **VERIFIED WORKING** for all three apps (Numbers B-phase, Keynote C6, Pages D GATE-SAVE). The on-disk file updates: mtime changes, re-open readback exact, Arabic codepoints intact. |
| `export ... to Path(out) as 'PDF'/'Microsoft Word'/...` | **VERIFIED WORKING** — the safe route for producing artifacts outside the container. |

Phase D closure: `save in <arbitrary path>` for an on-disk .pages file remains
BANNED; `save in` used merely to NAME a new, never-saved document is not the
trap (verified in the Phase C Keynote fixture flow) — but prefer export anyway.

## The rule

1. To modify an existing file: open it, mutate, plain `save` (in-place), close.
2. To produce a PDF/docx artifact: `export` to the destination path, close
   without saving.
3. NEVER write `save in <path>` for an existing on-disk file. A script that
   does is a bug — fix it, don't retry it.

Helpers: `../scripts/save_paths.sh` (source it) provides
`iwork_check_no_save_in` (lints a script for the forbidden pattern),
`iwork_export_pdf` and `iwork_read_body` (JXA export/read templates that
follow this rule).

## Why in-place save is safe here

The write path is: versioned backup FIRST, then app-level edit, then readback
verification, then rollback on mismatch (EditVerificationError). In-place
`save` is the only form the app accepts for on-disk files, and the backup +
verify + rollback protocol bounds the blast radius of any in-app edit.