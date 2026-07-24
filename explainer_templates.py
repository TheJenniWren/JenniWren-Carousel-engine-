"""
explainer_templates.py
JenniWren Studio 3.8 — COMP family (interior slides)

The body_standard template now uses the shared Studio 3.8 headline
subsystem in carousel_lib.py. Public renderer names and signatures remain
unchanged. sources_slide retains its established citation rendering.
"""

from __future__ import annotations

import logging
from typing import Any, List, Sequence, Tuple

from renderer_imports import carousel_lib as cl
from production_config import TemplateDefaults
from perf import cached_lf
from story_loader import StorySlide, StoryPackage
from template_shared import colors_from_names, body_segs, require_fields, draw_body_checked

logger = logging.getLogger("jenniwren.templates")


def _headline_inputs(
    slide: StorySlide,
    defaults: TemplateDefaults,
) -> Tuple[Sequence[str], Sequence[Any], Tuple[int, int]]:
    """Read and validate an editorially line-broken interior headline."""
    lines = slide.get("headline_lines")
    if isinstance(lines, str):
        lines = lines.split("\n")
    if not isinstance(lines, (list, tuple)) or not lines:
        raise ValueError(f"{slide.slide_id}: headline_lines must contain at least one line.")
    if any(not str(line).strip() for line in lines):
        raise ValueError(f"{slide.slide_id}: headline_lines may not contain blank lines.")

    colors = slide.get("headline_colors") or []
    if isinstance(colors, str):
        colors = [colors]
    if not isinstance(colors, (list, tuple)):
        raise ValueError(f"{slide.slide_id}: headline_colors must be a list.")

    raw_range = slide.get("headline_range", defaults.headline_range)
    if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
        raise ValueError(f"{slide.slide_id}: headline_range must be [minimum, maximum].")
    size_range = (int(raw_range[0]), int(raw_range[1]))
    if size_range[0] <= 0 or size_range[1] < size_range[0]:
        raise ValueError(f"{slide.slide_id}: invalid headline_range {size_range}.")

    return [str(line) for line in lines], colors, size_range


def _draw_headline_v38(
    draw,
    *,
    slide: StorySlide,
    lines: Sequence[str],
    colors: Sequence[Any],
    y0: int,
    size_range: Tuple[int, int],
    qa_notes: List[str],
) -> int:
    """Render and transfer Headline Engine v2 diagnostics into slide QA."""
    cl.clear_headline_diagnostics()
    bottom = cl.draw_headline(draw, lines, colors, int(y0), size_range)

    for note in cl.get_headline_qa_notes(clear=True):
        qa_notes.append(f"{slide.slide_id}: {note}")

    diagnostics = cl.get_last_headline_diagnostics()
    if diagnostics and diagnostics.get("used_minimum_size") and diagnostics.get("fits"):
        qa_notes.append(
            f"{slide.slide_id}: headline fit at the minimum configured size "
            f"({diagnostics['metrics']['font_size']}px); review copy length and line breaks."
        )
    return bottom


def render_body_standard(
    slide: StorySlide,
    n: int,
    total: int,
    story: StoryPackage,
    defaults: TemplateDefaults,
):
    require_fields(slide, "label", "headline_lines", "headline_colors", "body")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(
        draw,
        slide.get("label"),
        n,
        total,
        big=bool(slide.get("big_label", False)),
    )

    lines, raw_colors, size_range = _headline_inputs(slide, defaults)
    colors = colors_from_names(raw_colors, slide.slide_id)
    headline_y0 = int(slide.get("headline_y0", cl.HEAD_Y))
    headline_bottom = _draw_headline_v38(
        draw,
        slide=slide,
        lines=lines,
        colors=colors,
        y0=headline_y0,
        size_range=size_range,
        qa_notes=qa_notes,
    )

    divider_bottom = cl.draw_divider(draw, headline_bottom)
    draw_body_checked(
        draw,
        body_segs(slide.get("body"), slide.slide_id),
        divider_bottom,
        slide.get("body_size", defaults.body_size),
        slide.slide_id,
        qa_notes,
    )
    cl.draw_footer(
        draw,
        brand_name=story.brand_footer,
        arrow=bool(slide.get("arrow", True)),
    )
    return img, qa_notes


def render_sources_slide(
    slide: StorySlide,
    n: int,
    total: int,
    story: StoryPackage,
    defaults: TemplateDefaults,
):
    """Render a numbered source list using the established body primitives."""
    require_fields(slide, "citations")
    qa_notes: List[str] = []
    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label", "SOURCES"), n, total)

    fsz = max(slide.get("body_size", defaults.sources_body_size), cl.BODY_MIN_SIZE)
    font = cached_lf(cl.BASK_REG, fsz)
    asc, desc = font.getmetrics()
    line_height = int((asc + desc) * 1.32)
    max_width = cl.W - cl.BODY_L - cl.BODY_R
    y = cl.HEAD_Y
    citations = slide.get("citations")
    dropped = 0

    for index, citation in enumerate(citations, start=1):
        entry_segments = [(f"{index}. {cl.break_urls(citation)}", cl.WHITE)]
        wrapped = cl.wrap_lines(draw, entry_segments, font, max_width)
        citation_dropped = False

        for line_words in wrapped:
            if y + line_height > cl.FOOTER_SAFE:
                citation_dropped = True
                break
            x = cl.BODY_L
            space_width = cl.mw(draw, " ", font)
            for word_index, (word, color) in enumerate(line_words):
                draw.text((x, y), word, font=font, fill=color)
                x += cl.mw(draw, word, font)
                if word_index < len(line_words) - 1:
                    x += space_width
            y += line_height

        if citation_dropped:
            dropped += 1
        y += line_height // 2

    if dropped:
        qa_notes.append(
            f"sources_slide: {dropped} of {len(citations)} citation(s) did not fit "
            "above the footer-safe zone and were not rendered. Split the sources "
            "across another sources_slide."
        )

    cl.draw_footer(
        draw,
        brand_name=story.brand_footer,
        arrow=bool(slide.get("arrow", False)),
    )
    return img, qa_notes
