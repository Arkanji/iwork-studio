"""Claude desktop app installer — headless."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from iwork_studio import installer  # noqa: E402

UVX = "/Users/someone/.local/bin/uvx"


def _read(p: Path) -> dict:
    return json.loads(p.read_text())


def test_fresh_install_writes_absolute_uvx(tmp_path):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    r = installer.install(cfg, UVX)
    entry = _read(cfg)["mcpServers"]["iwork-studio"]
    assert entry["command"] == UVX  # absolute: the desktop app has no shell PATH
    assert entry["args"] == ["--from", "git+https://github.com/Arkanji/iwork-studio", "iwork-studio-mcp"]
    assert r["action"] == "added" and r["backup"] is None


def test_keeps_other_servers_and_settings_and_backs_up(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    original = {"mcpServers": {"other": {"command": "x"}}, "globalShortcut": "Cmd+Space"}
    cfg.write_text(json.dumps(original))
    r = installer.install(cfg, UVX)
    data = _read(cfg)
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["globalShortcut"] == "Cmd+Space"
    assert r["other_servers_kept"] == ["other"]
    assert _read(Path(r["backup"])) == original


def test_reinstall_updates_in_place(tmp_path):
    cfg = tmp_path / "c.json"
    installer.install(cfg, UVX)
    r = installer.install(cfg, "/opt/homebrew/bin/uvx")
    assert r["action"] == "updated"
    assert _read(cfg)["mcpServers"]["iwork-studio"]["command"] == "/opt/homebrew/bin/uvx"


def test_roots_become_absolute_env(tmp_path):
    cfg = tmp_path / "c.json"
    a, b = tmp_path / "Decks", tmp_path / "Sheets"
    installer.install(cfg, UVX, roots=[str(a), str(b)])
    env = _read(cfg)["mcpServers"]["iwork-studio"]["env"]
    assert env["IWORK_STUDIO_ROOTS"] == os.pathsep.join([str(a.resolve()), str(b.resolve())])


def test_dry_run_writes_nothing(tmp_path):
    cfg = tmp_path / "c.json"
    r = installer.install(cfg, UVX, dry_run=True)
    assert not cfg.exists() and r["dry_run"]


def test_broken_config_is_refused_untouched(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text("{not json")
    with pytest.raises(ValueError):
        installer.install(cfg, UVX)
    assert cfg.read_text() == "{not json"


def test_uninstall_removes_only_ours(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    installer.install(cfg, UVX)
    assert installer.uninstall(cfg)["action"] == "removed"
    assert _read(cfg)["mcpServers"] == {"other": {"command": "x"}}
    assert installer.uninstall(cfg)["action"] == "not installed"


def test_cli_install_and_missing_uvx(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c.json"
    monkeypatch.setattr(installer, "find_uvx", lambda: UVX)
    assert installer.main(["install", "--config", str(cfg)]) == 0
    assert "Cmd-Q" in capsys.readouterr().out

    def nope():
        raise FileNotFoundError("uvx not found. Install uv first")

    monkeypatch.setattr(installer, "find_uvx", nope)
    assert installer.main(["install", "--config", str(cfg)]) == 1
    assert "Install uv" in capsys.readouterr().err
