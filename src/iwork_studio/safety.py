"""iWork Studio — guards every write shares.

  run_jxa(app_kind, body, params, timeout)   run JavaScript for Automation with the script and
                                             its parameters on stdin (never on the command
                                             line, where `ps` shows them); a timeout becomes
                                             AppTimeoutError with no script text in it
  assert_not_open(path)                      refuse when Numbers/Keynote/Pages has this exact
                                             file open: a change made beside the app would be
                                             overwritten by the app's next save

On anything but macOS (or with no GUI session) no app can have the file open, so the
check passes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

__all__ = ["run_jxa", "close_without_saving", "assert_not_open", "AppTimeoutError", "AutomationDeniedError",
           "APP_FOR_EXT"]

APP_FOR_EXT = {".numbers": "Numbers", ".key": "Keynote", ".pages": "Pages"}


class AppTimeoutError(TimeoutError):
    """The app didn't answer in time. Nothing was changed (the write was rolled back)."""


class AutomationDeniedError(PermissionError):
    """macOS won't let iWork Studio script this app (System Settings → Privacy & Security → Automation)."""


def _script(app: str, body: str, params: dict) -> str:
    # Parameters travel inside the script, and the script travels on stdin.
    return ("function run() {\n  const params = JSON.parse(" + json.dumps(json.dumps(params, ensure_ascii=False))
            + ");\n  const app = Application(" + json.dumps(app) + ");\n" + body + "\n}")


def run_jxa(kind: str, body: str, params: dict, timeout: int = 300, *, raw: bool = False):
    """Run `body` (JavaScript with `params` and `app` defined) against Numbers/Keynote/Pages.
    Returns the parsed JSON the body returns (or the raw stdout when raw=True)."""
    from iwork_studio.apps import app_name

    name = app_name(kind)
    try:
        r = subprocess.run(["osascript", "-l", "JavaScript"], input=_script(name, body, params),
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise AppTimeoutError(f"{kind} didn't answer within {timeout} s. A dialog may be open in {kind}; "
                              "bring it to the front and dismiss it, then try again.") from None
    if r.returncode != 0:
        err = r.stderr.strip()
        if "-1743" in err or "Not authorized to send Apple events" in err:
            raise AutomationDeniedError(
                f"macOS isn't letting iWork Studio control {kind}. Allow it in System Settings → Privacy & "
                "Security → Automation (your AI app → " + kind + "), then try again.")
        raise RuntimeError(f"{kind} scripting failed (rc={r.returncode}): {err[:500]}")
    out = r.stdout.strip()
    return out if raw else json.loads(out or "{}")


def close_without_saving(kind: str, path: str | os.PathLike, timeout: int = 30) -> None:
    """Best effort, after a timeout: close this one document without saving, so a rollback
    doesn't swap the file underneath an open window. Never raises."""
    try:
        run_jxa(kind, """  app.documents().forEach(d => { try { const f = d.file(); if (f && f.toString().replace(/\\/$/, '') === params.path)
    app.close(d, {saving: 'no'}); } catch (e) {} });
  return JSON.stringify({});""", {"path": str(path).rstrip("/")}, timeout=timeout)
    except Exception:  # noqa: BLE001 — cleanup must never mask the real error
        pass


def _gui_session() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        from iwork_studio.keynote_slides import _assert_aqua

        _assert_aqua()
        return True
    except Exception:  # noqa: BLE001 — no GUI session: no app can hold the file open
        return False


def _open_paths(kind: str) -> list[str]:
    """Paths of the documents `kind` has open; [] when it isn't running (it is never launched)."""
    out = run_jxa(kind, """  if (!app.running()) return JSON.stringify({paths: []});
  const paths = [];
  app.documents().forEach(d => { try { const f = d.file(); if (f) paths.push(f.toString()); } catch (e) {} });
  return JSON.stringify({paths: paths});""", {}, timeout=30)
    return out.get("paths") or []


def assert_not_open(path: str | os.PathLike) -> None:
    """Raise DocumentOpenError when the owning app has this exact file open."""
    p = Path(path)
    kind = APP_FOR_EXT.get(p.suffix.lower())
    if kind is None or not _gui_session():
        return
    from iwork_studio.apps import CreatorStudioUnverifiedError

    try:
        paths = _open_paths(kind)
    except (CreatorStudioUnverifiedError, FileNotFoundError):
        return
    except AppTimeoutError:
        raise AppTimeoutError(f"{kind} didn't answer when asked whether {p.name} is open. A dialog may be "
                              f"open in {kind}; dismiss it and try again. Nothing was changed.") from None
    except RuntimeError as exc:
        if "can't be found" in str(exc).lower() or "-1728" in str(exc):
            return  # the app isn't installed: nothing can have the file open
        raise
    want = os.path.realpath(p)
    if any(os.path.realpath(q.rstrip("/")) == want for q in paths):
        from iwork_studio.keynote_slides import DocumentOpenError

        raise DocumentOpenError(f"{p.name} is open in {kind}. Save and close it first: a change made now would "
                                f"be overwritten the next time {kind} saves. Nothing was changed.")
