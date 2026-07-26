"""
explainer_templates.py
JenniWren Carousel Production Pipeline -- EXPLAINER family

v3.8.14
------
Production-stack Standard Explainer body hierarchy refinement.

This revision changes only render_body_standard() and its dedicated
measurement/drawing helpers. Cover rendering remains untouched.

Changes:
* body typography raised to 49px with 56px editorial leading
* narrower 850px editorial measure and larger 64px divider gap
* inline emphasis parsing restored for Standard Explainer body copy
* **text** renders in bold white
* [pink]text[/pink] renders in bold pink
* headline sizing, divider placement, and footer exclusion remain untouched
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from perf import cached_lf
from story_loader import StorySlide, StoryPackage
from template_shared import colors_from_names, body_segs, require_fields

logger = logging.getLogger("jenniwren.templates")

# Standard Explainer only. These values do not affect cover templates.
EXPLAINER_HEADLINE_FONT_TARGET = {1: 192, 2: 168, 3: 156, 4: 148}
EXPLAINER_HEADLINE_FONT_MIN = {1: 172, 2: 150, 3: 140, 4: 132}
# Measured visible ink-height targets. This corrects Barlow's large top bearing.
EXPLAINER_HEADLINE_INK_HEIGHT = {1: 180, 2: 162, 3: 134, 4: 118}
EXPLAINER_HEADLINE_MAX_W = cl.W - 108
EXPLAINER_HEADLINE_MIN_X_SCALE = 0.82
EXPLAINER_Y0 = {1: 160, 2: 150, 3: 166, 4: 174}
EXPLAINER_HEADLINE_LINE_GAP = 4
EXPLAINER_HEADLINE_DIVIDER_GAP = 15

EXPLAINER_BODY_SIZE = 49
EXPLAINER_BODY_MIN_SIZE = 46
EXPLAINER_BODY_LINE_ADVANCE = 56
EXPLAINER_BODY_MAX_W = 850
EXPLAINER_BODY_GAP = 64
EXPLAINER_FOOTER_BUFFER = 36

# Bold fallback: use explicit constant when available, otherwise infer it from
# the regular Libre Baskerville file name. If that file is missing, the loader
# falls back to the regular face.
EXPLAINER_BODY_BOLD = getattr(
    cl,
    "BASK_BOLD",
    str(cl.BASK_REG).replace("Regular.ttf", "Bold.ttf"),
)

BODY_WHITE = "white"
BODY_PINK = "pink"
BODY_REGULAR = "regular"
BODY_BOLD = "bold"


def _headline_value(mapping, line_count: int) -> int:
    return mapping.get(max(1, line_count), mapping[4])


def _ink_bbox(font, text: str):
    bbox = font.getbbox(text)
    left, top, right, bottom = bbox
    return bbox, max(1, right - left), max(1, bottom - top)


def _render_headline_line_layer(text: str, color, line_count: int):
    """Render one line with measured-ink height and capped width compression.

    The font is reduced only when the required horizontal compression would
    exceed the 18% cap. Vertical size is then normalized to the explicit ink
    target, so a wide line does not become visually short merely to fit width.
    """
    from PIL import Image, ImageDraw

    target_font = _headline_value(EXPLAINER_HEADLINE_FONT_TARGET, line_count)
    min_font = _headline_value(EXPLAINER_HEADLINE_FONT_MIN, line_count)
    target_ink_h = _headline_value(EXPLAINER_HEADLINE_INK_HEIGHT, line_count)

    chosen = None
    for size in range(target_font, min_font - 1, -1):
        font = cl.lf(cl.BARLOW, size)
        bbox, ink_w, ink_h = _ink_bbox(font, text)
        required_x_scale = min(1.0, EXPLAINER_HEADLINE_MAX_W / ink_w)
        if required_x_scale >= EXPLAINER_HEADLINE_MIN_X_SCALE:
            chosen = (font, size, bbox, ink_w, ink_h, required_x_scale)
            break

    if chosen is None:
        font = cl.lf(cl.BARLOW, min_font)
        bbox, ink_w, ink_h = _ink_bbox(font, text)
        required_x_scale = max(
            EXPLAINER_HEADLINE_MIN_X_SCALE,
            min(1.0, EXPLAINER_HEADLINE_MAX_W / ink_w),
        )
        chosen = (font, min_font, bbox, ink_w, ink_h, required_x_scale)

    font, size, bbox, ink_w, ink_h, x_scale = chosen
    pad = 3
    layer = Image.new("RGBA", (ink_w + pad * 2, ink_h + pad * 2), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    # Offset by the measured bbox so the layer contains ink only, not font bearings.
    ld.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=(*color, 255))

    out_w = max(1, round(ink_w * x_scale))
    out_h = max(1, target_ink_h)
    layer = layer.resize((out_w + pad * 2, out_h + pad * 2), Image.Resampling.LANCZOS)

    return layer, {
        "font_size": size,
        "x_scale": x_scale,
        "source_ink_height": ink_h,
        "display_ink_height": target_ink_h,
        "display_width": out_w,
    }


def _draw_standard_headline(draw, image, lines, colors, y0: int):
    line_count = max(1, len(lines))
    color_list = list(colors or [])
    if len(color_list) < len(lines):
        color_list.extend([cl.WHITE] * (len(lines) - len(color_list)))

    y = int(y0)
    reports = []
    for idx, line in enumerate(lines):
        layer, report = _render_headline_line_layer(str(line), color_list[idx], line_count)
        image.alpha_composite(layer, (cl.L_MARGIN, y))
        reports.append(report)
        y += layer.height
        if idx < len(lines) - 1:
            y += EXPLAINER_HEADLINE_LINE_GAP

    return {"top": y0, "bottom": y, "lines": reports}


def _body_color(value):
    if isinstance(value, tuple):
        return value
    return cl.PINK if str(value).lower() == BODY_PINK else cl.WHITE


def _body_font(size: int, style: str):
    path = EXPLAINER_BODY_BOLD if style == BODY_BOLD else cl.BASK_REG
    try:
        return cached_lf(path, size)
    except Exception:
        return cached_lf(cl.BASK_REG, size)


def _parse_inline_body(text: str):
    """Parse explainer body inline emphasis.

    Supported markers:
    * **text** -> bold white
    * [pink]text[/pink] -> bold pink
    Everything else remains regular white.
    """
    pattern = re.compile(r"(\[pink\].*?\[/pink\]|\*\*.*?\*\*)", re.DOTALL)
    parts = []
    pos = 0
    for match in pattern.finditer(text or ""):
        if match.start() > pos:
            parts.append((text[pos:match.start()], BODY_WHITE, BODY_REGULAR))
        token = match.group(0)
        if token.startswith("[pink]") and token.endswith("[/pink]"):
            parts.append((token[6:-7], BODY_PINK, BODY_BOLD))
        elif token.startswith("**") and token.endswith("**"):
            parts.append((token[2:-2], BODY_WHITE, BODY_BOLD))
        pos = match.end()
    if pos < len(text or ""):
        parts.append((text[pos:], BODY_WHITE, BODY_REGULAR))
    return [part for part in parts if part[0]]


def _prepare_body_segments(body, slide_id: str):
    if isinstance(body, str):
        return _parse_inline_body(body)

    prepared = []
    for seg in body_segs(body, slide_id):
        if isinstance(seg, dict):
            text = str(seg.get("text", ""))
            color = BODY_PINK if str(seg.get("color", "white")).lower() == BODY_PINK else BODY_WHITE
            style = BODY_BOLD if bool(seg.get("bold", False)) else BODY_REGULAR
        else:
            if len(seg) >= 2:
                text, color = seg[0], seg[1]
            else:
                text, color = seg[0], BODY_WHITE
            style = BODY_REGULAR
            color = BODY_PINK if str(color).lower() == BODY_PINK else BODY_WHITE
        prepared.append((str(text), color, style))
    return prepared



def _space_width(draw, regular_font, bold_font):
    return max(cl.mw(draw, " ", regular_font), cl.mw(draw, " ", bold_font))


def _wrap_body_lines(draw, styled_segs, font_size: int):
    regular_font = _body_font(font_size, BODY_REGULAR)
    bold_font = _body_font(font_size, BODY_BOLD)
    space_w = _space_width(draw, regular_font, bold_font)

    tokens = []
    for text, color_name, style in styled_segs or []:
        font = bold_font if style == BODY_BOLD else regular_font
        color = _body_color(color_name)
        for word in cl.break_urls(text).split():
            tokens.append((word, color, font))

    lines, cur, cur_w = [], [], 0
    for word, color, font in tokens:
        ww = cl.mw(draw, word, font)
        needed = ww + (space_w if cur else 0)
        if cur and cur_w + needed > EXPLAINER_BODY_MAX_W:
            lines.append(cur)
            cur, cur_w = [(word, color, font)], ww
        else:
            if cur:
                cur_w += space_w
            cur.append((word, color, font))
            cur_w += ww
    if cur:
        lines.append(cur)

    return {
        "lines": lines,
        "space_w": space_w,
        "regular_font": regular_font,
        "bold_font": bold_font,
    }


def _measure_body(draw, styled_segs, font_size: int):
    wrapped = _wrap_body_lines(draw, styled_segs, font_size)
    return {
        "font_size": font_size,
        "lines": wrapped["lines"],
        "space_w": wrapped["space_w"],
        "regular_font": wrapped["regular_font"],
        "bold_font": wrapped["bold_font"],
        "height": len(wrapped["lines"]) * EXPLAINER_BODY_LINE_ADVANCE,
    }


def _fit_body(draw, styled_segs, start_y: int, floor_y: int):
    for size in range(EXPLAINER_BODY_SIZE, EXPLAINER_BODY_MIN_SIZE - 1, -1):
        report = _measure_body(draw, styled_segs, size)
        if start_y + report["height"] <= floor_y:
            return report
    raise ValueError(
        f"body_standard copy does not fit the fixed editorial body zone at {EXPLAINER_BODY_MIN_SIZE}px. "
        "Shorten the paragraph or split it across slides."
    )


def _draw_explainer_body(draw, styled_segs, divider_bottom: int, slide_id: str):
    start_y = divider_bottom + EXPLAINER_BODY_GAP
    floor_y = cl.FOOTER_SAFE - EXPLAINER_FOOTER_BUFFER
    report = _fit_body(draw, styled_segs, start_y, floor_y)

    y = start_y
    space_w = report["space_w"]
    for lwords in report["lines"]:
        if y + EXPLAINER_BODY_LINE_ADVANCE > floor_y:
            raise ValueError(
                f"{slide_id}: body_standard copy crossed the footer exclusion zone. "
                "Shorten the paragraph or split it across slides."
            )
        x = cl.BODY_L
        for idx, (word, color, font) in enumerate(lwords):
            draw.text((x, y), word, font=font, fill=color)
            x += cl.mw(draw, word, font)
            if idx < len(lwords) - 1:
                x += space_w
        y += EXPLAINER_BODY_LINE_ADVANCE

    return {
        "start_y": start_y,
        "end_y": y,
        "font_size": report["font_size"],
        "line_advance": EXPLAINER_BODY_LINE_ADVANCE,
        "lines": len(report["lines"]),
    }


def render_body_standard(slide: StorySlide, n: int, total: int, story: StoryPackage,
                          defaults: TemplateDefaults):
    require_fields(slide, "label", "headline_lines", "headline_colors", "body")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))

    if img.mode != "RGBA":
        img = img.convert("RGBA")
        draw = cl.ImageDraw.Draw(img)

    lines = slide.get("headline_lines") or []
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    line_count = max(1, len(lines))
    y0 = int(slide.get("headline_y0", _headline_value(EXPLAINER_Y0, line_count)))

    headline_report = _draw_standard_headline(draw, img, lines, colors, y0)
    divider_y = headline_report["bottom"] + EXPLAINER_HEADLINE_DIVIDER_GAP
    draw.rectangle(
        [cl.L_MARGIN, divider_y, cl.W - cl.R_MARGIN, divider_y + cl.DIVIDER_H],
        fill=cl.PINK,
    )
    divider_bottom = divider_y + cl.DIVIDER_H

    body_report = _draw_explainer_body(
        draw,
        _prepare_body_segments(slide.get("body"), slide.slide_id),
        divider_bottom,
        slide.slide_id,
    )

    scales = ",".join(f"{item['x_scale']:.3f}" for item in headline_report["lines"])
    ink_heights = ",".join(str(item["display_ink_height"]) for item in headline_report["lines"])
    qa_notes.append(
        f"{slide.slide_id}: production renderer headline x-scales {scales}; "
        f"display ink heights {ink_heights}px; body {body_report['font_size']}px/"
        f"{body_report['line_advance']}px; footer clearance "
        f"{(cl.FOOTER_SAFE - EXPLAINER_FOOTER_BUFFER) - body_report['end_y']}px."
    )

    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img.convert("RGB"), qa_notes


def render_sources_slide(slide: StorySlide, n: int, total: int, story: StoryPackage,
                          defaults: TemplateDefaults):
    require_fields(slide, "citations")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label", "SOURCES"), n, total)

    fsz = max(slide.get("body_size", defaults.sources_body_size), cl.BODY_MIN_SIZE)
    font = cached_lf(cl.BASK_REG, fsz)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.32)
    max_w = cl.W - cl.BODY_L - cl.BODY_R
    y = cl.HEAD_Y
    citations = slide.get("citations")
    dropped = 0

    for i, citation in enumerate(citations, start=1):
        entry_segs = [(f"{i}. {cl.break_urls(citation)}", cl.WHITE)]
        wrapped = cl.wrap_lines(draw, entry_segs, font, max_w)
        for lwords in wrapped:
            if y + lh > cl.FOOTER_SAFE:
                dropped += 1
                break
            x = cl.BODY_L
            space_w = cl.mw(draw, " ", font)
            for j, (word, col) in enumerate(lwords):
                draw.text((x, y), word, font=font, fill=col)
                x += cl.mw(draw, word, font)
                if j < len(lwords) - 1:
                    x += space_w
            y += lh
        y += lh // 2

    if dropped:
        qa_notes.append(
            f"sources_slide: {dropped} of {len(citations)} citation(s) did not fit "
            f"above the footer-safe zone and were not rendered. Split into another "
            f"sources_slide."
        )

    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", False)))
    return img, qa_notes
