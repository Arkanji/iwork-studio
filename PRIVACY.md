# Privacy policy — iWork Studio

iWork Studio runs entirely on your own computer. It has no servers, no accounts and no analytics.

**What it reads and writes.** Only the Numbers, Keynote and Pages files you or your AI assistant point it at, and only inside the folders you allow (the folder picker in the Claude Desktop extension, or `IWORK_STUDIO_ROOTS`). Before each change it saves a backup next to the file (`<file>.backups/`), so you can undo it.

**What it stores.** Backups next to your files, design kits you choose to save (`~/.iwork-studio/kits/`), and logs of test runs you start yourself (`~/.iwork-studio/probes/`). All of it stays on your computer, and you can delete it at any time.

**What it sends.** Nothing. It makes no network requests. It drives Apple's Numbers, Keynote and Pages apps on your Mac through Apple's own scripting, which macOS asks you to allow once.

**Your AI assistant.** The assistant you connect it to (for example Claude) sees what the tools return — such as the text of a file you ask it to read — under that assistant's own privacy policy.

**Retention.** Backups keep the last 10 versions per file by default; delete the `.backups` folder to remove them.

**Contact.** Questions or concerns: open an issue at https://github.com/Arkanji/iwork-studio/issues.
