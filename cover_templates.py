"""
cover_templates.py
JenniWren Carousel Production Pipeline -- COV family

Cover-slide templates: the first slide a viewer sees. All three
compose directly from carousel_lib.py's primitives; see
template_shared.py for the shared helpers and ARCHITECTURE.md for why
this file exists as a split-out module.
"""

from __future__ import annotations

from typing import List

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from story_loader import StorySlide, StoryPackage
from template_shared import (
    colors_from_names, body_segs, require_fields, draw_body_checked, resolve_image,
)


def render_cover_headline(slide: StorySlide, n: int, total: int, story: StoryPackage,
                           defaults: TemplateDefaults):
    require_fields(slide, "label", "headline_lines", "headline_colors")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))
    lines = slide.get("headline_lines")
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    sr = tuple(slide.get("headline_range", defaults.headline_range))
    gb = cl.draw_headline(draw, lines, colors, cl.HEAD_Y, sr)
    db = cl.draw_divider(draw, gb)
    body = slide.get("body")
    if body:
        draw_body_checked(draw, body_segs(body, slide.slide_id), db,
                           slide.get("body_size", defaults.body_size), slide.slide_id, qa_notes)
    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes


def render_quote_lead(slide: StorySlide, n: int, total: int, story: StoryPackage,
                       defaults: TemplateDefaults):
    require_fields(slide, "label", "quote_lines", "quote_colors", "attribution")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))
    lines = slide.get("quote_lines")
    colors = colors_from_names(slide.get("quote_colors"), slide.slide_id)
    sr = tuple(slide.get("headline_range", defaults.headline_range))
    gb = cl.draw_headline(draw, lines, colors, cl.HEAD_Y, sr)
    db = cl.draw_divider(draw, gb)
    draw_body_checked(draw, [(f"\u2014 {slide.get('attribution')}", cl.WHITE)], db,
                       defaults.quote_attribution_size, slide.slide_id, qa_notes)
    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes


def render_photo_headline(slide: StorySlide, n: int, total: int, story: StoryPackage,
                           defaults: TemplateDefaults):
    require_fields(slide, "label", "image", "headline_lines", "headline_colors")
    qa_notes: List[str] = []
    image_path = resolve_image(slide, story)
    style = slide.get("photo_style", "fade")
    if style == "story":
        img, draw = cl.new_photo_story_canvas(str(image_path))
    else:
        img, draw = cl.new_photo_fade_canvas(
            str(image_path),
            fade_edge=slide.get("fade_edge", defaults.photo_fade_edge),
            fade_start=slide.get("fade_start", defaults.photo_fade_start),
        )
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))
    lines = slide.get("headline_lines")
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    sr = tuple(slide.get("headline_range", defaults.headline_range))
    y0 = slide.get("headline_y0", cl.H - defaults.photo_headline_y0_offset)
    gb = cl.draw_headline(draw, lines, colors, y0, sr)
    cl.draw_divider(draw, gb)
    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes
