"""iWork Studio — Keynote slide operations via the app (Phase G).

Ops: add, duplicate, delete, move, skip/unskip, set presenter notes.
Technique source: reichenbach/iwork_mcp (MIT), tested there on Keynote 14.5 /
15.1.1 against documents already OPEN in the app, with no backup and no
readback. Here every op rides the iWork Studio write protocol instead:

  0. gates: .key only · GATE-CHART · not open in Keynote · op verified
  1. inventory BEFORE (open → per-slide signature → close, no save)
  2. pre-flight validation against that inventory (no backup churn)
  3. versioned backup (shared with keynote_io, manifest-recorded)
  4. app op + IN-PLACE save + close   (GATE-SAVE: never `save in <path>`)
  5. inventory AFTER, re-read from disk in a fresh open
  6. expectation gate: exactly the requested change, every other slide's
     signature unchanged, in order
  7. parser re-parse gate (keynote-parser must still unpack the deck)
  8. any failure ⇒ atomic restore from the step-3 backup, error re-raised

Slide signature = (skipped, presenter notes, `object text` of every text
item). `object text` is the -1700-safe form on Keynote 15.4; the slide
`title`/`body` properties are never used (keynote-1700-defect.md).

STATUS: ON by default. The ops have not yet been observed on a live iWork
15.4 Mac (VERIFIED_OPS is empty until `scripts/probe_keynote_slides.py`
passes there); the expectation gate + rollback above is what makes running
them before that safe — a wrong app result is rolled back, never kept.
Off switch: IWORK_STUDIO_DISABLE_SLIDE_OPS=1 (raises SlideOpsDisabledError).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from iwork_studio import keynote_io
from iwork_studio.apps import app_name
from iwork_studio.keynote_applescript import _assert_aqua

__all__ = [
    "read_slides",
    "add_slide",
    "duplicate_slide",
    "delete_slide",
    "move_slide",
    "set_skipped",
    "set_presenter_notes",
    "is_verified",
    "slide_ops_enabled",
    "SLIDE_OPS",
    "VERIFIED_OPS",
    "SlideOpsDisabledError",
    "SlideOpError",
    "SlideOpVerificationError",
    "DocumentOpenError",
]

_APP = "Keynote"
SLIDE_OPS = ("add", "duplicate", "delete", "move", "skip", "notes")
# Ops observed passing on a live Mac (scripts/probe_keynote_slides.py).
VERIFIED_OPS: frozenset[str] = frozenset()


class SlideOpsDisabledError(RuntimeError):
    """Slide ops are switched off on this machine (IWORK_STUDIO_DISABLE_SLIDE_OPS=1)."""


class SlideOpError(ValueError):
    """Bad request (slide out of range, deleting the last slide, …)."""


class SlideOpVerificationError(RuntimeError):
    """The app did something other than the requested change — rolled back."""


class DocumentOpenError(PermissionError):
    """The deck is open in Keynote; closing it could drop unsaved edits."""


def is_verified(op: str) -> bool:
    return op in VERIFIED_OPS


def slide_ops_enabled() -> bool:
    return os.environ.get("IWORK_STUDIO_DISABLE_SLIDE_OPS") != "1"


def _gate_op(op: str) -> None:
    if not slide_ops_enabled():
        raise SlideOpsDisabledError(
            f"keynote slide op {op!r} refused: IWORK_STUDIO_DISABLE_SLIDE_OPS=1 is set"
        )


# ── JXA runner: params as JSON argv (no string interpolation of content) ─────


def _jxa(body: str, params: dict, timeout: int = 180) -> dict:
    _assert_aqua()
    script = (
        "function run(argv) {\n"
        "  const params = JSON.parse(argv[0]);\n"
        f"  const app = Application({json.dumps(app_name(_APP))});\n"
        f"{body}\n"
        "}"
    )
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script, json.dumps(params)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"JXA failed (rc={result.returncode}): {result.stderr.strip()[:500]}"
        )
    return json.loads(result.stdout.strip() or "{}")


_OPEN_CHECK = """
  const target = params.path;
  const already = app.documents().some(d => {
    try { const f = d.file(); return f && f.toString() === target; } catch (e) { return false; }
  });
  if (already) return JSON.stringify({open_in_app: true});
"""

_INVENTORY = """
  const inv = [];
  const slides = doc.slides();
  for (let s = 0; s < slides.length; s++) {
    let notes = "";
    try { notes = slides[s].presenterNotes().toString(); } catch (e) { notes = null; }
    const texts = [];
    const tis = slides[s].textItems();
    for (let i = 0; i < tis.length; i++) texts.push(tis[i].objectText().toString());
    inv.push({skipped: slides[s].skipped(), notes: notes, texts: texts});
  }
"""


def read_slides(path: str | os.PathLike) -> list[dict]:
    """Per-slide signature via the app: [{"skipped", "notes", "texts"}]."""
    target = str(Path(path).resolve())
    out = _jxa(
        _OPEN_CHECK
        + "  const doc = app.open(Path(target));\n"
        + _INVENTORY
        + "  app.close(doc, {saving: 'no'});\n"
        + "  return JSON.stringify({slides: inv});",
        {"path": target},
    )
    if out.get("open_in_app"):
        raise DocumentOpenError(
            f"{Path(target).name} is open in Keynote. Save and close it first — "
            "iWork Studio will not close a window that may hold unsaved edits."
        )
    return out["slides"]


# Op bodies run between open and in-place save. `doc` is in scope.
_OP_JS = {
    "add": """
  const slide = app.Slide({});
  if (params.after === null) doc.slides.push(slide);
  else doc.slides.splice(params.after, 0, slide);
""",
    "duplicate": """
  app.duplicate(doc.slides[params.n - 1]);
""",
    "delete": """
  app.delete(doc.slides[params.n - 1]);
""",
    "move": """
  app.move(doc.slides[params.n - 1], {to: doc.slides[params.to - 1]});
""",
    "skip": """
  doc.slides[params.n - 1].skipped = params.skipped;
""",
    "notes": """
  doc.slides[params.n - 1].presenterNotes = params.notes;
""",
}


def _apply(target: Path, op: str, params: dict) -> None:
    body = (
        "  const doc = app.open(Path(params.path));\n"
        + "  try {\n"
        + _OP_JS[op]
        + "    app.save(doc);             // IN-PLACE save only — GATE-SAVE\n"
        + "  } finally {\n"
        + "    app.close(doc, {saving: 'no'});  // never leave the deck open\n"
        + "  }\n"
        + "  return JSON.stringify({ok: true});"
    )
    _jxa(body, {"path": str(target), **params}, timeout=300)


def _norm(sig: dict) -> dict:
    notes = sig.get("notes")
    if isinstance(notes, str):
        notes = notes.replace("\r\n", "\n").replace("\r", "\n")
    return {"skipped": bool(sig.get("skipped")), "notes": notes, "texts": list(sig.get("texts", []))}


def _expected(before: list[dict], op: str, p: dict) -> list[dict] | None:
    """Expected AFTER inventory; None entries are 'any slide' wildcards."""
    b = [_norm(s) for s in before]
    if op == "add":
        at = len(b) if p["after"] is None else p["after"]
        return b[:at] + [None] + b[at:]
    if op == "duplicate":
        i = p["n"] - 1
        return b[: i + 1] + [b[i]] + b[i + 1 :]
    if op == "delete":
        i = p["n"] - 1
        return b[:i] + b[i + 1 :]
    if op == "move":
        moved = b.pop(p["n"] - 1)
        b.insert(p["to"] - 1, moved)
        return b
    if op == "skip":
        b[p["n"] - 1]["skipped"] = p["skipped"]
        return b
    if op == "notes":
        b[p["n"] - 1]["notes"] = _norm({"notes": p["notes"]})["notes"]
        return b
    raise SlideOpError(f"unknown op {op!r}")


def _check(expected: list, after: list[dict]) -> None:
    got = [_norm(s) for s in after]
    if len(got) != len(expected):
        raise SlideOpVerificationError(
            f"slide count {len(got)} after the op, expected {len(expected)}"
        )
    for idx, (want, have) in enumerate(zip(expected, got), start=1):
        if want is not None and want != have:
            raise SlideOpVerificationError(
                f"slide {idx} is not what the op should have produced: "
                f"expected {want!r}, found {have!r}"
            )


def _validate(op: str, p: dict, count: int) -> None:
    def in_range(name: str) -> None:
        v = p[name]
        if not isinstance(v, int) or not 1 <= v <= count:
            raise SlideOpError(f"{name}={v!r} out of range (deck has {count} slides)")

    if op == "add":
        a = p["after"]
        if a is not None and (not isinstance(a, int) or not 0 <= a <= count):
            raise SlideOpError(f"after={a!r} out of range 0..{count}")
    elif op == "move":
        in_range("n")
        in_range("to")
        if p["n"] == p["to"]:
            raise SlideOpError("move: source and destination are the same slide")
    else:
        in_range("n")
    if op == "delete" and count <= 1:
        raise SlideOpError("Keynote cannot delete the only slide in a deck")


def _restore(target: Path, backup: Path) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.rb", suffix=".key")
    os.close(fd)
    shutil.copy2(backup, tmp_name)
    os.replace(tmp_name, target)


def _run(path, op: str, params: dict, backup_dir=None, max_backups: int = 10) -> dict:
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    if target.suffix.lower() != ".key":
        raise SlideOpError(f"{target.name} is not a .key deck")
    _gate_op(op)
    if keynote_io.contains_charts(target):
        raise keynote_io.ChartRefusalError(
            f"GATE-CHART: {target.name} contains chart instances; slide ops "
            "refuse chart decks until a probe proves them"
        )

    before = read_slides(target)
    _validate(op, params, len(before))
    expected = _expected(before, op, params)

    bdir = Path(backup_dir) if backup_dir else target.parent / f"{target.name}.backups"
    backup = keynote_io._versioned_backup(target, bdir)
    keynote_io._prune_backups(bdir, max_backups)
    try:
        _apply(target, op, params)
        after = read_slides(target)
        _check(expected, after)
        keynote_io.read_key(target)  # parser re-parse gate
    except Exception:
        _restore(target, backup)
        raise

    keynote_io._append_manifest(
        bdir,
        {
            "ts": _dt.datetime.now().isoformat(timespec="seconds"),
            "op": f"slide_{op}",
            "route": "applescript",
            "verified_op": is_verified(op),
            "file": target.name,
            "params": params,
            "slides_before": len(before),
            "slides_after": len(after),
            "backup": backup.name,
            "bytes": target.stat().st_size,
        },
    )
    return {
        "ok": True,
        "file": str(target),
        "op": op,
        "params": params,
        "slides_before": len(before),
        "slides_after": len(after),
        "backup": str(backup),
        "verified_op": is_verified(op),
    }


# ── public ops (1-based slide numbers) ────────────────────────────────────────


def add_slide(path, after: int | None = None, **kw) -> dict:
    """Insert a slide after slide `after` (0 = first, None = end)."""
    return _run(path, "add", {"after": after}, **kw)


def duplicate_slide(path, n: int, **kw) -> dict:
    return _run(path, "duplicate", {"n": n}, **kw)


def delete_slide(path, n: int, **kw) -> dict:
    return _run(path, "delete", {"n": n}, **kw)


def move_slide(path, n: int, to: int, **kw) -> dict:
    """Move slide `n` so it ends up at position `to`."""
    return _run(path, "move", {"n": n, "to": to}, **kw)


def set_skipped(path, n: int, skipped: bool = True, **kw) -> dict:
    return _run(path, "skip", {"n": n, "skipped": bool(skipped)}, **kw)


def set_presenter_notes(path, n: int, notes: str, **kw) -> dict:
    return _run(path, "notes", {"n": n, "notes": notes}, **kw)
