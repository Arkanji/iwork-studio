"""iWork Studio — build Keynote decks from an outline, and set a slide's text.

  build_deck(path, slides, theme=…)       new .key from a theme + outline (layout,
                                          title, body bullets, notes, image)
  set_slide_text(path, slide, title, body) fill a slide's title / body boxes

Keynote's slide `title` / `body` properties throw -1700 (trap K1), so the boxes
are found from the text items themselves: the title is the top-most box, the body
the largest of the rest. The write picks boxes by position in its own session and
the check re-picks them by position — never by index, because Keynote doesn't keep
text-box order stable between sessions (trap L4).

Safety: set_slide_text rides the theming protocol (backup → app edit → re-read →
rollback). build_deck makes a new file that never overwrites; if any slide reads
back wrong, the new file is deleted and the error says which slide.
"""

from __future__ import annotations

from pathlib import Path

from iwork_studio import keynote_slides as ks
from iwork_studio import keynote_theme as kt

__all__ = ["build_deck", "set_slide_text", "DeckError", "pick_roles"]

_TITLE_LAYOUTS = ("Title", "Title - Center", "Title & Subtitle", "Title - Top")
_CONTENT_LAYOUTS = ("Title & Bullets", "Title, Bullets & Photo", "Bullets", "Title - Top")
_MAX_SLIDES = 200


class DeckError(ValueError):
    """Bad outline (unknown layout, too many slides, a layout with no room for the text…)."""


def _norm(text: str | None) -> str:
    return "\n".join(line.rstrip() for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()


def _body_text(body) -> str | None:
    if body is None:
        return None
    if isinstance(body, (list, tuple)):
        return "\n".join(str(b) for b in body)
    return str(body)


def pick_roles(items: list[dict]) -> dict:
    """{"title": index|None, "body": index|None} from text-item positions."""
    placed = [i for i in items if i.get("y") is not None]
    if not placed:
        return {"title": items[0]["index"] if items else None,
                "body": items[1]["index"] if len(items) > 1 else None}
    title = min(placed, key=lambda i: i["y"])
    rest = [i for i in placed if i["index"] != title["index"]]
    body = max(rest, key=lambda i: i.get("area") or 0) if rest else None
    return {"title": title["index"], "body": body["index"] if body else None}


def _check_fits(items: list[dict], title: str | None, body: str | None, where: str) -> None:
    roles = pick_roles(items)
    if title is not None and body is not None and roles["body"] is None:
        raise DeckError(f"{where}: this layout has one text box; give only a title or only a body, "
                        "or choose a layout like 'Title & Bullets'")
    if roles["title"] is None and (title is not None or body is not None):
        raise DeckError(f"{where}: this layout has no text box")


def _check_roles(items: list[dict], title: str | None, body: str | None, where: str) -> None:
    """Read-back by role (Keynote doesn't keep text-box order stable — trap L4)."""
    roles = pick_roles(items)
    text = {it["index"]: it["text"] for it in items}
    if title is not None and _norm(text.get(roles["title"])) != _norm(title):
        raise ks.SlideOpVerificationError(f"{where}: title box reads {text.get(roles['title'])!r}, wanted {title!r}")
    if body is not None:
        idx = roles["body"] if roles["body"] is not None else roles["title"]
        if _norm(text.get(idx)) != _norm(body):
            raise ks.SlideOpVerificationError(f"{where}: body box reads {text.get(idx)!r}, wanted {body!r}")


def _other_texts(items: list[dict]):
    from collections import Counter

    roles = pick_roles(items)
    return Counter(it["text"] for it in items if it["index"] not in (roles["title"], roles["body"]) and it["text"].strip())


# Boxes are chosen by position in the same session that writes them: Keynote's
# text-item order isn't stable between sessions, so an index from an earlier read
# can point at a different box. Same rule as pick_roles: top-most = title,
# largest of the rest = body.
_FILL_JS = """    const roles = (s) => {
      const items = s.textItems();
      const info = items.map((it, i) => {
        let y = null, area = 0;
        try { y = it.position().y; area = it.width() * it.height(); } catch (e) {}
        return {i: i, y: y, area: area};
      });
      const placed = info.filter(o => o.y !== null);
      if (!placed.length) return {items: items, title: items.length ? 0 : null, body: items.length > 1 ? 1 : null};
      const title = placed.reduce((a, b) => (b.y < a.y ? b : a)).i;
      const rest = placed.filter(o => o.i !== title);
      const body = rest.length ? rest.reduce((a, b) => (b.area > a.area ? b : a)).i : null;
      return {items: items, title: title, body: body};
    };
    for (const sp of params.specs) {
      const s = doc.slides[sp.n - 1];
      const r = roles(s);
      if (sp.title !== null) r.items[r.title].objectText = sp.title;
      if (sp.body !== null) r.items[r.body !== null ? r.body : r.title].objectText = sp.body;
      if (sp.notes !== null) s.presenterNotes = sp.notes;
    }
"""


def set_slide_text(path, slide: int, *, title: str | None = None, body=None, **kw) -> dict:
    """Fill the title and/or body box of `slide` (1-based). `body` may be a list of bullet lines."""
    body = _body_text(body)
    if title is None and body is None:
        raise DeckError("give a title and/or a body")

    def plan(before):
        n = len(before["slides"])
        if not isinstance(slide, int) or not 1 <= slide <= n:
            raise kt.ThemeError(f"slide {slide!r} out of range (deck has {n})")
        _check_fits(before["slides"][slide - 1]["items"], title, body, f"slide {slide}")

        def expect(b, a):
            kt._same_slide_count(b, a)
            for i, (x, y) in enumerate(zip(b["slides"], a["slides"]), start=1):
                if i != slide and kt._sig(x) != kt._sig(y):
                    raise ks.SlideOpVerificationError(f"slide {i} changed collaterally")
            sa, sb = a["slides"][slide - 1], b["slides"][slide - 1]
            if sa.get("layout") != sb.get("layout"):
                raise ks.SlideOpVerificationError(f"slide {slide} layout changed")
            _check_roles(sa["items"], title, body, f"slide {slide}")
            if _other_texts(sa["items"]) != _other_texts(sb["items"]):
                raise ks.SlideOpVerificationError(f"slide {slide}: another text box changed")

        return _FILL_JS, {"specs": [{"n": slide, "title": title, "body": body, "notes": None}]}, \
            expect, {"slide": slide, "title": title, "body": body}

    return kt._run(path, "set_slide_text", plan, **kw)


def _pick_layout(available: list[str], wanted: str | None, first: bool) -> str:
    if wanted:
        if wanted not in available:
            raise DeckError(f"unknown layout {wanted!r}; this theme has: {available}")
        return wanted
    for name in (_TITLE_LAYOUTS if first else _CONTENT_LAYOUTS):
        if name in available:
            return name
    return available[0]


def build_deck(path, slides: list[dict], *, theme: str | None = None, transition: str | None = None,
               kit=None) -> dict:
    """slides = [{"title": "…", "body": ["point", "point"], "layout": "Title & Bullets",
    "notes": "…", "image": "/path/logo.png"}, …]. The first slide defaults to a title layout,
    the rest to Title & Bullets. `kit` (a design kit name or dict) sets the theme and styles every
    slide. Creates a new deck (never overwrites)."""
    from iwork_studio import app_ops

    target = Path(path).expanduser().resolve()
    if target.suffix.lower() != ".key":
        raise DeckError("the new deck must end in .key")
    if target.exists():
        raise DeckError(f"{target} already exists; choose another name")
    if not slides or len(slides) > _MAX_SLIDES:
        raise DeckError(f"give 1–{_MAX_SLIDES} slides")
    for i, sp in enumerate(slides, start=1):
        if not isinstance(sp, dict) or not any(sp.get(k) for k in ("title", "body", "image", "notes")):
            raise DeckError(f"slide {i}: give at least a title, body, notes or image")
        if sp.get("image") and not Path(str(sp["image"])).expanduser().is_file():
            raise DeckError(f"slide {i}: image {sp['image']!r} not found")
    if transition:
        if transition.strip().lower() not in app_ops.TRANSITIONS + ("none", "no transition"):
            raise DeckError(f"unknown transition {transition!r}")

    design_kit = None
    if kit is not None:
        from iwork_studio import design

        design_kit = design.get_kit(kit)
        theme = theme or design_kit.get("theme")
    created = app_ops.create_document(target, theme)
    try:
        available = kt.read_style(target)["layouts"]
        layouts = [_pick_layout(available, sp.get("layout"), i == 0) for i, sp in enumerate(slides)]
        body = """        set n to (item 2 of argv) as integer
        set base slide of slide 1 to master slide (item 3 of argv)
        repeat with i from 2 to n
          make new slide at end of slides with properties {base slide:master slide (item (i + 2) of argv)}
        end repeat"""
        kt._applescript_op(target, body, [len(slides), *layouts])

        shaped = kt.read_style(target)
        if len(shaped["slides"]) != len(slides):
            raise ks.SlideOpVerificationError(f"deck has {len(shaped['slides'])} slides, expected {len(slides)}")
        specs = []
        for i, (sp, sl) in enumerate(zip(slides, shaped["slides"]), start=1):
            _check_fits(sl["items"], sp.get("title"), _body_text(sp.get("body")), f"slide {i} ({layouts[i - 1]})")
            specs.append({"n": i, "title": sp.get("title"), "body": _body_text(sp.get("body")), "notes": sp.get("notes")})
        ks._jxa("  const doc = app.open(Path(params.path));\n  try {\n" + _FILL_JS
                + "    app.save(doc);\n  } finally {\n    app.close(doc, {saving: 'no'});\n  }\n"
                + "  return JSON.stringify({ok: true});", {"path": str(target), "specs": specs})

        after = kt.read_style(target)
        notes = ks.read_slides(target)
        for i, (sp, spec, sl) in enumerate(zip(slides, specs, after["slides"]), start=1):
            if sl.get("layout") != layouts[i - 1]:
                raise ks.SlideOpVerificationError(f"slide {i} layout reads {sl.get('layout')!r}, wanted {layouts[i - 1]!r}")
            _check_roles(sl["items"], spec["title"], spec["body"], f"slide {i}")
            if sp.get("notes") is not None and _norm(notes[i - 1].get("notes")) != _norm(sp["notes"]):
                raise ks.SlideOpVerificationError(f"slide {i} presenter notes didn't land")
        for i, sp in enumerate(slides, start=1):
            if sp.get("image"):
                app_ops.add_image(target, i, sp["image"], x=sp.get("image_x"), y=sp.get("image_y"),
                                  width=sp.get("image_width"), backup_dir=target.parent / f".{target.name}.build")
            if transition:
                app_ops.set_transition(target, i, transition, backup_dir=target.parent / f".{target.name}.build")
        if design_kit is not None:
            from iwork_studio import design

            design.apply_to_keynote(target, design_kit, set_theme=False, backup_dir=target.parent / f".{target.name}.build")
    except Exception:
        target.unlink(missing_ok=True)
        _cleanup(target)
        raise
    _cleanup(target)
    return {"ok": True, "file": str(target), "theme": created["template"], "slides": len(slides),
            "layouts": layouts, "transition": transition, "kit": design_kit["name"] if design_kit else None}


def _cleanup(target: Path) -> None:
    import shutil

    shutil.rmtree(target.parent / f".{target.name}.build", ignore_errors=True)
