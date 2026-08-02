"""
data_templates.py
JenniWren Carousel Production Pipeline -- DATA family

Statistic-driven templates. Timeline lives in its own module
(timeline_templates.py) since it has meaningfully different layout
logic (a vertical dated sequence, not a single number or grid).
"""

from __future__ import annotations

from typing import List

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from story_loader import StorySlide, StoryPackage
from template_shared import colors_from_names, require_fields


def render_stat_callout(slide: StorySlide, n: int, total: int, story: StoryPackage,
                         defaults: TemplateDefaults):
    require_fields(slide, "label", "stat_text", "stat_label")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))
    pill_bot = cl.draw_stat_callout(
        draw,
        slide.get("stat_text"),
        slide.get("stat_label"),
        y0=slide.get("stat_y0", 200),
        stat_size=slide.get("stat_size"),
        stat_range=tuple(slide.get("stat_range", defaults.stat_range)),
    )
    y = pill_bot
    headline_lines = slide.get("headline_lines")
    if headline_lines:
        colors = colors_from_names(slide.get("headline_colors", ["white"] * len(headline_lines)), slide.slide_id)
        sr = tuple(slide.get("headline_range", defaults.stat_headline_range))
        y = cl.draw_headline(draw, headline_lines, colors, y + 40, sr)
    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes


def render_stat_grid(slide: StorySlide, n: int, total: int, story: StoryPackage,
                      defaults: TemplateDefaults):
    require_fields(slide, "label", "stat_items")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))
    y0 = cl.HEAD_Y
    headline_lines = slide.get("headline_lines")
    if headline_lines:
        colors = colors_from_names(slide.get("headline_colors", ["white"] * len(headline_lines)), slide.slide_id)
        sr = tuple(slide.get("headline_range", defaults.grid_headline_range))
        y0 = cl.draw_headline(draw, headline_lines, colors, cl.HEAD_Y, sr) + 60
    items = [tuple(item) for item in slide.get("stat_items")]
    grid_bottom = cl.draw_stat_grid(
        draw, items, y0,
        cols=slide.get("grid_cols", defaults.grid_cols),
        cell_h=slide.get("grid_cell_h", defaults.grid_cell_h),
    )
    if grid_bottom > cl.FOOTER_SAFE:
        qa_notes.append(
            f"stat_grid extends to y={grid_bottom}, past the footer-safe line "
            f"(y={cl.FOOTER_SAFE}) -- reduce grid_cell_h or item count."
        )
    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes
