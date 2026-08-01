"""
document_templates.py
JenniWren Carousel Production Pipeline -- COMP family (evidence)
"""

from __future__ import annotations

import re

from typing import List

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from story_loader import StorySlide, StoryPackage
from template_shared import colors_from_names, require_fields


def render_document_card(slide: StorySlide, n: int, total: int, story: StoryPackage,
                         defaults: TemplateDefaults):
    """Evidence — Document Card v3.8.34."""
    require_fields(slide, "label", "doc_lines", "headline_lines", "headline_colors")
    qa_notes: List[str] = []

    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total,
                    big=bool(slide.get("big_label", False)))

    card_top = 122
    requested_h = int(slide.get("doc_card_h", 472) or 472)
    highlight_idxs = set(slide.get("doc_highlight", []) or [])

    card_bottom = cl.draw_document_card(
        draw, img, slide.get("doc_lines") or [], highlight_idxs, card_top,
        card_h=requested_h,
        annotation=bool(slide.get("doc_annotation", True)),
    )

    headline_lines = list(slide.get("headline_lines") or [])
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    default_range = tuple(getattr(defaults, "document_headline_range", (82, 150)))
    scaled_range = (
        max(60, int(default_range[0] * 0.90)),
        max(72, int(default_range[1] * 0.90)),
    )
    sr = tuple(slide.get("headline_range", scaled_range))

    headline_top = card_bottom + 18
    headline_bottom = cl.draw_headline(draw, headline_lines, colors, headline_top, sr)
    divider_bottom = cl.draw_divider(draw, headline_bottom, gap=6)

    def normalize_body_segments(value):
        if not value:
            return []
        segs = []

        def add(text, color="white"):
            text = str(text or "").strip()
            if text:
                segs.append((text, cl.PINK if str(color).lower() == "pink" else cl.WHITE))

        def parse_inline(text, base_color="white"):
            text = str(text or "")
            pattern = re.compile(r"(<pink>.*?</pink>|\[\[pink:.*?\]\])", re.I | re.S)
            pos = 0
            for match in pattern.finditer(text):
                if match.start() > pos:
                    add(text[pos:match.start()], base_color)
                token = match.group(0)
                add(token[6:-7] if token.lower().startswith("<pink>") else token[7:-2], "pink")
                pos = match.end()
            if pos < len(text):
                add(text[pos:], base_color)

        def walk(node, inherited="white"):
            if node is None:
                return
            if isinstance(node, str):
                parse_inline(node, inherited)
            elif isinstance(node, dict):
                color = str(node.get("color") or inherited).lower()
                if "text" in node:
                    parse_inline(node.get("text"), color)
                else:
                    for key in ("segments", "content", "children", "body"):
                        if key in node:
                            walk(node.get(key), color)
                            break
            elif isinstance(node, (list, tuple)):
                if len(node) == 2 and isinstance(node[0], str) and isinstance(node[1], str):
                    parse_inline(node[0], node[1])
                else:
                    for child in node:
                        walk(child, inherited)
            else:
                parse_inline(str(node), inherited)

        walk(value)
        return segs

    body_segments = normalize_body_segments(slide.get("body") or slide.get("supporting_body"))
    if body_segments:
        body_top = divider_bottom + 18
        max_bottom = cl.FOOTER_SAFE - 8
        max_w = cl.W - cl.L_MARGIN - cl.R_MARGIN

        chosen = None
        for size in range(min(42, int(slide.get("body_size", 40) or 40)), 37, -1):
            font = cl.lf(cl.BASK_REG, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 1.22)
            wrapped = cl.wrap_lines(draw, body_segments, font, max_w)
            if wrapped and len(wrapped) <= 4 and body_top + lh * len(wrapped) <= max_bottom:
                chosen = (font, wrapped, lh)
                break

        if chosen is None:
            font = cl.lf(cl.BASK_REG, 38)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 1.20)
            chosen = (font, cl.wrap_lines(draw, body_segments, font, max_w), lh)

        font, wrapped, lh = chosen
        max_lines_fit = max(0, int((max_bottom - body_top) // max(1, lh)))
        visible = wrapped[:max_lines_fit]
        if len(visible) < len(wrapped):
            qa_notes.append("document_card supporting body exceeded the available space above the footer.")

        y = body_top
        space_w = cl.mw(draw, " ", font)
        for line in visible:
            x = cl.L_MARGIN
            for i, (word, fill) in enumerate(line):
                draw.text((x, y), word, font=font, fill=fill)
                x += cl.mw(draw, word, font)
                if i < len(line) - 1:
                    x += space_w
            y += lh

    cl.draw_footer(draw, brand_name=story.brand_footer,
                   arrow=bool(slide.get("arrow", True)))
    return img, qa_notes


