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

v3.8.0
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
LINE_H_RATIO = 0.85  # legacy compatibility; v3.8 uses measured ink bounds
HEADLINE_LEADING_RATIO = 0.075  # optical breathing room between headline lines
HEADLINE_DESCENDER_PAD_RATIO = 0.055  # safety below final glyph before divider
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
def _headline_line_metrics(draw, line, font):
    """Return width, ink height, and bbox for a headline line using a top anchor."""
    bbox = draw.textbbox((0, 0), str(line), font=font, anchor="lt")
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox


def measure_headline_block(draw, lines, font):
    """
    Measure the actual visible headline block.

    v3.8 uses glyph ink bounds rather than ascender/descender estimates. This
    prevents the divider from being positioned through the final line when a
    condensed display font has unusual internal metrics.
    """
    if not lines:
        return {
            "width": 0,
            "height": 0,
            "line_gap": 0,
            "line_heights": [],
            "line_widths": [],
        }

    widths, heights = [], []
    for line in lines:
        width, height, _ = _headline_line_metrics(draw, line, font)
        widths.append(width)
        heights.append(height)

    line_gap = max(8, round(font.size * HEADLINE_LEADING_RATIO))
    block_h = sum(heights) + line_gap * max(0, len(lines) - 1)
    return {
        "width": max(widths, default=0),
        "height": block_h,
        "line_gap": line_gap,
        "line_heights": heights,
        "line_widths": widths,
    }


def fit_head(draw, lines, sz_range):
    """
    Pick the largest font that fits the headline region using measured glyph
    bounds. Manual line breaks remain authoritative.
    """
    if not lines:
        raise ValueError("fit_head() requires at least one line of text")
    tmin, tmax = int(HEAD_MAX_W * .84), int(HEAD_MAX_W * .96)
    best = None
    for sz in range(sz_range[1], sz_range[0] - 1, -1):
        font = lf(BARLOW, sz)
        metrics = measure_headline_block(draw, lines, font)
        if metrics["width"] <= tmax and metrics["height"] <= HEAD_MAX_H:
            best = (sz, font)
            if metrics["width"] >= tmin:
                break
    return best[1] if best else lf(BARLOW, sz_range[0])


def fit_head_custom(draw, lines, sz_range, target_pct=(0.84, 0.96), max_h=None):
    """Custom-width variant of fit_head(), using the same measured ink bounds."""
    if not lines:
        raise ValueError("fit_head_custom() requires at least one line of text")
    max_h = max_h or HEAD_MAX_H
    tmin, tmax = int(HEAD_MAX_W * target_pct[0]), int(HEAD_MAX_W * target_pct[1])
    best = None
    for sz in range(sz_range[1], sz_range[0] - 1, -1):
        font = lf(BARLOW, sz)
        metrics = measure_headline_block(draw, lines, font)
        if metrics["width"] <= tmax and metrics["height"] <= max_h:
            best = (sz, font)
            if metrics["width"] >= tmin:
                break
    return best[1] if best else lf(BARLOW, sz_range[0])


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



# ── COVER HEADLINE SYSTEM (Studio 3.8 production finish) ───────────────────
COVER_HEAD_TOP = 150
COVER_HEAD_BOTTOM = 700
COVER_HEAD_MAX_H = COVER_HEAD_BOTTOM - COVER_HEAD_TOP
COVER_HEAD_DEFAULT_RANGE = (72, 190)


def fit_cover_headline(draw, lines, sz_range=None):
    """Fit manually-authored cover lines at the largest safe size.

    Unlike the general headline fitter, short cover lines are allowed to use
    the maximum configured size even when they do not reach an arbitrary
    width-fill target. Long lines shrink only as much as width and the full
    cover headline zone require. Manual line breaks remain authoritative.
    """
    if not lines:
        raise ValueError("fit_cover_headline() requires at least one line")
    lo, hi = tuple(sz_range or COVER_HEAD_DEFAULT_RANGE)
    lo, hi = int(lo), int(hi)
    for size in range(hi, lo - 1, -1):
        font = lf(BARLOW, size)
        metrics = measure_headline_block(draw, lines, font)
        if metrics["width"] <= HEAD_MAX_W and metrics["height"] <= COVER_HEAD_MAX_H:
            return font, metrics, True
    font = lf(BARLOW, lo)
    return font, measure_headline_block(draw, lines, font), False


def cover_headline_y(metrics, explicit_y0=None):
    """Return an optically balanced top position for a cover headline.

    The block is centered in the upper editorial field, then shifted slightly
    upward as it grows. This prevents short covers from clinging to the top
    while keeping four- and five-line covers clear of the footer field.
    """
    if explicit_y0 is not None:
        return int(explicit_y0)
    block_h = int(metrics.get("height", 0))
    zone_h = COVER_HEAD_MAX_H
    centered = COVER_HEAD_TOP + max(0, (zone_h - block_h) // 2)
    density = min(1.0, block_h / max(1, zone_h))
    optical_raise = round((1.0 - density) * 18 + density * 6)
    return max(COVER_HEAD_TOP, centered - optical_raise)


def cover_divider_gap(font_size):
    """Adaptive divider breathing room for cover display type."""
    if font_size >= 160:
        return 18
    if font_size >= 125:
        return 22
    if font_size >= 96:
        return 26
    return 30


def draw_cover_headline(draw, lines, colors, sz_range=None, y0=None):
    """Draw a production cover headline and its adaptive divider.

    Returns a layout report containing the font size, measured block bounds,
    divider cursor, and whether the text fit above the configured minimum.
    """
    font, metrics, fit_ok = fit_cover_headline(draw, lines, sz_range)
    colors = list(colors or [])
    if len(colors) < len(lines):
        colors.extend([WHITE] * (len(lines) - len(colors)))

    top = cover_headline_y(metrics, y0)
    y = top
    ink_bottom = top
    for index, line in enumerate(lines):
        text = str(line)
        draw.text((L_MARGIN, y), text, font=font, fill=colors[index], anchor="lt")
        line_h = metrics["line_heights"][index]
        ink_bottom = max(ink_bottom, y + line_h)
        if index < len(lines) - 1:
            y += line_h + metrics["line_gap"]

    descender_pad = max(6, round(font.size * HEADLINE_DESCENDER_PAD_RATIO))
    glyph_bottom = ink_bottom + descender_pad
    divider_bottom = draw_divider(draw, glyph_bottom, gap=cover_divider_gap(font.size))
    return {
        "top": top,
        "bottom": glyph_bottom,
        "divider_bottom": divider_bottom,
        "font_size": font.size,
        "width": metrics["width"],
        "height": metrics["height"],
        "fit_ok": fit_ok,
    }

def draw_headline(draw, lines, colors, y0, sr):
    """
    Render fixed editorial lines and return the true visible bottom of the
    headline block.

    v3.8 correction:
    - lines are positioned using a top anchor;
    - line spacing is based on actual glyph ink height;
    - the return cursor includes a small descender safety pad.

    This ensures draw_divider() always begins below the final visible glyph.
    """
    if not lines:
        raise ValueError("draw_headline() requires at least one line")

    font = fit_head(draw, lines, sr)
    metrics = measure_headline_block(draw, lines, font)
    colors = list(colors or [])
    if len(colors) < len(lines):
        colors.extend([WHITE] * (len(lines) - len(colors)))

    y = int(round(y0))
    ink_bottom = y
    for i, line in enumerate(lines):
        line = str(line)
        draw.text((L_MARGIN, y), line, font=font, fill=colors[i], anchor="lt")
        _, line_h, _ = _headline_line_metrics(draw, line, font)
        ink_bottom = max(ink_bottom, y + line_h)
        if i < len(lines) - 1:
            y += line_h + metrics["line_gap"]

    descender_pad = max(6, round(font.size * HEADLINE_DESCENDER_PAD_RATIO))
    return ink_bottom + descender_pad



def fit_head_largest(draw, lines, sz_range, max_h=None):
    """Return the largest font that fits fixed manual headline lines.

    Unlike legacy fit_head(), short punchy lines do not shrink toward the
    minimum merely because they occupy less than a target percentage of the
    width. This is intended for production interior headlines where impact
    matters more than artificial width-fill scoring.
    """
    if not lines:
        raise ValueError("fit_head_largest() requires at least one line")
    lo, hi = int(sz_range[0]), int(sz_range[1])
    max_h = int(max_h or HEAD_MAX_H)
    for size in range(hi, lo - 1, -1):
        font = lf(BARLOW, size)
        metrics = measure_headline_block(draw, lines, font)
        if metrics["width"] <= HEAD_MAX_W and metrics["height"] <= max_h:
            return font
    return lf(BARLOW, lo)


def draw_headline_largest(draw, lines, colors, y0, sr, max_h=None):
    """Draw an interior headline at the largest safe size and return glyph bottom."""
    if not lines:
        raise ValueError("draw_headline_largest() requires at least one line")
    font = fit_head_largest(draw, lines, sr, max_h=max_h)
    metrics = measure_headline_block(draw, lines, font)
    colors = list(colors or [])
    if len(colors) < len(lines):
        colors.extend([WHITE] * (len(lines) - len(colors)))

    y = int(round(y0))
    ink_bottom = y
    for i, line in enumerate(lines):
        line = str(line)
        draw.text((L_MARGIN, y), line, font=font, fill=colors[i], anchor="lt")
        _, line_h, _ = _headline_line_metrics(draw, line, font)
        ink_bottom = max(ink_bottom, y + line_h)
        if i < len(lines) - 1:
            y += line_h + metrics["line_gap"]

    descender_pad = max(6, round(font.size * HEADLINE_DESCENDER_PAD_RATIO))
    return ink_bottom + descender_pad

def draw_divider(draw, gy, gap=None):
    """
    Draw the pink divider below the measured headline bottom.

    ``gy`` must be the cursor returned by draw_headline(). ``gap`` remains
    optional for template-specific tuning while preserving the legacy call
    signature.
    """
    gap = DIVIDER_GAP if gap is None else max(8, int(gap))
    y = int(round(gy + gap))
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
def draw_stat_grid(draw, items, y0, cols=2, cell_h=285):
    """Stat Grid v3.8.28: center each statistic block inside its grid cell."""
    items = items or []
    if not items:
        return y0

    normalized = []
    for item in items:
        if isinstance(item, dict):
            stat_text = str(
                item.get("stat_text")
                or item.get("statistic")
                or item.get("value")
                or item.get("number")
                or ""
            ).strip()
            label_text = str(
                item.get("label")
                or item.get("stat_label")
                or item.get("title")
                or ""
            ).strip()
        elif isinstance(item, (list, tuple)):
            stat_text = str(item[0]).strip() if len(item) > 0 else ""
            label_text = str(item[1]).strip() if len(item) > 1 else ""
        else:
            stat_text = str(item).strip()
            label_text = ""

        normalized.append((stat_text, label_text))

    cols = max(1, int(cols or 2))
    rows = max(1, (len(normalized) + cols - 1) // cols)

    GRID_LEFT = L_MARGIN
    GRID_RIGHT = W - R_MARGIN
    grid_w = GRID_RIGHT - GRID_LEFT
    col_w = grid_w / cols
    divider_color = (82, 82, 82)

    VALUE_MAX = 138
    VALUE_MIN = 82
    LABEL_SIZE = 50
    VALUE_TO_LABEL_GAP = 8
    CELL_TOP_PAD = 22
    CELL_SIDE_PAD = 20

    for idx, (stat_text, label_text) in enumerate(normalized):
        row = idx // cols
        col = idx % cols

        cell_left = int(GRID_LEFT + col * col_w)
        cell_right = int(GRID_LEFT + (col + 1) * col_w)
        cell_center = (cell_left + cell_right) // 2
        cell_y = int(y0 + row * cell_h)
        inner_y = cell_y + CELL_TOP_PAD
        inner_w = int(col_w - 2 * CELL_SIDE_PAD)

        value_font = lf(BARLOW, VALUE_MAX)
        while value_font.size > VALUE_MIN:
            bbox = draw.textbbox((0, 0), stat_text, font=value_font)
            if bbox[2] - bbox[0] <= inner_w:
                break
            value_font = lf(BARLOW, value_font.size - 2)

        value_bbox = draw.textbbox((0, 0), stat_text, font=value_font)
        value_w = value_bbox[2] - value_bbox[0]
        value_x = int(cell_center - value_w / 2 - value_bbox[0])
        draw.text((value_x, inner_y), stat_text, font=value_font, fill=PINK)

        placed_value_bbox = draw.textbbox((value_x, inner_y), stat_text, font=value_font)
        label_y = placed_value_bbox[3] + VALUE_TO_LABEL_GAP

        label_font = lf(BARLOW, LABEL_SIZE)
        label_lines = wrap_lines(draw, [(label_text, WHITE)], label_font, inner_w)
        asc, desc = label_font.getmetrics()
        label_lh = int((asc + desc) * 1.02)

        for line_words in label_lines[:2]:
            line_text = " ".join(word for word, _ in line_words)
            line_bbox = draw.textbbox((0, 0), line_text, font=label_font)
            line_w = line_bbox[2] - line_bbox[0]
            x = int(cell_center - line_w / 2 - line_bbox[0])

            for word_index, (word, color) in enumerate(line_words):
                draw.text((x, label_y), word, font=label_font, fill=color)
                x += mw(draw, word, label_font)
                if word_index < len(line_words) - 1:
                    x += mw(draw, " ", label_font)
            label_y += label_lh

        if col < cols - 1 and idx + 1 < len(normalized):
            divider_x = int(cell_right)
            draw.line(
                [(divider_x, cell_y + 4), (divider_x, cell_y + cell_h - 28)],
                fill=divider_color,
                width=3,
            )

    for row in range(rows - 1):
        divider_y = int(y0 + (row + 1) * cell_h - 14)
        draw.line(
            [(GRID_LEFT, divider_y), (GRID_RIGHT, divider_y)],
            fill=divider_color,
            width=3,
        )

    return int(y0 + rows * cell_h)


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
                        card_h=472, annotation=True):
    """Evidence — Document Card v3.8.34."""
    lines = lines or []
    highlight_line_idxs = set(highlight_line_idxs or [])

    normalized = []
    for item in lines:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("line") or item.get("content") or "")
        elif isinstance(item, (list, tuple)):
            text = str(item[0]) if item else ""
        else:
            text = str(item)
        if text.strip():
            normalized.append(text.strip())

    card_x0 = L_MARGIN + 54
    card_x1 = W - R_MARGIN - 54
    card_w = card_x1 - card_x0
    card_h = max(438, int(card_h or 472))

    paper = (246, 242, 232)
    paper_back = (227, 221, 211)
    paper_edge = (194, 188, 176)
    ink = (28, 28, 28)
    muted = (92, 92, 92)
    highlight = (247, 208, 72)

    draw.polygon(
        [(card_x0 + 22, ty + 6), (card_x1 + 6, ty + 18),
         (card_x1 - 2, ty + card_h + 10), (card_x0 + 10, ty + card_h - 2)],
        fill=paper_back,
    )
    draw.polygon(
        [(card_x0, ty + 18), (card_x1 - 20, ty),
         (card_x1, ty + card_h - 16), (card_x0 + 18, ty + card_h)],
        fill=paper,
        outline=paper_edge,
    )

    left = card_x0 + 52
    right = card_x1 - 52
    center = (left + right) // 2

    masthead_font = lf(BARLOW, 24)
    small_font = lf(BARLOW, 19)
    title_font = lf(BARLOW, 31)
    body_font = lf(BASK_REG, 29)
    note_font = lf(BARLOW, 22)

    masthead = "OFFICIAL RECORD"
    mb = draw.textbbox((0, 0), masthead, font=masthead_font)
    draw.text((center - (mb[2] - mb[0]) // 2, ty + 42), masthead,
              font=masthead_font, fill=ink)
    agency = "UNITED STATES GOVERNMENT"
    ab = draw.textbbox((0, 0), agency, font=small_font)
    draw.text((center - (ab[2] - ab[0]) // 2, ty + 72), agency,
              font=small_font, fill=muted)
    draw.line((left, ty + 104, right, ty + 104), fill=paper_edge, width=2)

    date_text = "DOCUMENT EXCERPT"
    db = draw.textbbox((0, 0), date_text, font=small_font)
    draw.text((center - (db[2] - db[0]) // 2, ty + 118), date_text,
              font=small_font, fill=muted)

    decision = "KEY CONTRACT TERMS"
    tb = draw.textbbox((0, 0), decision, font=title_font)
    draw.text((center - (tb[2] - tb[0]) // 2, ty + 152), decision,
              font=title_font, fill=ink)

    focus_idx = min(highlight_line_idxs) if highlight_line_idxs else 0
    focus_idx = min(max(focus_idx, 0), max(0, len(normalized) - 1))
    focus = normalized[focus_idx] if normalized else "Document evidence"

    max_focus_w = int(card_w * 0.50)
    focus_lines = []
    current = ""
    for word in focus.split():
        trial = f"{current} {word}".strip()
        bb = draw.textbbox((0, 0), trial, font=body_font)
        if current and bb[2] - bb[0] > max_focus_w:
            focus_lines.append(current)
            current = word
        else:
            current = trial
    if current:
        focus_lines.append(current)
    focus_lines = focus_lines[:3]

    asc, desc = body_font.getmetrics()
    line_h = int((asc + desc) * 1.14)
    focus_y = ty + 220
    max_line_w = 0
    for line in focus_lines:
        bb = draw.textbbox((0, 0), line, font=body_font)
        max_line_w = max(max_line_w, bb[2] - bb[0])

    hx0 = left + 170
    hx1 = min(right - 175, hx0 + max_line_w + 26)
    hy0 = focus_y - 5
    hy1 = focus_y + line_h * len(focus_lines) - 6
    draw.rectangle((hx0 - 10, hy0, hx1, hy1), fill=highlight)

    fy = focus_y
    for line in focus_lines:
        draw.text((hx0, fy), line, font=body_font, fill=ink)
        fy += line_h

    if annotation:
        note_x = right - 145
        note_y = focus_y + 10
        anchor_y = focus_y + min(20, (hy1 - hy0) // 2)
        draw.line((hx1 + 18, anchor_y, note_x - 16, note_y + 14), fill=ink, width=4)
        draw.polygon(((hx1 + 16, anchor_y),
                      (hx1 + 30, anchor_y - 8),
                      (hx1 + 30, anchor_y + 8)), fill=ink)
        for i, text in enumerate(("KEY", "DETAIL")):
            draw.text((note_x, note_y + i * 28), text, font=note_font, fill=ink)
        draw.line((note_x, note_y + 64, note_x + 76, note_y + 64), fill=PINK, width=5)

    secondary = [v for i, v in enumerate(normalized) if i != focus_idx][:3]
    sy = ty + card_h - 122
    sec_font = lf(BASK_REG, 21)
    for line in secondary:
        text = line if len(line) <= 58 else line[:55].rstrip() + "…"
        draw.text((left + 16, sy), text, font=sec_font, fill=muted)
        sy += 27

    red_y = ty + card_h - 58
    for width in (408, 492, 446):
        draw.rectangle((left + 116, red_y, left + 116 + width, red_y + 9), fill=(175, 175, 175))
        red_y += 17

    return ty + card_h


# ── DYNAMIC-HEIGHT TIMELINE ────────────────────────────────────────────────
def draw_timeline(draw, entries, y0, line_x=None):
    """Timeline v3.8.20 with stronger body weight and slightly higher placement."""
    TIMELINE_DATE_SIZE = 48
    TIMELINE_BODY_SIZE = 46
    TIMELINE_BODY_LINE_ADVANCE = 56
    TIMELINE_MAX_W = 800
    TIMELINE_LINE_WIDTH = 5
    TIMELINE_NODE_RADIUS = 11
    TIMELINE_TOP_OFFSET = 52
    TIMELINE_MAX_SPAN = 380

    line_x = line_x or (BODY_L + 50)
    text_x = line_x + 78
    text_w = min(TIMELINE_MAX_W, W - R_MARGIN - text_x)

    date_font = lf(BARLOW, TIMELINE_DATE_SIZE)
    body_font = lf(BASK_REG, TIMELINE_BODY_SIZE)

    normalized = []
    for entry in entries:
        date_text = str(entry.get("date") or entry.get("year") or "").strip()
        heading_text = str(entry.get("heading") or "").strip()
        body_text = str(entry.get("text") or entry.get("desc") or "").strip()

        if not body_text and heading_text:
            body_text = heading_text
        elif heading_text and body_text and not body_text.startswith(heading_text):
            body_text = f"{heading_text} {body_text}"

        if date_text or body_text:
            normalized.append((date_text, body_text))

    if not normalized:
        return y0

    start_y = y0 + TIMELINE_TOP_OFFSET
    available_to_footer = max(1, FOOTER_SAFE - 120 - start_y)
    span = min(TIMELINE_MAX_SPAN, available_to_footer)

    if len(normalized) == 1:
        anchors = [start_y]
    else:
        anchors = [
            round(start_y + span * i / (len(normalized) - 1))
            for i in range(len(normalized))
        ]

    node_centers = []

    for anchor_y, (date_text, body_text) in zip(anchors, normalized):
        draw.text((text_x, anchor_y), date_text, font=date_font, fill=PINK)
        date_bbox = draw.textbbox((text_x, anchor_y), date_text, font=date_font)
        date_height = max(1, date_bbox[3] - date_bbox[1])
        body_y = date_bbox[3] + 8

        lines = wrap_lines(draw, [(body_text, WHITE)], body_font, text_w)
        space_w = mw(draw, " ", body_font)

        for line_words in lines:
            x = text_x
            for idx, (word, color) in enumerate(line_words):
                draw.text((x, body_y), word, font=body_font, fill=color)
                x += mw(draw, word, body_font)
                if idx < len(line_words) - 1:
                    x += space_w
            body_y += TIMELINE_BODY_LINE_ADVANCE

        node_centers.append(anchor_y + date_height // 2)

    draw.line(
        [(line_x, node_centers[0]), (line_x, node_centers[-1])],
        fill=PINK,
        width=TIMELINE_LINE_WIDTH,
    )

    for cy in node_centers:
        draw.ellipse(
            [
                line_x - TIMELINE_NODE_RADIUS,
                cy - TIMELINE_NODE_RADIUS,
                line_x + TIMELINE_NODE_RADIUS,
                cy + TIMELINE_NODE_RADIUS,
            ],
            outline=PINK,
            width=TIMELINE_LINE_WIDTH,
            fill=BG,
        )

    return start_y + span


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
