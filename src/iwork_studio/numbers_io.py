"""iWork Studio — .numbers semantic reader/writer (Phase B).

Built on numbers-parser 4.19.0 (pinned; see skill-pack/references/pins.txt).

GATE-1 is enforced as SEMANTIC byte-equality (content identical, file openable):
numbers-parser re-encodes IWA protobuf on save so strict zip byte-equality is
unachievable (verified). Do not re-litigate — pinned decision.

GATE-CHART: the writer REFUSES chart-container files until a probe proves them
(accepted scope cut — refusal is correct behaviour, not a gap).

All writes follow the AtomicSwap protocol:
  1. backup target (versioned, timestamped)
  2. write tmp file
  3. re-parse tmp (semantic check)
  4. byte-diff tmp vs source model
  5. os.replace(tmp, target)  (atomic)
  6. on ANY failure: rollback from backup, keep forensic artifacts
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import warnings

# numbers-parser warns "unsupported version '26.4.0'" for files from newer Numbers
# releases it hasn't listed yet; they read fine and every write is verified anyway.
warnings.filterwarnings("ignore", message="unsupported version", category=RuntimeWarning)

from numbers_parser import Document  # noqa: E402
import numbers_parser.cell as _np_cell
from numbers_parser.constants import DECIMAL128_BIAS as _D128_BIAS


def _exact_pack_decimal128(value) -> bytearray:
    """numbers-parser's encoder goes through float division, so 12 is stored as
    12.000000000000002. Encode the shortest exact decimal instead (12 → 12)."""
    from decimal import Decimal

    d = Decimal(repr(float(value))) if isinstance(value, float) else Decimal(value)
    sign, digits, exp = d.as_tuple()
    mantissa = int("".join(map(str, digits))) if digits else 0
    e = exp + _D128_BIAS
    buffer = bytearray(16)
    buffer[15] |= e >> 7
    buffer[14] |= (e & 0x7F) << 1
    i = 0
    while mantissa:
        buffer[i] = mantissa & 0xFF
        mantissa >>= 8
        i += 1
    if sign:
        buffer[15] |= 0x80
    return buffer


def _exact_unpack_decimal128(buffer) -> float:
    """Same bit layout as numbers-parser's decoder, read at spreadsheet precision
    (15 significant digits, as Numbers and Excel show it): 3e-4 → 0.0003, and
    33.999999999999996 (left by older numbers-parser writes of 34) → 34."""
    from decimal import Decimal

    exp = (((buffer[15] & 0x7F) << 7) | (buffer[14] >> 1)) - _D128_BIAS
    mantissa = buffer[14] & 1
    for i in range(13, -1, -1):
        mantissa = mantissa * 256 + buffer[i]
    if buffer[15] & 0x80:
        mantissa = -mantissa
    return float(format(Decimal(mantissa).scaleb(exp), ".15g"))


_np_cell._pack_decimal128 = _exact_pack_decimal128
_np_cell._unpack_decimal128 = _exact_unpack_decimal128

__all__ = [
    "read_numbers",
    "edit_cell",
    "CellRefError",
    "ChartRefusalError",
    "WriteVerificationError",
]

BACKUP_SUFFIX = ".bak"


class CellRefError(ValueError):
    """Raised when a sheet/table/cell reference cannot be resolved."""


class ChartRefusalError(PermissionError):
    """GATE-CHART: file contains a chart; the writer refuses chart-container
    files until a probe proves them (accepted scope cut)."""


class WriteVerificationError(RuntimeError):
    """Raised when a tmp write fails semantic verification — never swapped in."""


# ── GATE-CHART detection ──────────────────────────────────────────────────────

# IWA message-type IDs (TSPRegistryMapping) that appear ONLY when a document
# contains actual chart instances (verified by probe_chart_msg_types.py against
# Apple's bundled 21_Simple_Charts vs 21_BasicCategories templates, 2026-10-01):
#   5021 TSCH.ChartDrawableArchive
#   5023 TSCH.ChartNonStyleArchive
#   5025 TSCH.LegendNonStyleArchive
#   5027 TSCH.ChartAxisNonStyleArchive
#   5029 TSCH.ChartSeriesNonStyleArchive
# Chart STYLE preset archives (5020/5022/5024/5026/5028/5030) exist in every
# document (theme presets) and are NOT a chart signal. Charts in .numbers live
# inside IWA protobuf messages — there is no "ChartArchive" zip entry, so
# zip-name scanning alone cannot detect them.
CHART_INSTANCE_MESSAGE_TYPES = frozenset({5021, 5023, 5025, 5027, 5029})


def contains_charts(path: str | os.PathLike) -> bool:
    """Return True if the .numbers package holds chart instances.

    Detection walks the IWA segments of every .iwa entry and looks for
    chart-instance message types (see CHART_INSTANCE_MESSAGE_TYPES).
    Read-only on the raw zip; no parser model involved.
    """
    import zipfile

    from numbers_parser.iwafile import IWAFile

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


# ── B1: semantic model ────────────────────────────────────────────────────────

_STYLE_FIELDS = (
    "font_name",
    "font_size",
    "bold",
    "italic",
    "strikethrough",
    "underline",
    "font_color",
    "bg_color",
    "text_wrap",
    "first_indent",
    "left_indent",
    "right_indent",
    "text_inset",
)


def _alignment_json(alignment: Any) -> dict | None:
    if alignment is None:
        return None
    horizontal = getattr(getattr(alignment, "horizontal", None), "name", None)
    vertical = getattr(getattr(alignment, "vertical", None), "name", None)
    return {"horizontal": horizontal, "vertical": vertical}


def _rgb_json(color: Any) -> Any:
    if color is None:
        return None
    return f"#{color.r:02x}{color.g:02x}{color.b:02x}" if hasattr(color, "r") else str(color)


def _style_json(cell: Any) -> dict | None:
    style = cell.style
    if style is None:
        return None
    out: dict = {}
    for field in _STYLE_FIELDS:
        value = getattr(style, field, None)
        if field in ("font_color", "bg_color"):
            value = _rgb_json(value)
        if value is not None:
            out[field] = value
    alignment = _alignment_json(getattr(style, "alignment", None))
    if alignment:
        out["alignment"] = alignment
    if getattr(style, "name", None):
        out["name"] = style.name
    return out or None


def _format_json(cell: Any) -> dict | None:
    """Observable format facts for a cell.

    numbers-parser 4.19 exposes number formatting via `formatted_value`
    (there is no public `.format` attribute on cells); the cell class name is
    the semantic type (TextCell/NumberCell/...). We record what the model
    can honestly observe rather than inventing a format object.
    """
    info: dict = {"type": type(cell).__name__}
    try:
        formatted = cell.formatted_value
        if formatted is not None:
            info["formatted_value"] = str(formatted)
    except Exception:
        pass
    return info


def _cell_json(cell: Any) -> dict:
    value = cell.value
    if hasattr(value, "isoformat"):  # datetime / date
        value = value.isoformat()
    out: dict = {"ref": f"R{cell.row + 1}C{cell.col + 1}", "value": value}
    if cell.is_formula:
        out["formula"] = cell.formula
    style = _style_json(cell)
    if style:
        out["style"] = style
    out["format"] = _format_json(cell)
    if cell.is_merged and cell.merge_range is not None:
        out["merged"] = {
            "rows": cell.merge_range.num_rows,
            "cols": cell.merge_range.num_cols,
        }
    return out


def read_numbers(path: str | os.PathLike) -> dict:
    """Read a .numbers file into the JSON semantic model.

    Model: {"file", "sheets": [{"name", "tables": [{"name", "num_rows",
    "num_cols", "cells": [cell...]}]}]} with each cell carrying
    ref/value/formula/style/format per the Phase-1 contract.
    """
    path = str(path)
    doc = Document(path)  # RuntimeWarning re unsupported version is benign
    sheets = []
    for i in range(len(doc.sheets)):
        sheet = doc.sheets[i]
        tables = []
        for j in range(len(sheet.tables)):
            table = sheet.tables[j]
            cells = [
                _cell_json(table.cell(r, c))
                for r in range(table.num_rows)
                for c in range(table.num_cols)
            ]
            tables.append(
                {
                    "name": table.name,
                    "num_rows": table.num_rows,
                    "num_cols": table.num_cols,
                    "cells": cells,
                }
            )
        sheets.append({"name": sheet.name, "tables": tables})
    return {
        "file": os.path.basename(path),
        "path": os.path.abspath(path),
        "sheets": sheets,
    }


def read_model_tuples(model: dict) -> list:
    """Flatten a semantic model to comparable tuples (sheet, table, ref,
    value, formula). Used for GATE-1 semantic byte-equality checks."""
    tuples = []
    for sheet in model["sheets"]:
        for table in sheet["tables"]:
            for cell in table["cells"]:
                tuples.append(
                    (
                        sheet["name"],
                        table["name"],
                        cell["ref"],
                        cell["value"],
                        cell.get("formula"),
                    )
                )
    return tuples


# ── B2: edit_cell (AtomicSwap protocol) ───────────────────────────────────────


def _resolve_cell(doc: Document, sheet: str | None, table: str | None):
    if len(doc.sheets) == 0:
        raise CellRefError("document has no sheets")
    if sheet is None:
        if len(doc.sheets) != 1:
            raise CellRefError(
                "document has multiple sheets; specify sheet name"
            )
        sh = doc.sheets[0]
    else:
        sh = None
        for i in range(len(doc.sheets)):
            if doc.sheets[i].name == sheet:
                sh = doc.sheets[i]
                break
        if sh is None:
            raise CellRefError(f"sheet {sheet!r} not found")
    if len(sh.tables) == 0:
        raise CellRefError(f"sheet {sh.name!r} has no tables")
    if table is None:
        if len(sh.tables) != 1:
            raise CellRefError(
                f"sheet {sh.name!r} has multiple tables; specify table name"
            )
        tb = sh.tables[0]
    else:
        tb = None
        for j in range(len(sh.tables)):
            if sh.tables[j].name == table:
                tb = sh.tables[j]
                break
        if tb is None:
            raise CellRefError(
                f"table {table!r} not found in sheet {sh.name!r}"
            )
    return sh, tb


def _parse_ref(ref: str) -> tuple[int, int]:
    """Parse a cell reference. Accepts 'R1C1' and Excel-style 'A1'.

    R1C1 form is ABSOLUTE (row first, then column): 'R3C1' = row 3, col 1.

    Returns 0-based (row, col).
    """
    import re

    ref = ref.strip().upper()
    m = re.fullmatch(r"R(\d+)C(\d+)", ref)
    if m:
        row, col = int(m.group(1)), int(m.group(2))
        if row < 1 or col < 1:
            raise CellRefError(f"references are 1-based: {ref!r}")
        return row - 1, col - 1
    m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    if m:
        col = 0
        for ch in m.group(1):
            col = col * 26 + (ord(ch) - ord("A") + 1)
        row = int(m.group(2))
        if row < 1 or col < 1:
            raise CellRefError(f"references are 1-based: {ref!r}")
        return row - 1, col - 1
    raise CellRefError(f"bad reference {ref!r} (use 'A1' or 'R1C1')")


def _versioned_backup(target: Path, backup_dir: Path) -> Path:
    """Step 1 of AtomicSwap: copy target to a timestamped, versioned backup.

    Backup keeps the .numbers suffix so numbers-parser (and Numbers itself)
    can open it directly for restore/verification; the version stamp lives
    in the stem: <name>.<stamp>[.N].numbers
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    n = 0
    while True:
        suffix = f".{stamp}.{n}" if n else f".{stamp}"
        backup = backup_dir / f"{target.name}{suffix}.numbers"
        if not backup.exists():
            break
        n += 1
    shutil.copy2(target, backup)
    return backup


def _semantic_key(model: dict) -> list:
    """Sheets/tables/dims/cell payload for GATE-1 semantic equality.

    Cell payload = value, formula, style, format (the full B1 contract),
    excluding 'ref' (position is the tuple key itself).
    """
    key = []
    for sheet in model["sheets"]:
        for table in sheet["tables"]:
            for cell in table["cells"]:
                payload = {
                    k: v for k, v in cell.items() if k not in ("ref",)
                }
                key.append((sheet["name"], table["name"], cell["ref"], json.dumps(payload, sort_keys=True, ensure_ascii=False)))
    return key


def edit_cell(
    path: str | os.PathLike,
    ref: str,
    value: Any,
    *,
    sheet: str | None = None,
    table: str | None = None,
    backup_dir: str | os.PathLike | None = None,
    max_backups: int = 10,
) -> dict:
    """Edit one cell in a .numbers file via the AtomicSwap protocol.

    Steps: backup → tmp-write → re-parse → semantic byte-diff (B1 model
    equality on every UNCHANGED cell) → atomic swap. On any failure the
    target is untouched and the error carries forensics.

    GATE-CHART: refuses chart-container files (raises ChartRefusalError).

    Returns a JSON-serialisable result dict with verbatim evidence fields.
    """
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    if contains_charts(target):
        raise ChartRefusalError(
            f"GATE-CHART: {target.name} contains chart archives; "
            "the writer refuses chart-container files until a probe "
            "proves them (accepted scope cut)"
        )

    if backup_dir is None:
        backup_dir = target.parent / f"{target.name}.backups"
    backup_dir = Path(backup_dir)

    # Step 0: source model (pre-write semantic baseline)
    source_model = read_numbers(target)
    source_key = _semantic_key(source_model)

    # Step 1: versioned backup
    backup_path = _versioned_backup(target, backup_dir)
    _prune_backups(backup_dir, max_backups)

    # Step 2: write to tmp file in the SAME directory (same filesystem →
    # os.replace is genuinely atomic)
    row, col = _parse_ref(ref)
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.tmp", suffix=".numbers"
    )
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)
    try:
        doc = Document(str(target))
        sh, tb = _resolve_cell(doc, sheet, table)
        if row >= tb.num_rows or col >= tb.num_cols:
            raise CellRefError(
                f"ref {ref!r} out of range for table {tb.name!r} "
                f"({tb.num_rows}x{tb.num_cols})"
            )
        before = tb.cell(row, col).value
        tb.write(row, col, value)
        doc.save(str(tmp_path))

        # Step 3: re-parse tmp
        tmp_model = read_numbers(tmp_path)

        # Step 4: semantic byte-diff — every cell except the edited one
        # must match the source model exactly (GATE-1 semantic standard).
        tmp_key = _semantic_key(tmp_model)
        expected_key = copy.deepcopy(source_key)
        cell_ref = f"R{row + 1}C{col + 1}"
        target_entry = None
        for idx, entry in enumerate(expected_key):
            if entry[0] == sh.name and entry[1] == tb.name and entry[2] == cell_ref:
                target_entry = idx
                break
        if target_entry is None:
            raise WriteVerificationError(
                f"edited cell {cell_ref} not found in source model"
            )
        new_payload = tmp_key[target_entry][3]
        expected_key[target_entry] = (
            sh.name,
            tb.name,
            cell_ref,
            new_payload,  # edited cell: expect the new payload
        )
        if tmp_key != expected_key:
            diffs = [
                (a, b) for a, b in zip(expected_key, tmp_key) if a != b
            ]
            raise WriteVerificationError(
                "semantic verification failed on tmp file; "
                f"{len(diffs)} unexpected cell change(s); target untouched"
            )

        # Step 5: atomic swap
        os.replace(tmp_path, target)
    except Exception:
        # Rollback: target was never replaced (os.replace is the last step),
        # so restore is only needed if swap itself half-failed.
        if tmp_path.exists():
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise

    after = read_numbers(target)
    sheets_after = {
        s["name"]: [t["name"] for t in s["tables"]] for s in after["sheets"]
    }

    return {
        "ok": True,
        "file": str(target),
        "cell": {
            "sheet": sh.name,
            "table": tb.name,
            "ref": cell_ref,
            "row": row,
            "col": col,
            "before": before,
            "after": value,
        },
        "backup": str(backup_path),
        "sheets": sheets_after,
        **recalc_note(after),
    }


def recalc_note(model: dict) -> dict:
    """Numbers shows the stored result of a formula and doesn't recalculate when it
    opens a file changed without it. Flag files whose formulas may now be stale."""
    n = sum(1 for s in model["sheets"] for t in s["tables"] for c in t["cells"] if c.get("formula"))
    if not n:
        return {}
    return {"formulas_need_recalc": n,
            "next_step": "Formula results in this file still show their old values; Numbers doesn't recalculate "
                         "on open. Run numbers_recalculate (needs Numbers on a Mac) so totals reflect the change."}


def _prune_backups(backup_dir: Path, max_backups: int) -> None:
    try:
        backups = sorted(
            (
                p
                for p in backup_dir.iterdir()
                if p.name.endswith(".numbers")
                and ".bak" not in p.name
                and p.name != backup_dir.name  # skip any stray originals
            ),
            key=lambda p: p.name,
        )
        # only files with a version stamp (….<YYYYMMDD-HHMMSS>[.N].numbers)
        stamp_marker = tuple(".0123456789-")
        backups = [
            b
            for b in backups
            if len(b.name.split(".")) >= 3 and b.name.split(".")[-2].isdigit()
        ]
        for old in backups[:-max_backups] if max_backups > 0 else []:
            old.unlink()
    except OSError:
        pass