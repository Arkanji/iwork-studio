# TCC & Modal Preflight Playbook (Pages, applies to all iWork apps)

## Verified behavior (Phase D, live)

With EITHER of these on screen, EVERY AppleEvent to the app — even
`count of documents` — times out with error **-1712**:

1. First-launch **TCC consent** dialog ("Hermes wants to control Pages…")
2. The Pages **Open dialog / template chooser** modal

System Events UI reads still work; only AppleEvents to the app are blocked.
Dismissing the modal once (a single GUI click) instantly restores event
handling — verified live during Phase D: with the dialog up, `count of
documents` timed out; after one GUI dismissal, the whole route probed clean.

## The rule

An AppleEvent timeout (-1712) does NOT mean "retry harder". It means
**a human must look at the screen ONCE**. Therefore:

- Run `pages_io.preflight()` (CLI: `edit_pages.py preflight`) before any
  Pages op. It returns `{"ok": true, "documents": N}` or raises
  `PagesUnavailableError` with exactly one actionable prompt:
  dismiss the modal / approve the TCC dialog.
- NEVER retry-loop on -1712. One prompt, fail loud, surface to the operator.
- TCC consent is one-time per app per controlling host; after approval it
  never reappears on this machine.
- Headless (no Aqua session at all) raises `AquaSessionError` earlier —
  also fail-loud with guidance (SC4: never silently).

## Dismissing the modal programmatically is out of scope

The verified protocol is: detect (-1712) → prompt the human once → they
click → proceed. Automating the click was considered and rejected: TCC
dialogs are deliberately resistant to synthetic clicks, and the Pages
template chooser is an app-modal UI — a human's single click is the
reliable path (re-verified live in Phase D).

## Keynote / Numbers

Same class of issue on first-ever automation of each app; the TCC consent
appears once per app. The .key/.numbers primary routes are pure-Python
(no AppleEvents) so they are immune; only render-verify and the Keynote
AppleScript fallback touch events — if those time out with -1712, apply the
same one-prompt rule.