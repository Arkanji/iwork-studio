"""iWork Studio — dry run: preview any write without touching the file.

The real operation runs on a temporary copy (full protocol, full checks), the
copy is compared with the original, and then it is deleted. The original is
never opened for writing and no backup is made. Because the preview *is* the
operation, it can't drift from what the write would really do.
"""

from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["dry_run", "diff_files"]

_MAX = 100


def _swap_paths(obj: Any, old: str, new: str) -> Any:
    if isinstance(obj, str):
        return obj.replace(old, new)
    if isinstance(obj, dict):
        return {k: _swap_paths(v, old, new) for k, v in obj.items() if k != "backup"}
    if isinstance(obj, list):
        return [_swap_paths(v, old, new) for v in obj]
    return obj


def _ref(r: int, c: int) -> str:
    from iwork_studio.numbers_format import _col_letters

    return f"{_col_letters(c)}{r + 1}"


def _diff_numbers(a: Path, b: Path) -> dict:
    from numbers_parser import Document

    from iwork_studio.numbers_format import _doc_snap

    sa, sb = _doc_snap(Document(str(a))), _doc_snap(Document(str(b)))
    out: dict = {"tables_added": [f"{s} › {t}" for s, t in sb if (s, t) not in sa],
                 "tables_removed": [f"{s} › {t}" for s, t in sa if (s, t) not in sb], "cells": [], "layout": []}
    for key in sa:
        if key not in sb:
            continue
        ta, tb = sa[key], sb[key]
        where = f"{key[0]} › {key[1]}"
        if ta["shape"] != tb["shape"]:
            out["layout"].append({"table": where, "size": {"before": ta["shape"], "after": tb["shape"]}})
        for k in ("widths", "heights", "headers", "merges"):
            if ta[k] != tb[k] and ta["shape"] == tb["shape"]:
                out["layout"].append({"table": where, k: {"before": ta[k], "after": tb[k]}})
        for rc in sorted(set(ta["cells"]) | set(tb["cells"])):
            ca, cb = ta["cells"].get(rc), tb["cells"].get(rc)
            if ca == cb:
                continue
            aspects = [x for x in ("value", "formula", "style", "format", "border")
                       if (ca or {}).get(x) != (cb or {}).get(x)]
            entry = {"cell": f"{where} › {_ref(*rc)}", "changed": aspects}
            if "value" in aspects or "formula" in aspects:
                entry["before"] = (ca or {}).get("formula") or (ca or {}).get("value")
                entry["after"] = (cb or {}).get("formula") or (cb or {}).get("value")
            if "format" in aspects:
                entry["shown_as"] = {"before": (ca or {}).get("format", (None, None))[1],
                                     "after": (cb or {}).get("format", (None, None))[1]}
            out["cells"].append(entry)
    out["cells_changed"] = len(out["cells"]) or None
    out["cells"] = out["cells"][:_MAX]
    return {k: v for k, v in out.items() if v not in ([], None)}


def _diff_keynote(a: Path, b: Path) -> dict:
    from collections import Counter

    from iwork_studio.keynote_io import read_key

    def slides(p):
        return [Counter(t for t in s["texts"] if t.strip()) for s in read_key(p)["slides"]
                if s["source"].startswith("Index/Slide")]

    sa, sb = slides(a), slides(b)
    out: dict = {"slides": {"before": len(sa), "after": len(sb)}} if len(sa) != len(sb) else {}
    gone, new = sum(sa, Counter()) - sum(sb, Counter()), sum(sb, Counter()) - sum(sa, Counter())
    if gone:
        out["text_removed"] = list(gone.elements())[:_MAX]
    if new:
        out["text_added"] = list(new.elements())[:_MAX]
    return out


def _diff_pages(a: Path, b: Path) -> dict:
    from iwork_studio.pages_io import OutOfScopeError, read_body_text

    try:
        ta, tb = read_body_text(a), read_body_text(b)
    except OutOfScopeError:
        return {"body": "page-layout document: no body text to compare"}
    if ta == tb:
        return {}
    pa, pb = ta.replace("\r", "\n").split("\n"), tb.replace("\r", "\n").split("\n")
    lines = [line for line in difflib.unified_diff(pa, pb, "before", "after", lineterm="", n=0)
             if not line.startswith(("---", "+++", "@@"))]
    return {"body_diff": lines[:_MAX]}


def diff_files(a, b) -> dict:
    """What differs between two versions of the same iWork file."""
    a, b = Path(a), Path(b)
    kind = a.suffix.lower()
    try:
        if kind == ".numbers":
            return _diff_numbers(a, b)
        if kind == ".key":
            return _diff_keynote(a, b)
        if kind == ".pages":
            return _diff_pages(a, b)
    except Exception as exc:  # noqa: BLE001 — the operation's own result still describes the change
        return {"unavailable": f"{type(exc).__name__}: {exc}"}
    return {}


def dry_run(fn, path, *args, **kwargs) -> dict:
    """Run `fn(copy_of_path, *args, **kwargs)` on a temporary copy and report what would change."""
    src = Path(path).resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    work = Path(tempfile.mkdtemp(prefix="iwork-dryrun-"))
    copy = work / src.name
    try:
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, copy)
        result = fn(copy, *args, **kwargs)
        changes = diff_files(src, copy)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    result = _swap_paths(result if isinstance(result, dict) else {"result": result}, str(copy), str(src))
    return {"dry_run": True, "file_untouched": True, "would_change": changes or "nothing visible in the content",
            "result": result}
