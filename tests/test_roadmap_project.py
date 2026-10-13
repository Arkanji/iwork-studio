"""The roadmap board: quadrant rules, the backlog data, and `score` writing back — headless."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("roadmap_project", REPO / "scripts" / "roadmap_project.py")
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)


@pytest.mark.parametrize("scores,want", [
    ((5, 5, 3, 1.5), (13, "Gold Mine")),
    ((4, 3, 1, 0.5), (8, "Quick Win")),
    ((5, 5, 3, 2.5), (13, "Big Bet")),
    ((3, 3, 1, 3), (7, "Trap")),
    ((4, 4, 3, 1.5), (11, "Gold Mine")),   # 11 is high; 1.5 sprints is quick
    ((4, 4, 2, 1.6), (10, "Trap")),
    ((5, 4, None, 1), (None, None)),       # a missing score leaves the quadrant empty
])
def test_quadrant_rules(scores, want):
    assert rp.quadrant(*scores) == want


def test_backlog_is_complete_and_has_no_traps():
    data = json.loads((REPO / "specs" / "roadmap.json").read_text(encoding="utf-8"))
    titles = [i["title"] for i in data["items"]]
    assert len(titles) == len(set(titles))
    for i in data["items"]:
        assert i["status"] in ("Todo", "In Progress", "Done") and i["track"] in [t[0] for t in rp.TRACKS]
        _, quad = rp.quadrant(i["vf"], i["ms"], i["fp"], i["sprints"])
        assert quad != "Trap", i["title"]  # traps stay off the roadmap
        if i.get("spec"):
            assert (REPO / i["spec"]).exists(), i["spec"]


def test_score_writes_only_what_changed(monkeypatch):
    fields = {n: {"id": n, "name": n, "dataType": "NUMBER"} for n in rp.NUMBER_FIELDS}
    fields["Quadrant"] = {"id": "Q", "name": "Quadrant", "dataType": "SINGLE_SELECT",
                          "options": [{"id": q[0], "name": q[0]} for q in rp.QUADRANTS]}
    state = {"id": "P", "url": "u", "fields": fields, "items": [
        {"id": "a", "title": "A", "values": {"Vision Fit": 5, "Market Signals": 5, "Financial Potential": 3,
                                             "Sprints": 1, "Attractiveness": 13.0, "Quadrant": "Gold Mine"}},
        {"id": "b", "title": "B", "values": {"Vision Fit": 5, "Market Signals": 5, "Financial Potential": 3,
                                             "Sprints": 3}},
        {"id": "c", "title": "C", "values": {"Vision Fit": 4}}]}
    writes = []
    monkeypatch.setattr(rp, "find_project", lambda gh, title: {"id": "P"})
    monkeypatch.setattr(rp, "project_state", lambda gh, pid: state)
    monkeypatch.setattr(rp, "set_value", lambda gh, p, item, field, v: writes.append((item, field["name"], v)))
    rp.score(object(), {"project": "x"})
    assert writes == [("b", "Attractiveness", 13.0), ("b", "Quadrant", "Big Bet")]
