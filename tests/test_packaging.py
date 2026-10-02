"""pyproject.toml dependency pins must match pins.txt (single source of truth)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_pyproject_pins_match_pins_txt():
    pins = {
        line.split("==")[0].lower(): line.strip()
        for line in (REPO / "skill-pack" / "references" / "pins.txt").read_text().splitlines()
        if re.match(r"^[A-Za-z0-9_.-]+==", line)
    }
    deps = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["dependencies"]
    declared = {d.split("==")[0].lower(): d for d in deps}
    assert declared == pins
