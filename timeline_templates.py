"""
timeline_templates.py
JenniWren Carousel Production Pipeline -- DATA family (timeline)
"""

from __future__ import annotations

from typing import List

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from story_loader import StorySlide, StoryPackage
from template_shared import colors_from_names, require_fields


def render_timeline(slide: StorySlide, n: int, total: int, story: StoryPackage,
                     defaults: TemplateDefaults):
    require_fields(slide, "label", "headline_lines", "headline_colors", "timeline_entries")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))
    lines = slide.get("headline_lines")
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    sr = tuple(slide.get("headline_range", defaults.headline_range))
    gb = cl.draw_headline(draw, lines, colors, cl.HEAD_Y, sr)
    tl_bottom = cl.draw_timeline(draw, slide.get("timeline_entries"), gb + 60)
    if tl_bottom > cl.FOOTER_SAFE:
        qa_notes.append(
            f"timeline extends to y={tl_bottom}, past the footer-safe line "
            f"(y={cl.FOOTER_SAFE}) -- trim entries or shorten descriptions."
        )
    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes
