"""iWork Studio — design kits: make decks and tables look designed, in one call.

A kit is a small, opinionated system: a heading + body font pair (Latin and
Arabic, all bundled with macOS — nothing to install), a restrained colour palette
(neutrals + one accent) checked for WCAG contrast, and a type scale.

  list_kits()                          names + a one-line description
  apply_to_keynote(path, kit)          theme, fonts, sizes and colours on every slide
  apply_to_numbers(path, kit, …)       header band, body font, row banding,
                                       right-aligned number columns

Principles are paraphrased from Impeccable by Paul Bakaus (Apache-2.0) and
UI/UX Pro Max by Next Level Builder (MIT); several palettes are adapted from UI/UX
Pro Max's colour data. See THIRD_PARTY_NOTICES.md.

Both apply_* ride the usual protocol: backup → change → re-read → rollback. Text is
never changed; only fonts, sizes, colours, fills and alignment.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

__all__ = ["KITS", "list_kits", "get_kit", "contrast", "apply_to_keynote", "apply_to_numbers", "DesignError"]

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


class DesignError(ValueError):
    """Unknown kit, bad colour, too little contrast, unknown font…"""


# Fonts: macOS-bundled PostScript names (also in Numbers' font map).
KITS: dict[str, dict] = {
    "executive": {
        "about": "Calm and corporate: slate neutrals, one blue accent, Helvetica Neue / Geeza Pro",
        "theme": "Basic White", "background": "#FFFFFF",
        "fonts": {"heading": "HelveticaNeue-Bold", "body": "HelveticaNeue",
                  "heading_ar": "GeezaPro-Bold", "body_ar": "GeezaPro",
                  "family": "Helvetica Neue", "family_ar": "Geeza Pro"},
        "colors": {"title": "#0F172A", "body": "#334155", "accent": "#0369A1",
                   "header_fill": "#0F172A", "header_text": "#FFFFFF", "band": "#F1F5F9"},
    },
    "banking": {
        "about": "Trust and weight: deep navy with a restrained gold accent, Avenir Next / Damascus",
        "theme": "Basic White", "background": "#FFFFFF",
        "fonts": {"heading": "AvenirNext-DemiBold", "body": "AvenirNext-Regular",
                  "heading_ar": "DamascusSemiBold", "body_ar": "Damascus",
                  "family": "Avenir Next", "family_ar": "Damascus"},
        "colors": {"title": "#1E3A8A", "body": "#0F172A", "accent": "#A16207",
                   "header_fill": "#1E3A8A", "header_text": "#FFFFFF", "band": "#F8FAFC"},
    },
    "classic": {
        "about": "Formal documents and boards: serif headings, navy and amber, Baskerville / Al Nile",
        "theme": "Basic White", "background": "#FFFFFF",
        "fonts": {"heading": "Baskerville-SemiBold", "body": "Baskerville",
                  "heading_ar": "AlNile-Bold", "body_ar": "AlNile",
                  "family": "Baskerville", "family_ar": "Al Nile"},
        "colors": {"title": "#1E3A8A", "body": "#0F172A", "accent": "#B45309",
                   "header_fill": "#1E3A8A", "header_text": "#FFFFFF", "band": "#F8FAFC"},
    },
    "teal": {
        "about": "Fresh and confident: deep teal headings, Avenir Next / Damascus",
        "theme": "Basic White", "background": "#FFFFFF",
        "fonts": {"heading": "AvenirNext-Bold", "body": "AvenirNext-Regular",
                  "heading_ar": "DamascusBold", "body_ar": "Damascus",
                  "family": "Avenir Next", "family_ar": "Damascus"},
        "colors": {"title": "#0F766E", "body": "#134E4A", "accent": "#0369A1",
                   "header_fill": "#0F766E", "header_text": "#FFFFFF", "band": "#F0FDFA"},
    },
    "analytics": {
        "about": "Data-forward: strong blue, amber highlights, Helvetica Neue / Geeza Pro",
        "theme": "Basic White", "background": "#FFFFFF",
        "fonts": {"heading": "HelveticaNeue-Bold", "body": "HelveticaNeue",
                  "heading_ar": "GeezaPro-Bold", "body_ar": "GeezaPro",
                  "family": "Helvetica Neue", "family_ar": "Geeza Pro"},
        "colors": {"title": "#1E40AF", "body": "#1E3A8A", "accent": "#D97706",
                   "header_fill": "#1E40AF", "header_text": "#FFFFFF", "band": "#EFF6FF"},
    },
    "midnight": {
        "about": "Dark stage: near-black slides, white headings, mint accent, Avenir Next / Damascus",
        "theme": "Basic Black", "background": "#000000",
        "fonts": {"heading": "AvenirNext-Bold", "body": "AvenirNext-Regular",
                  "heading_ar": "DamascusBold", "body_ar": "Damascus",
                  "family": "Avenir Next", "family_ar": "Damascus"},
        "colors": {"title": "#F8FAFC", "body": "#CBD5E1", "accent": "#34D399",
                   "header_fill": "#0F172A", "header_text": "#F8FAFC", "band": "#F1F5F9",
                   "table_text": "#0F172A"},
    },
}

# Type scale (pt on Keynote's 1920×1080 canvas). Big jumps for decks, as the
# slide-typography data suggests: a title slide states one thing, large.
_SCALE = {"title_slide": {"title": 88, "body": 32}, "content": {"title": 52, "body": 28}}


def _lum(hexcolor: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two #RRGGBB colours."""
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def list_kits() -> list[dict]:
    return [{"name": k, "about": v["about"], "theme": v["theme"], "fonts": v["fonts"], "colors": v["colors"]}
            for k, v in KITS.items()]


def get_kit(kit) -> dict:
    """A kit by name, or a custom one: {"fonts": {...}, "colors": {...}, "theme": "...",
    "background": "#FFFFFF"} — missing keys fall back to "executive". Contrast is checked:
    titles and body text need 4.5:1 against the background, table text 4.5:1 on its fill."""
    if isinstance(kit, str):
        if kit not in KITS:
            raise DesignError(f"unknown kit {kit!r}; kits: {sorted(KITS)} (or pass your own colours and fonts)")
        k = KITS[kit]
        return {**k, "name": kit}
    if not isinstance(kit, dict):
        raise DesignError("kit must be a kit name or a dict of fonts/colors")
    base = KITS["executive"]
    k = {"name": kit.get("name", "custom"), "about": "custom kit", "theme": kit.get("theme", base["theme"]),
         "background": kit.get("background", base["background"]),
         "fonts": {**base["fonts"], **(kit.get("fonts") or {})},
         "colors": {**base["colors"], **(kit.get("colors") or {})}}
    for name, value in [("background", k["background"]), *k["colors"].items()]:
        if not _HEX.match(str(value)):
            raise DesignError(f"colour {name}={value!r} must be #RRGGBB")
    bg = k["background"]
    for role in ("title", "body"):
        if contrast(k["colors"][role], bg) < 4.5:
            raise DesignError(f"{role} colour {k['colors'][role]} on {bg} has contrast "
                              f"{contrast(k['colors'][role], bg)}:1; needs 4.5:1 to be readable")
    if contrast(k["colors"]["header_text"], k["colors"]["header_fill"]) < 4.5:
        raise DesignError("header_text on header_fill needs 4.5:1 contrast")
    return k


def _font(kit: dict, role: str, text: str) -> str:
    return kit["fonts"][f"{role}_ar" if _ARABIC.search(text or "") else role]


def _family(kit: dict, text: str) -> str:
    """Numbers styles take a font family plus a bold flag."""
    return kit["fonts"]["family_ar" if _ARABIC.search(text or "") else "family"]


# ── Keynote ───────────────────────────────────────────────────────────────────


def apply_to_keynote(path, kit="executive", *, set_theme: bool = True, **kw) -> dict:
    """Theme (optional), then every slide's title and body boxes: font (Arabic-aware),
    size from the scale, colour from the palette. Text is checked unchanged."""
    from iwork_studio import keynote_slides as ks
    from iwork_studio import keynote_theme as kt
    from iwork_studio.keynote_deck import _TITLE_LAYOUTS, pick_roles

    k = get_kit(kit)
    steps = []
    if set_theme and k.get("theme"):
        current = kt.read_style(path)["theme"]
        if current != k["theme"] and k["theme"] in kt.list_themes():
            steps.append(kt.set_theme(path, k["theme"], **kw))

    def fmt(role: str, scale: dict, arabic: bool) -> dict:
        kind = "heading" if role == "title" else "body"
        return {"font": k["fonts"][f"{kind}_ar" if arabic else kind],
                "size": scale.get(role), "rgb": kt._rgb16(k["colors"]["title" if role == "title" else "body"])}

    def plan(before):
        specs = []
        for s in before["slides"]:
            scale = _SCALE["title_slide" if (s["slide"] == 1 or s.get("layout") in _TITLE_LAYOUTS) else "content"]
            specs.append({"n": s["slide"], **{f"{role}_{lang}": fmt(role, scale, lang == "ar")
                                              for role in ("title", "body", "other") for lang in ("lat", "ar")}})

        def check(where, got, w):
            if not got:
                return
            if not kt._font_eq(got.get("font"), w["font"]):
                raise ks.SlideOpVerificationError(
                    f"{where}: font reads {got.get('font')!r}, wanted {w['font']!r} (is that font installed on this Mac?)")
            if w["size"] is not None and abs(float(got.get("size") or 0) - w["size"]) > 0.1:
                raise ks.SlideOpVerificationError(f"{where}: size reads {got.get('size')!r}, wanted {w['size']}")
            want_hex = "#" + "".join(f"{v // 257:02x}" for v in w["rgb"])
            if not kt._close(got.get("color"), want_hex):
                raise ks.SlideOpVerificationError(f"{where}: colour reads {got.get('color')!r}, wanted {want_hex}")

        def lang(text):
            return "ar" if _ARABIC.search(text or "") else "lat"

        def expect(b, a):
            kt._same_slide_count(b, a)
            for x, y, sp in zip(b["slides"], a["slides"], specs):
                if kt._texts(x) != kt._texts(y) or x.get("layout") != y.get("layout"):
                    raise ks.SlideOpVerificationError(f"slide {x['slide']}: text or layout changed")
                tb, bb = y.get("title_box"), y.get("body_box")
                if tb is None and bb is None:  # Keynote didn't expose them: fallback by type size
                    roles = pick_roles(y["items"])
                    for it in y["items"]:
                        role = "title" if it["index"] == roles["title"] else "body" if it["index"] == roles["body"] else "other"
                        check(f"slide {y['slide']}", it, sp[f"{role}_{lang(it['text'])}"])
                    continue
                check(f"slide {y['slide']} title", tb, sp[f"title_{lang((tb or {}).get('text'))}"])
                check(f"slide {y['slide']} body", bb, sp[f"body_{lang((bb or {}).get('text'))}"])
                skip = {(tb or {}).get("text"), (bb or {}).get("text")}
                for it in y["items"]:
                    if it["text"].strip() and it["text"] not in skip:
                        check(f"slide {y['slide']}", it, sp[f"other_{lang(it['text'])}"])

        # Every box gets the body/other style first; then Keynote's own title and body
        # boxes get theirs (the text-item list repeats placeholder boxes, so it can't
        # tell which box is the title).
        script = """    const AR = /[\\u0600-\\u06FF\\u0750-\\u077F\\u08A0-\\u08FF\\uFB50-\\uFDFF\\uFE70-\\uFEFF]/;
    const style = (ot, w) => { ot.font = w.font; if (w.size !== null) ot.size = w.size; ot.color = w.rgb; };
    const lang = (ot) => (AR.test(ot().toString()) ? "ar" : "lat");
    for (const sp of params.specs) {
      const s = doc.slides[sp.n - 1];
      s.textItems().forEach(it => { const ot = it.objectText; style(ot, sp["other_" + lang(ot)]); });
      let viaDefault = true;
      for (const role of ["title", "body"]) {
        try {
          const ot = (role === "title" ? s.defaultTitleItem : s.defaultBodyItem).objectText;
          ot();  // throws if the layout has no such box
          style(ot, sp[role + "_" + lang(ot)]);
        } catch (e) { if (role === "title") viaDefault = false; }
      }
      if (!viaDefault) {  // fallback: by type size, duplicates ignored (same rule as pick_roles)
        const items = s.textItems(), seen = {}, boxes = [];
        items.forEach((it, i) => {
          let x = null, y = null, area = 0, size = 0;
          try { const p = it.position(); x = p.x; y = p.y; area = it.width() * it.height(); } catch (e) {}
          try { size = it.objectText.size(); } catch (e) {}
          const key = x + "," + y + "," + area;
          if (y !== null && seen[key]) return;
          seen[key] = true;
          boxes.push({i: i, y: y || 0, area: area, size: size});
        });
        if (boxes.length) {
          const t = boxes.reduce((p, q) => (q.size > p.size || (q.size === p.size && q.y < p.y) ? q : p));
          const rest = boxes.filter(o => o.i !== t.i);
          const bd = rest.length ? rest.reduce((p, q) => (q.size > p.size || (q.size === p.size && q.area > p.area) ? q : p)) : null;
          const tot = items[t.i].objectText;
          style(tot, sp["title_" + lang(tot)]);
          if (bd) { const bot = items[bd.i].objectText; style(bot, sp["body_" + lang(bot)]); }
        }
      }
    }
"""
        boxes = sum(len(s["items"]) for s in before["slides"])
        return script, {"specs": specs}, expect, {"kit": k["name"], "text_boxes": boxes}

    out = kt._run(path, "apply_design", plan, **kw)
    if steps:
        out["theme_set_to"] = k["theme"]
    return out


# ── Numbers ───────────────────────────────────────────────────────────────────


def apply_to_numbers(path, kit="executive", *, sheet: str | None = None, table: str | None = None,
                     banding: bool = True, **kw) -> dict:
    """Header rows: heading font, bold, header fill and text colour. Body: body font
    and colour, alternate rows tinted (banding), number columns right-aligned.
    Values are never changed; every other table is checked untouched."""
    from numbers_parser import Alignment

    from iwork_studio.numbers_format import (_STYLE_FIELDS, _hex, _protected_write, _rgb, _style_snap,
                                             _col_letters)
    from iwork_studio.numbers_io import WriteVerificationError

    k = get_kit(kit)
    c = k["colors"]
    body_color = c.get("table_text", c["body"] if contrast(c["body"], "#FFFFFF") >= 4.5 else "#0F172A")

    def plan(doc, tb):
        h = tb.num_header_rows
        numeric_cols = set()
        for col in range(tb.num_cols):
            vals = [tb.cell(r, col).value for r in range(h, tb.num_rows)]
            vals = [v for v in vals if v not in (None, "")]
            if vals and sum(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals) >= len(vals) / 2:
                numeric_cols.add(col)
        overrides = {}
        for r in range(tb.num_rows):
            for col in range(tb.num_cols):
                text = str(tb.cell(r, col).value or "")
                if r < h:
                    o = {"font_name": _family(k, text), "bold": True,
                         "font_color": _rgb(c["header_text"]), "bg_color": _rgb(c["header_fill"])}
                else:
                    o = {"font_name": _family(k, text), "font_color": _rgb(body_color)}
                    if banding and (r - h) % 2 == 1:
                        o["bg_color"] = _rgb(c["band"])
                if col in numeric_cols:
                    o["_align"] = "right"
                overrides[(r, col)] = o
        for (r, col), o in overrides.items():
            cur = tb.cell(r, col).style
            kwargs = {f: getattr(cur, f) for f in _STYLE_FIELDS if getattr(cur, f, None) is not None}
            kwargs.update({f: v for f, v in o.items() if not f.startswith("_")})
            if "_align" in o:
                kwargs["alignment"] = Alignment(o["_align"], cur.alignment.vertical.name.lower())
            tb.set_cell_style(r, col, doc.add_style(name=f"iws-{uuid.uuid4().hex[:10]}", **kwargs))

        def check(t):
            for (r, col), o in overrides.items():
                got = _style_snap(t.cell(r, col).style) or {}
                for f, v in o.items():
                    if f == "_align":
                        if ((got.get("alignment") or (None,))[0] or "").lower() != "right":
                            raise WriteVerificationError(f"{_col_letters(col)}{r + 1}: not right-aligned")
                        continue
                    want = _hex(v) if f in ("font_color", "bg_color") else v
                    if got.get(f) != want:
                        raise WriteVerificationError(f"{_col_letters(col)}{r + 1}: {f} reads {got.get(f)!r}, wanted {want!r}")

        return {"cells": {"style": set(overrides)}, "check": check,
                "summary": {"kit": k["name"], "header_rows": h, "number_columns": sorted(_col_letters(x) for x in numeric_cols),
                            "banding": banding}}

    try:
        return _protected_write(path, sheet, table, "apply_design", plan, **kw)
    except KeyError as exc:  # numbers-parser only knows fonts in Numbers' font list
        raise DesignError(f"font family {exc} isn't one Numbers knows; use a macOS font family like "
                          "'Helvetica Neue' or 'Geeza Pro'") from exc
