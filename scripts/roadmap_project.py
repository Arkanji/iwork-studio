#!/usr/bin/env python3
"""The roadmap as a GitHub Project, with the quadrant computed from the scores.

    python scripts/roadmap_project.py setup   # create the project, its fields and the items in specs/roadmap.json
    python scripts/roadmap_project.py score   # recompute Attractiveness and Quadrant on every item

GitHub Projects has no formula fields, so `score` reads each item's Vision Fit, Market
Signals, Financial Potential and Sprints and writes Attractiveness (their sum, /15) and
Quadrant back. The roadmap workflow runs it every hour and on demand.

Needs ROADMAP_TOKEN: a classic token with the `project` scope (and `repo` to link the
project to this repository). Runs in GitHub Actions; nothing here touches local files
except reading specs/roadmap.json.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "specs" / "roadmap.json"
API = "https://api.github.com/graphql"

HIGH_ATTRACTIVENESS = 11   # out of 15
HIGH_FEASIBILITY = 1.5     # sprints or fewer
QUADRANTS = [  # name, colour, description
    ("Gold Mine", "GREEN", "High attractiveness, quick to build: do now"),
    ("Quick Win", "BLUE", "Lower attractiveness, quick to build: batch them"),
    ("Big Bet", "PURPLE", "High attractiveness, slow to build: probe first, plan"),
    ("Trap", "RED", "Lower attractiveness, slow to build: don't"),
]
TRACKS = [("Now", "GREEN", "This release or the next"), ("Next", "BLUE", "Two to four weeks"),
          ("Later", "GRAY", "After that"), ("Parked", "YELLOW", "Big Bets, waiting on a probe")]
NUMBER_FIELDS = ["Vision Fit", "Market Signals", "Financial Potential", "Sprints", "Attractiveness"]
TEXT_FIELDS = ["Release", "Spec"]


def quadrant(vf, ms, fp, sprints) -> tuple[float | None, str | None]:
    """(attractiveness, quadrant) from the four scores; (None, None) if any is missing."""
    if None in (vf, ms, fp, sprints):
        return None, None
    attractiveness = float(vf) + float(ms) + float(fp)
    high = attractiveness >= HIGH_ATTRACTIVENESS
    quick = float(sprints) <= HIGH_FEASIBILITY
    if high and quick:
        return attractiveness, "Gold Mine"
    if quick:
        return attractiveness, "Quick Win"
    if high:
        return attractiveness, "Big Bet"
    return attractiveness, "Trap"


class GitHub:
    def __init__(self, token: str):
        self.token = token

    def q(self, query: str, **variables) -> dict:
        req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables}).encode(),
                                     headers={"Authorization": f"bearer {self.token}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read())
        if out.get("errors"):
            raise RuntimeError(json.dumps(out["errors"])[:800])
        return out["data"]


FIELDS_Q = """fields(first: 50) { nodes {
  ... on ProjectV2FieldCommon { id name dataType }
  ... on ProjectV2SingleSelectField { id name options { id name } } } }"""


def find_project(gh: GitHub, title: str) -> dict | None:
    data = gh.q("""query { viewer { id login projectsV2(first: 50) { nodes { id number title } } } }""")
    for p in data["viewer"]["projectsV2"]["nodes"]:
        if p["title"] == title:
            return p
    return None


def project_state(gh: GitHub, project_id: str) -> dict:
    data = gh.q("""query($id: ID!) { node(id: $id) { ... on ProjectV2 { id number url %s
      items(first: 100) { nodes { id
        content { ... on DraftIssue { title } ... on Issue { title } ... on PullRequest { title } }
        fieldValues(first: 30) { nodes {
          ... on ProjectV2ItemFieldNumberValue { number field { ... on ProjectV2FieldCommon { name } } }
          ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { name } } }
          ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } } } } } } } } }"""
                % FIELDS_Q, id=project_id)
    node = data["node"]
    fields = {f["name"]: f for f in node["fields"]["nodes"] if f}
    items = []
    for it in node["items"]["nodes"]:
        values = {}
        for v in it["fieldValues"]["nodes"]:
            if not v or "field" not in v:
                continue
            values[v["field"]["name"]] = v.get("number", v.get("text", v.get("name")))
        items.append({"id": it["id"], "title": (it.get("content") or {}).get("title"), "values": values})
    return {"id": node["id"], "url": node["url"], "fields": fields, "items": items}


def set_value(gh: GitHub, project_id: str, item_id: str, field: dict, value) -> None:
    if field.get("options") is not None:
        opt = next((o["id"] for o in field["options"] if o["name"] == value), None)
        if opt is None:
            raise RuntimeError(f"{field['name']} has no option {value!r}")
        v = {"singleSelectOptionId": opt}
    elif field.get("dataType") == "NUMBER":
        v = {"number": float(value)}
    else:
        v = {"text": str(value)}
    gh.q("""mutation($p: ID!, $i: ID!, $f: ID!, $v: ProjectV2FieldValue!) {
      updateProjectV2ItemFieldValue(input: {projectId: $p, itemId: $i, fieldId: $f, value: $v}) { projectV2Item { id } } }""",
         p=project_id, i=item_id, f=field["id"], v=v)


def ensure_fields(gh: GitHub, project_id: str, fields: dict) -> None:
    def add(name, dtype, options=None):
        if name in fields:
            return
        inp = {"projectId": project_id, "dataType": dtype, "name": name}
        if options:
            inp["singleSelectOptions"] = [{"name": n, "color": c, "description": d} for n, c, d in options]
        gh.q("""mutation($in: CreateProjectV2FieldInput!) { createProjectV2Field(input: $in) {
          projectV2Field { ... on ProjectV2FieldCommon { id } } } }""", **{"in": inp})
        print(f"  field: {name}")

    for name in NUMBER_FIELDS:
        add(name, "NUMBER")
    for name in TEXT_FIELDS:
        add(name, "TEXT")
    add("Quadrant", "SINGLE_SELECT", QUADRANTS)
    add("Track", "SINGLE_SELECT", TRACKS)


def setup(gh: GitHub, data: dict) -> None:
    viewer = gh.q("query { viewer { id login } }")["viewer"]
    project = find_project(gh, data["project"])
    if project:
        print(f"project exists: {data['project']} (#{project['number']})")
    else:
        project = gh.q("""mutation($o: ID!, $t: String!) { createProjectV2(input: {ownerId: $o, title: $t}) {
          projectV2 { id number } } }""", o=viewer["id"], t=data["project"])["createProjectV2"]["projectV2"]
        print(f"created project #{project['number']} (private)")
        repo = os.environ.get("GITHUB_REPOSITORY")
        if repo:
            owner, name = repo.split("/")
            try:
                rid = gh.q("query($o: String!, $n: String!) { repository(owner: $o, name: $n) { id } }",
                           o=owner, n=name)["repository"]["id"]
                gh.q("""mutation($p: ID!, $r: ID!) { linkProjectV2ToRepository(input: {projectId: $p, repositoryId: $r}) {
                  repository { id } } }""", p=project["id"], r=rid)
                print(f"linked to {repo}")
            except RuntimeError as exc:  # linking is a nicety; the board works without it
                print(f"  (not linked to the repo: {exc})")
    state = project_state(gh, project["id"])
    ensure_fields(gh, project["id"], state["fields"])
    state = project_state(gh, project["id"])
    have = {it["title"] for it in state["items"]}
    base = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'Arkanji/iwork-studio')}/blob/main/"
    for item in data["items"]:
        if item["title"] in have:
            continue
        body = f"Spec: {base}{item['spec']}" if item.get("spec") else ""
        new = gh.q("""mutation($p: ID!, $t: String!, $b: String) { addProjectV2DraftIssue(input: {projectId: $p, title: $t, body: $b}) {
          projectItem { id } } }""", p=project["id"], t=item["title"], b=body)["addProjectV2DraftIssue"]["projectItem"]
        f = state["fields"]
        for key, name in (("vf", "Vision Fit"), ("ms", "Market Signals"), ("fp", "Financial Potential"),
                          ("sprints", "Sprints"), ("release", "Release"), ("track", "Track"), ("status", "Status")):
            if item.get(key) not in (None, "") and name in f:
                set_value(gh, project["id"], new["id"], f[name], item[key])
        if item.get("spec"):
            set_value(gh, project["id"], new["id"], f["Spec"], base + item["spec"])
        print(f"  item: {item['title']}")
    score(gh, data)
    print(f"\nBoard: {state['url']}")


def score(gh: GitHub, data: dict) -> None:
    project = find_project(gh, data["project"])
    if not project:
        raise SystemExit(f"no project titled {data['project']!r}: run `setup` first")
    state = project_state(gh, project["id"])
    f = state["fields"]
    changed = 0
    for it in state["items"]:
        v = it["values"]
        att, quad = quadrant(v.get("Vision Fit"), v.get("Market Signals"), v.get("Financial Potential"),
                             v.get("Sprints"))
        if att is None:
            continue
        if v.get("Attractiveness") != att:
            set_value(gh, state["id"], it["id"], f["Attractiveness"], att)
            changed += 1
        if v.get("Quadrant") != quad:
            set_value(gh, state["id"], it["id"], f["Quadrant"], quad)
            changed += 1
    print(f"scored {len(state['items'])} items, {changed} cells updated")


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "score"
    token = os.environ.get("ROADMAP_TOKEN")
    if not token:
        print("ROADMAP_TOKEN is not set (a classic token with the `project` scope)", file=sys.stderr)
        return 2
    data = json.loads(DATA.read_text(encoding="utf-8"))
    gh = GitHub(token)
    if mode == "setup":
        setup(gh, data)
    elif mode == "score":
        score(gh, data)
    else:
        print("usage: roadmap_project.py setup|score", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
