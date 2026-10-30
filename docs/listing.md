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
| Hermes Agent (tools + skill) | `hermes plugins install iwork-studio`, then `hermes plugins enable iwork-studio` |
| Skill only | `npx skills add Arkanji/iwork-studio --skill iwork-studio` |
| Python | `pip install iwork-studio` |

MCP Registry name: `io.github.Arkanji/iwork-studio`

## Directories

Status as of 2026-10-13. Re-check pending reviews after two weeks.

| Directory | Status | Notes |
|---|---|---|
| Official MCP Registry | ✅ Listed | Published by every release |
| awesome-mcp-servers (punkpeye) | ✅ Listed | Merged 2026-10-08 |
| Glama | ✅ Claimed | Verified owner. Its README copy refreshes on its own crawl (Admin tab may offer a sync). Its quality score marks tool count 2/5 |
| skills.sh | ✅ Installed once | Appears once its install count catches up. Always use `npx skills add Arkanji/iwork-studio --skill iwork-studio` |
| cursor.directory | ⏳ Submitted | Public after their security scan. Reads `.mcp.json` |
| mcpservers.org | ⏳ Submitted (free plan) | Review within about 2 weeks, email on approval |
| mcp.so | ⏳ Free ticket sent | Listing itself is paid ($39); not worth it. Leave the ticket |
| Hermes plugin catalog | ⏳ [PR open](https://github.com/NousResearch/hermes-agent/pull/147001) | Package in `hermes/`. Each release needs a new PR moving the pinned SHA (`plugin-catalog/iwork-studio.yaml`) |
| PulseMCP | — Nothing to do | Pulls from the official Registry |
| LobeHub | ✗ Skipped | Its GitHub connect asks for private-repo access. Revisit only if it offers public-only access |
| Smithery | — Later, optional | Local servers only as an uploaded `.mcpb`; our `"type": "uv"` may be rejected |

**Rule for any directory:** GitHub sign-in with profile and email is fine; never grant repository
access (public or private) for a listing.

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
