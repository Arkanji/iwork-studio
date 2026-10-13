# Listing kit

Copy-ready text for the GitHub About box and the MCP directories. Every listing tells the same
three things: **safe** (it never damages your file), **designed** (decks from your data and your
brand), and **Arabic-ready**. Don't lead with tool counts.

## GitHub About box

Edit it with the ⚙️ next to **About** on the repo page.

**Description** (266 characters):

```
The safe way to let AI edit your Numbers, Keynote and Pages files. Designed decks from your data and brand, checked as rendered; Arabic/RTL-ready; every change backed up, verified and undoable. MCP server + Python library + agent skill for Claude and any MCP client.
```

**Website**:

```
https://pypi.org/project/iwork-studio/
```

**Topics** (20, the GitHub maximum; lowercase letters, digits and hyphens only). Type them one at
a time:

```
mcp mcp-server model-context-protocol claude claude-code ai-agents apple-iwork keynote numbers pages macos applescript jxa presentations spreadsheets arabic rtl design-system python automation
```

Under **Include in the home page**, keep **Releases** ticked; untick Packages and Deployments
(they're empty).

## Short description (91 characters)

```
Safe AI editing for Apple Numbers, Keynote & Pages: designed decks, Arabic-ready, undoable.
```

## Long description

```
iWork Studio lets Claude and other AI agents create, edit, design and export Apple Numbers, Keynote and Pages files without ever damaging them. Every change is backed up first, made on a copy, read back and checked, then swapped in atomically, and any change can be undone in one call. Turn a spreadsheet into a designed Keynote deck with chart and table slides in your brand, reviewed as rendered. Arabic and right-to-left text round-trip exactly. Runs locally on your Mac; reading and editing Numbers and Keynote files also works on Linux.
```

## Install lines

| Client | Line |
|---|---|
| Claude Desktop (Mac) | Download `iwork-studio-<version>.mcpb` from the [latest release](https://github.com/Arkanji/iwork-studio/releases/latest) and double-click it |
| Claude Desktop (Terminal) | `curl -LsSf https://raw.githubusercontent.com/Arkanji/iwork-studio/main/install.sh \| sh` |
| Claude Code (plugin: tools + skill) | `claude plugin marketplace add Arkanji/iwork-studio`, then `claude plugin install iwork-studio@iwork-studio` |
| Claude Code (tools only) | `claude mcp add iwork-studio -- uvx --from iwork-studio@latest iwork-studio-mcp` |
| Any MCP client | `uvx --from iwork-studio@latest iwork-studio-mcp config`, then paste the printed JSON |
| Skill only | `npx skills add Arkanji/iwork-studio --skill iwork-studio` |
| Python | `pip install iwork-studio` |

MCP Registry name: `io.github.Arkanji/iwork-studio`

## Directories

Ordered by reach per minute. Each entry was checked on 2026-10-13; anything marked *unverified*
couldn't be confirmed from the site itself.

| # | Directory | What to do | Notes |
|---|---|---|---|
| 1 | **skills.sh** | Run once: `npx skills add Arkanji/iwork-studio --skill iwork-studio` | No form. The leaderboard counts installs, so the listing appears after the first one. Always pass `--skill iwork-studio`. Also feeds the Hermes Agent Skills Hub. |
| 2 | **Glama** | Nothing to submit (already listed). To claim it: open the server's page on glama.ai, sign in with GitHub, click **Claim ownership** | Uses `glama.json` (already on `main`). Re-claim after editing that file. |
| 3 | **mcp.so** | Form: https://mcp.so/submit, paste the GitHub URL | Takes public GitHub servers. Other fields *unverified*. |
| 4 | **mcpservers.org** | Form: https://mcpservers.org/submit | Fields: name, category (Productivity), short description, repo link, MCP Registry name (`io.github.Arkanji/iwork-studio`), leave "remote" unticked, contact email. Choose the free plan (review within about 2 weeks). No PRs accepted. |
| 5 | **LobeHub** | In Terminal: `npx -y @lobehub/market-cli login`, then `npx -y @lobehub/market-cli github connect`, then `npx -y @lobehub/market-cli plugin submit https://github.com/Arkanji/iwork-studio` | Import takes a few minutes; check with `… plugin list --output json`. GitHub issues asking for a listing get closed. |
| 6 | **cursor.directory** | https://cursor.directory/plugins/new, sign in, paste the repo URL | Reads `.mcp.json` as the install config (it points at the PyPI package). |
| 7 | **PulseMCP** | Probably nothing: it pulls from the official MCP Registry, where we're listed | Its submit form was reported paused in October 2026 (*unverified*). Check pulsemcp.com in a week. |
| — | **Smithery** | Optional, later | Local servers are listed only as an uploaded `.mcpb` (`smithery mcp publish ./iwork-studio-<version>.mcpb -n <your-org>/iwork-studio`). Our bundle's `"type": "uv"` may be rejected (*unverified*); try it once and tell us the error. |
| ✅ | awesome-mcp-servers (punkpeye) | Done (merged 2026-10-08) | |
| ✅ | Official MCP Registry | Done (published by every release) | |

## Screenshots, in this order

Use these wherever a form asks for images.

1. `assets/demo.gif`, the 15-second demo.
2. A designed chart slide (from the gallery, once it exists).
3. The same slide in Arabic, right to left.
4. A rollback message ("didn't match, file untouched, undo in one call").

## Tags (for forms that ask)

```
productivity, presentations, spreadsheets, documents, macos, apple, design, arabic
```
