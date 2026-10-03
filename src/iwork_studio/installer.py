"""iWork Studio — register the MCP server with MCP clients.

    iwork-studio-mcp install [--roots DIR ...] [--dry-run]   # Claude desktop app
    iwork-studio-mcp uninstall                                # remove it again
    iwork-studio-mcp config                                   # JSON for any other client

The Claude desktop app does not inherit your shell's PATH, so a bare "uvx"
fails with "spawn uvx ENOENT". The installer writes the absolute uvx path.
Like every write in this project: the existing config is backed up first, the
new one is written to a temp file and swapped in atomically, and every other
server already in the config is kept as is.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_NAME = "iwork-studio"
SOURCE = "git+https://github.com/Arkanji/iwork-studio"
UVX_CANDIDATES = ("~/.local/bin/uvx", "/opt/homebrew/bin/uvx", "/usr/local/bin/uvx", "~/.cargo/bin/uvx")


def claude_desktop_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def find_uvx() -> str:
    found = shutil.which("uvx")
    if found:
        return str(Path(found).resolve())
    for cand in UVX_CANDIDATES:
        p = Path(os.path.expanduser(cand))
        if p.exists():
            return str(p)
    raise FileNotFoundError(
        "uvx not found. Install uv first:  curl -LsSf https://astral.sh/uv/install.sh | sh"
    )


def server_entry(uvx: str, roots: list[str] | None = None) -> dict:
    entry: dict = {"command": uvx, "args": ["--from", SOURCE, "iwork-studio-mcp"]}
    if roots:
        resolved = [str(Path(os.path.expanduser(r)).resolve()) for r in roots]
        entry["env"] = {"IWORK_STUDIO_ROOTS": os.pathsep.join(resolved)}
    return entry


def _load(path: Path) -> dict:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON ({exc}); fix or remove it, then re-run") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def _write(path: Path, data: dict) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.{stamp}.bak")
        shutil.copy2(path, backup)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    json.loads(Path(tmp).read_text(encoding="utf-8"))  # re-parse gate
    os.replace(tmp, path)
    return backup


def install(config_path: Path, uvx: str, roots: list[str] | None = None, dry_run: bool = False) -> dict:
    data = _load(config_path)
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f'"mcpServers" in {config_path} is not an object')
    previous = servers.get(SERVER_NAME)
    servers[SERVER_NAME] = server_entry(uvx, roots)
    backup = None if dry_run else _write(config_path, data)
    return {
        "config": str(config_path),
        "action": "updated" if previous else "added",
        "entry": servers[SERVER_NAME],
        "other_servers_kept": sorted(k for k in servers if k != SERVER_NAME),
        "backup": str(backup) if backup else None,
        "dry_run": dry_run,
    }


def uninstall(config_path: Path) -> dict:
    data = _load(config_path)
    servers = data.get("mcpServers", {})
    if SERVER_NAME not in servers:
        return {"config": str(config_path), "action": "not installed"}
    del servers[SERVER_NAME]
    backup = _write(config_path, data)
    return {"config": str(config_path), "action": "removed", "backup": str(backup) if backup else None}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="iwork-studio-mcp", description="iWork Studio MCP server")
    sub = ap.add_subparsers(dest="cmd")
    p_in = sub.add_parser("install", help="add iWork Studio to the Claude desktop app")
    p_in.add_argument("--roots", nargs="+", metavar="DIR",
                      help="only let the server touch files inside these folders (recommended)")
    p_in.add_argument("--dry-run", action="store_true", help="show the change without writing it")
    p_in.add_argument("--config", type=Path, default=None, help=argparse.SUPPRESS)
    p_un = sub.add_parser("uninstall", help="remove iWork Studio from the Claude desktop app")
    p_un.add_argument("--config", type=Path, default=None, help=argparse.SUPPRESS)
    p_cfg = sub.add_parser("config", help="print the JSON entry for any MCP client")
    p_cfg.add_argument("--roots", nargs="+", metavar="DIR")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "install":
            result = install(args.config or claude_desktop_config_path(), find_uvx(), args.roots, args.dry_run)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            if not args.dry_run:
                print("\nDone. Quit the Claude app completely (Cmd-Q) and reopen it.\n"
                      "Then ask Claude: \"what can iwork-studio do on this Mac?\"")
        elif args.cmd == "uninstall":
            result = uninstall(args.config or claude_desktop_config_path())
            print(json.dumps(result, indent=2, ensure_ascii=False))
            if result["action"] == "removed":
                print("\nDone. Quit the Claude app completely (Cmd-Q) and reopen it.")
        elif args.cmd == "config":
            print(json.dumps({"mcpServers": {SERVER_NAME: server_entry(find_uvx(), args.roots)}},
                             indent=2, ensure_ascii=False))
        else:
            ap.print_help()
            return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
