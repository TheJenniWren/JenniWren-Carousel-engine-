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


def render_body_standard(slide: StorySlide, n: int, total: int, story: StoryPackage,
                          defaults: TemplateDefaults):
    """Production-safe standard explainer with measured, content-driven spacing."""
    require_fields(slide, "label", "headline_lines", "headline_colors", "body")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))

    lines = list(slide.get("headline_lines") or [])
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    headline_range = tuple(slide.get("headline_range", (72, 150)))

    headline_report = cl.draw_interior_headline(
        draw,
        lines,
        colors,
        sz_range=headline_range,
    )
    if not headline_report["fit_ok"]:
        qa_notes.append(
            f"{slide.slide_id}: headline did not fit the standard explainer field "
            f"at the minimum configured size ({headline_range[0]}px). Rewrite or "
            f"add a manual line break."
        )

    body_report = cl.draw_interior_body(
        draw,
        body_segs(slide.get("body"), slide.slide_id),
        headline_report["divider_bottom"],
        preferred_size=slide.get("body_size", defaults.body_size),
        min_size=slide.get("body_min_size", cl.INTERIOR_BODY_MIN_SIZE),
    )
    if not body_report["fit_ok"]:
        qa_notes.append(
            f"{slide.slide_id}: body copy requires {body_report['required_height']}px "
            f"but only {body_report['available_height']}px is available above the "
            f"footer-safe zone. Shorten the copy or split it across slides."
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
