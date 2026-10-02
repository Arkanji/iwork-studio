"""iWork Studio — app-name resolution (classic iWork vs "Creator Studio").

iWork 15.1+ can ship as separate "<App> Creator Studio.app" bundles
(upstream ground truth: reichenbach/iwork_mcp, tested 15.1.1). A hardcoded
Application('Pages') then drives the wrong app — or nothing.

Resolution order (evidence-first):
  1. IWORK_STUDIO_<APP>_APP env override (exact app name) — operator pin
  2. the classic bundle "<App>.app" if installed — the VERIFIED route
     (capability matrix: iWork 15.4 build 7051.0.79)
  3. "<App> Creator Studio.app":
     - Keynote: ALLOWED — open/in-place save/close + PDF export observed
       working on Keynote Creator Studio 15.3.1 (live, 2026-10-02: slide ops
       7/7, aqua suite PASS).
     - Pages: ALLOWED — preflight, read, replace_all, set_body (in-place
       save) and PDF export observed working on Pages Creator Studio
       (live aqua suite, 2026-10-02).
     - Numbers: refused with CreatorStudioUnverifiedError until probed. Its
       only app route is render-verify (PDF export); the old AppleScript
       export timed out on Numbers Creator Studio (live, 2026-10-02) and
       has been replaced by the JXA form. IWORK_STUDIO_ALLOW_CREATOR_STUDIO=1
       opts in, for probing. (Numbers reads/edits never need the app.)
  4. nothing found → the classic name; the app route then fails loud as
     before (AquaSessionError / JXA error).

Resolution is lazy (per call), so importing on Linux/headless never fails.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["app_name", "app_bundle_candidates", "CreatorStudioUnverifiedError"]

IWORK_APPS = ("Numbers", "Pages", "Keynote")
_APP_DIRS = ("/Applications", "~/Applications")
# Creator Studio apps whose open → in-place save → close loop has been
# observed working live. Add one only with a passing live probe.
CREATOR_STUDIO_OBSERVED = frozenset({"Keynote", "Pages"})


class CreatorStudioUnverifiedError(RuntimeError):
    """Only the Creator Studio bundle is installed and it has not passed the
    iWork Studio probes (save/export are reported broken upstream)."""


def app_bundle_candidates(app: str) -> dict[str, bool]:
    """Which bundles exist for `app`: {"classic": bool, "creator_studio": bool}."""
    found = {"classic": False, "creator_studio": False}
    for root in _APP_DIRS:
        base = Path(os.path.expanduser(root))
        if (base / f"{app}.app").exists():
            found["classic"] = True
        if (base / f"{app} Creator Studio.app").exists():
            found["creator_studio"] = True
    return found


def app_name(app: str) -> str:
    """Resolve the scripting name for Numbers / Pages / Keynote."""
    if app not in IWORK_APPS:
        raise ValueError(f"unknown iWork app {app!r}; expected one of {IWORK_APPS}")
    override = os.environ.get(f"IWORK_STUDIO_{app.upper()}_APP")
    if override:
        return override
    found = app_bundle_candidates(app)
    if found["classic"] or not found["creator_studio"]:
        return app
    if app in CREATOR_STUDIO_OBSERVED or os.environ.get("IWORK_STUDIO_ALLOW_CREATOR_STUDIO") == "1":
        return f"{app} Creator Studio"
    raise CreatorStudioUnverifiedError(
        f"only '{app} Creator Studio.app' is installed. It is not verified for "
        "iWork Studio: upstream (reichenbach/iwork_mcp, 15.1.1) reports in-place "
        "save hangs on a modal and export fails with error 6 — the two calls "
        "every app route here depends on. Install classic "
        f"{app} from the App Store, or set IWORK_STUDIO_ALLOW_CREATOR_STUDIO=1 "
        "to run the probes first."
    )
