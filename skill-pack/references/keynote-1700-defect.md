# Keynote 15.4 — the -1700 `title`/`body` Defect

## Defect

On Keynote 15.4 (build 7051.0.79), the AppleScript slide properties
`title` and `body` throw error **-1700** (errAEDescriptorRecord / can't get
the property) even on slides that plainly have a title and body.

## Verified workaround

Read and write text via the slide's **text items** and their `object text**:

```javascript
// JXA — read every text item of every slide
const app = Application('Keynote');
const doc = app.open(Path(src));
const slides = doc.slides();
for (const s of slides) {
  const items = s.textItems();
  for (const item of items) {
    const text = item.objectText().toString();
  }
}
```

Write single item: `item.objectText = 'new text'` (the library's
`write_text_item` does this against slide/item indices).

## What the library does about it

- `iwork_studio.keynote_applescript.read_text_items` / `write_text_item` /
  `applescript_edit_text` use `object text` exclusively — the -1700 surface
  is never touched.
- `iwork_studio.keynote_io.edit_text` (the primary route) does not use
  AppleScript at all: it unpacks the .key to its YAML tree via
  keynote-parser and edits text there, repacking under AtomicSwap.

## Rule

Never script `slide.title` / `slide.body` on Keynote 15.4. If a future iWork
version fixes it, re-verify before switching — until then this is a hard
property of the app version pin.

Verified by live probes (Phase C).