# Listing kit

Copy-ready text for directories and the GitHub About box. Keep every listing on the same three
messages: **safe** (never damages your file), **designed** (decks from your data and brand),
**Arabic-ready**. Don't lead with tool counts.

## GitHub About box

**Description** (≤ 350 characters):

> The safe way to let AI edit your Numbers, Keynote and Pages files. Designed decks from your data and brand, checked as rendered; Arabic/RTL-ready; every change backed up, verified and undoable. MCP server + Python library + agent skill for Claude and any MCP client.

**Website**: `https://pypi.org/project/iwork-studio/`

**Topics** (GitHub allows 20):

`mcp` `mcp-server` `model-context-protocol` `claude` `claude-code` `ai-agents` `apple-iwork` `keynote` `numbers` `pages` `macos` `applescript` `jxa` `presentations` `spreadsheets` `arabic` `rtl` `design-system` `python` `automation`

## Short description (≤ 100 characters)

> Safe AI editing for Apple Numbers, Keynote & Pages: designed decks, Arabic-ready, undoable.

## One-paragraph description

> iWork Studio lets Claude and other AI agents create, edit, design and export Apple Numbers, Keynote and Pages files without ever damaging them. Every change is backed up first, made on a copy, read back and checked, then swapped in atomically, with one-call undo. Turn a spreadsheet into a designed Keynote deck with chart and table slides in your brand, reviewed as rendered. Arabic and right-to-left text round-trip exactly. Works in Claude Desktop (one-click extension), Claude Code (plugin), and any MCP client.

## Install lines

| Client | Line |
|---|---|
| Claude Desktop (Mac) | Download `iwork-studio-<version>.mcpb` from the latest GitHub release and double-click it |
| Claude Desktop (Terminal) | `curl -LsSf https://raw.githubusercontent.com/Arkanji/iwork-studio/main/install.sh \| sh` |
| Claude Code (plugin) | `claude plugin marketplace add Arkanji/iwork-studio` then `claude plugin install iwork-studio@iwork-studio` |
| Claude Code (tools only) | `claude mcp add iwork-studio -- uvx --from iwork-studio@latest iwork-studio-mcp` |
| Any MCP client | `uvx --from iwork-studio@latest iwork-studio-mcp config` → paste the JSON |
| Skill only (skills.sh) | `npx skills add Arkanji/iwork-studio` |
| Python | `pip install iwork-studio` |

## Per-directory notes

| Directory | Where | Fields to fill | Notes |
|---|---|---|---|
| mcp.so | mcp.so → Submit | name, GitHub URL, short description, tags | Uses the GitHub README |
| PulseMCP | pulsemcp.com → Submit | GitHub URL | May already pull from the MCP Registry; check first |
| Smithery | smithery.ai → Add server | GitHub repo; local (stdio) server | Python `uvx` launch |
| Cursor directory | cursor.directory → Submit MCP | name, description, install JSON | Paste the `config` JSON |
| LobeHub | lobehub.com/mcp → Submit | GitHub URL, category Productivity | Reads README + screenshots |
| mcpservers.org | mcpservers.org → Submit | GitHub URL, category | |
| skills.sh | `npx skills add Arkanji/iwork-studio` once | — | Listing comes from installs; also feeds the Hermes Agent Skills Hub |

## Screenshots to attach (in order)

1. `assets/demo.gif`: the 15-second demo.
2. A designed deck slide (chart slide) from the gallery.
3. The same slide in Arabic (RTL).
4. A rollback message ("didn't match, file untouched, undo in one call").

## Tags

`productivity` `presentations` `spreadsheets` `documents` `macos` `apple` `design` `arabic`
