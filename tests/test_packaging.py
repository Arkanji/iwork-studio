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


def test_release_versions_agree():
    """pyproject, server.json and the Desktop-extension manifest ship the same version."""
    import json
    import tomllib

    v = tomllib.load(open(REPO / "pyproject.toml", "rb"))["project"]["version"]
    server = json.load(open(REPO / "server.json"))
    manifest = json.load(open(REPO / "mcpb" / "manifest.json"))
    assert server["version"] == server["packages"][0]["version"] == manifest["version"] == v
    plugin = json.loads((REPO / "skill-pack" / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["version"] == v
    assert plugin["mcpServers"]["iwork-studio"]["args"] == ["--from", f"iwork-studio=={v}", "iwork-studio-mcp"]
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert market["plugins"][0]["source"] == "./skill-pack"
    from iwork_studio import __version__

    assert __version__ == v


def test_registry_ownership_line():
    """The MCP Registry checks this line in the PyPI README to verify the package."""
    import json

    name = json.load(open(REPO / "server.json"))["name"]
    assert name == "io.github.Arkanji/iwork-studio"  # GitHub login, case-sensitive
    assert f"mcp-name: {name} " in (REPO / "README.md").read_text() or f"mcp-name: {name} -->" in (REPO / "README.md").read_text()
    assert len(json.load(open(REPO / "server.json"))["description"]) <= 100


def test_serve_accepts_roots(monkeypatch):
    import os

    from iwork_studio import mcp_server

    ran = {}
    monkeypatch.setattr(mcp_server.mcp, "run", lambda transport: ran.setdefault("t", transport))
    monkeypatch.delenv("IWORK_STUDIO_ROOTS", raising=False)
    monkeypatch.setattr("sys.argv", ["iwork-studio-mcp", "serve", "--roots", "~/Documents", "/tmp/x"])
    mcp_server.main()
    assert ran["t"] == "stdio"
    assert os.environ["IWORK_STUDIO_ROOTS"] == os.pathsep.join([os.path.expanduser("~/Documents"), "/tmp/x"])
    monkeypatch.setattr("sys.argv", ["iwork-studio-mcp", "serve", "--roots", "${user_config.allowed_folders}"])
    monkeypatch.delenv("IWORK_STUDIO_ROOTS")
    mcp_server.main()
    assert "IWORK_STUDIO_ROOTS" not in os.environ
