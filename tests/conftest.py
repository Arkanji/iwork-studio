"""Phase B test fixtures.

Creates fresh .numbers files by copying verified fixtures generated from
numbers-parser 4.19.0 (tests/fixtures/). Fixtures are copied into the
pytest tmp dir per-test so tests never mutate the shared fixture files.

Fixture provenance:
- numbers_fixture_src     : copy of tests/fixtures/arabic.numbers
                            (Numbers 15.4 file, sheet 'بيانات', table 'جدول' 4x3,
                            Arabic + English + number cells)
- chart_fixture_src       : copy of tests/fixtures/chart.numbers
                            (built by make_chart_fixture.py via Numbers
                            AppleScript — contains one 2x2 chart)
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NUMBERS_SRC = REPO / "tests" / "fixtures" / "arabic.numbers"
CHART_SRC = REPO / "tests" / "fixtures" / "chart.numbers"


@pytest.fixture()
def numbers_file(tmp_path) -> Path:
    """A fresh copy of the Arabic+English+numbers 4x3 fixture."""
    dest = tmp_path / "fixture.numbers"
    shutil.copy2(NUMBERS_SRC, dest)
    return dest


@pytest.fixture()
def chart_file(tmp_path) -> Path:
    """A .numbers file containing a chart (for GATE-CHART refusal)."""
    if not CHART_SRC.exists():
        pytest.skip("chart fixture not built (requires Aqua; run make_chart_fixture.py)")
    dest = tmp_path / "chart_fixture.numbers"
    shutil.copy2(CHART_SRC, dest)
    return dest

# ── live runs: quit the iWork apps the run launched (like Cmd-Q) ─────────────
# Lets the live suite run unattended (e.g. overnight). Only apps that were NOT
# running when the session started are quit, and only if every open document is
# a temporary test file — a document of yours is never closed. Opt out with
# IWORK_STUDIO_KEEP_APPS=1.

import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402

_APPS = ("Keynote", "Pages", "Numbers")
_running_at_start: dict[str, bool] = {}


def _scripting_names() -> dict[str, str]:
    sys.path.insert(0, str(REPO / "src"))
    from iwork_studio.apps import app_name

    out = {}
    for kind in _APPS:
        try:
            out[kind] = app_name(kind)
        except Exception:  # noqa: BLE001 — app not installed / unverified
            pass
    return out


def _osa(script: str, *args: str, lang: str = "JavaScript") -> str:
    cmd = ["osascript", "-l", lang, "-e", script, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.stdout.strip() if r.returncode == 0 else ""


def _is_running(name: str) -> bool:
    # .running() never launches the app
    return _osa("function run(argv){return String(Application(argv[0]).running());}", name, lang="JavaScript") == "true"


def _open_files(name: str) -> list[str]:
    js = ("function run(argv){const a=Application(argv[0]);return JSON.stringify(a.documents().map(d=>"
          "{try{const f=d.file();return f?f.toString():''}catch(e){return ''}}));}")
    import json

    try:
        return json.loads(_osa(js, name, lang="JavaScript") or "[]")
    except ValueError:
        return ["?"]


def _is_temp(path: str) -> bool:
    if not path:
        return False
    roots = {os.path.realpath(tempfile.gettempdir()), "/private/var/folders", "/var/folders", "/private/tmp", "/tmp"}
    real = os.path.realpath(path)
    return any(real.startswith(r.rstrip("/") + "/") for r in roots)


def _live_run(session) -> bool:
    return sys.platform == "darwin" and not os.environ.get("IWORK_STUDIO_KEEP_APPS") and any(
        item.get_closest_marker("aqua") for item in session.items)


def pytest_collection_finish(session):
    if _live_run(session):
        for kind, name in _scripting_names().items():
            _running_at_start[name] = _is_running(name)


def pytest_sessionfinish(session, exitstatus):
    if not _running_at_start:
        return
    for name, was_running in _running_at_start.items():
        if was_running or not _is_running(name):
            continue
        files = _open_files(name)
        if all(_is_temp(f) for f in files):
            _osa("function run(argv){Application(argv[0]).quit({saving: 'no'}); return 'ok';}", name, lang="JavaScript")
        else:
            sys.stderr.write(f"\n[iwork-studio] left {name} open: it has documents that aren't test files\n")
