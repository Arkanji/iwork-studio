"""iWork Studio — build Keynote decks from an outline, and set a slide's text.

  build_deck(path, slides, theme=…)       new .key from a theme + outline (layout,
                                          title, body bullets, notes, image)
  set_slide_text(path, slide, title, body) fill a slide's title / body boxes

Keynote's slide `title` / `body` properties throw -1700 (trap K1), so the boxes
are found from the text items themselves: the title is the top-most box, the body
the largest of the rest. Positions come from the same inventory used to verify,
so what is written is what gets checked.

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


def _assign(items: list[dict], title: str | None, body: str | None, where: str) -> dict[int, str]:
    roles = pick_roles(items)
    out: dict[int, str] = {}
    if title is not None and body is not None and roles["body"] is None:
        raise DeckError(f"{where}: this layout has one text box; give only a title or only a body, "
                        "or choose a layout like 'Title & Bullets'")
    if title is not None:
        if roles["title"] is None:
            raise DeckError(f"{where}: this layout has no text box for a title")
        out[roles["title"]] = title
    if body is not None:
        idx = roles["body"] if roles["body"] is not None else roles["title"]
        if idx is None:
            raise DeckError(f"{where}: this layout has no text box for the body")
        out[idx] = body
    return out


_FILL_JS = """    const specs = params.specs;
    for (const sp of specs) {
      const s = doc.slides[sp.n - 1];
      for (const k of Object.keys(sp.texts)) s.textItems[parseInt(k, 10)].objectText = sp.texts[k];
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
        items = before["slides"][slide - 1]["items"]
        texts = _assign(items, title, body, f"slide {slide}")

        def expect(b, a):
            kt._same_slide_count(b, a)
            for i, (x, y) in enumerate(zip(b["slides"], a["slides"]), start=1):
                if i != slide and kt._sig(x) != kt._sig(y):
                    raise ks.SlideOpVerificationError(f"slide {i} changed collaterally")
            sa, sb = a["slides"][slide - 1], b["slides"][slide - 1]
            if sa.get("layout") != sb.get("layout"):
                raise ks.SlideOpVerificationError(f"slide {slide} layout changed")
            got = {it["index"]: it["text"] for it in sa["items"]}
            for it in sb["items"]:
                want = texts.get(it["index"], it["text"])
                if _norm(got.get(it["index"])) != _norm(want):
                    raise ks.SlideOpVerificationError(
                        f"slide {slide} text box {it['index']} reads {got.get(it['index'])!r}, wanted {want!r}")

        return _FILL_JS, {"specs": [{"n": slide, "texts": {str(k): v for k, v in texts.items()}, "notes": None}]}, \
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


def build_deck(path, slides: list[dict], *, theme: str | None = None, transition: str | None = None) -> dict:
    """slides = [{"title": "…", "body": ["point", "point"], "layout": "Title & Bullets",
    "notes": "…", "image": "/path/logo.png"}, …]. The first slide defaults to a title layout,
    the rest to Title & Bullets. Creates a new deck (never overwrites)."""
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
            texts = _assign(sl["items"], sp.get("title"), _body_text(sp.get("body")), f"slide {i} ({layouts[i - 1]})")
            specs.append({"n": i, "texts": {str(k): v for k, v in texts.items()}, "notes": sp.get("notes")})
        ks._jxa("  const doc = app.open(Path(params.path));\n  try {\n" + _FILL_JS
                + "    app.save(doc);\n  } finally {\n    app.close(doc, {saving: 'no'});\n  }\n"
                + "  return JSON.stringify({ok: true});", {"path": str(target), "specs": specs})

        after = kt.read_style(target)
        notes = ks.read_slides(target)
        for i, (sp, spec, sl) in enumerate(zip(slides, specs, after["slides"]), start=1):
            if sl.get("layout") != layouts[i - 1]:
                raise ks.SlideOpVerificationError(f"slide {i} layout reads {sl.get('layout')!r}, wanted {layouts[i - 1]!r}")
            got = {it["index"]: it["text"] for it in sl["items"]}
            for k, want in spec["texts"].items():
                if _norm(got.get(int(k))) != _norm(want):
                    raise ks.SlideOpVerificationError(f"slide {i} reads {got.get(int(k))!r}, wanted {want!r}")
            if sp.get("notes") is not None and _norm(notes[i - 1].get("notes")) != _norm(sp["notes"]):
                raise ks.SlideOpVerificationError(f"slide {i} presenter notes didn't land")
        for i, sp in enumerate(slides, start=1):
            if sp.get("image"):
                app_ops.add_image(target, i, sp["image"], x=sp.get("image_x"), y=sp.get("image_y"),
                                  width=sp.get("image_width"), backup_dir=target.parent / f".{target.name}.build")
            if transition:
                app_ops.set_transition(target, i, transition, backup_dir=target.parent / f".{target.name}.build")
    except Exception:
        target.unlink(missing_ok=True)
        _cleanup(target)
        raise
    _cleanup(target)
    return {"ok": True, "file": str(target), "theme": created["template"], "slides": len(slides),
            "layouts": layouts, "transition": transition}


def _cleanup(target: Path) -> None:
    import shutil

    shutil.rmtree(target.parent / f".{target.name}.build", ignore_errors=True)
