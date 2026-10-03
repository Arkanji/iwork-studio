# Design guide — decks, tables and documents that look designed

For agents using iWork Studio. Start with a design kit (`iwork_list_design_kits`),
then follow these rules when you write the content. A kit handles fonts, sizes and
colours; the content still has to be designed.

Principles paraphrased from Impeccable (Paul Bakaus, Apache-2.0) and UI/UX Pro Max
(Next Level Builder, MIT). See `THIRD_PARTY_NOTICES.md`.

## The fast path

| Want | Call |
|---|---|
| A new designed deck | `keynote_build_deck(path, slides, kit="executive")` |
| Restyle an existing deck | `keynote_apply_design(path, kit)` (preview first with `dry_run=true`) |
| A designed table | `numbers_create` → `numbers_apply_design(path, kit)` → `numbers_set_number_format` for money/% |
| A brand | pass `kit={"colors": {"title": "#…", "body": "#…", "accent": "#…", "header_fill": "#…", "header_text": "#…", "band": "#…"}, "fonts": {…}}` — contrast is checked (4.5:1) |

Kits: **executive** (calm corporate) · **banking** (navy + gold) · **classic** (serif, boards
and formal reports) · **teal** (fresh) · **analytics** (data-forward) · **midnight** (dark stage,
mint accent). All fonts ship with macOS, Arabic included (Geeza Pro, Damascus, Al Nile).

## Slides

- **One idea per slide.** The title states the takeaway ("Revenue grew 35% in Q2"), not the
  topic ("Revenue").
- **Few words.** Aim for 30 words or fewer per slide; 3–5 bullets, each one line. Move the rest
  to presenter notes (`notes` in the outline).
- **Big contrast in size.** The kits use 88 pt titles on title slides, 52 pt titles and 28 pt
  body on content slides. Don't shrink text to fit — cut words or split the slide.
- **Structure the deck as a story.** A reliable spine: hook → problem → insight → proof (numbers)
  → plan → ask. For reviews: where we are → what changed → what's next → decisions needed.
- **Charts:** one message per chart. Pie ≤ 6 slices; grouped bars ≤ 4 series and ≤ 8 categories;
  stacked ≤ 5 segments. Put the takeaway in the slide title, not a legend.
- **Use the accent sparingly** — for the one thing that matters, never as decoration.

## Tables (Numbers, Pages tables)

- Header row: heavier weight on a tinted or dark band (the kits do this).
- **Right-align numbers**, one precision per column (all 0 or all 2 decimals), thousand separators,
  currency codes (`numbers_set_number_format(..., "currency", currency_code="SAR")`).
- Banding is optional; for wide tables it helps the eye follow a row.
- Don't style every cell differently. Hierarchy comes from weight and space, not colour.

## Colour

- Text needs **4.5:1** contrast against its background (3:1 for large text and lines). Custom kits
  are checked; don't override with low-contrast colours.
- Never use colour as the only signal — pair it with a word, a sign or position (▲ +12%).
- Pick a strategy and keep it: restrained (neutrals + one accent) suits most business decks.

## Typography

- One font family (plus its Arabic partner) is usually right. Add a second only for a clear role.
- Body text reads best at 45–75 characters per line.
- More space above a heading than below it.

## Arabic

- Kits switch to the Arabic font automatically for Arabic text (per text box / cell).
- New Pages paragraphs are written left-to-right; tell the user to set right-to-left in Pages
  (Format › Text) if the result shows `arabic_paragraphs_left_to_right`.
- When checking a render, assert one Arabic word.

## Avoid

- Walls of bullets, sentences that wrap three lines, or a title that only names the topic.
- Grids of identical boxes, decorative gradients and glows, emoji instead of icons.
- Ten colours in one deck; colour as decoration.
- Shrinking fonts to cram content.
