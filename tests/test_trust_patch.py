"""Trust patch (specs/001-trust-patch): regression tests for every fix — headless."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import backups, keynote_io, numbers_format, numbers_io, numbers_structure, pages_io, safety  # noqa: E402
from iwork_studio.keynote_slides import DocumentOpenError  # noqa: E402

KEY_SRC = REPO / "tests" / "fixtures" / "arabic.key"
PAGES_SRC = REPO / "tests" / "fixtures" / "arabic.pages"


def _sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ── US3: private, bounded backups ────────────────────────────────────────────

@pytest.mark.parametrize("ext", [".numbers", ".key", ".pages"])
def test_fifteen_writes_keep_ten_backups_for_every_type(tmp_path, ext):
    f = tmp_path / f"doc{ext}"
    f.write_bytes(b"v0")
    made = []
    for i in range(15):
        f.write_bytes(f"v{i}".encode())
        made.append(backups.make_backup(f, check_open=False))
    left = sorted(p.name for p in backups.backup_dir_for(f).iterdir())
    assert len(left) == 10
    assert made[-1].name in left and made[0].name not in left  # newest kept
    assert not backups.legacy_dir_for(f).exists()  # nothing beside the file


def test_backups_live_in_the_private_folder(numbers_file):
    out = numbers_io.edit_cell(numbers_file, "B2", "x")
    root = Path(os.environ["IWORK_STUDIO_BACKUP_DIR"])
    assert root in Path(out["backup"]).parents
    assert not (numbers_file.parent / f"{numbers_file.name}.backups").exists()


def test_prune_only_touches_that_files_backups(tmp_path):
    a, b = tmp_path / "a.numbers", tmp_path / "b.numbers"
    for f in (a, b):
        f.write_bytes(b"x")
    bdir = tmp_path / "shared"
    for _ in range(12):
        backups.make_backup(a, bdir, keep=0, check_open=False)
    backups.make_backup(b, bdir, keep=0, check_open=False)
    (bdir / "notes.txt").write_text("keep me")
    backups.prune_dir(bdir, 10)
    names = [p.name for p in bdir.iterdir()]
    assert sum(n.startswith("a.numbers.") for n in names) == 10
    assert sum(n.startswith("b.numbers.") for n in names) == 1 and "notes.txt" in names


def test_legacy_backups_are_listed_and_restorable(numbers_file):
    original = _sha(numbers_file)
    legacy = backups.legacy_dir_for(numbers_file)
    legacy.mkdir()
    shutil.copy2(numbers_file, legacy / f"{numbers_file.name}.20250101-000000.numbers")
    numbers_io.edit_cell(numbers_file, "B2", "changed")
    names = [b["name"] for b in backups.list_backups(numbers_file)]
    assert f"{numbers_file.name}.20250101-000000.numbers" in names
    backups.restore_backup(numbers_file, f"{numbers_file.name}.20250101-000000.numbers")
    assert _sha(numbers_file) == original


def test_restoring_the_oldest_of_ten_survives_pruning(numbers_file):
    first = backups.make_backup(numbers_file, check_open=False)
    want = _sha(first)
    for _ in range(9):
        backups.make_backup(numbers_file, check_open=False)
    numbers_io.edit_cell(numbers_file, "B2", "changed")  # now 10 newer ones may push `first` out
    if first.exists():
        backups.restore_backup(numbers_file, first.name)
        assert _sha(numbers_file) == want


def test_restore_still_refuses_other_files(numbers_file, tmp_path):
    other = tmp_path / "other.numbers"
    shutil.copy2(numbers_file, other)
    b = backups.make_backup(other, check_open=False)
    with pytest.raises(backups.BackupError):
        backups.restore_backup(numbers_file, b.name)


# ── US1: never write beside an open document ─────────────────────────────────

@pytest.fixture()
def open_in_app(monkeypatch):
    def refuse(path):
        raise DocumentOpenError(f"{Path(path).name} is open")

    monkeypatch.setattr(safety, "assert_not_open", refuse)


@pytest.fixture()
def key_file(tmp_path):
    d = tmp_path / "deck.key"
    d.write_bytes(KEY_SRC.read_bytes())
    return d


@pytest.mark.parametrize("write", [
    lambda f: numbers_io.edit_cell(f, "B2", "x"),
    lambda f: numbers_format.set_cell_style(f, "A1:B2", bold=True),
    lambda f: numbers_structure.insert(f, "rows", values=[["a", "b", "c"]]),
    lambda f: numbers_structure.add_table(f, "New", [["a", "b"], [1, 2]]),
])
def test_numbers_writes_refuse_an_open_file(numbers_file, open_in_app, write):
    before = _sha(numbers_file)
    with pytest.raises(DocumentOpenError):
        write(numbers_file)
    assert _sha(numbers_file) == before


def test_keynote_replace_refuses_an_open_deck(key_file, open_in_app):
    before = _sha(key_file)
    with pytest.raises(DocumentOpenError):
        keynote_io.edit_text(key_file, "English", "x")
    assert _sha(key_file) == before


def test_restore_refuses_an_open_file(numbers_file, monkeypatch):
    numbers_io.edit_cell(numbers_file, "B2", "x")
    name = backups.list_backups(numbers_file)[0]["name"]
    before = _sha(numbers_file)
    monkeypatch.setattr(safety, "assert_not_open", lambda p: (_ for _ in ()).throw(DocumentOpenError("open")))
    with pytest.raises(DocumentOpenError):
        backups.restore_backup(numbers_file, name)
    assert _sha(numbers_file) == before


def test_open_check_matches_the_exact_path(tmp_path, monkeypatch):
    f = tmp_path / "budget.numbers"
    f.write_bytes(b"x")
    monkeypatch.setattr(safety, "_gui_session", lambda: True)
    monkeypatch.setattr(safety, "_open_paths", lambda kind: [str(tmp_path / "other.numbers")])
    safety.assert_not_open(f)  # a different file is open: fine
    monkeypatch.setattr(safety, "_open_paths", lambda kind: [str(f)])
    with pytest.raises(DocumentOpenError, match="overwritten"):
        safety.assert_not_open(f)


def test_open_check_is_skipped_without_a_gui(tmp_path, monkeypatch):
    monkeypatch.setattr(safety, "_gui_session", lambda: False)
    monkeypatch.setattr(safety, "_open_paths", lambda kind: pytest.fail("no app query without a GUI"))
    safety.assert_not_open(tmp_path / "x.numbers")


# ── US6: timeouts and secrets ────────────────────────────────────────────────

class _R:
    def __init__(self, rc=0, out="{}", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_script_and_params_go_on_stdin_never_argv(monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw.get("input")
        return _R(out=json.dumps({"ok": True}))

    monkeypatch.setattr(safety.subprocess, "run", run)
    safety.run_jxa("Numbers", "return JSON.stringify({ok: true});", {"props": {"password": "s3cret-pw"}})
    assert "s3cret-pw" not in " ".join(seen["cmd"]) and "s3cret-pw" in seen["input"]


def test_timeout_message_has_no_script_or_secret(monkeypatch):
    def run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd + [kw.get("input", "")], 1)

    monkeypatch.setattr(safety.subprocess, "run", run)
    with pytest.raises(safety.AppTimeoutError) as exc:
        safety.run_jxa("Pages", "return 1;", {"password": "s3cret-pw"}, timeout=1)
    assert "s3cret-pw" not in str(exc.value) and "return 1" not in str(exc.value)


def test_apple_event_timeout_is_an_app_timeout(monkeypatch):
    monkeypatch.setattr(safety.subprocess, "run", lambda cmd, **kw: _R(1, "", "execution error: Error: AppleEvent timed "
                                                                              "out. (-1712)"))
    with pytest.raises(safety.AppTimeoutError, match="dialog"):
        safety.run_jxa("Pages", "return 1;", {})


def test_automation_denied_has_a_hint(monkeypatch):
    monkeypatch.setattr(safety.subprocess, "run", lambda cmd, **kw: _R(1, "", "execution error: Not authorized "
                                                                              "to send Apple events (-1743)"))
    with pytest.raises(safety.AutomationDeniedError, match="Automation"):
        safety.run_jxa("Keynote", "return 1;", {})


def test_app_write_timeout_closes_the_document_then_rolls_back(tmp_path, monkeypatch):
    from iwork_studio import app_ops, numbers_structure as ns

    p = tmp_path / "book.numbers"
    ns.create(p, [{"name": "S", "tables": [{"name": "T", "rows": [["a", "b"], [1, 2], [3, 4]]}]}])
    before = _sha(p)
    closed = []

    def slow(*a, **k):
        p.write_bytes(b"half-written")
        raise safety.AppTimeoutError("Numbers didn't answer")

    monkeypatch.setattr(app_ops, "_jxa", slow)
    monkeypatch.setattr(safety, "close_without_saving", lambda kind, path: closed.append(Path(path).name))
    with pytest.raises(safety.AppTimeoutError):
        app_ops.sort_table(p, "B")
    assert closed == ["book.numbers"] and _sha(p) == before


# ── US5: the edited cell is read back ────────────────────────────────────────

def test_edit_cell_reports_the_read_back_value(numbers_file):
    out = numbers_io.edit_cell(numbers_file, "B2", 1250)
    assert out["cell"]["after"] == 1250


def test_edit_cell_rolls_back_when_the_cell_reads_wrong(numbers_file, monkeypatch):
    before = _sha(numbers_file)
    monkeypatch.setattr(numbers_io, "_same_value", lambda want, got: False)
    with pytest.raises(numbers_io.WriteVerificationError, match="reads"):
        numbers_io.edit_cell(numbers_file, "B2", 1250)
    assert _sha(numbers_file) == before


@pytest.mark.parametrize("want,got,ok", [
    (12, 12.0, True), (12, "12", False), ("12", 12, False), (True, 1, False), ("سارة", "سارة", True),
    (0.0003, 0.0003, True), (1.5, 1.6, False),
])
def test_same_value_is_strict_about_kind(want, got, ok):
    assert numbers_io._same_value(want, got) is ok


# ── US4: the deck outline stays inside the fence ─────────────────────────────

def test_deck_outline_paths_are_fenced_and_relative_to_the_deck(tmp_path, monkeypatch):
    from iwork_studio import mcp_server

    ToolError = mcp_server.ToolError

    inside = tmp_path / "work"
    inside.mkdir()
    monkeypatch.setenv("IWORK_STUDIO_ROOTS", str(inside))
    deck = inside / "q3.key"
    out = mcp_server._fence_outline(deck, [{"title": "x", "chart": {"from": "data.numbers"}, "image": "pic.png"}])
    assert out[0]["chart"]["from"] == str(inside / "data.numbers") and out[0]["image"] == str(inside / "pic.png")
    for bad in ({"image": "/etc/hosts.png"}, {"table": {"from": "../secret.numbers"}}, {"chart": {"from": "/tmp/x.numbers"}}):
        with pytest.raises(ToolError, match="outside"):
            mcp_server._fence_outline(deck, [bad])


# ── US2: Pages replace rewrites only matching paragraphs ─────────────────────

@pytest.fixture()
def pages_stub(tmp_path, monkeypatch):
    dest = tmp_path / "report.pages"
    dest.write_bytes(PAGES_SRC.read_bytes())
    before = "مقدمة التقرير 2025\rالقسم الأول\rنتائج 2025 و2025\rالخاتمة\r"
    state = {"reads": [before], "scripts": []}

    def read(p):
        return state["reads"].pop(0) if len(state["reads"]) > 1 else state["reads"][0]

    def jxa(script, timeout=180):
        state["scripts"].append(script)
        state["reads"] = [before.replace("2025", "2026")]
        return json.dumps({"changed": [0, 2], "paragraphs": 4})

    monkeypatch.setattr(pages_io, "preflight", lambda timeout=20: {"ok": True})
    monkeypatch.setattr(pages_io, "read_body_text", read)
    monkeypatch.setattr(pages_io, "_directions_or_none", lambda p: None)
    monkeypatch.setattr(pages_io, "_jxa", jxa)
    return dest, state


def test_pages_replace_writes_only_matching_paragraphs(pages_stub):
    dest, state = pages_stub
    out = pages_io.edit_pages_body(dest, find="2025", replace="2026")
    script = state["scripts"][-1]
    assert "doc.bodyText =" not in script and "paras[i] = " in script
    assert out["replacements"] == 3 and out["paragraphs_rewritten"] == 2
    assert "نتائج 2026 و2026" in out["after"]


@pytest.mark.parametrize("find,replace", [("القسم\rالأول", "x"), ("2025", "a\nb")])
def test_pages_replace_refuses_paragraph_breaks(pages_stub, find, replace):
    dest, state = pages_stub
    before = _sha(dest)
    with pytest.raises(pages_io.PagesOutOfScopeError, match="paragraph"):
        pages_io.edit_pages_body(dest, find=find, replace=replace)
    assert state["scripts"] == [] and _sha(dest) == before


# ── US7 / US8: install from PyPI; honest docs; no personal names ─────────────

def test_installer_pins_the_released_package():
    from iwork_studio import __version__, installer

    entry = installer.server_entry("/x/uvx")
    assert entry["args"][:2] == ["--from", f"iwork-studio=={__version__}"]
    assert "git+" not in (REPO / "install.sh").read_text()


def test_server_instructions_name_writes_without_dry_run():
    from iwork_studio import mcp_server

    text = mcp_server.INSTRUCTIONS if hasattr(mcp_server, "INSTRUCTIONS") else mcp_server.mcp.instructions
    assert "dry_run" in text and "iwork_restore_backup" in text and "iwork_export" in text


def test_examples_use_made_up_names():
    banned = ["".join(["Re", "sal"]).lower()]
    roots = ["src", "tests", "skill-pack", "specs", "scripts", "mcpb", "assets", ".specify/memory"]
    files = [REPO / f for f in ["README.md", "AGENTS.md", "llms.txt", "CHANGELOG.md", "PRIVACY.md", "server.json",
                                "glama.json"]]
    for r in roots:
        files += [p for p in (REPO / r).rglob("*") if p.is_file() and p.suffix in (".md", ".py", ".json", ".txt", ".sh",
                                                                                 ".html", ".css", ".js", ".svg")]
    import re

    # the company's Arabic name as a whole word (رسالة, "letter", is a normal word and stays allowed)
    arabic = re.compile("(?<![\u0600-\u06FF])" + "".join(["ر", "سال"]) + "(?![\u0600-\u06FF])")
    pillars = ["".join(["Programmable ", "value"]).lower(), "".join(["programmable ", "gift"]).lower(),
               "".join(["غير ", "النقدية"]), "".join(["قابلة ", "للبرمجة"]), "".join(["non-", "cash"])]
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="ignore")
        text = raw.lower()
        for word in banned + pillars:
            assert word not in text, f"{word!r} in {f.relative_to(REPO)}"
        assert not arabic.search(raw), f"company name in {f.relative_to(REPO)}"


# ── live (macOS + the apps): pytest -m aqua -k trust ─────────────────────────

def _jxa_live(kind, body, params):
    from iwork_studio.keynote_slides import _assert_aqua

    _assert_aqua()
    return safety.run_jxa(kind, body, params, timeout=180)


@pytest.mark.aqua
def test_live_trust_open_numbers_file_is_refused(tmp_path):
    p = tmp_path / "open.numbers"
    numbers_structure.create(p, [{"name": "S", "tables": [{"name": "T", "rows": [["a", "b"], [1, 2]]}]}])
    _jxa_live("Numbers", "app.open(Path(params.p)); return JSON.stringify({});", {"p": str(p)})
    try:
        before = _sha(p)
        with pytest.raises(DocumentOpenError):
            numbers_io.edit_cell(p, "B2", 5)
        assert _sha(p) == before
    finally:
        safety.close_without_saving("Numbers", p)
    assert numbers_io.edit_cell(p, "B2", 5)["cell"]["after"] == 5  # closed: the write goes through


@pytest.mark.aqua
def test_live_trust_pages_replace_keeps_other_paragraphs_formatting(tmp_path):
    p = tmp_path / "styled.pages"
    p.write_bytes(PAGES_SRC.read_bytes())
    pages_io.edit_pages_body(p, mode="set_body", new_body="alpha one\rbeta two\rgamma three")
    style = """  const doc = app.open(Path(params.p));
  const par = doc.bodyText.paragraphs[2];
  par.font = 'Courier'; par.size = 30;
  app.save(doc); app.close(doc, {saving: 'no'});
  return JSON.stringify({});"""
    _jxa_live("Pages", style, {"p": str(p)})
    out = pages_io.edit_pages_body(p, find="alpha", replace="delta")
    assert out["paragraphs_rewritten"] == 1 and out["after"].startswith("delta one")
    read = """  const doc = app.open(Path(params.p));
  const par = doc.bodyText.paragraphs[2];
  const r = {font: par.font(), size: par.size()};
  app.close(doc, {saving: 'no'});
  return JSON.stringify(r);"""
    got = _jxa_live("Pages", read, {"p": str(p)})
    assert got["font"].startswith("Courier") and round(got["size"]) == 30, got
