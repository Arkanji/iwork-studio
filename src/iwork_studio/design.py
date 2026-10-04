"""iWork Studio — design kits: make decks and tables look designed, in one call.

A kit is a small, opinionated system: a heading + body font pair (Latin and
Arabic, all bundled with macOS — nothing to install), a restrained colour palette
(neutrals + one accent) checked for WCAG contrast, and a type scale.

  list_kits()                          names + a one-line description (presets and saved kits)
  extract_kit(path)                    a kit from your own deck or table: its fonts and colours
  save_kit(name, kit) / delete_kit()   keep a brand kit by name, reuse it anywhere
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

import json
import os
import re
import uuid
from collections import Counter
from pathlib import Path

__all__ = ["KITS", "list_kits", "get_kit", "contrast", "extract_kit", "save_kit", "delete_kit",
           "apply_to_keynote", "apply_to_numbers", "DesignError"]

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
    """Presets, then the kits you saved (marked saved: true)."""
    out = [{"name": k, "about": v["about"], "theme": v["theme"], "fonts": v["fonts"], "colors": v["colors"]}
           for k, v in KITS.items()]
    for name, v in sorted(_saved_kits().items()):
        out.append({"name": name, "about": v.get("about", "saved kit"), "theme": v.get("theme"),
                    "fonts": v.get("fonts", {}), "colors": v.get("colors", {}), "saved": True})
    return out


# ── Saved kits: one JSON file per kit in ~/.iwork-studio/kits (IWORK_STUDIO_KITS_DIR) ──

_KIT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,39}$")


def _kits_dir() -> Path:
    return Path(os.environ.get("IWORK_STUDIO_KITS_DIR") or Path.home() / ".iwork-studio" / "kits")


def _kit_file(name: str) -> Path:
    if not isinstance(name, str) or not _KIT_NAME.match(name):
        raise DesignError(f"kit name {name!r}: use letters, digits, spaces, '-' or '_' (up to 40)")
    return _kits_dir() / f"{name.lower().replace(' ', '-')}.json"


def _saved_kits() -> dict[str, dict]:
    out = {}
    d = _kits_dir()
    if d.is_dir():
        for f in d.glob("*.json"):
            try:
                v = json.loads(f.read_text(encoding="utf-8"))
                out[v["name"]] = v
            except (OSError, ValueError, KeyError, TypeError):
                continue  # a damaged file is skipped, never fatal
    return out


def save_kit(name: str, kit, *, overwrite: bool = False) -> dict:
    """Save a kit by name (contrast is checked first). Never replaces a saved kit unless
    overwrite=True; never shadows a preset."""
    if isinstance(name, str) and name.lower() in {k.lower() for k in KITS}:
        raise DesignError(f"{name!r} is a preset kit; pick another name")
    f = _kit_file(name)
    k = get_kit({**kit, "name": name} if isinstance(kit, dict) else kit)
    if f.exists() and not overwrite:
        raise DesignError(f"a kit named {name!r} is already saved; pass overwrite=true to replace it")
    record = {"name": name, "about": k.get("about") if k.get("about") != "custom kit" else "saved kit",
              "theme": k["theme"], "background": k["background"], "fonts": k["fonts"], "colors": k["colors"]}
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)
    return {"saved": name, "file": str(f), "kit": record}


def delete_kit(name: str) -> dict:
    """Delete a saved kit. Returns its contents, so it can be saved again."""
    f = _kit_file(name)
    saved = _saved_kits()
    if name not in saved or not f.exists():
        raise DesignError(f"no saved kit named {name!r}; saved kits: {sorted(saved)}")
    f.unlink()
    return {"deleted": name, "kit": saved[name]}


def get_kit(kit) -> dict:
    """A kit by name (preset or saved), or a custom one: {"fonts": {...}, "colors": {...},
    "theme": "...", "background": "#FFFFFF", "base": "executive"} — missing keys fall back to
    the base preset (default "executive"). Contrast is checked:
    titles and body text need 4.5:1 against the background, table text 4.5:1 on its fill."""
    if isinstance(kit, str):
        if kit in KITS:
            return {**KITS[kit], "name": kit}
        saved = _saved_kits()
        if kit not in saved:
            raise DesignError(f"unknown kit {kit!r}; kits: {sorted(KITS)}, saved: {sorted(saved)} "
                              "(or pass your own colours and fonts)")
        kit = saved[kit]
    if not isinstance(kit, dict):
        raise DesignError("kit must be a kit name or a dict of fonts/colors")
    base_name = kit.get("base", "executive")
    if base_name not in KITS:
        raise DesignError(f"base kit {base_name!r} must be a preset: {sorted(KITS)}")
    base = KITS[base_name]
    k = {"name": kit.get("name", "custom"), "about": kit.get("about", "custom kit"), "theme": kit.get("theme", base["theme"]),
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


# ── Extract a kit from your own file ──────────────────────────────────────────


def _mix(hexcolor: str, other: str, t: float) -> str:
    """Blend hexcolor toward other by t (0..1)."""
    a = [int(hexcolor[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def _top(counter: Counter):
    return counter.most_common(1)[0][0] if counter else None


def _norm_hex(c) -> str | None:
    c = str(c or "")
    return c.upper() if _HEX.match(c) else None


def _ps_names(family: str) -> tuple[str | None, str | None]:
    """(regular, bold) PostScript names for a font family, from Numbers' font list."""
    from numbers_parser.model import FONT_FAMILY_TO_NAME, FONT_NAME_TO_FAMILY

    regular = FONT_FAMILY_TO_NAME.get(family)
    names = [n for n, f in FONT_NAME_TO_FAMILY.items() if f == family]
    bold = next((n for suffix in ("-Bold", "Bold", "-DemiBold", "-SemiBold", "SemiBold")
                 for n in names if n.endswith(suffix)), None)
    return regular, bold or regular


def _family_of(ps: str | None) -> str | None:
    from numbers_parser.model import FONT_NAME_TO_FAMILY

    return FONT_NAME_TO_FAMILY.get(ps) if ps else None


def _assemble(found: dict, notes: list[str]) -> dict:
    """found: title_color/body_color/brand/accent, background, fonts by role and script
    (heading, body, heading_ar, body_ar, family, family_ar), theme. Missing parts
    come from the nearest preset; the table colours are derived from the brand colour."""
    bg = found.get("background") or "#FFFFFF"
    dark = _lum(bg) < 0.4
    base = KITS["midnight" if dark else "executive"]
    title = found.get("title_color") or base["colors"]["title"]
    body = found.get("body_color") or base["colors"]["body"]
    brand = found.get("brand") or title
    # Table header: the brand colour if white text reads on it, else the darker of title/body.
    fill = brand if contrast("#FFFFFF", brand) >= 4.5 else min((title, body, brand), key=_lum)
    header_text = "#FFFFFF" if contrast("#FFFFFF", fill) >= contrast("#000000", fill) else "#000000"
    fonts = dict(base["fonts"])
    for key in ("heading", "body", "heading_ar", "body_ar", "family", "family_ar"):
        if found.get(key):
            fonts[key] = found[key]
        else:
            notes.append(f"{key} font not found in the file; kept {fonts[key]!r} from the {('midnight' if dark else 'executive')} preset")
    colors = {"title": title, "body": body, "accent": found.get("accent") or brand,
              "header_fill": fill, "header_text": header_text, "band": _mix(fill, "#FFFFFF", 0.92)}
    if dark:
        colors["table_text"] = "#0F172A"
    kit = {"base": "midnight" if dark else "executive", "about": found.get("about", "extracted kit"),
           "theme": found.get("theme") or base["theme"], "background": bg, "fonts": fonts, "colors": colors}
    return kit


def _problems(kit: dict) -> list[str]:
    c, bg = kit["colors"], kit["background"]
    out = []
    for role in ("title", "body"):
        r = contrast(c[role], bg)
        if r < 4.5:
            out.append(f"{role} colour {c[role]} on {bg} is {r}:1; needs 4.5:1")
    return out


def _from_numbers(path, sheet, table) -> tuple[dict, dict]:
    from iwork_studio.numbers_format import read_layout

    lay = read_layout(path, sheet=sheet, table=table)
    h = lay.get("header_rows", 1)
    stats = {k: Counter() for k in ("head_font", "head_color", "head_fill", "body_font", "body_font_ar",
                                    "head_font_ar", "body_color", "fills")}
    for c in lay["cells"]:
        st = c.get("style") or {}
        text = str(c.get("value") or "")
        ar = "_ar" if _ARABIC.search(text) else ""
        header = c["row"] < h if "row" in c else int(re.sub(r"\D", "", c["ref"])) <= h
        if header:
            if st.get("font_name"):
                stats["head_font" + ar][st["font_name"]] += 1
            if _norm_hex(st.get("font_color")):
                stats["head_color"][_norm_hex(st["font_color"])] += 1
            if _norm_hex(st.get("bg_color")):
                stats["head_fill"][_norm_hex(st["bg_color"])] += 1
        else:
            if st.get("font_name"):
                stats["body_font" + ar][st["font_name"]] += 1
            if _norm_hex(st.get("font_color")):
                stats["body_color"][_norm_hex(st["font_color"])] += 1
            if _norm_hex(st.get("bg_color")):
                stats["fills"][_norm_hex(st["bg_color"])] += 1
    found: dict = {"background": "#FFFFFF", "about": f"from {Path(path).name}"}
    fill = _top(stats["head_fill"])
    body_color = _top(stats["body_color"])
    if fill:
        found["brand"] = fill
        found["title_color"] = fill if contrast(fill, "#FFFFFF") >= 4.5 else body_color
    if body_color:
        found["body_color"] = body_color
    for role, key in (("heading", "head_font"), ("body", "body_font")):
        fam = _top(stats[key])
        if fam:
            regular, bold = _ps_names(fam)
            found[role] = bold if role == "heading" else regular
            if role == "body":
                found["family"] = fam
        fam_ar = _top(stats[key + "_ar"])
        if fam_ar:
            regular, bold = _ps_names(fam_ar)
            found[f"{role}_ar"] = bold if role == "heading" else regular
            if role == "body":
                found["family_ar"] = fam_ar
    if not found.get("family") and found.get("heading"):
        found["family"] = _family_of(found["heading"])
    source = {"table": lay.get("table"), "sheet": lay.get("sheet"), "cells_read": len(lay["cells"])}
    return found, source


def _from_keynote(path) -> tuple[dict, dict]:
    from iwork_studio import keynote_theme as kt
    from iwork_studio.keynote_deck import pick_roles

    st = kt.read_style(path)
    stats = {k: Counter() for k in ("title_font", "title_font_ar", "title_color", "body_font", "body_font_ar",
                                    "body_color", "other_color")}
    for s in st["slides"]:
        boxes = {"title": s.get("title_box"), "body": s.get("body_box")}
        if boxes["title"] is None and boxes["body"] is None and s.get("items"):
            roles = pick_roles(s["items"])
            by_index = {it["index"]: it for it in s["items"]}
            boxes = {r: by_index.get(roles.get(r)) for r in ("title", "body")}
        for role, b in boxes.items():
            if not b or not str(b.get("text") or "").strip():
                continue
            ar = "_ar" if _ARABIC.search(b["text"]) else ""
            if b.get("font"):
                stats[f"{role}_font{ar}"][b["font"]] += 1
            if _norm_hex(b.get("color")):
                stats[f"{role}_color"][_norm_hex(b["color"])] += 1
        skip = {str((b or {}).get("text")) for b in boxes.values()}
        for it in s.get("items", []):
            if it.get("text", "").strip() and it["text"] not in skip and _norm_hex(it.get("color")):
                stats["other_color"][_norm_hex(it["color"])] += 1
    found: dict = {"theme": st.get("theme"), "about": f"from {Path(path).name}"}
    title, body = _top(stats["title_color"]), _top(stats["body_color"])
    if title:
        found["title_color"] = title
    if body:
        found["body_color"] = body
    accents = [c for c, _ in stats["other_color"].most_common() if c not in (title, body)]
    if accents:
        found["accent"] = accents[0]
    # Keynote doesn't script slide backgrounds: judge it from the text colour.
    ref = title or body
    found["background"] = "#000000" if ref and _lum(ref) > 0.5 else "#FFFFFF"
    for role, key in (("heading", "title_font"), ("body", "body_font")):
        if _top(stats[key]):
            found[role] = _top(stats[key])
        if _top(stats[key + "_ar"]):
            found[f"{role}_ar"] = _top(stats[key + "_ar"])
    for k, src in (("family", "body"), ("family_ar", "body_ar")):
        fam = _family_of(found.get(src)) or _family_of(found.get("heading" + src[4:]))
        if fam:
            found[k] = fam
    source = {"theme": st.get("theme"), "slides_read": len(st["slides"])}
    return found, source


def extract_kit(path, *, name: str | None = None, save: bool = False, overwrite: bool = False,
                sheet: str | None = None, table: str | None = None) -> dict:
    """A design kit from your own file: heading/body fonts (Latin and Arabic) and the title,
    body and brand colours. .numbers reads the table's header and body styles (no app);
    .key reads every slide's title and body boxes (needs Keynote). What the file doesn't
    show comes from the nearest preset and is listed in `notes`. save=True stores it under
    `name` (contrast must pass)."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".numbers":
        found, source = _from_numbers(p, sheet, table)
    elif ext == ".key":
        found, source = _from_keynote(p)
    else:
        raise DesignError(f"can extract a kit from .key or .numbers, not {ext or 'this file'}")
    notes: list[str] = []
    if ext == ".key":
        notes.append(f"background judged {found['background']} from the text colour (Keynote doesn't expose slide backgrounds)")
    kit = _assemble(found, notes)
    if name:
        kit["name"] = name
    problems = _problems(kit)
    out = {"kit": kit, "source": source, "notes": notes, "contrast_ok": not problems, "problems": problems}
    if save:
        if not name:
            raise DesignError("pass a name to save the kit")
        if problems:
            raise DesignError("can't save: " + "; ".join(problems) + ". Adjust the colours and save with iwork_save_design_kit")
        out["saved"] = save_kit(name, kit, overwrite=overwrite)["file"]
    return out


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
