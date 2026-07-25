"""
explainer_templates.py
JenniWren Carousel Production Pipeline -- EXPLAINER family

v3.8.4
------
Standard explainer slides now use a dedicated editorial-prose layout
system instead of delegating body copy to carousel_lib.draw_body().
This keeps cover templates untouched while correcting the explainer
failure mode that inflated short copy into poster-size type.

Key changes in render_body_standard():
* custom headline fitter that preserves short headlines at strong sizes
* fixed explainer body zone with deliberate whitespace
* stable body-size selection (prefer 35px, only step down if needed)
* tighter body leading and stricter footer clearance
* no vertical centering and no opportunistic upscaling of short copy
"""

from __future__ import annotations

import logging
from typing import Dict, List, Sequence, Tuple

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from perf import cached_lf
from story_loader import StorySlide, StoryPackage
from template_shared import colors_from_names, body_segs, require_fields

logger = logging.getLogger("jenniwren.templates")

# --- Standard Explainer editorial layout constants (v3.8.5) ---
# Headline targets are intentionally explicit. Long lines are compressed
# horizontally only as much as needed to keep the requested display height.
EXPLAINER_HEADLINE_TARGET = {1: 192, 2: 168, 3: 156, 4: 148}
EXPLAINER_HEADLINE_MIN = {1: 176, 2: 154, 3: 146, 4: 138}
EXPLAINER_HEADLINE_MAX_W = cl.W - 108
EXPLAINER_HEADLINE_MIN_X_SCALE = 0.78
EXPLAINER_Y0 = {1: 168, 2: 170, 3: 176, 4: 182}
EXPLAINER_HEADLINE_LINE_GAP = 4
EXPLAINER_HEADLINE_DIVIDER_GAP = 18

# Body is fixed editorial prose, not a maximize-to-fill block.
# 33px was chosen after the requested 29px floor proved likely too small.
EXPLAINER_BODY_SIZE = 33
EXPLAINER_BODY_MIN_SIZE = 31
EXPLAINER_BODY_LINE_ADVANCE = 39
EXPLAINER_BODY_MAX_W = 880
EXPLAINER_BODY_GAP = 24
EXPLAINER_FOOTER_BUFFER = 34


# --- Dedicated Standard Explainer helpers ---------------------------------
def _headline_target_size(line_count: int) -> int:
    return EXPLAINER_HEADLINE_TARGET.get(line_count, EXPLAINER_HEADLINE_TARGET[4])


def _headline_min_size(line_count: int) -> int:
    return EXPLAINER_HEADLINE_MIN.get(line_count, EXPLAINER_HEADLINE_MIN[4])


def _render_headline_line_layer(text: str, color, target_size: int):
    """Render one headline line at display height, squeezing width only if required."""
    from PIL import Image

    size = int(target_size)
    min_size = _headline_min_size(1)
    while size >= min_size:
        font = cl.lf(cl.BARLOW, size)
        bbox = font.getbbox(text, anchor="lt")
        width = max(1, bbox[2] - bbox[0])
        height = max(1, bbox[3] - bbox[1])
        x_scale = min(1.0, EXPLAINER_HEADLINE_MAX_W / width)
        if x_scale >= EXPLAINER_HEADLINE_MIN_X_SCALE:
            layer = Image.new("RGBA", (width + 8, height + 8), (0, 0, 0, 0))
            ld = cl.ImageDraw.Draw(layer)
            ld.text((0, 0), text, font=font, fill=(*color, 255), anchor="lt")
            if x_scale < 0.999:
                layer = layer.resize((max(1, round(layer.width * x_scale)), layer.height), Image.Resampling.LANCZOS)
            return layer, size, x_scale
        size -= 2

    font = cl.lf(cl.BARLOW, min_size)
    bbox = font.getbbox(text, anchor="lt")
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    x_scale = min(1.0, EXPLAINER_HEADLINE_MAX_W / width)
    layer = Image.new("RGBA", (width + 8, height + 8), (0, 0, 0, 0))
    ld = cl.ImageDraw.Draw(layer)
    ld.text((0, 0), text, font=font, fill=(*color, 255), anchor="lt")
    if x_scale < 0.999:
        layer = layer.resize((max(1, round(layer.width * x_scale)), layer.height), Image.Resampling.LANCZOS)
    return layer, min_size, x_scale


def _draw_standard_headline(draw, image, lines, colors, y0: int):
    line_count = max(1, len(lines))
    target = _headline_target_size(line_count)
    color_list = list(colors or [])
    if len(color_list) < len(lines):
        color_list.extend([cl.WHITE] * (len(lines) - len(color_list)))

    y = int(y0)
    reports = []
    for idx, line in enumerate(lines):
        layer, size, x_scale = _render_headline_line_layer(str(line), color_list[idx], target)
        image.alpha_composite(layer, (cl.L_MARGIN, y))
        reports.append({"font_size": size, "x_scale": x_scale, "height": layer.height, "width": layer.width})
        y += layer.height
        if idx < len(lines) - 1:
            y += EXPLAINER_HEADLINE_LINE_GAP

    return {"top": y0, "bottom": y, "lines": reports}


def _measure_body(draw, segs, font_size: int):
    font = cached_lf(cl.BASK_REG, font_size)
    lines = cl.wrap_lines(draw, segs, font, EXPLAINER_BODY_MAX_W)
    return {"font": font, "font_size": font_size, "lines": lines, "height": len(lines) * EXPLAINER_BODY_LINE_ADVANCE}


def _fit_body(draw, segs, start_y: int, floor_y: int):
    for size in range(EXPLAINER_BODY_SIZE, EXPLAINER_BODY_MIN_SIZE - 1, -1):
        report = _measure_body(draw, segs, size)
        if start_y + report["height"] <= floor_y:
            return report, False
    return _measure_body(draw, segs, EXPLAINER_BODY_MIN_SIZE), True


def _draw_explainer_body(draw, segs, divider_bottom: int, slide_id: str, qa_notes):
    start_y = divider_bottom + EXPLAINER_BODY_GAP
    floor_y = cl.FOOTER_SAFE - EXPLAINER_FOOTER_BUFFER
    report, overflow = _fit_body(draw, segs, start_y, floor_y)

    y = start_y
    lines_drawn = 0
    space_w = cl.mw(draw, " ", report["font"])
    for lwords in report["lines"]:
        if y + EXPLAINER_BODY_LINE_ADVANCE > floor_y:
            overflow = True
            break
        x = cl.BODY_L
        for idx, (word, col) in enumerate(lwords):
            draw.text((x, y), word, font=report["font"], fill=col)
            x += cl.mw(draw, word, report["font"])
            if idx < len(lwords) - 1:
                x += space_w
        y += EXPLAINER_BODY_LINE_ADVANCE
        lines_drawn += 1

    if overflow:
        raise ValueError(
            f"{slide_id}: body_standard copy does not fit the fixed editorial body zone at "
            f"{report['font_size']}px. Shorten the paragraph or split it across slides."
        )

    return {
        "start_y": start_y,
        "end_y": y,
        "font_size": report["font_size"],
        "line_advance": EXPLAINER_BODY_LINE_ADVANCE,
        "lines": len(report["lines"]),
        "lines_drawn": lines_drawn,
    }


def render_body_standard(slide: StorySlide, n: int, total: int, story: StoryPackage,
                          defaults: TemplateDefaults):
    require_fields(slide, "label", "headline_lines", "headline_colors", "body")
    qa_notes = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))

    # alpha_composite is required for the explainer-only compressed headline layers.
    if img.mode != "RGBA":
        img = img.convert("RGBA")
        draw = cl.ImageDraw.Draw(img)

    lines = slide.get("headline_lines") or []
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    line_count = max(1, len(lines))
    y0 = int(slide.get("headline_y0", EXPLAINER_Y0.get(line_count, EXPLAINER_Y0[4])))

    headline_report = _draw_standard_headline(draw, img, lines, colors, y0)
    divider_y = headline_report["bottom"] + EXPLAINER_HEADLINE_DIVIDER_GAP
    draw.rectangle([cl.L_MARGIN, divider_y, cl.W - cl.R_MARGIN, divider_y + cl.DIVIDER_H], fill=cl.PINK)
    divider_bottom = divider_y + cl.DIVIDER_H

    body_report = _draw_explainer_body(
        draw,
        body_segs(slide.get("body"), slide.slide_id),
        divider_bottom,
        slide.slide_id,
        qa_notes,
    )

    h_sizes = ",".join(str(item["font_size"]) for item in headline_report["lines"])
    h_scales = ",".join(f"{item['x_scale']:.2f}" for item in headline_report["lines"])
    qa_notes.append(
        f"{slide.slide_id}: headline target sizes {h_sizes}; horizontal scales {h_scales}; "
        f"body {body_report['font_size']}px/{body_report['line_advance']}px; "
        f"footer clearance {(cl.FOOTER_SAFE - EXPLAINER_FOOTER_BUFFER) - body_report['end_y']}px."
    )

    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img.convert("RGB"), qa_notes

def render_sources_slide(slide: StorySlide, n: int, total: int, story: StoryPackage,
                          defaults: TemplateDefaults):
    """
    Not present in carousel_lib.py as a dedicated function -- composed
    here from draw_top_bar + the same wrap/line-height primitives
    draw_body() uses internally. Closes a carousel out with a scannable
    source list (satisfies the 'sources' component called for in the
    build spec).
    """
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
        y += lh // 2  # gap between citations

    if dropped:
        qa_notes.append(
            f"sources_slide: {dropped} of {len(citations)} citation(s) did not fit "
            f"above the footer-safe zone and were not rendered. Split into another "
            f"sources_slide."
        )

    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", False)))
    return img, qa_notes
