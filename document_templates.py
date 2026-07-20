"""
document_templates.py
JenniWren Carousel Production Pipeline -- COMP family (evidence)
"""

from __future__ import annotations

from typing import List

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from story_loader import StorySlide, StoryPackage
from template_shared import colors_from_names, require_fields


def render_document_card(slide: StorySlide, n: int, total: int, story: StoryPackage,
                          defaults: TemplateDefaults):
    require_fields(slide, "label", "doc_lines", "headline_lines", "headline_colors")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))
    card_h = slide.get("doc_card_h", defaults.doc_card_h)
    highlight_idxs = set(slide.get("doc_highlight", []))
    card_bottom = cl.draw_document_card(
        draw, img, slide.get("doc_lines"), highlight_idxs, 140,
        card_h=card_h, annotation=bool(slide.get("doc_annotation", True)),
    )
    lines = slide.get("headline_lines")
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    sr = tuple(slide.get("headline_range", defaults.document_headline_range))
    gb = cl.draw_headline(draw, lines, colors, card_bottom + 50, sr)
    cl.draw_divider(draw, gb)
    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes
