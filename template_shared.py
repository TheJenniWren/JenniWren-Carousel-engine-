"""
template_shared.py
JenniWren Carousel Production Pipeline

Helpers shared by every template family module (cover_templates.py,
data_templates.py, timeline_templates.py, comparison_templates.py,
document_templates.py, explainer_templates.py). Pulled out of the old
monolithic templates.py so each family module only imports what it
actually composes slides from.

Every function here was written directly against carousel_lib.py's
verified signatures -- see ARCHITECTURE.md for why that matters and
what NOT to copy from (`cov templates.py`).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Tuple

from renderer_imports import carousel_lib as cl
from perf import cached_lf
from story_loader import StorySlide, StoryPackage

logger = logging.getLogger("jenniwren.templates")

COLOR_MAP = {"white": cl.WHITE, "pink": cl.PINK}


class TemplateError(Exception):
    """Raised when a slide can't be composed against its template."""


def colors_from_names(names: List[str], slide_id: str) -> List[Tuple[int, int, int]]:
    out = []
    for n in names:
        key = str(n).lower()
        if key not in COLOR_MAP:
            raise TemplateError(
                f"Slide '{slide_id}': unknown color '{n}' -- only 'white' and "
                f"'pink' are permitted by the brand palette (DESIGN_RULES.md Section 2)."
            )
        out.append(COLOR_MAP[key])
    return out


def body_segs(body: List[Dict[str, str]], slide_id: str) -> List[Tuple[str, Tuple[int, int, int]]]:
    segs = []
    for seg in body:
        text = seg.get("text", "")
        color = colors_from_names([seg.get("color", "white")], slide_id)[0]
        segs.append((cl.break_urls(text), color))
    return segs


def require_fields(slide: StorySlide, *fields: str) -> None:
    missing = [f for f in fields if slide.get(f) in (None, "", [])]
    if missing:
        raise TemplateError(
            f"Slide '{slide.slide_id}' (template '{slide.template}') is missing "
            f"required field(s): {', '.join(missing)}"
        )


def draw_body_checked(
    draw, segs: List[Tuple[str, Tuple[int, int, int]]], ty: int, fsz: int,
    slide_id: str, qa_notes: List[str],
) -> int:
    """
    Wraps cl.draw_body() with a truncation check. carousel_lib.draw_body
    silently stops drawing once text would cross FOOTER_SAFE (documented
    in its own docstring as a known footgun) -- this reproduces its exact
    wrap/line-height math *before* calling it so we can tell, after the
    real draw call, whether fewer lines were drawn than the copy needed.
    Does not change draw_body's behavior; only observes it.

    Performance note: this necessarily wraps the text twice (once here
    to know the expected line count, once inside draw_body() itself,
    which recomputes the wrap internally and isn't exposed as a
    separate step). That duplication is small and bounded -- one extra
    wrap_lines() call per body-bearing slide -- and the alternative
    (skip the precheck) would mean silently shipping clipped copy, which
    is the exact failure mode this pipeline exists to catch. Not
    optimized away; see CHANGELOG.md.
    """
    fsz = max(fsz, cl.BODY_MIN_SIZE)
    font = cached_lf(cl.BASK_REG, fsz)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.32)
    max_w = cl.W - cl.BODY_L - cl.BODY_R
    expected_lines = len(cl.wrap_lines(draw, segs, font, max_w))

    y_end = cl.draw_body(draw, segs, ty, fsz=fsz)

    lines_drawn = round((y_end - (ty + cl.BODY_GAP)) / lh) if lh else expected_lines
    if lines_drawn < expected_lines:
        qa_notes.append(
            f"body text truncated: {expected_lines - lines_drawn} of "
            f"{expected_lines} wrapped line(s) did not fit above the footer-safe zone."
        )
    return y_end


def resolve_image(slide: StorySlide, story: StoryPackage, field_name: str = "image") -> Path:
    rel = slide.get(field_name)
    if not rel:
        raise TemplateError(f"Slide '{slide.slide_id}' is missing required field: {field_name}")
    path = story.resolve_image(rel)
    if not path.exists():
        raise TemplateError(f"Slide '{slide.slide_id}' references missing image: {path}")
    return path
