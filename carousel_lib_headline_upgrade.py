"""
TheJenniWren Carousel Production Library
========================================
Shared rendering library for TheJenniWren editorial carousel system.

Features
--------
* Canvas creation
* Typography
* Text fitting
* Image placement
* Shared rendering helpers
* Template utilities

Fonts
-----
* Barlow Condensed ExtraBold
* Libre Baskerville Regular
* Libre Baskerville Italic

All bundled assets are resolved relative to this module using pathlib.Path.

v3.7.2
------
This revision is an engineering upgrade, not a redesign. Every function,
class, constant, signature, default value, and return value from 3.7.1 is
preserved exactly, so every existing template module continues to import
and render unchanged. Additions in this revision are:

* Font + text-measurement caching (invisible, output-identical).
* A shared layout/spacing system (SPACING, compute_content_zones(),
  white-space helpers) that new helpers and future template work can use.
* Restrained optical-alignment helpers, returned as offsets a caller can
  opt into - nothing existing applies them automatically.
* New, additive typography helpers (pull quote, label, source tag, CTA
  text) that delegate wrapping/fitting to text_fitting_engine.py instead
  of re-implementing it, per the v3.7.2 text-engine integration.
* Defensive guards for empty/None input and missing image assets on a
  handful of functions, without changing any normal-path output.

Nothing above touches the pixel-tuned production logic in fit_head(),
fit_head_custom(), wrap_lines(), draw_headline(), draw_body(), or any
other existing helper - those remain the single source of truth for
every current template call site.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
import re

# text_fitting_engine integration is additive only (see "NEW TYPOGRAPHY
# HELPERS" below) - no existing function in this file has been rewritten
# to depend on it, so this module still imports and runs even if the
# text engine is unavailable for some reason.
try:
    from .text_fitting_engine import (
        wrap_text as _te_wrap_text,
        measure_lines as _te_measure_lines,
        fit_text as _te_fit_text,
        draw_fitted_text as _te_draw_fitted_text,
    )
except ImportError:  # pragma: no cover - allows standalone/script use
    try:
        from text_fitting_engine import (
            wrap_text as _te_wrap_text,
            measure_lines as _te_measure_lines,
            fit_text as _te_fit_text,
            draw_fitted_text as _te_draw_fitted_text,
        )
    except ImportError:
        _te_wrap_text = None
        _te_measure_lines = None
        _te_fit_text = None
        _te_draw_fitted_text = None


# ── BRAND CONSTANTS (non-negotiable — see DESIGN_RULES.md) ─────────────────
ROOT = Path(__file__).resolve().parent
BARLOW = ROOT / "BarlowCondensed-ExtraBold.ttf"
BASK_REG = ROOT / "LibreBaskerville-Regular.ttf"
BASK_ITA = ROOT / "LibreBaskerville-Italic.ttf"

W, H = 1080, 1350
BG, WHITE, PINK = (10, 10, 10), (255, 255, 255), (255, 10, 114)

L_MARGIN = R_MARGIN = 54
HEAD_MAX_W = W - L_MARGIN - R_MARGIN
HEAD_MAX_H = int(H * 0.42)  # cap on total headline block height (~42% of canvas)
BODY_L = BODY_R = 68
LINE_H_RATIO = 0.85  # headline tight-stacking ratio
DIVIDER_GAP, DIVIDER_H = 30, 6
DIVIDER_W = int(W * 0.90)
BODY_GAP = 32
FOOTER_SAFE = H - 130  # body text must not render below this y
HEAD_Y = 185  # default headline start y
BODY_MIN_SIZE = 44  # hard floor for body text size


# ── SHARED LAYOUT SYSTEM & SPACING SCALE (v3.7.2) ───────────────────────
# Additive only: these name and group the regions the constants above
# already describe. Nothing here overrides L_MARGIN, HEAD_Y, FOOTER_SAFE,
# DIVIDER_GAP, BODY_GAP, etc. - existing drawing functions keep using
# those directly and are unaffected by anything in this section.

CONTENT_W = W - L_MARGIN - R_MARGIN  # inner content width
TOP_SAFE = 9                          # top pink bar height (see new_canvas)
BOTTOM_SAFE = 8                       # bottom pink bar height (see new_canvas)
GUTTER = 20                           # default gutter between side-by-side elements

# Small, consistent spacing scale for new helpers. Existing per-function
# gap constants (DIVIDER_GAP, BODY_GAP, ...) are left exactly as-is.
SPACING: Dict[str, int] = {
    "tight": 12,
    "standard": 24,
    "section": 32,
    "major": 48,
    "footer": 64,
}


def compute_content_zones() -> Dict[str, Tuple[int, int]]:
    """
    Return the approximate (top, bottom) y-range each named region
    occupies on the standard 1080x1350 canvas, derived from the existing
    brand constants. Informational/composition use only - no drawing
    function consults this to decide where to render; it exists for new
    helpers, diagnostics, and future template work.
    """
    headline_top, headline_bottom = HEAD_Y, HEAD_Y + HEAD_MAX_H
    divider_top = headline_bottom
    divider_bottom = divider_top + DIVIDER_GAP + DIVIDER_H
    body_top = divider_bottom
    body_bottom = FOOTER_SAFE
    footer_top, footer_bottom = FOOTER_SAFE, H - 90
    logo_top, logo_bottom = H - 90, H
    return {
        "header": (0, HEAD_Y),
        "headline": (headline_top, headline_bottom),
        "divider": (divider_top, divider_bottom),
        "body": (body_top, body_bottom),
        "footer": (footer_top, footer_bottom),
        "source_tag": (footer_top - 40, footer_top),
        "logo": (logo_top, logo_bottom),
    }


def remaining_vertical_space(cursor_y: int, floor: int = FOOTER_SAFE) -> int:
    """Vertical px remaining between cursor_y and floor (e.g. FOOTER_SAFE)."""
    return max(0, floor - cursor_y)


def available_body_height(ty: int, floor: int = FOOTER_SAFE, gap: int = BODY_GAP) -> int:
    """Vertical px available for body copy starting after a divider at ty."""
    return max(0, floor - (ty + gap))


def safe_spacing_compression(base_gap: int, deficit: int, min_gap: int = 8) -> int:
    """
    Reduce an optional gap to help dense copy fit, without ever dropping
    below min_gap. Callers should compress optional spacing between
    blocks before ever reducing font-size hierarchy.
    """
    if deficit <= 0:
        return base_gap
    return max(min_gap, base_gap - deficit)


def footer_clearance(cursor_y: int, floor: int = FOOTER_SAFE) -> bool:
    """True if cursor_y still leaves the footer/branding zone clear."""
    return cursor_y <= floor


def collision_risk(blocks: List[Tuple[int, int]]) -> bool:
    """
    Given a list of (top, bottom) y-ranges for blocks drawn in order,
    return True if any block overlaps the next one - e.g. body text
    about to collide with the source tag, logo, or next-slide arrow.
    """
    for (_, prev_bottom), (next_top, _) in zip(blocks, blocks[1:]):
        if next_top < prev_bottom:
            return True
    return False


# ── CACHES (v3.7.2) ──────────────────────────────────────────────────────
_FONT_CACHE: Dict[Tuple[str, int], "ImageFont.FreeTypeFont"] = {}
_MEASURE_CACHE: Dict[Tuple[Any, str], int] = {}


def _font_key(font) -> Any:
    """Stable cache key for a font object: (path, size) when available,
    falling back to object identity for fonts not loaded via lf()."""
    path = getattr(font, "path", None)
    size = getattr(font, "size", None)
    if path is not None and size is not None:
        return (str(path), size)
    return ("id", id(font))


# ── FONT LOADING ─────────────────────────────────────────────────────────
def lf(path, size):
    """Load a TrueType font (cached - identical font files/sizes are not
    re-loaded from disk on repeat calls)."""
    if not path:
        raise ValueError("lf() requires a font path")
    key = (str(path), size)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        font = ImageFont.truetype(str(path), size)
    except OSError as e:
        raise RuntimeError(f"Unable to load font: {path}") from e
    _FONT_CACHE[key] = font
    return font


def mw(draw, text, font):
    """Measure text width in pixels (cached per font+text)."""
    if text is None:
        text = ""
    key = (_font_key(font), text)
    cached = _MEASURE_CACHE.get(key)
    if cached is not None:
        return cached
    bb = draw.textbbox((0, 0), text, font=font)
    width = bb[2] - bb[0]
    _MEASURE_CACHE[key] = width
    return width


# ── OPTICAL ALIGNMENT HELPERS (v3.7.2) ──────────────────────────────────
# Small, capped adjustments only. These return an offset in px for a
# caller to optionally apply; no existing drawing function applies these
# automatically, so current template output is unchanged unless a
# template explicitly opts in.

def optical_offset_headline(block_height: int, zone_height: int) -> int:
    """Large headlines read as more centered when nudged slightly above
    true mathematical center. Offset is negative (moves up), capped small."""
    slack = max(0, zone_height - block_height)
    return -min(int(slack * 0.12), int(zone_height * 0.04))


def optical_offset_body(block_height: int, zone_height: int) -> int:
    """Lighter version of the headline nudge, for paragraph blocks."""
    slack = max(0, zone_height - block_height)
    return -min(int(slack * 0.06), int(zone_height * 0.02))


def optical_offset_divider(headline_weight: int, body_weight: int) -> int:
    """Small nudge toward whichever neighboring block carries more visual
    weight, so a divider doesn't read as mathematically dead-center."""
    total = headline_weight + body_weight
    if total <= 0:
        return 0
    balance = (headline_weight - body_weight) / total
    return int(balance * 4)


def optical_offset_bignum(digit_count: int) -> int:
    """
    Big Number digits (draw_stat_callout) can read slightly bottom-heavy
    at large sizes since digits have no descenders. Small upward nudge,
    capped, roughly proportional to digit count.
    """
    return -min(6, max(0, digit_count))


def allcaps_compensation(font_size: int) -> int:
    """
    All-caps headline lines sit slightly differently than mixed-case
    lines at the same size (no ascenders/descenders to balance against).
    Returns a small px nudge a caller can apply to line height/leading.
    """
    return -max(1, int(font_size * 0.015))


# ── HEADLINE SIZE PRE-CALCULATION (run BEFORE building any slide) ──────────
def max_sz(draw, text, lo=60, hi=180, target_pct=0.96):
    """
    Given a line of headline text, find the largest font size (in the
    range lo-hi) that fits within target_pct of HEAD_MAX_W.
    Returns (size, pixel_width).

    Standard range for fit_head()/fit_head_custom() calls is (100, 180).
    Use this on every headline line during planning, before writing any
    slide-building code. Flag any line whose max_sz comes back below
    ~95pt or below ~72% of canvas width as "too narrow" — rewrite the
    copy. If the line is an intentional short punch-word, use
    draw_stat_callout() or accept the narrow render deliberately.
    """
    for sz in range(hi, lo - 1, -1):
        f = lf(BARLOW, sz)
        w = mw(draw, text, f)
        if w <= int(HEAD_MAX_W * target_pct):
            return sz, w
    return lo, 0


def precalc_report(lines):
    """
    Print a quick report for a list of headline lines so you can see
    the limiting line and the spread before committing to a build.
    Call this from a throwaway script during planning.
    """
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    sizes = [max_sz(draw, l) for l in lines]
    lim = min(s for s, _ in sizes)
    spr = max(s for s, _ in sizes) - lim
    flag = " ⚠ REWRITE" if lim < 95 else ""
    print(f"limiting={lim}pt spread={spr}pt{flag}")
    for l, (sz, w) in zip(lines, sizes):
        pct = int(w / HEAD_MAX_W * 100)
        narrow = " ←NARROW" if pct < 72 else ""
        print(f"  {sz:>3}pt {pct:>3}% \'{l}\'{narrow}")


# ── GENERIC WORD-WRAP ───────────────────────────────────────────────────
def break_urls(text):
    """Insert a space after '/' in long URLs so the wrapper treats each
    segment as a breakable token instead of one giant unbreakable word."""
    if not text:
        return text or ""
    return re.sub(r'(https?://\S+)', lambda m: m.group(1).replace('/', '/ '), text)


def wrap_lines(draw, segs, font, max_w):
    """
    Generic word-wrapper. segs: list of (text, color) tuples (color-
    segmented inline text). Returns a list of lines, where each line is
    itself a list of (word, color) tuples — ready to be drawn word by
    word with per-word color.
    """
    segs = segs or []
    tw = []
    for txt, col in segs:
        txt = break_urls(txt)
        for word in txt.split():
            tw.append((word, col))

    lines, cur, cur_w = [], [], 0
    space_w = mw(draw, ' ', font)
    for word, col in tw:
        ww = mw(draw, word, font)
        needed = ww + (space_w if cur else 0)
        if cur and cur_w + needed > max_w:
            lines.append(cur)
            cur, cur_w = [(word, col)], ww
        else:
            if cur:
                cur_w += space_w
            cur.append((word, col))
            cur_w += ww
    if cur:
        lines.append(cur)
    return lines


# ── CORE DRAWING FUNCTIONS ──────────────────────────────────────────────────
def _headline_metrics(draw, lines, font, line_spacing=0.84):
    """Return visual metrics for a manually broken headline block.

    The renderer never wraps or merges ``lines``. Metrics are based on
    the actual glyph bounding boxes rather than nominal point size, which
    gives tighter and more consistent editorial stacking.
    """
    if not lines:
        raise ValueError("headline metrics require at least one line")

    boxes = [draw.textbbox((0, 0), str(line), font=font) for line in lines]
    widths = [max(0, box[2] - box[0]) for box in boxes]
    heights = [max(1, box[3] - box[1]) for box in boxes]
    asc, desc = font.getmetrics()
    step = max(1, int((asc + desc) * float(line_spacing)))
    block_h = heights[0] if len(lines) == 1 else step * (len(lines) - 1) + heights[-1]
    return {
        "boxes": boxes,
        "widths": widths,
        "heights": heights,
        "step": step,
        "block_h": block_h,
    }


def fit_head(draw, lines, sz_range, max_w=None, max_h=None, line_spacing=0.84):
    """Choose the largest font that fits the authored headline block.

    Manual line breaks are authoritative. The search checks both the
    widest authored line and the full stacked block, then returns the
    largest size that fits. It does not re-wrap, rebalance, or rewrite.
    """
    if not lines:
        raise ValueError("fit_head() requires at least one line of text")

    max_w = int(max_w or HEAD_MAX_W)
    max_h = int(max_h or HEAD_MAX_H)
    lo, hi = sorted((int(sz_range[0]), int(sz_range[1])))

    for size in range(hi, lo - 1, -1):
        font = lf(BARLOW, size)
        metrics = _headline_metrics(draw, lines, font, line_spacing=line_spacing)
        if max(metrics["widths"]) <= max_w and metrics["block_h"] <= max_h:
            return font

    # Preserve legacy behavior: render at the declared floor rather than fail.
    return lf(BARLOW, lo)


def fit_head_custom(draw, lines, sz_range, target_pct=(0.84, 0.96), max_h=None,
                    line_spacing=0.84):
    """Largest-fit headline search with a custom maximum width target.

    ``target_pct[1]`` controls the width ceiling. The lower target remains
    advisory only; maximum readable size takes precedence.
    """
    if not lines:
        raise ValueError("fit_head_custom() requires at least one line of text")
    max_w = int(HEAD_MAX_W * float(target_pct[1]))
    return fit_head(
        draw,
        lines,
        sz_range,
        max_w=max_w,
        max_h=max_h or HEAD_MAX_H,
        line_spacing=line_spacing,
    )


def draw_top_bar(draw, label, n, total_slides, big=False):
    """
    Pink label pill, top-left. Set big=True to enlarge for BREAKING-style
    cover slides (larger font + larger pill dimensions).
    """
    fsz = 40 if big else 28
    pad_v_top = 26 if big else 32
    pad_v_bot = 84 if big else 76
    f = lf(BARLOW, fsz)
    bb = draw.textbbox((0, 0), label, font=f)
    lw = bb[2] - bb[0] + (48 if big else 36)
    draw.rectangle([L_MARGIN, pad_v_top, L_MARGIN + lw, pad_v_bot], fill=PINK)
    ty = pad_v_top + ((pad_v_bot - pad_v_top) - fsz) // 2 - 4
    draw.text((L_MARGIN + (24 if big else 18), ty), label, font=f, fill=WHITE)

    cf = lf(BARLOW, 30)
    ct = f"{n:02d} / {total_slides:02d}"
    cbb = draw.textbbox((0, 0), ct, font=cf)
    draw.text((W - R_MARGIN - (cbb[2] - cbb[0]), 34), ct, font=cf, fill=WHITE)


def draw_headline(draw, lines, colors, y0, sr, *, line_spacing=0.84,
                  max_w=None, max_h=None):
    """Draw a manually broken, mixed-color editorial headline.

    ``lines`` are authoritative: no wrapping or rewriting occurs.
    ``colors`` may contain RGB tuples or resolved brand colors. Missing
    color entries default to WHITE so older payloads remain valid.
    The whole block is sized together at the largest font that fits.
    """
    if not lines:
        raise ValueError("draw_headline() requires at least one line")

    normalized_lines = [str(line) for line in lines]
    normalized_colors = list(colors or [])
    if len(normalized_colors) < len(normalized_lines):
        normalized_colors.extend([WHITE] * (len(normalized_lines) - len(normalized_colors)))

    font = fit_head(
        draw,
        normalized_lines,
        sr,
        max_w=max_w or HEAD_MAX_W,
        max_h=max_h or HEAD_MAX_H,
        line_spacing=line_spacing,
    )
    metrics = _headline_metrics(draw, normalized_lines, font, line_spacing=line_spacing)

    y = int(y0)
    visual_bottom = y
    for index, line in enumerate(normalized_lines):
        box = metrics["boxes"][index]
        # Offset by the glyph's top bearing so each visual line starts on the
        # intended stack position, not on a font-dependent invisible margin.
        draw_y = y - box[1]
        draw.text((L_MARGIN, draw_y), line, font=font, fill=normalized_colors[index])
        visual_bottom = draw_y + box[3]
        if index < len(normalized_lines) - 1:
            y += metrics["step"]

    return int(visual_bottom)


def draw_divider(draw, gy):
    """Pink divider bar below the headline block. Returns new y cursor."""
    y = gy + DIVIDER_GAP
    draw.rectangle([L_MARGIN, y, L_MARGIN + DIVIDER_W, y + DIVIDER_H], fill=PINK)
    return y + DIVIDER_H


def draw_body(draw, segs, ty, fsz=46):
    """
    segs: list of (text, color) tuples — break text into WHITE/PINK
    segments inline.
    ty: y position returned by draw_divider (this function adds
    BODY_GAP internally — don't add it again in the caller).
    fsz: body font size. Floors at BODY_MIN_SIZE=44pt — if you pass
    something lower, it's silently raised to 44 rather than shrinking
    further; shorten copy instead.

    IMPORTANT: this function silently stops drawing once it would cross
    FOOTER_SAFE — meaning if your copy is too long, words get cut with
    NO error or warning. Always re-view the rendered slide and check the
    last visible word makes grammatical sense (no orphaned clipped words).
    """
    fsz = max(fsz, BODY_MIN_SIZE)
    font = lf(BASK_REG, fsz)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.32)
    y = ty + BODY_GAP
    mxw = W - BODY_L - BODY_R

    lo = wrap_lines(draw, segs, font, mxw)

    for lwords in lo:
        if y + lh > FOOTER_SAFE:
            break  # silent truncation — always check rendered output
        x = BODY_L
        space_w = mw(draw, ' ', font)
        for i, (word, col) in enumerate(lwords):
            draw.text((x, y), word, font=font, fill=col)
            x += mw(draw, word, font)
            if i < len(lwords) - 1:
                x += space_w
        y += lh
    return y


# ── BRANDING HELPERS ─────────────────────────────────────────────────────
# draw_footer() is the existing brand signature (wordmark + next-slide
# arrow). No new branding elements are introduced in v3.7.2; brand_palette()
# below is only a convenience accessor for the same BG/WHITE/PINK constants
# already defined above.

def draw_footer(draw, brand_name="TheJenniWren", arrow=True):
    """
    Bottom-left brand signature in Baskerville Italic. arrow=True draws
    the pink "next slide" triangle bottom-right. Set arrow=False on the
    final slide of a carousel.
    """
    f = lf(BASK_ITA, 44)
    draw.text((L_MARGIN, H - 90), brand_name, font=f, fill=WHITE)
    if arrow:
        ax, ay = W - 90, H - 90
        pts = [(ax, ay + 22), (ax + 52, ay + 22), (ax + 52, ay + 8),
               (ax + 72, ay + 34), (ax + 52, ay + 60), (ax + 52, ay + 46),
               (ax, ay + 46)]
        draw.polygon(pts, fill=PINK)


def brand_palette() -> Dict[str, Tuple[int, int, int]]:
    """Convenience accessor for the existing brand colors. Does not add
    any new colors - returns the same BG/WHITE/PINK constants above."""
    return {"bg": BG, "white": WHITE, "pink": PINK}


def new_canvas():
    """Black canvas with top/bottom pink bars. Returns (img, draw)."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 9], fill=PINK)
    draw.rectangle([0, H - 8, W, H], fill=PINK)
    return img, draw


# ── PHOTO / FADE CANVASES ───────────────────────────────────────────────
def new_photo_fade_canvas(image_path, fade_edge="bottom", fade_start=0.35):
    """
    Generic photo canvas with a gradient fade to black on one edge, so
    text can render legibly over the faded portion.

    image_path: path to the source photo.
    fade_edge: "bottom" (fade at bottom, most common for text-under-photo
    layouts), "top", "left", or "right".
    fade_start: fraction of canvas (0-1) at which the fade begins — e.g.
    0.35 means the top 35% is untouched photo and the fade ramps across
    the remaining 65%.

    Returns (img, draw). Still adds the standard top/bottom pink bars.
    Photo is cover-cropped to fill the full 1080x1350 canvas.
    """
    try:
        photo = Image.open(image_path).convert("RGB")
    except (FileNotFoundError, OSError) as e:
        raise FileNotFoundError(f"Unable to open image asset: {image_path}") from e

    src_ratio = photo.width / photo.height
    dst_ratio = W / H
    if src_ratio > dst_ratio:
        new_h = H
        new_w = int(H * src_ratio)
    else:
        new_w = W
        new_h = int(W / src_ratio)
    photo = photo.resize((new_w, new_h))
    left = (new_w - W) // 2
    top = (new_h - H) // 2
    photo = photo.crop((left, top, left + W, top + H))

    img = photo.copy()
    fade = Image.new("L", (W, H), 0)
    fdraw = ImageDraw.Draw(fade)
    start_px = int(H * fade_start) if fade_edge in ("top", "bottom") else int(W * fade_start)

    if fade_edge == "bottom":
        for y in range(H):
            a = 0 if y < start_px else int(255 * (y - start_px) / (H - start_px))
            fdraw.line([(0, y), (W, y)], fill=a)
    elif fade_edge == "top":
        for y in range(H):
            a = 0 if y > (H - start_px) else int(255 * ((H - start_px) - y) / (H - start_px))
            fdraw.line([(0, y), (W, y)], fill=a)
    elif fade_edge == "left":
        for x in range(W):
            a = 0 if x > (W - start_px) else int(255 * ((W - start_px) - x) / (W - start_px))
            fdraw.line([(x, 0), (x, H)], fill=a)
    else:  # right
        for x in range(W):
            a = 0 if x < start_px else int(255 * (x - start_px) / (W - start_px))
            fdraw.line([(x, 0), (x, H)], fill=a)

    black = Image.new("RGB", (W, H), BG)
    img = Image.composite(black, img, fade)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 9], fill=PINK)
    draw.rectangle([0, H - 8, W, H], fill=PINK)
    return img, draw


def new_photo_story_canvas(image_path):
    """
    Photo Story template wrapper. Top ~55% photo, fading to black by
    ~90% down the canvas, so headline+body render on black in the
    lower portion.
    """
    return new_photo_fade_canvas(image_path, fade_edge="bottom", fade_start=0.30)


# ── BIG NUMBER / STAT CALLOUT ────────────────────────────────────────────
def draw_stat_callout(draw, stat_text, context_label, y0=200, stat_size=None,
                       stat_range=(200, 420)):
    """
    Big Number template element: huge pink digits + a pink-pill
    "context line" beneath.

    stat_text: the number/stat as a string, e.g. "770,000".
    context_label: short all-caps line rendered in a pink pill beneath
    the number, e.g. "PEOPLE LOST COVERAGE".
    y0: top y of the stat digits.
    stat_size: pass an explicit size to bypass auto-fit entirely — this
    is the escape hatch for short/punchy values that would otherwise
    look wrong if force-fit to 84-96% width (e.g. a single short
    number "25").
    stat_range: search range for auto-fit if stat_size is None.

    Returns the y-pixel where the context pill ends (feed into
    draw_divider or draw_body next).
    """
    stat_text = stat_text or ""
    context_label = context_label or ""

    if stat_size:
        font = lf(BARLOW, stat_size)
    else:
        font = fit_head_custom(draw, [stat_text], stat_range,
                                target_pct=(0.90, 0.98))
    draw.text((L_MARGIN, y0), stat_text, font=font, fill=PINK)
    bb = draw.textbbox((L_MARGIN, y0), stat_text, font=font)
    stat_bottom = bb[3]

    label_font = lf(BARLOW, 32)
    lbb = draw.textbbox((0, 0), context_label, font=label_font)
    lw = lbb[2] - lbb[0] + 40
    pill_top = stat_bottom + 24
    pill_bot = pill_top + 56
    draw.rectangle([L_MARGIN, pill_top, L_MARGIN + lw, pill_bot], fill=PINK)
    draw.text((L_MARGIN + 20, pill_top + 12), context_label, font=label_font, fill=WHITE)
    return pill_bot


# ── STAT GRID (By the Numbers template) ──────────────────────────────────
def draw_stat_grid(draw, items, y0, cols=2, cell_h=210):
    """
    By the Numbers template: a grid of (stat, label) pairs with thin
    divider rules between cells.

    items: list of (stat_text, label_text) tuples, e.g.
    [("$10M", "KENTUCKY SENATE PAC"), ("$5M", "OHIO GOVERNOR PAC")]
    y0: top y of the grid.
    cols: number of columns (2 for a 2x2/2x3 grid; use cols=1 for a
    single-column ranked list, e.g. a donor-comparison slide).
    cell_h: vertical height allotted per row — tune if labels wrap to
    more than 2 lines.

    Returns the y-pixel where the grid ends.
    """
    items = items or []
    usable_w = W - L_MARGIN - R_MARGIN
    col_w = usable_w // cols
    stat_font = lf(BARLOW, 90)
    label_font = lf(BARLOW, 30)
    label_max_w = col_w - 30

    rows = (len(items) + cols - 1) // cols
    for idx, (stat_text, label_text) in enumerate(items):
        row = idx // cols
        col = idx % cols
        cx = L_MARGIN + col * col_w
        cy = y0 + row * cell_h

        draw.text((cx, cy), stat_text, font=stat_font, fill=PINK)
        sbb = draw.textbbox((cx, cy), stat_text, font=stat_font)
        label_y = sbb[3] + 14

        label_lines = wrap_lines(draw, [(label_text, WHITE)], label_font, label_max_w)
        space_w = mw(draw, ' ', label_font)
        asc, desc = label_font.getmetrics()
        label_lh = int((asc + desc) * 1.2)
        ly = label_y
        for lwords in label_lines:
            x = cx
            for i, (word, col_) in enumerate(lwords):
                draw.text((x, ly), word, font=label_font, fill=col_)
                x += mw(draw, word, label_font)
                if i < len(lwords) - 1:
                    x += space_w
            ly += label_lh

        if col < cols - 1 and (idx + 1) < len(items):
            draw.line([(cx + col_w - 15, cy), (cx + col_w - 15, cy + cell_h - 30)],
                       fill=(60, 60, 60), width=2)

    grid_bottom = y0 + rows * cell_h

    for r in range(rows - 1):
        ry = y0 + (r + 1) * cell_h - 24
        draw.line([(L_MARGIN, ry), (W - R_MARGIN, ry)], fill=(60, 60, 60), width=2)

    return grid_bottom


# ── CALL BLOCK (highlighted statement bar) ───────────────────────────────
def draw_call_block(draw, text, ty, bg=PINK, text_color=WHITE, fsz=40, pad=28):
    """
    Full-width highlighted bar with a bold centered statement, e.g.
    "DISTRACT. DIVIDE. DETAIN." Height is dynamic based on how many
    lines the text wraps to.

    ty: y position to start the block.
    Returns the y-pixel where the block ends.
    """
    text = text or ""
    font = lf(BARLOW, fsz)
    max_w = W - 2 * L_MARGIN - 2 * pad
    lines = wrap_lines(draw, [(text, text_color)], font, max_w)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.0)
    block_h = pad * 2 + lh * len(lines)

    draw.rectangle([L_MARGIN, ty, W - R_MARGIN, ty + block_h], fill=bg)
    y = ty + pad
    for lwords in lines:
        line_text = " ".join(w for w, _ in lwords)
        lbb = draw.textbbox((0, 0), line_text, font=font)
        lw = lbb[2] - lbb[0]
        x = L_MARGIN + ((W - 2 * L_MARGIN) - lw) // 2  # centered
        draw.text((x, y), line_text, font=font, fill=text_color)
        y += lh
    return ty + block_h


# ── CHECK / X ICON (Scorecard "Delivered?" column) ────────────────────────
def draw_check(draw, cx, cy, size=32, ok=False, color=None):
    """
    Draws a checkmark (ok=True) or an X (ok=False) centered at (cx, cy),
    per the Scorecard sample's "Delivered?" column. Default color is
    PINK for X — pass color=WHITE or a green-adjacent value only if the
    brand palette is deliberately extended for a specific slide.
    """
    color = color or PINK
    w = size // 2
    if ok:
        draw.line([(cx - w, cy), (cx - w // 3, cy + w)], fill=color, width=6)
        draw.line([(cx - w // 3, cy + w), (cx + w, cy - w)], fill=color, width=6)
    else:
        draw.line([(cx - w, cy - w), (cx + w, cy + w)], fill=color, width=6)
        draw.line([(cx - w, cy + w), (cx + w, cy - w)], fill=color, width=6)


# ── DOCUMENT EVIDENCE CARD ────────────────────────────────────────────────
def draw_document_card(draw, img, lines, highlight_line_idxs, ty,
                        card_h=520, annotation=True):
    """
    Torn-paper document excerpt card with a pink highlight behind key
    line(s) and an optional curved arrow annotation pointing at the
    highlight.

    img: the PIL Image being drawn on (needed to paste the card, since
    the torn-paper texture is a flat-color placeholder rather than an
    actual texture asset — swap in a real torn-paper PNG if available).
    lines: list of strings, the document text, already pre-wrapped by
    the caller (short excerpt — this function does not re-wrap, since
    document text usually needs precise, deliberate line breaks
    matching the real document's formatting).
    highlight_line_idxs: set/list of line indices (0-based) to render
    with a pink highlight bar behind them.
    ty: top y of the card.
    card_h: card height — dynamic sizing based on `lines` count is left
    to the caller.
    annotation: draw the pink curved arrow pointing at the first
    highlighted line.

    Returns the y-pixel where the card ends.
    """
    lines = lines or []
    highlight_line_idxs = highlight_line_idxs or set()
    card_h = max(card_h, 1)

    draw = ImageDraw.Draw(img)
    card_bg = (240, 236, 227)  # aged paper tone — off-white, not pure white
    card_x0, card_x1 = L_MARGIN, W - R_MARGIN
    draw.rectangle([card_x0, ty, card_x1, ty + card_h], fill=card_bg)

    doc_font = lf(BASK_REG, 30)
    text_color = (20, 20, 20)
    pad = 40
    y = ty + pad
    asc, desc = doc_font.getmetrics()
    lh = int((asc + desc) * 1.25)

    for i, line in enumerate(lines):
        lbb = draw.textbbox((0, 0), line, font=doc_font)
        lw = lbb[2] - lbb[0]
        if i in highlight_line_idxs:
            draw.rectangle([card_x0 + pad - 8, y - 4, card_x0 + pad + lw + 8, y + lh - 8],
                            fill=(255, 170, 195))
        draw.text((card_x0 + pad, y), line, font=doc_font, fill=text_color)
        y += lh

    if annotation and highlight_line_idxs:
        first_hl = min(highlight_line_idxs)
        ay = ty + pad + lh * first_hl + lh // 2
        ax = card_x0 + 15
        draw.line([(ax - 60, ay + 50), (ax - 10, ay)], fill=PINK, width=5)
        draw.polygon([(ax - 10, ay), (ax - 22, ay - 6), (ax - 18, ay + 10)], fill=PINK)

    return ty + card_h


# ── DYNAMIC-HEIGHT TIMELINE ────────────────────────────────────────────────
def draw_timeline(draw, entries, y0, line_x=None):
    """
    Vertical timeline with connector line, circle nodes, year/era
    labels, pink sub-heading, and white description per entry —
    dynamic height per entry based on how many lines the description
    wraps to.

    entries: list of dicts, each with:
        "year": str — e.g. "2018" or "NOW"
        "heading": str — pink sub-heading, e.g. "Family separations begin."
        "desc": str — white description, wrapped automatically
    y0: top y of the first node.
    line_x: x position of the vertical connector line/nodes. Defaults
    to BODY_L + 40.

    Returns the y-pixel where the timeline ends (last entry's bottom).
    """
    if not entries:
        return y0

    line_x = line_x or (BODY_L + 40)
    text_x = line_x + 70
    text_w = W - R_MARGIN - text_x
    node_r = 9

    year_font = lf(BARLOW, 38)
    heading_font = lf(BARLOW, 32)
    desc_font = lf(BASK_REG, 28)
    asc_d, desc_d = desc_font.getmetrics()
    desc_lh = int((asc_d + desc_d) * 1.25)

    y = y0
    line_top = y0
    entry_positions = []

    for e in entries:
        entry_top = y
        draw.text((text_x, y), e["year"], font=year_font, fill=WHITE)
        y += year_font.size + 10

        draw.text((text_x, y), e["heading"], font=heading_font, fill=PINK)
        y += heading_font.size + 8

        desc_lines = wrap_lines(draw, [(e["desc"], WHITE)], desc_font, text_w)
        space_w = mw(draw, ' ', desc_font)
        for lwords in desc_lines:
            x = text_x
            for i, (word, col) in enumerate(lwords):
                draw.text((x, y), word, font=desc_font, fill=col)
                x += mw(draw, word, desc_font)
                if i < len(lwords) - 1:
                    x += space_w
            y += desc_lh

        node_cy = entry_top + year_font.size // 2
        entry_positions.append(node_cy)
        y += 34  # gap before next entry

    line_bottom = y - 34
    draw.line([(line_x, line_top + year_font.size // 2), (line_x, line_bottom)],
               fill=PINK, width=3)
    for cy in entry_positions:
        draw.ellipse([line_x - node_r, cy - node_r, line_x + node_r, cy + node_r],
                      outline=PINK, width=4, fill=BG)

    return y


# ── NEW TYPOGRAPHY HELPERS (v3.7.2) ─────────────────────────────────────
# Additive only. These delegate all wrapping/fitting/widow-relief to
# text_fitting_engine.py rather than re-implementing it, per the v3.7.2
# text-engine integration requirement. No existing template call site
# depends on them, and no function above has been changed to call them.
# If the text engine isn't importable for some reason, each helper below
# degrades to a harmless no-op (returns the input y-cursor unchanged)
# rather than raising.

def _font_loader_factory(path):
    """Return a font_loader callable (size -> font) bound to a font path,
    routed through the cached lf() so repeated sizes aren't reloaded."""
    def _load(size: int):
        return lf(path, size)
    return _load


def draw_pull_quote(draw, quote_text: str, ty: int, attribution: str = "",
                     max_width: Optional[int] = None, box_height: int = 260,
                     size_range: Tuple[int, int] = (40, 88)) -> int:
    """
    Editorial pull quote in Baskerville Italic, auto-fit via
    text_fitting_engine. Optional small attribution line beneath in
    Barlow. Returns the y-pixel where the block ends.
    """
    if _te_draw_fitted_text is None or not quote_text:
        return ty

    max_width = max_width or (W - BODY_L - BODY_R)
    box = (BODY_L, ty, BODY_L + max_width, ty + box_height)
    result = _te_draw_fitted_text(
        draw, box, f"\u201c{quote_text}\u201d",
        _font_loader_factory(BASK_ITA),
        fill=WHITE, align="center", valign="top",
        start_size=size_range[1], min_size=size_range[0],
    )
    y = ty + result["height"]

    if attribution:
        attr_font = lf(BARLOW, 26)
        abb = draw.textbbox((0, 0), attribution, font=attr_font)
        aw = abb[2] - abb[0]
        ax = BODY_L + (max_width - aw) // 2
        draw.text((ax, y + 16), attribution, font=attr_font, fill=PINK)
        y += 16 + attr_font.size

    return y


def draw_label(draw, text: str, x: int, y: int, fsz: int = 28,
               color=WHITE, bg=None, pad: int = 12) -> Tuple[int, int, int, int]:
    """
    Small standalone label/eyebrow text, optionally on a solid
    background pill. Returns (x, y, width, height) of the drawn block.
    """
    if not text:
        return (x, y, 0, 0)

    font = lf(BARLOW, fsz)
    if _te_measure_lines is not None:
        w, h, _ = _te_measure_lines(draw, [text], font, line_spacing=0)
    else:
        bb = draw.textbbox((0, 0), text, font=font)
        w, h = bb[2] - bb[0], bb[3] - bb[1]

    if bg is not None:
        draw.rectangle([x, y, x + w + pad * 2, y + h + pad * 2], fill=bg)
        draw.text((x + pad, y + pad), text, font=font, fill=color)
        return (x, y, w + pad * 2, h + pad * 2)

    draw.text((x, y), text, font=font, fill=color)
    return (x, y, w, h)


def draw_source_tag(draw, source_text: str, y: Optional[int] = None, fsz: int = 22) -> int:
    """
    Small italic source attribution, right-aligned above the footer
    zone (e.g. "Source: DHS FOIA release, June 2026"). Returns the
    y-pixel of the tag's top.
    """
    if not source_text:
        return y if y is not None else FOOTER_SAFE

    y = y if y is not None else (FOOTER_SAFE - 34)
    font = lf(BASK_ITA, fsz)
    bb = draw.textbbox((0, 0), source_text, font=font)
    tw = bb[2] - bb[0]
    x = W - R_MARGIN - tw
    draw.text((x, y), source_text, font=font, fill=(160, 160, 160))
    return y


def draw_cta_text(draw, text: str, ty: int, fsz_range: Tuple[int, int] = (40, 64),
                   bg=PINK, text_color=WHITE, pad: int = 32) -> int:
    """
    Full-width call-to-action bar (e.g. "FOLLOW FOR MORE"), auto-fit via
    text_fitting_engine. Returns the y-pixel where the block ends.
    """
    if _te_fit_text is None or _te_measure_lines is None or not text:
        return ty

    max_w = W - 2 * L_MARGIN - 2 * pad
    font, lines, _size = _te_fit_text(
        draw, text, _font_loader_factory(BARLOW), max_w, 200,
        start_size=fsz_range[1], min_size=fsz_range[0],
    )
    _width, height, line_h = _te_measure_lines(draw, lines, font, line_spacing=4)
    block_h = pad * 2 + height

    draw.rectangle([L_MARGIN, ty, W - R_MARGIN, ty + block_h], fill=bg)
    y = ty + pad
    for line in lines:
        lbb = draw.textbbox((0, 0), line, font=font)
        lw = lbb[2] - lbb[0]
        x = L_MARGIN + ((W - 2 * L_MARGIN) - lw) // 2
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_h + 4
    return ty + block_h


# ── COMPATIBILITY NOTES (v3.7.2) ─────────────────────────────────────────
# wrap_lines(), fit_head(), fit_head_custom(), draw_headline(), and
# draw_body() remain the canonical, pixel-tuned implementations for every
# existing template call site and are intentionally NOT rewritten to call
# text_fitting_engine.py - doing so would change their fitting behavior
# and break current template output. New template work that wants the
# editorial composition engine directly should use the helpers in the
# "NEW TYPOGRAPHY HELPERS" section above, or text_fitting_engine.py itself.

def text_engine_available() -> bool:
    """True if text_fitting_engine.py imported successfully. New helpers
    above already check this internally and no-op gracefully if False;
    exposed for callers that want to branch on it themselves."""
    return _te_fit_text is not None


# ── EXAMPLE SLIDE BUILDS (reference patterns — copy these structures) ──────
def _example_standard():
    """Reference pattern for a standard Explainer/What-It-Means style
    slide. Not meant to be called directly in production."""
    OUT_DIR = Path("/mnt/user-data/outputs/example_carousel")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TOTAL_SLIDES = 1

    img, draw = new_canvas()
    draw_top_bar(draw, "BREAKING · SOURCE", 1, TOTAL_SLIDES)

    lines = ["HEADLINE LINE ONE", "PINK EMPHASIS LINE", "FINAL LINE HERE"]
    colors = [WHITE, PINK, PINK]  # minimum 2 pink lines
    gb = draw_headline(draw, lines, colors, HEAD_Y, (100, 180))  # standard range
    db = draw_divider(draw, gb)

    draw_body(draw, [
        ("Plain body text leading into the ", WHITE),
        ("emphasized phrase", PINK),
        (" and back to plain text to close out the paragraph.", WHITE),
    ], db, fsz=46)

    draw_footer(draw)
    img.save(str(OUT_DIR / "slide_01.png"))


def _example_stat_callout():
    """Reference pattern for a Big Number cover slide using
    draw_stat_callout()."""
    img, draw = new_canvas()
    draw_top_bar(draw, "COVER-05 · BIG NUMBER", 1, 1)
    pill_bot = draw_stat_callout(draw, "770,000", "NUMBER CONTEXT LINE", y0=200)
    gb = draw_headline(draw, ["Headline Explaining", "What This Number Means"],
                        [WHITE, WHITE], pill_bot + 40, (60, 100))
    draw_footer(draw)


def _example_timeline():
    """Reference pattern for a Timeline slide using draw_timeline()."""
    img, draw = new_canvas()
    draw_top_bar(draw, "TIMELINE", 6, 10)
    gb = draw_headline(draw, ["HOW WE GOT HERE.", "WHERE THIS IS GOING."],
                        [WHITE, PINK], HEAD_Y, (100, 180))
    entries = [
        {"year": "2018", "heading": "Family separations begin.",
         "desc": "The Trump administration launches a zero-tolerance immigration policy."},
        {"year": "NOW", "heading": "Promises broken.",
         "desc": "Detention numbers are higher than ever. Families are still being torn apart."},
    ]
    draw_timeline(draw, entries, gb + 60)
    draw_footer(draw)


if __name__ == "__main__":
    print("This is a library module — import its functions into a build script.")
    print("Run precalc_report() on your headline lines before building slides.")
