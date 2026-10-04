"""iWork Studio — design review: render a deck and check what was actually drawn.

The writers check that text landed in the right box. This checks that it *looks*
right: Keynote renders the deck to PDF, and every text line's drawn box is compared
with the text box it belongs to.

  review_deck(path)              findings per slide (errors and warnings), read-only
  slide_image(path, slide)       one slide as a JPEG, for an agent that can look at it

Findings:
  off_slide   (error)    text drawn past the slide's edge
  overflow    (error)    text runs past the bottom of its box
  overlap     (warning)  two text boxes draw on top of each other
  small_text  (warning)  text under 18 pt on a 1920-wide slide — hard to read in a room
  dense       (warning)  more than 6 bullets or 45 words on a slide, or a title over 12 words
  fonts       (info)     more than 3 font families in the deck

The file is never changed: Keynote opens it, exports, and closes without saving.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

__all__ = ["review_deck", "analyse", "slide_image", "ReviewError"]

_MIN_PT = 18.0  # on a 1920-wide slide
_MAX_BULLETS, _MAX_WORDS, _MAX_TITLE_WORDS = 6, 45, 12


class ReviewError(RuntimeError):
    """The deck couldn't be rendered or reviewed."""


def _chars(text: str) -> Counter:
    t = unicodedata.normalize("NFKC", text or "")
    return Counter(ch for ch in t if not ch.isspace())


def _belongs(line: str, item: Counter) -> bool:
    """Line drawn from this box? Its characters (order ignored: PDF text layers reorder
    right-to-left runs) are nearly all in the box's text."""
    lc = _chars(line)
    total = sum(lc.values())
    if not total:
        return False
    missing = sum((lc - item).values())
    return missing <= max(1, total // 10)


def _excerpt(text: str, n: int = 50) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _union(lines: list[dict]) -> tuple[float, float, float, float] | None:
    if not lines:
        return None
    return (min(ln["x0"] for ln in lines), min(ln["top"] for ln in lines),
            max(ln["x1"] for ln in lines), max(ln["bottom"] for ln in lines))


def _inter(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _area(r) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _boxes(slide: dict) -> list[dict]:
    """Text boxes with geometry, duplicates (Keynote lists placeholders twice) dropped."""
    seen, out = set(), []
    for it in slide.get("items", []):
        if not (it.get("text") or "").strip():
            continue
        key = (it.get("x"), it.get("y"), it.get("w"), it.get("h"), it.get("text"), it.get("font"))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def analyse(style: dict, pages: list[dict]) -> list[dict]:
    """Findings from the Keynote inventory (read_style) and the rendered PDF lines
    (pdf.lines), one page per slide in order. Pure: no app needed."""
    findings: list[dict] = []

    def add(slide, kind, severity, message, text=None):
        f = {"slide": slide, "kind": kind, "severity": severity, "message": message}
        if text:
            f["text"] = _excerpt(text)
        findings.append(f)

    slide_w, slide_h = float(style.get("width") or 0), float(style.get("height") or 0)
    for sl, page in zip(style["slides"], pages):
        n = sl["slide"]
        pw, ph = float(page["width"]), float(page["height"])
        # Box geometry is in slide points; the PDF page may be scaled.
        sx, sy = (pw / slide_w, ph / slide_h) if slide_w and slide_h else (1.0, 1.0)
        lines = page["lines"]
        tol = 2.0

        off = [ln for ln in lines if ln["x0"] < -tol or ln["x1"] > pw + tol or ln["top"] < -tol or ln["bottom"] > ph + tol]
        for ln in off:
            add(n, "off_slide", "error", "text is drawn past the edge of the slide; shorten it or make the box smaller",
                ln["text"])

        # Which rendered lines belong to which box: horizontal overlap + same characters.
        drawn: dict[int, list[dict]] = {}
        boxes = _boxes(sl)
        for i, it in enumerate(boxes):
            if None in (it.get("x"), it.get("y"), it.get("w"), it.get("h")):
                continue
            x0, x1 = it["x"] * sx, (it["x"] + it["w"]) * sx
            chars = _chars(it["text"])
            mine = []
            for ln in lines:
                ov = min(x1, ln["x1"]) - max(x0, ln["x0"])
                if ov > 0.5 * max(1.0, ln["x1"] - ln["x0"]) and ln["top"] >= it["y"] * sy - 0.5 * ln["size"] - tol \
                        and _belongs(ln["text"], chars):
                    mine.append(ln)
            drawn[i] = mine
            if mine:
                bottom = (it["y"] + it["h"]) * sy
                over = max(ln["bottom"] for ln in mine) - bottom
                size = sorted(ln["size"] for ln in mine)[len(mine) // 2] or 10
                if over > max(4.0, 0.35 * size):
                    add(n, "overflow", "error",
                        f"text runs {round(over)} pt past the bottom of its box; cut words, split the slide, or use a smaller size",
                        it["text"])

        rects = {i: _union(v) for i, v in drawn.items() if v}
        keys = sorted(rects)
        for a in range(len(keys)):
            for b in range(a + 1, len(keys)):
                ra, rb = rects[keys[a]], rects[keys[b]]
                small = min(_area(ra), _area(rb)) or 1
                if _inter(ra, rb) > 0.15 * small:
                    add(n, "overlap", "warning", "two text boxes are drawn on top of each other",
                        f"{_excerpt(boxes[keys[a]]['text'], 25)} / {_excerpt(boxes[keys[b]]['text'], 25)}")

        floor = _MIN_PT * pw / 1920.0
        small = [ln for ln in lines if 0 < ln["size"] < floor - 0.25]
        if small:
            add(n, "small_text", "warning",
                f"{len(small)} line(s) drawn under {_MIN_PT:g} pt (smallest {min(ln['size'] for ln in small) * 1920.0 / pw:.0f} pt); "
                "hard to read from the back of a room", small[0]["text"])

        body = (sl.get("body_box") or {}).get("text") or ""
        title = (sl.get("title_box") or {}).get("text") or ""
        bullets = [b for b in re.split(r"[\r\n]+", body) if b.strip()]
        words = len(body.split())
        if len(bullets) > _MAX_BULLETS:
            add(n, "dense", "warning", f"{len(bullets)} bullets; keep it to {_MAX_BULLETS} or split the slide", body)
        elif words > _MAX_WORDS:
            add(n, "dense", "warning", f"{words} words in the body; aim for under {_MAX_WORDS}", body)
        if len(title.split()) > _MAX_TITLE_WORDS:
            add(n, "dense", "warning", f"title is {len(title.split())} words; a title states one takeaway", title)

    from numbers_parser.model import FONT_NAME_TO_FAMILY

    families = Counter()
    for sl in style["slides"]:
        for it in _boxes(sl):
            if it.get("font"):
                families[FONT_NAME_TO_FAMILY.get(it["font"], it["font"].split("-")[0])] += 1
    if len(families) > 3:
        add(None, "fonts", "info", f"{len(families)} font families ({', '.join(sorted(families))}); "
            "two (a heading and a body font) read as designed")
    return findings


def _pages_for_slides(style: dict, pages: list[dict], path) -> list[dict]:
    """Keynote's PDF leaves skipped slides out: line pages up with the slides shown."""
    if len(pages) == len(style["slides"]):
        return pages
    from iwork_studio import keynote_slides as ks

    shown = [s for s, info in zip(style["slides"], ks.read_slides(path)) if not info.get("skipped")]
    if len(shown) != len(pages):
        raise ReviewError(f"the PDF has {len(pages)} pages for {len(style['slides'])} slides; can't line them up")
    style["slides"] = shown
    return pages


def review_deck(path) -> dict:
    """Render the deck through Keynote and report what looks wrong, per slide."""
    from iwork_studio import keynote_applescript, keynote_theme as kt
    from iwork_studio import pdf as _pdf

    target = Path(path).resolve()
    if target.suffix.lower() != ".key":
        raise ReviewError(f"{target.name} is not a .key deck")
    style = kt.read_style(target)
    work = Path(tempfile.mkdtemp(prefix="iwork-review-"))
    try:
        pages = _pdf.lines(keynote_applescript.render_pdf(target, out_dir=work))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    total = len(style["slides"])
    pages = _pages_for_slides(style, pages, target)
    findings = analyse(style, pages)
    counts = Counter(f["severity"] for f in findings)
    return {"ok": counts["error"] == 0, "file": str(target), "slides": total, "slides_reviewed": len(pages),
            "errors": counts["error"], "warnings": counts["warning"], "findings": findings,
            "next": "fix errors first (keynote_set_slide_text to shorten, or split the slide); "
                    "look at a slide with keynote_slide_image"}


def slide_image(path, slide: int, *, width: int = 1280) -> bytes:
    """One slide as JPEG bytes (exported by Keynote, scaled to `width` px)."""
    from iwork_studio import exporter

    target = Path(path).resolve()
    if not isinstance(slide, int) or slide < 1:
        raise ReviewError("slide is 1-based")
    if not 320 <= int(width) <= 2560:
        raise ReviewError("width must be 320–2560 px")
    work = Path(tempfile.mkdtemp(prefix="iwork-slide-"))
    try:
        out = work / "slides"
        exporter.export(target, "images", out, image_format="jpeg")
        natural = lambda f: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", f.name)]  # noqa: E731
        imgs = sorted((f for f in out.rglob("*") if f.suffix.lower() in (".jpg", ".jpeg")), key=natural)
        if slide > len(imgs):
            raise ReviewError(f"slide {slide} out of range: {len(imgs)} slide images (skipped slides aren't exported)")
        small = work / "slide.jpg"
        r = subprocess.run(["sips", "-Z", str(int(width)), "-s", "format", "jpeg", str(imgs[slide - 1]),
                            "--out", str(small)], capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not small.exists():
            raise ReviewError(f"couldn't scale the slide image: {r.stderr.strip()[:200]}")
        return small.read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)
