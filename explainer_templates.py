"""
explainer_templates.py
JenniWren Carousel Production Pipeline -- COMP family (interior slides)

body_standard is the default interior slide (headline + paragraph).
sources_slide closes a carousel with a numbered citation list; it has
no dedicated carousel_lib.py function, so it's composed here from the
same low-level primitives (wrap_lines, lf, mw) draw_body() itself uses
internally -- see its docstring for why a single draw_body() call
wasn't the right fit for a numbered list.
"""

from __future__ import annotations

import logging
from typing import List

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from perf import cached_lf
from story_loader import StorySlide, StoryPackage
from template_shared import colors_from_names, body_segs, require_fields, draw_body_checked

logger = logging.getLogger("jenniwren.templates")


def _draw_standard_body(draw, segs, divider_bottom: int, requested_size: int,
                        slide_id: str, qa_notes: List[str]):
    """Render standard-explainer body copy with compact editorial leading.

    The old shared body renderer used a 44 px floor and 1.32 leading, which
    produced oversized paragraphs with excessive vertical gaps. This template
    uses a 40 px preferred size, may fit down to 36 px, and uses 1.14 leading.
    It never silently truncates: overflow is reported in qa_notes.
    """
    preferred = min(int(requested_size or 40), 40)
    preferred = max(36, preferred)
    max_w = cl.W - cl.BODY_L - cl.BODY_R
    body_top = int(divider_bottom + 30)
    available = cl.FOOTER_SAFE - body_top

    chosen = None
    for size in range(preferred, 35, -1):
        font = cached_lf(cl.BASK_REG, size)
        asc, desc = font.getmetrics()
        line_h = max(size + 8, int((asc + desc) * 1.14))
        wrapped = cl.wrap_lines(draw, segs, font, max_w)
        needed = len(wrapped) * line_h
        if needed <= available:
            chosen = (font, line_h, wrapped, size)
            break

    if chosen is None:
        size = 36
        font = cached_lf(cl.BASK_REG, size)
        asc, desc = font.getmetrics()
        line_h = max(size + 8, int((asc + desc) * 1.14))
        wrapped = cl.wrap_lines(draw, segs, font, max_w)
        chosen = (font, line_h, wrapped, size)
        qa_notes.append(
            f"{slide_id}: body copy exceeds the standard explainer safe area at 36 px; shorten copy."
        )

    font, line_h, wrapped, size = chosen
    y = body_top
    space_w = cl.mw(draw, " ", font)
    for words in wrapped:
        if y + line_h > cl.FOOTER_SAFE:
            break
        x = cl.BODY_L
        for i, (word, color) in enumerate(words):
            draw.text((x, y), word, font=font, fill=color)
            x += cl.mw(draw, word, font)
            if i < len(words) - 1:
                x += space_w
        y += line_h
    return y, size


def render_body_standard(slide: StorySlide, n: int, total: int, story: StoryPackage,
                          defaults: TemplateDefaults):
    require_fields(slide, "label", "headline_lines", "headline_colors", "body")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))
    lines = slide.get("headline_lines")
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)

    # Standard explainer headlines should read with nearly cover-level authority.
    # Manual lines remain fixed; short headlines no longer collapse to the minimum.
    configured = tuple(slide.get("headline_range", defaults.headline_range))
    sr = (max(82, int(configured[0])), max(190, int(configured[1])))
    line_count = len(lines or [])
    y0 = 168 if line_count <= 1 else (160 if line_count == 2 else 154)
    max_head_h = 330 if line_count <= 2 else 390
    glyph_bottom = cl.draw_headline_largest(draw, lines, colors, y0, sr, max_h=max_head_h)

    # Tight but clear relationship: headline -> divider -> body.
    divider_bottom = cl.draw_divider(draw, glyph_bottom, gap=18)
    requested_body_size = int(slide.get("body_size", min(defaults.body_size, 40)))
    _draw_standard_body(
        draw,
        body_segs(slide.get("body"), slide.slide_id),
        divider_bottom,
        requested_body_size,
        slide.slide_id,
        qa_notes,
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
