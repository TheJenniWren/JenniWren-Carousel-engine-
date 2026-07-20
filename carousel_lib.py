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
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import re

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


# ── FONT LOADING ─────────────────────────────────────────────────────────
def lf(path, size):
    """Load a TrueType font."""
    try:
        return ImageFont.truetype(str(path), size)
    except OSError as e:
        raise RuntimeError(f"Unable to load font: {path}") from e


def mw(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


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
    return re.sub(r'(https?://\S+)', lambda m: m.group(1).replace('/', '/ '), text)


def wrap_lines(draw, segs, font, max_w):
    """
    Generic word-wrapper. segs: list of (text, color) tuples (color-
    segmented inline text). Returns a list of lines, where each line is
    itself a list of (word, color) tuples — ready to be drawn word by
    word with per-word color.
    """
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
def fit_head(draw, lines, sz_range):
    """
    Pick the largest font size in sz_range such that:
    - the widest line occupies between 84% and 96% of HEAD_MAX_W, AND
    - the total block height (all lines, tight-stacked) does not
      exceed HEAD_MAX_H.

    Short-line collapse: if a line is very short (e.g. a single word
    like "DEAD."), this function will still try to size it up to fill
    84-96% of width, which can look absurd on a 2-3 character line.
    The fix is not to change this function's math — rewrite the copy
    to a longer line, or use draw_stat_callout() with an explicit
    stat_size, bypassing fit_head() entirely for that element.
    """
    tmin, tmax = int(HEAD_MAX_W * .84), int(HEAD_MAX_W * .96)
    best = None
    for sz in range(sz_range[1], sz_range[0] - 1, -1):
        font = lf(BARLOW, sz)
        mx = max(mw(draw, l, font) for l in lines)
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * 0.88)
        block_h = lh * (len(lines) - 1) + (asc + desc)
        if mx <= tmax and block_h <= HEAD_MAX_H:
            best = (sz, font)
            if mx >= tmin:
                break
    return best[1] if best else lf(BARLOW, sz_range[0])


def fit_head_custom(draw, lines, sz_range, target_pct=(0.84, 0.96), max_h=None):
    """
    Same mechanism as fit_head(), but with a custom width-fill target
    instead of the fixed 84-96%. Needed for elements like Big Number
    stat digits, which should fill much more of the canvas width.
    """
    max_h = max_h or HEAD_MAX_H
    tmin, tmax = int(HEAD_MAX_W * target_pct[0]), int(HEAD_MAX_W * target_pct[1])
    best = None
    for sz in range(sz_range[1], sz_range[0] - 1, -1):
        font = lf(BARLOW, sz)
        mx = max(mw(draw, l, font) for l in lines)
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * 0.88)
        block_h = lh * (len(lines) - 1) + (asc + desc)
        if mx <= tmax and block_h <= max_h:
            best = (sz, font)
            if mx >= tmin:
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


def draw_headline(draw, lines, colors, y0, sr):
    """
    lines: list of strings (already pre-calculated / rewritten for balance)
    colors: parallel list — WHITE or PINK per line.
    RULE: every headline needs at least 2 pink lines minimum.
    y0: starting y position (use HEAD_Y)
    sr: (lo, hi) font size search range — use (100, 180) as the standard range.
    Returns the y-pixel of the bottom of the headline block (for
    passing into draw_divider).
    """
    font = fit_head(draw, lines, sr)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 0.88)
    y = y0
    for i, (line, col) in enumerate(zip(lines, colors)):
        draw.text((L_MARGIN, y), line, font=font, fill=col)
        if i < len(lines) - 1:
            y += lh
    bb = draw.textbbox((L_MARGIN, y), lines[-1], font=font)
    return bb[3]


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
    photo = Image.open(image_path).convert("RGB")
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
