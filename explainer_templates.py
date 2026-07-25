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

# --- Standard Explainer editorial layout constants (v3.8.4) ---
EXPLAINER_HEADLINE_RANGES = {
    1: (120, 210),
    2: (110, 198),
    3: (102, 186),
    4: (96, 176),
}
EXPLAINER_Y0 = {1: 170, 2: 170, 3: 178, 4: 186}
EXPLAINER_BODY_PREFERRED_SIZES = (35, 34, 33, 32)
EXPLAINER_BODY_MAX_W = cl.W - 156           # slightly shorter measure than default body
EXPLAINER_BODY_GAP = 28                      # fixed gap below divider
EXPLAINER_BODY_LINE_HEIGHT = 1.10            # tighter editorial leading
EXPLAINER_FOOTER_BUFFER = 26                 # extra clearance above footer-safe zone
EXPLAINER_HEAD_MAX_H = 390                   # keep interior headline compact


# --- Dedicated Standard Explainer helpers ---------------------------------
def _fit_standard_headline(
    draw, lines: Sequence[str], size_range: Tuple[int, int], max_h: int = EXPLAINER_HEAD_MAX_H
):
    """Return the largest headline font that fits.

    Unlike cl.fit_head(), this does not require short headlines to hit a
    width-fill threshold; if a large size fits, it is retained.
    """
    if not lines:
        raise ValueError("_fit_standard_headline() requires at least one line")
    lo, hi = size_range
    lo, hi = int(lo), int(hi)
    fallback = cl.lf(cl.BARLOW, lo)
    fallback_metrics = cl.measure_headline_block(draw, lines, fallback)
    for size in range(hi, lo - 1, -1):
        font = cl.lf(cl.BARLOW, size)
        metrics = cl.measure_headline_block(draw, lines, font)
        if metrics["width"] <= cl.HEAD_MAX_W and metrics["height"] <= max_h:
            return font, metrics, True
    return fallback, fallback_metrics, False


def _draw_standard_headline(
    draw,
    lines: Sequence[str],
    colors: Sequence[Tuple[int, int, int]],
    y0: int,
    size_range: Tuple[int, int],
) -> Dict[str, int]:
    font, metrics, fit_ok = _fit_standard_headline(draw, lines, size_range)
    color_list = list(colors or [])
    if len(color_list) < len(lines):
        color_list.extend([cl.WHITE] * (len(lines) - len(color_list)))

    y = int(round(y0))
    ink_bottom = y
    for idx, line in enumerate(lines):
        text = str(line)
        draw.text((cl.L_MARGIN, y), text, font=font, fill=color_list[idx], anchor="lt")
        line_h = metrics["line_heights"][idx]
        ink_bottom = max(ink_bottom, y + line_h)
        if idx < len(lines) - 1:
            y += line_h + metrics["line_gap"]

    descender_pad = max(6, round(font.size * cl.HEADLINE_DESCENDER_PAD_RATIO))
    return {
        "top": y0,
        "bottom": ink_bottom + descender_pad,
        "font_size": font.size,
        "fit_ok": int(fit_ok),
        "width": metrics["width"],
        "height": metrics["height"],
    }


def _measure_explainer_body(draw, segs, font_size: int, max_w: int = EXPLAINER_BODY_MAX_W):
    font = cached_lf(cl.BASK_REG, font_size)
    asc, desc = font.getmetrics()
    line_h = max(font_size + 2, int(round((asc + desc) * EXPLAINER_BODY_LINE_HEIGHT)))
    lines = cl.wrap_lines(draw, segs, font, max_w)
    block_h = len(lines) * line_h
    return {
        "font": font,
        "font_size": font_size,
        "line_height": line_h,
        "lines": lines,
        "height": block_h,
        "max_w": max_w,
    }


def _fit_explainer_body(draw, segs, start_y: int, floor_y: int):
    """Prefer a stable editorial size; only step down if copy would collide with footer."""
    for size in EXPLAINER_BODY_PREFERRED_SIZES:
        report = _measure_explainer_body(draw, segs, size)
        if start_y + report["height"] <= floor_y:
            return report, False
    report = _measure_explainer_body(draw, segs, EXPLAINER_BODY_PREFERRED_SIZES[-1])
    return report, True


def _draw_explainer_body(
    draw,
    segs,
    divider_bottom: int,
    slide_id: str,
    qa_notes: List[str],
) -> Dict[str, int]:
    start_y = divider_bottom + EXPLAINER_BODY_GAP
    floor_y = cl.FOOTER_SAFE - EXPLAINER_FOOTER_BUFFER
    left = cl.BODY_L
    report, overflow = _fit_explainer_body(draw, segs, start_y, floor_y)

    y = start_y
    lines_drawn = 0
    space_w = cl.mw(draw, " ", report["font"])
    for lwords in report["lines"]:
        if y + report["line_height"] > floor_y:
            overflow = True
            break
        x = left
        for idx, (word, col) in enumerate(lwords):
            draw.text((x, y), word, font=report["font"], fill=col)
            x += cl.mw(draw, word, report["font"])
            if idx < len(lwords) - 1:
                x += space_w
        y += report["line_height"]
        lines_drawn += 1

    if overflow:
        qa_notes.append(
            f"{slide_id}: explainer body overflowed the fixed editorial body zone; "
            f"rendered {lines_drawn} of {len(report['lines'])} wrapped lines at "
            f"{report['font_size']}px. Shorten copy or split the slide."
        )

    return {
        "start_y": start_y,
        "end_y": y,
        "font_size": report["font_size"],
        "line_height": report["line_height"],
        "lines": len(report["lines"]),
        "lines_drawn": lines_drawn,
        "overflow": int(overflow),
    }


def render_body_standard(slide: StorySlide, n: int, total: int, story: StoryPackage,
                          defaults: TemplateDefaults):
    require_fields(slide, "label", "headline_lines", "headline_colors", "body")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))

    lines = slide.get("headline_lines") or []
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    line_count = max(1, len(lines))

    base_sr = tuple(slide.get("headline_range", defaults.headline_range))
    explainer_sr = EXPLAINER_HEADLINE_RANGES.get(line_count, EXPLAINER_HEADLINE_RANGES[4])
    sr = (max(base_sr[0], explainer_sr[0]), max(base_sr[1], explainer_sr[1]))
    y0 = int(slide.get("headline_y0", EXPLAINER_Y0.get(line_count, EXPLAINER_Y0[4])))

    headline_report = _draw_standard_headline(draw, lines, colors, y0, sr)
    divider_bottom = cl.draw_divider(draw, headline_report["bottom"], gap=26)
    body_report = _draw_explainer_body(
        draw,
        body_segs(slide.get("body"), slide.slide_id),
        divider_bottom,
        slide.slide_id,
        qa_notes,
    )

    if not headline_report["fit_ok"]:
        qa_notes.append(
            f"{slide.slide_id}: headline hit the minimum explainer range and may need copy tightening."
        )

    # Optional diagnostics for local smoke testing; harmless if ignored upstream.
    qa_notes.append(
        f"{slide.slide_id}: headline {headline_report['font_size']}px, body {body_report['font_size']}px, "
        f"footer clearance {max(0, (cl.FOOTER_SAFE - EXPLAINER_FOOTER_BUFFER) - body_report['end_y'])}px."
    )

    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes


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
