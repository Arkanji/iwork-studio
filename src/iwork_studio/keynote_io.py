"""iWork Studio — .key semantic reader/writer (Phase C).

Built on keynote-parser 1.14.5.0 (pinned; see specs/001-iwork-studio/pins.txt).
Same code path as the `keynote-parser unpack|pack` CLI:
``keynote_parser.file_utils.process(input, output, replacements=[])``.

GATE-1 is enforced as SEMANTIC equality (YAML-tree digest stable across
repack; .key byte hash differs from protobuf re-encode but is byte-STABLE
from the first repack on — verified scripts/c_preprobe.py P3,
verified). Do not re-litigate — pinned decision.

GATE-CHART: the writer REFUSES chart-container decks until a probe proves
them (accepted scope cut, same as Phase B). Detection = IWA message types
TSCH.ChartDrawableArchive(5021)/ChartNonStyle(5023)/LegendNonStyle(5025)/
ChartAxisNonStyle(5027)/ChartSeriesNonStyle(5029) — the same registry
keynote_parser ships for Keynote files (verified mapping.py v14_5).
Style PRESETS (5020/5022/5024/5026/5028/5030) exist in every document
(verified: all 98 bundled .kth templates carry 5020-5030 even counts and
zero instance types) and are NOT a chart signal.

C5 schema-hash manifest: EVERY write appends a JSONL entry recording the
YAML-tree structural skeleton hash (schema_hash) before/after, parser
version, and byte identity. A text-only edit MUST leave schema_hash
unchanged; a change = rename-storm suspect (Keynote 16 failure mode) and
fails the write. Parser-version changes re-baseline explicitly instead of
failing silently.

Library defect worked around (verified live, scripts/c_preprobe4.py):
``Replacement.correct_multiline_replacement`` counts only "\\n" paragraph
separators, but Keynote stores paragraphs as "\\r" — any replacement on
multi-paragraph text raises NotImplementedError. ``_FixedReplacement``
splits on \\r too (UTF-16 index bookkeeping preserved).

All writes follow the AtomicSwap protocol (data-model.md).
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml
from keynote_parser import __version__ as KEYPAD_VERSION
from keynote_parser.codec import IWAFile
from keynote_parser.file_utils import process
from keynote_parser.replacement import Replacement

# libyaml C loader when available: ~25x faster on a 50-file deck tree and
# parse-identical to SafeLoader (verified on both test fixtures,
# roundtrip_a3.key + chart_fixture.key — same objects, same schema_hash).
_YamlLoader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

__all__ = [
    "read_key",
    "unpack_key",
    "edit_text",
    "contains_charts",
    "schema_hash",
    "tree_hash",
    "texts_of_tree",
    "read_manifest",
    "ChartRefusalError",
    "EditTextError",
    "WriteVerificationError",
    "SchemaDriftError",
    "FileLockedError",
]

BACKUP_SUFFIX = ".bak"
DEFAULT_MANIFEST = "manifest.jsonl"


class ChartRefusalError(PermissionError):
    """GATE-CHART: deck contains chart instances; writer refuses
    chart-container files until a probe proves them (accepted scope cut)."""


class EditTextError(ValueError):
    """Bad find/replace request (not found, paragraph-count change, …)."""


class WriteVerificationError(RuntimeError):
    """Tmp write failed semantic verification — never swapped in."""


class SchemaDriftError(WriteVerificationError):
    """C5 rename-storm detection: the YAML-tree skeleton changed across a
    text-only write, or drifted from the manifest baseline under the same
    parser version."""


class FileLockedError(PermissionError):
    """Target is not writable (locked / open elsewhere) — the AppleScript
    fallback (keynote_applescript) is the route for open-in-app files."""


# ── GATE-CHART detection (C4) ─────────────────────────────────────────────────

# TSCH message type IDs that appear ONLY with actual chart instances.
# keynote_parser.versions.v14_5.mapping ground truth:
#   5021 TSCH.ChartDrawableArchive        5023 TSCH.ChartNonStyleArchive
#   5025 TSCH.LegendNonStyleArchive       5027 TSCH.ChartAxisNonStyleArchive
#   5029 TSCH.ChartSeriesNonStyleArchive
# Style presets 5020/5022/5024/5026/5028/5030 exist in every document
# (all 98 bundled .kth templates: presets present, instance types absent).
CHART_INSTANCE_MESSAGE_TYPES = frozenset({5021, 5023, 5025, 5027, 5029})


def contains_charts(path: str | os.PathLike) -> bool:
    """True if the .key package holds chart instances.

    Walks the IWA segments of every .iwa zip entry and looks for
    chart-instance message types. Read-only on the raw zip; no model.
    """
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.endswith(".iwa"):
                continue
            try:
                iwa = IWAFile.from_buffer(zf.read(name))
            except Exception:
                continue
            for chunk in iwa.chunks:
                for archive in chunk.archives:
                    for mi in archive.header.message_infos:
                        if mi.type in CHART_INSTANCE_MESSAGE_TYPES:
                            return True
    return False


# ── C1: unpacked IWA-YAML tree (source of truth) ──────────────────────────────


def unpack_key(path: str | os.PathLike, out_dir: str | os.PathLike) -> Path:
    """Unpack a .key package to its IWA-YAML tree (same code path as the
    `keynote-parser unpack` CLI). The tree is the source of truth."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    process(str(path), str(out_dir), replacements=[])
    return out_dir


def _walk_text_objects(data: dict):
    """Yield every dict object carrying a 'text' list in a parsed YAML tree."""
    stack: list = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if isinstance(cur.get("text"), list):
                yield cur
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            for x in cur:
                if isinstance(x, (dict, list)):
                    stack.append(x)


def texts_of_tree(tree_dir: str | os.PathLike) -> list[dict]:
    """Inventory of every text payload in a tree: [{"source": <rel yaml>,
    "text": <joined string>}] sorted by source path (stable order)."""
    tree_dir = Path(tree_dir)
    import glob

    out = []
    for f in sorted(glob.glob(str(tree_dir / "**" / "*.yaml"), recursive=True)):
        rel = os.path.relpath(f, tree_dir)
        with open(f, encoding="utf-8") as fh:
            data = yaml.load(fh, Loader=_YamlLoader)
        if not isinstance(data, dict):
            continue
        for obj in _walk_text_objects(data):
            out.append({"source": rel, "text": "".join(obj["text"])})
    return out


# structural skeleton: keys + _pbtype + list lengths, NO scalar values.
def _skeleton(o):
    if isinstance(o, dict):
        return ("d", tuple(sorted((k, _skeleton(v)) for k, v in o.items() if v is not None)))
    if isinstance(o, list):
        return ("l", len(o), tuple(_skeleton(x) for x in o))
    if isinstance(o, bool):
        return ("b",)
    if isinstance(o, (int, float)):
        return ("n",)
    if isinstance(o, str):
        return ("s",)
    if o is None:
        return ("z",)
    return ("?", type(o).__name__)


def _digest_tree(tree_dir: Path, skeleton_only: bool) -> str:
    import glob

    h = hashlib.sha256()
    for f in sorted(glob.glob(str(tree_dir / "**" / "*.yaml"), recursive=True)):
        rel = os.path.relpath(f, tree_dir)
        h.update(rel.encode("utf-8"))
        if skeleton_only:
            with open(f, encoding="utf-8") as fh:
                data = yaml.load(fh, Loader=_YamlLoader)
            h.update(repr(_skeleton(data)).encode("utf-8"))
        else:
            h.update(Path(f).read_bytes())
    return h.hexdigest()


def schema_hash(tree_dir: str | os.PathLike) -> str:
    """C5: structural skeleton hash of a tree — invariant under text-only
    edits; jumps on any schema rename (Keynote 16 rename-storm signal)."""
    return _digest_tree(Path(tree_dir), skeleton_only=True)


def tree_hash(tree_dir: str | os.PathLike) -> str:
    """Full content hash of a tree (path + yaml bytes). Stable across
    repacks (verified scripts/c_preprobe.py P3: double round-trip stable)."""
    return _digest_tree(Path(tree_dir), skeleton_only=False)


def read_key(path: str | os.PathLike) -> dict:
    """C1: read a .key file into the JSON semantic model (disposable,
    read-only view over the YAML tree, per data-model.md).

    Model: {"file", "path", "parser_version", "contains_charts",
    "schema_hash", "slides": [{"source", "texts": [...]}]}
    """
    path = str(path)
    with tempfile.TemporaryDirectory(prefix="iwork-readkey-") as tmp:
        tree = unpack_key(path, Path(tmp) / "tree")
        slides: dict[str, list[str]] = {}
        for entry in texts_of_tree(tree):
            slides.setdefault(entry["source"], []).append(entry["text"])
        return {
            "file": os.path.basename(path),
            "path": os.path.abspath(path),
            "parser_version": KEYPAD_VERSION,
            "contains_charts": contains_charts(path),
            "schema_hash": schema_hash(tree),
            "slides": [
                {"source": k, "texts": v} for k, v in sorted(slides.items())
            ],
        }


# ── C2: the fixed Replacement (library defect workaround) ─────────────────────


class _FixedReplacement(Replacement):
    """Replacement that treats \\r (Keynote's paragraph separator, verified
    in evidence fixtures) the same as \\n when re-aligning tableParaStyle.

    Upstream counts only "\\n" (replacement.py:64-69) so every edit on
    \\r-separated multi-paragraph text raises NotImplementedError
    (reproduced live, scripts/c_preprobe4.py). UTF-16 surrogate bookkeeping
    from upstream is preserved.
    """

    def correct_multiline_replacement(self, _dict):
        text = _dict["text"][0]

        new_offsets = [0]
        utf16_index = 0
        for c in text:
            width = 2 if ord(c) > 0xFFFF else 1
            if c == "\n" or c == "\r":
                new_offsets.append(utf16_index + width)
            utf16_index += width

        entries = _dict["tableParaStyle"]["entries"]
        if len(entries) != len(new_offsets):
            raise NotImplementedError(
                "Replacement changed the paragraph count: %s" % text
            )
        for para_entry, offset in zip(entries, new_offsets):
            para_entry["characterIndex"] = offset
        return _dict


_U6_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _unescape_u6(s: str) -> str:
    """Escape-awareness for \\u06xx Arabic sequences: keynote-parser's YAML
    stores Arabic as \\uXXXX escapes; if the caller passes find/replace in
    that escaped form, unescape to real codepoints (data-level replace
    operates on real Unicode, not YAML bytes). 17 sequences verified
    preserved through the tree (probe A3-probe-4)."""
    return _U6_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), s)


# ── C5: manifest ──────────────────────────────────────────────────────────────


def _manifest_path(backup_dir: Path) -> Path:
    return Path(backup_dir) / DEFAULT_MANIFEST


def read_manifest(target: str | os.PathLike, backup_dir: str | os.PathLike | None = None) -> list[dict]:
    """C5: the write manifest for a target file (JSONL entries, oldest first)."""
    target = Path(target)
    if backup_dir is None:
        backup_dir = target.parent / f"{target.name}.backups"
    mp = _manifest_path(Path(backup_dir))
    if not mp.exists():
        return []
    entries = []
    for line in mp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def _append_manifest(backup_dir: Path, entry: dict) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    mp = _manifest_path(backup_dir)
    with mp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return mp


# ── helpers ───────────────────────────────────────────────────────────────────


def _versioned_backup(target: Path, backup_dir: Path) -> Path:
    """Step 1 of AtomicSwap: timestamped versioned backup keeping the .key
    suffix (restorable by double-click / parser)."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    n = 0
    while True:
        suffix = f".{stamp}.{n}" if n else f".{stamp}"
        backup = backup_dir / f"{target.name}{suffix}.key"
        if not backup.exists():
            break
        n += 1
    shutil.copy2(target, backup)
    return backup


def _prune_backups(backup_dir: Path, max_backups: int) -> None:
    try:
        backups = sorted(
            (
                p
                for p in backup_dir.iterdir()
                if p.name.endswith(".key") and p.name != backup_dir.name
            ),
            key=lambda p: p.name,
        )
        for old in backups[:-max_backups] if max_backups > 0 else []:
            old.unlink()
    except OSError:
        pass


def _sha256_file(p: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _zip_members(path: str | os.PathLike) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return sorted(zf.namelist())


# ── C2+C5: edit_text (AtomicSwap protocol) ────────────────────────────────────


def edit_text(
    path: str | os.PathLike,
    find: str,
    replace: str,
    *,
    regex: bool = False,
    backup_dir: str | os.PathLike | None = None,
    max_backups: int = 10,
) -> dict:
    """Replace text across a .key deck via the keynote-parser replace op
    (same code path as `keynote-parser replace`), under the AtomicSwap
    protocol:

    1. GATE-CHART refusal (C4)
    2. writability probe (locked files → FileLockedError; the AppleScript
       fallback in keynote_applescript is the open-in-app route, C6)
    3. unpack source → YAML tree (source of truth), pre-flight find check
    4. versioned backup
    5. write tmp .key via process() with _FixedReplacement (\\r-aware)
    6. re-unpack tmp; verify: zip members equal, schema_hash UNCHANGED
       (C5 rename-storm gate), every text change == expected replace
    7. os.replace (atomic swap)
    8. manifest entry appended (C5)

    `find`/`replace` are literal by default; pass regex=True for the raw
    library semantics. Literal find/replace containing \\uXXXX escape
    sequences are unescaped first (escape-aware for Arabic \\u06xx).
    """
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    if contains_charts(target):
        raise ChartRefusalError(
            f"GATE-CHART: {target.name} contains chart instances; the writer "
            "refuses chart-container decks until a probe proves them "
            "(accepted scope cut)"
        )

    # writability probe — locked/open files must take the C6 route
    try:
        with open(target, "r+b"):
            pass
    except OSError as exc:
        raise FileLockedError(
            f"{target} is not writable ({exc}); use the AppleScript fallback "
            "(iwork_studio.keynote_applescript) for open-in-app files"
        ) from exc

    if backup_dir is None:
        backup_dir = target.parent / f"{target.name}.backups"
    backup_dir = Path(backup_dir)

    # escape-aware for \u06xx sequences
    find_s = _unescape_u6(find)
    replace_s = _unescape_u6(replace)
    if not find_s:
        raise EditTextError("find must be non-empty")
    # literal mode ALWAYS escapes: a literal 'a.b' must not match 'axb'.
    # regex mode passes the caller's pattern through verbatim (library
    # semantics). \uXXXX escapes were already unescaped above.
    pattern = find_s if regex else re.escape(find_s)

    with tempfile.TemporaryDirectory(prefix="iwork-editkey-") as tmp:
        tmp = Path(tmp)
        src_tree = unpack_key(target, tmp / "src_tree")

        # pre-flight: find must occur in the deck (no write, no backup churn)
        src_texts = texts_of_tree(src_tree)
        src_joined = [e["text"] for e in src_texts]
        n_hits = sum(len(re.findall(pattern, t)) for t in src_joined)
        if n_hits == 0:
            raise EditTextError(
                f"find {find!r} does not occur in {target.name}"
            )

        schema_before = schema_hash(src_tree)
        tree_before = tree_hash(src_tree)

        # C5 manifest baseline: cross-write schema movement is RECORDED,
        # not hard-failed — a Keynote app save legitimately restructures
        # the tree (verified live, scripts/c_preprobe5.py: app save grows
        # the deck and surfaces master texts). The rename-storm HARD gate
        # is the in-write check below: a text-only edit must never change
        # the skeleton. Parser-version changes re-baseline explicitly.
        manifest = read_manifest(target, backup_dir)
        baseline_shift = False
        if manifest:
            last = manifest[-1]
            if last.get("parser_version") != KEYPAD_VERSION:
                baseline_shift = True
            elif last.get("schema_hash_after") != schema_before:
                baseline_shift = True  # external edit (app save) — auditable

        backup_path = _versioned_backup(target, backup_dir)
        _prune_backups(backup_dir, max_backups)

        # tmp write in the SAME directory (atomic os.replace needs the
        # same filesystem)
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent), prefix=f".{target.name}.tmp", suffix=".key"
        )
        os.close(tmp_fd)
        tmp_key = Path(tmp_name)

        try:
            replacement = _FixedReplacement(pattern, replace_s)
            completed = process(str(target), str(tmp_key), replacements=[replacement])
            if not completed:
                raise EditTextError(
                    "replacement produced no changes (find matched at "
                    "pre-flight but not at pack time — parser inconsistency)"
                )

            # Step: re-parse + verify the tmp file
            out_tree = unpack_key(tmp_key, tmp / "out_tree")

            if _zip_members(tmp_key) != _zip_members(target):
                raise WriteVerificationError(
                    "tmp deck zip members differ from source — refusing swap"
                )

            schema_after = schema_hash(out_tree)
            if schema_after != schema_before:
                raise SchemaDriftError(
                    "text-only edit changed the structural skeleton "
                    f"({schema_before} -> {schema_after}); Keynote "
                    "rename-storm suspect — target untouched"
                )

            # every text change must be exactly find->replace
            out_texts = texts_of_tree(out_tree)
            if len(out_texts) != len(src_texts):
                raise WriteVerificationError(
                    f"text object count changed {len(src_texts)} -> "
                    f"{len(out_texts)} — refusing swap"
                )
            changes = []
            for s_entry, o_entry in zip(src_texts, out_texts):
                s_t, o_t = s_entry["text"], o_entry["text"]
                if s_t == o_t:
                    continue
                if re.sub(pattern, replace_s, s_t) != o_t:
                    raise WriteVerificationError(
                        f"unexpected text change in {o_entry['source']}: "
                        f"{s_t!r} -> {o_t!r} is not the requested replacement"
                    )
                changes.append(
                    {"source": o_entry["source"], "before": s_t, "after": o_t}
                )
            if not changes:
                raise WriteVerificationError(
                    "no text changed between source and tmp trees"
                )

            # atomic swap
            os.replace(tmp_key, target)
        except Exception:
            if tmp_key.exists():
                try:
                    os.unlink(tmp_key)
                except OSError:
                    pass
            raise

        tree_after = tree_hash(out_tree)
        entry = {
            "ts": _dt.datetime.now().isoformat(timespec="seconds"),
            "op": "edit_text",
            "file": target.name,
            "parser_version": KEYPAD_VERSION,
            "find": find,
            "replace": replace,
            "regex": regex,
            "changed_texts": len(changes),
            "occurrences": n_hits,
            "schema_hash_before": schema_before,
            "schema_hash_after": schema_after,
            "tree_hash_before": tree_before,
            "tree_hash_after": tree_after,
            "sha256_after": _sha256_file(target),
            "bytes": target.stat().st_size,
            "backup": backup_path.name,
            "baseline_shift": baseline_shift,
        }
        manifest_path = _append_manifest(backup_dir, entry)

    return {
        "ok": True,
        "file": str(target),
        "find": find,
        "replace": replace,
        "occurrences": n_hits,
        "changes": changes,
        "backup": str(backup_path),
        "manifest": str(manifest_path),
        "schema_hash": schema_after,
        "parser_version": KEYPAD_VERSION,
        "baseline_shift": baseline_shift,
    }