"""iWork Studio — Keynote theming via the app (theme, slide layout, text format).

Ops: list themes · inspect a deck's styling · change the theme · change a
slide's layout (master) · set font / size / colour of a text item.

Same protocol as keynote_slides: gates (.key, GATE-CHART, deck not open in
Keynote) → styled inventory → backup → op + in-place save → fresh re-read →
expectation gate → parser re-parse → atomic restore on any mismatch.

Expectations (what "nothing else changed" means here):
  theme   : theme reads back; same slide count; every slide keeps its text
            (non-empty text items compared as a multiset — a theme swap may
            re-lay out placeholders but must not lose words)
  layout  : that slide's layout reads back and keeps its text; every other
            slide unchanged (layout + text + item formatting)
  format  : the item's font/size/colour read back; all text everywhere
            unchanged; every other item's formatting unchanged

Charts: the app does the edit, so decks with charts are allowed; every slide's
chart count is checked unchanged (add_chart: +1 on its slide only).

Not exposed by Apple's scripting (refuse, don't improvise): shape fill /
border, text alignment (writes silently no-op), editing a theme's masters.
JXA `masterSlides()` throws -1700, so layouts go through AppleScript.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from iwork_studio import keynote_io
from iwork_studio import keynote_slides as ks
from iwork_studio.apps import app_name

__all__ = ["list_themes", "read_style", "set_theme", "set_slide_layout", "format_text", "ThemeError"]

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


class ThemeError(ValueError):
    """Bad request (unknown theme/layout, ambiguous text item, bad colour…)."""


# ── app I/O ───────────────────────────────────────────────────────────────────

_STYLE_INVENTORY = """
  const inv = {theme: null, slides: []};
  try { inv.theme = doc.documentTheme().name(); } catch (e) {}
  const slides = doc.slides();
  for (let s = 0; s < slides.length; s++) {
    const items = [];
    const tis = slides[s].textItems();
    for (let i = 0; i < tis.length; i++) {
      const ot = tis[i].objectText;
      let font = null, size = null, color = null;
      try { font = ot.font(); } catch (e) {}
      try { size = ot.size(); } catch (e) {}
      try { color = ot.color(); } catch (e) {}
      items.push({index: i, text: ot().toString(), font: font, size: size, color: color});
    }
    let transition = null, images = null;
    try {
      const tp = slides[s].transitionProperties();
      transition = {effect: tp.transitionEffect, duration: tp.transitionDuration,
                    delay: tp.transitionDelay, automatic: tp.automaticTransition};
    } catch (e) {}
    try { images = slides[s].images().length; } catch (e) {}
    let charts = null;
    try { charts = slides[s].charts().length; } catch (e) {}
    inv.slides.push({slide: s + 1, items: items, transition: transition, images: images, charts: charts});
  }
"""


def _layouts(path: str) -> dict:
    """AppleScript (JXA master-slide access throws -1700): all layout names and
    each slide's layout. Returned as two newline-separated sections."""
    name = app_name("Keynote")
    if '"' in name:
        raise ThemeError(f"refusing unsafe app name {name!r}")
    script = f"""on run argv
  tell application "{name}"
    set d to open (POSIX file (item 1 of argv))
    try
      set AppleScript's text item delimiters to linefeed
      set ms to (name of every master slide of d) as text
      set bs to {{}}
      repeat with s in slides of d
        set end of bs to (name of base slide of s)
      end repeat
      set bsText to bs as text
    on error errMsg number errNum
      close d saving no
      error errMsg number errNum
    end try
    close d saving no
    return ms & linefeed & "<<<SLIDES>>>" & linefeed & bsText
  end tell
end run"""
    r = subprocess.run(["osascript", "-e", script, path], capture_output=True, text=True, timeout=ks.APP_TIMEOUT)
    if r.returncode != 0:
        raise RuntimeError(f"AppleScript failed (rc={r.returncode}): {r.stderr.strip()[:400]}")
    masters, _, bases = r.stdout.rstrip("\n").partition("\n<<<SLIDES>>>\n")
    return {"layouts": [m for m in masters.split("\n") if m], "slide_layouts": [b for b in bases.split("\n") if b]}


def read_style(path) -> dict:
    """Theme, available layouts, and per slide: layout + text items with font/size/colour."""
    ks._assert_aqua()
    target = str(Path(path).resolve())
    out = ks._jxa(
        ks._OPEN_CHECK
        + "  const doc = app.open(Path(target));\n"
        + _STYLE_INVENTORY
        + "  app.close(doc, {saving: 'no'});\n"
        + "  return JSON.stringify(inv);",
        {"path": target},
    )
    if out.get("open_in_app"):
        raise ks.DocumentOpenError(
            f"{Path(target).name} is open in Keynote. Save and close it first — "
            "iWork Studio will not close a window that may hold unsaved edits."
        )
    lay = _layouts(target)
    for s, layout in zip(out["slides"], lay["slide_layouts"]):
        s["layout"] = layout
        for it in s["items"]:
            it["color"] = _color_hex(it.get("color"))
    out["layouts"] = lay["layouts"]
    out["file"] = target
    return out


def list_themes() -> list[str]:
    out = ks._jxa("  return JSON.stringify({themes: app.themes().map(t => t.name())});", {})
    return out["themes"]


# ── helpers ───────────────────────────────────────────────────────────────────


def _color_hex(c) -> str | None:
    """Normalise a scripting colour (0–65535 ints, or 0–1 floats) to #rrggbb."""
    if not c or len(c) < 3:
        return None
    vals = [float(x) for x in c[:3]]
    scale = 65535.0 if max(vals) > 1.0 else 1.0
    return "#" + "".join(f"{round(v / scale * 255):02x}" for v in vals)


def _rgb16(hexcolor: str) -> list[int]:
    m = _HEX.match(hexcolor or "")
    if not m:
        raise ThemeError(f"colour {hexcolor!r} must be hex like #1A7F79")
    h = m.group(1)
    return [int(h[i:i + 2], 16) * 257 for i in (0, 2, 4)]


def _close(a: str | None, b: str | None, tol: int = 2) -> bool:
    if a is None or b is None:
        return a == b
    return all(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) <= tol for i in (1, 3, 5))


def _font_eq(a: str | None, b: str | None) -> bool:
    norm = lambda s: re.sub(r"[\s_-]", "", s or "").lower()  # noqa: E731
    return norm(a) == norm(b)


def _texts(slide: dict) -> Counter:
    return Counter(i["text"] for i in slide["items"] if i["text"].strip())


def _sig(slide: dict) -> tuple:
    return (slide.get("layout"), sorted((i["text"], i.get("font"), round(i.get("size") or 0, 1), i.get("color"))
                                        for i in slide["items"] if i["text"].strip()))


# ── protected op runner ───────────────────────────────────────────────────────


def _run(path, op: str, plan, *, backup_dir=None, max_backups: int = 10) -> dict:
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    if target.suffix.lower() != ".key":
        raise ThemeError(f"{target.name} is not a .key deck")
    ks._gate_op("notes")  # shares the slide-ops on/off switch
    has_charts = keynote_io.contains_charts(target)

    before = read_style(target)
    if has_charts and any(sl.get("charts") is None for sl in before["slides"]):
        raise keynote_io.ChartRefusalError(
            f"GATE-CHART: {target.name} has charts and this Keynote doesn't report them per slide, "
            "so the result can't be checked; refusing")
    script, params, expect, summary = plan(before)  # validates; raises ThemeError before any backup

    bdir = Path(backup_dir) if backup_dir else target.parent / f"{target.name}.backups"
    backup = keynote_io._versioned_backup(target, bdir)
    keynote_io._prune_backups(bdir, max_backups)
    try:
        if isinstance(script, dict) and "applescript" in script:
            _applescript_op(target, script["applescript"], script.get("args", []))
        else:
            ks._jxa(
                "  const doc = app.open(Path(params.path));\n  try {\n" + script
                + "    app.save(doc);\n  } finally {\n    app.close(doc, {saving: 'no'});\n  }\n"
                + "  return JSON.stringify({ok: true});",
                {"path": str(target), **params},
            )
        after = read_style(target)
        expect(before, after)
        if op != "add_chart" and [x.get("charts") for x in before["slides"]] != [x.get("charts") for x in after["slides"]]:
            raise ks.SlideOpVerificationError("a chart was added, lost or moved — rolled back")
        keynote_io.read_key(target)  # parser re-parse gate
    except Exception:
        ks._restore(target, backup)
        raise
    return {"ok": True, "file": str(target), "op": op, "backup": str(backup), **summary}


def _applescript_op(target: Path, body: str, args: list[str]) -> None:
    """open → body (inside `tell d`, argv: path then args) → in-place save → close."""
    ks._assert_aqua()
    name = app_name("Keynote")
    if '"' in name:
        raise ThemeError(f"refusing unsafe app name {name!r}")
    script = f"""on run argv
  tell application "{name}"
    set d to open (POSIX file (item 1 of argv))
    try
      tell d
{body}
      end tell
      save d
    on error errMsg number errNum
      close d saving no
      error errMsg number errNum
    end try
    close d saving no
  end tell
end run"""
    r = subprocess.run(["osascript", "-e", script, str(target), *map(str, args)],
                       capture_output=True, text=True, timeout=ks.APP_TIMEOUT)
    if r.returncode != 0:
        raise RuntimeError(f"AppleScript failed (rc={r.returncode}): {r.stderr.strip()[:500]}")


def _same_slide_count(before, after):
    if len(after["slides"]) != len(before["slides"]):
        raise ks.SlideOpVerificationError(f"slide count {len(before['slides'])} → {len(after['slides'])}")


# ── ops ───────────────────────────────────────────────────────────────────────


def set_theme(path, theme: str, **kw) -> dict:
    def plan(before):
        themes = list_themes()
        if theme not in themes:
            raise ThemeError(f"unknown theme {theme!r}; available: {themes}")

        def expect(b, a):
            if a["theme"] != theme:
                raise ks.SlideOpVerificationError(f"theme reads {a['theme']!r}, wanted {theme!r}")
            _same_slide_count(b, a)
            for sb, sa in zip(b["slides"], a["slides"]):
                lost = _texts(sb) - _texts(sa)
                if lost:
                    raise ks.SlideOpVerificationError(f"slide {sb['slide']}: text lost in theme change: {list(lost)[:3]}")

        script = "    doc.documentTheme = app.themes.byName(params.theme);\n"
        return script, {"theme": theme}, expect, {"theme": theme, "previous_theme": before["theme"]}

    return _run(path, "set_theme", plan, **kw)


def set_slide_layout(path, slide: int, layout: str, **kw) -> dict:
    def plan(before):
        n = len(before["slides"])
        if not isinstance(slide, int) or not 1 <= slide <= n:
            raise ThemeError(f"slide {slide!r} out of range (deck has {n})")
        if layout not in before["layouts"]:
            raise ThemeError(f"unknown layout {layout!r}; available: {before['layouts']}")

        def expect(b, a):
            _same_slide_count(b, a)
            sa = a["slides"][slide - 1]
            if sa["layout"] != layout:
                raise ks.SlideOpVerificationError(f"slide {slide} layout reads {sa['layout']!r}, wanted {layout!r}")
            if _texts(b["slides"][slide - 1]) - _texts(sa):
                raise ks.SlideOpVerificationError(f"slide {slide}: text lost in layout change")
            for i, (x, y) in enumerate(zip(b["slides"], a["slides"]), start=1):
                if i != slide and _sig(x) != _sig(y):
                    raise ks.SlideOpVerificationError(f"slide {i} changed collaterally")

        # AppleScript: JXA master-slide access throws -1700 (trap K1)
        script = {"applescript": "        set base slide of slide ((item 2 of argv) as integer) to master slide (item 3 of argv)",
                  "args": [slide, layout]}
        return script, {}, expect, {
            "slide": slide, "layout": layout, "previous_layout": before["slides"][slide - 1]["layout"]}

    return _run(path, "set_slide_layout", plan, **kw)


def format_text(path, slide: int, *, item: int | None = None, match: str | None = None,
                font: str | None = None, size: float | None = None, color: str | None = None, **kw) -> dict:
    """Font (PostScript name), size (pt) and/or colour (#RRGGBB) of one text item,
    picked by 0-based `item` index or by unique text `match`."""
    if font is None and size is None and color is None:
        raise ThemeError("give font, size and/or color")
    if size is not None and not 4 <= float(size) <= 400:
        raise ThemeError("size must be 4–400 pt")
    rgb = _rgb16(color) if color is not None else None

    def plan(before):
        n = len(before["slides"])
        if not isinstance(slide, int) or not 1 <= slide <= n:
            raise ThemeError(f"slide {slide!r} out of range (deck has {n})")
        items = before["slides"][slide - 1]["items"]
        if match is not None:
            hits = [i for i in items if match in i["text"]]
            if len(hits) != 1:
                raise ThemeError(f"{len(hits)} text items on slide {slide} contain {match!r}; need exactly one "
                                 f"(or pass item=). Items: {[(i['index'], i['text'][:30]) for i in items]}")
            idx = hits[0]["index"]
        elif item is not None:
            if not 0 <= item < len(items):
                raise ThemeError(f"item {item} out of range (slide {slide} has {len(items)} text items)")
            idx = item
        else:
            raise ThemeError("give item= (0-based) or match= (unique text)")
        want_hex = None if color is None else "#" + _HEX.match(color).group(1).lower()

        def expect(b, a):
            _same_slide_count(b, a)
            for i, (x, y) in enumerate(zip(b["slides"], a["slides"]), start=1):
                if _texts(x) != _texts(y):
                    raise ks.SlideOpVerificationError(f"slide {i}: text changed")
                if i != slide and _sig(x) != _sig(y):
                    raise ks.SlideOpVerificationError(f"slide {i} changed collaterally")
            got = next(it for it in a["slides"][slide - 1]["items"] if it["index"] == idx)
            if font is not None and not _font_eq(got["font"], font):
                raise ks.SlideOpVerificationError(f"font reads {got['font']!r}, wanted {font!r} (use a PostScript name)")
            if size is not None and abs(float(got["size"] or 0) - float(size)) > 0.1:
                raise ks.SlideOpVerificationError(f"size reads {got['size']!r}, wanted {size}")
            if want_hex is not None and not _close(got["color"], want_hex):
                raise ks.SlideOpVerificationError(f"colour reads {got['color']!r}, wanted {want_hex}")
            others_b = [it for it in b["slides"][slide - 1]["items"] if it["index"] != idx]
            others_a = [it for it in a["slides"][slide - 1]["items"] if it["index"] != idx]
            if [(o["text"], o["font"], o["size"], o["color"]) for o in others_b] != \
               [(o["text"], o["font"], o["size"], o["color"]) for o in others_a]:
                raise ks.SlideOpVerificationError(f"another text item on slide {slide} changed")

        script = "    const ot = doc.slides[params.n - 1].textItems[params.i].objectText;\n"
        if font is not None:
            script += "    ot.font = params.font;\n"
        if size is not None:
            script += "    ot.size = params.size;\n"
        if rgb is not None:
            script += "    ot.color = params.rgb;\n"
        return script, {"n": slide, "i": idx, "font": font, "size": size, "rgb": rgb}, expect, {
            "slide": slide, "item": idx, "font": font, "size": size, "color": want_hex}

    return _run(path, "format_text", plan, **kw)
