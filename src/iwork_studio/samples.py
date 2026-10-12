"""iWork Studio — sample files, so a first try needs nothing of the user's own.

  copy_samples(folder)   copies sample-sales.numbers (synthetic sales data, an English
                         and an Arabic sheet) and sample-outline.md into `folder`;
                         never overwrites a file that's already there
"""

from __future__ import annotations

import shutil
from pathlib import Path

__all__ = ["copy_samples", "SAMPLES", "TRY_IT"]

_DIR = Path(__file__).resolve().parent / "samples"
SAMPLES = ("sample-sales.numbers", "sample-outline.md")

TRY_IT = [
    "Copy the iWork Studio samples to my Desktop, then turn sample-sales.numbers into a 5-slide board deck "
    "with the executive kit: a chart of the quarters and a table of the regions.",
    "In sample-sales.numbers, style the Quarterly revenue table with the minimal kit and format Q1–Q4 as "
    "currency.",
    "Build the same deck in Arabic from the المبيعات sheet, right-to-left, then check it with the design review.",
]


def copy_samples(folder) -> dict:
    """Copy the sample files into `folder` (created if missing). Existing files are skipped."""
    dest = Path(folder).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    copied, skipped = [], []
    for name in SAMPLES:
        target = dest / name
        if target.exists():
            skipped.append(str(target))
            continue
        shutil.copy2(_DIR / name, target)
        copied.append(str(target))
    return {"ok": True, "folder": str(dest), "copied": copied, "skipped_existing": skipped, "try_it": TRY_IT}
