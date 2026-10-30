# iWork Studio for Hermes

The safe way to let Hermes edit your Apple Numbers, Keynote and Pages files. Build designed
Keynote decks from your data and your brand, edit spreadsheets and documents, and export to PDF,
Excel, Word or PowerPoint. Every change is backed up first, made on a copy, read back and checked,
then swapped in; any change can be undone in one call. Arabic and right-to-left text round-trip
exactly.

This package gives Hermes the `iwork-studio` MCP server (65 tools) and the `iwork-studio` skill
that tells the agent how to use them. Full documentation: the
[main README](https://github.com/Arkanji/iwork-studio#readme).

![iWork Studio demo](https://raw.githubusercontent.com/Arkanji/iwork-studio/v2.6.1/assets/demo.gif)

## Install

```bash
hermes plugins install iwork-studio
hermes plugins enable iwork-studio
```

Needs macOS with [`uv`](https://docs.astral.sh/uv/) on the PATH. Then ask Hermes
*"what can iwork-studio do on this Mac?"*.

- **Fence it** (recommended): set `IWORK_STUDIO_ROOTS` to the folders it may touch,
  `:`-separated (for example `~/Documents:~/Desktop`), in your shell or profile `.env`.
- **Load less** (optional): `IWORK_STUDIO_TOOLSETS=keynote,design` (any of `files`, `numbers`,
  `keynote`, `pages`, `design`; default all).
- **First run:** macOS asks once whether Hermes may control Keynote, Pages or Numbers. Click
  **OK**. (Missed it? System Settings → Privacy & Security → Automation.)

## What it does on your Mac

- **Downloads once:** the first start fetches `iwork-studio==2.6.1` and its Python dependencies
  from PyPI with `uvx` (about 60 MB). That release is built and published by this repository's
  [release workflow](https://github.com/Arkanji/iwork-studio/blob/main/.github/workflows/release.yml)
  from the `v2.6.1` tag, through PyPI trusted publishing.
- **Drives Apple's apps:** Pages, render checks, exports and Keynote slide operations run the real
  Numbers, Keynote or Pages app through `osascript` (Apple's scripting). Reading and editing
  `.numbers` and `.key` files is pure Python and needs no app.
- **Reads and writes:** only the iWork files the agent points it at, inside `IWORK_STUDIO_ROOTS`
  when set. Backups go to `~/.iwork-studio/backups/` (last 10 per file), saved design kits to
  `~/.iwork-studio/kits/`.
- **Sends nothing:** no network calls after the download, no accounts, no telemetry. See
  [PRIVACY.md](https://github.com/Arkanji/iwork-studio/blob/main/PRIVACY.md).
- **No self-updates:** the version is fixed by this package; new versions arrive through the
  Hermes catalog.

## License

MIT
