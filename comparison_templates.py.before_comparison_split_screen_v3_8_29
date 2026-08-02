"""
comparison_templates.py
JenniWren Carousel Production Pipeline -- COMP family (emphasis/comparison)

call_block is the one COMP-family template built so far: a full-width
highlighted statement bar used to land a contrast or a hard claim. If
a true two-panel "promise vs. reality" comparison template gets built
against carousel_lib.py later, it belongs here alongside call_block.
"""

from __future__ import annotations

from typing import List

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from story_loader import StorySlide, StoryPackage
from template_shared import colors_from_names, body_segs, require_fields, draw_body_checked


def render_call_block(slide: StorySlide, n: int, total: int, story: StoryPackage,
                       defaults: TemplateDefaults):
    require_fields(slide, "label", "call_text")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))
    y = cl.HEAD_Y
    headline_lines = slide.get("headline_lines")
    if headline_lines:
        colors = colors_from_names(slide.get("headline_colors", ["white"] * len(headline_lines)), slide.slide_id)
        sr = tuple(slide.get("headline_range", defaults.call_headline_range))
        y = cl.draw_headline(draw, headline_lines, colors, cl.HEAD_Y, sr) + 50
    y = cl.draw_call_block(draw, slide.get("call_text"), y,
                            fsz=slide.get("call_size", defaults.call_block_size))
    body = slide.get("body")
    if body:
        draw_body_checked(draw, body_segs(body, slide.slide_id), y + 20,
                           slide.get("body_size", defaults.body_size), slide.slide_id, qa_notes)
    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes
