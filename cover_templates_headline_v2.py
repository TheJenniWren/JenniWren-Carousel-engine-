"""
cover_templates.py
JenniWren Carousel Production Pipeline -- COV family

Cover-slide templates: the first slide a viewer sees. All three
compose directly from carousel_lib.py's primitives; see
template_shared.py for the shared helpers and ARCHITECTURE.md for why
this file exists as a split-out module.

v3.7.2
------
Controlled template-family upgrade, not a redesign. Every template ID,
public function, function signature, and editorial identity is
unchanged. Two carousel_lib.py v3.7.2 additions are applied here, both
restrained and additive:

* cl.optical_offset_headline() nudges the headline's *default* start
  position a few px so large display type reads as centered rather than
  sitting slightly low. It is never applied when a slide explicitly
  sets its own headline_y0 - an explicit value is left exactly as the
  writer/designer set it.
* cl.footer_clearance() flags (via the existing qa_notes mechanism -
  the same list draw_body_checked() already reports into) any slide
  whose divider ends past FOOTER_SAFE, i.e. at real risk of colliding
  with the footer wordmark/arrow, for human review before publish.
  This is detection, not silent correction, matching how draw_body()'s
  own footer-collision risk is already handled in this codebase.

Nothing else changes. fit_head()'s tuned 84-96%-width-fill search,
draw_headline(), draw_divider(), and draw_body() (via draw_body_checked)
are called exactly as in 3.7.1. text_fitting_engine.py's semantic/
editorial fitting is intentionally not introduced for headline or quote
text here: headline_lines/quote_lines are pre-authored, already-broken
lines (not auto-wrapped), and swapping the tuned fit_head() search for
the editorial-scoring engine would change font sizes and line treatment
across every cover family, not fix anything - exactly what the upgrade
brief asks us not to do.
"""

from __future__ import annotations

from typing import List

from renderer_imports import carousel_lib as cl
from headline_engine_v2 import render_headline, diagnostic_note
from production_config import TemplateDefaults
from story_loader import StorySlide, StoryPackage
from template_shared import (
    colors_from_names, body_segs, require_fields, draw_body_checked, resolve_image,
)

# Sentinel so we can tell "slide didn't set headline_y0" apart from
# "slide explicitly set headline_y0" - the optical nudge below only
# ever applies to the computed default, never to an explicit value.
_UNSET = object()


def _headline_block_height(draw, lines, sr) -> int:
    """
    Height (px) of the headline block cl.draw_headline() will render for
    `lines` at the size cl.fit_head() selects for `sr`. Reuses
    cl.fit_head() itself - the public, tuned size-search - rather than
    re-implementing font-size selection; only reads metrics off the font
    it returns, mirroring the same block-height formula draw_headline()
    already uses internally.
    """
    font = cl.fit_head(draw, lines, sr)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 0.88)
    return lh * (len(lines) - 1) + (asc + desc)


def _optical_headline_y0(draw, lines, sr, base_y0: int, zone_height: int) -> int:
    """Small, capped upward nudge on a *default* headline start position.
    Magnitude is entirely governed by cl.optical_offset_headline() itself
    (never more than a few percent of the available zone height)."""
    block_h = _headline_block_height(draw, lines, sr)
    return base_y0 + cl.optical_offset_headline(block_h, zone_height)


def _flag_footer_risk(y_cursor: int, label: str, qa_notes: List[str]) -> None:
    """Append a QA note - never alters rendering - if content drawn up to
    y_cursor has crossed FOOTER_SAFE and risks colliding with the footer
    wordmark/arrow drawn by cl.draw_footer(). Message format matches
    template_shared.draw_body_checked()'s own qa_notes entries: plain
    text, no slide-id prefix, since qa_notes is already scoped to a
    single slide's render call by the caller."""
    if not cl.footer_clearance(y_cursor):
        overshoot = y_cursor - cl.FOOTER_SAFE
        qa_notes.append(
            f"{label} ends {overshoot}px past FOOTER_SAFE — "
            f"check for collision with footer wordmark/arrow."
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

    explicit_y0 = slide.get("headline_y0", _UNSET)
    region_top = cl.HEAD_Y if explicit_y0 is _UNSET else int(explicit_y0)
    region_bottom = region_top + int(slide.get("headline_max_height", cl.HEAD_MAX_H))

    gb, headline_report = render_headline(
        draw,
        lines=lines,
        colors=colors,
        font_path=cl.BARLOW,
        region=(cl.L_MARGIN, region_top, cl.W - cl.R_MARGIN, region_bottom),
        min_size=int(sr[0]),
        max_size=int(sr[1]),
        line_height_ratio=float(slide.get("headline_line_height", cl.LINE_H_RATIO)),
        align=slide.get("headline_align", "left"),
        balance=slide.get("headline_balance", "optical"),
        default_color=cl.WHITE,
    )
    note = diagnostic_note(f"{slide.slide_id} headline", headline_report)
    if note:
        qa_notes.append(note)

    db = cl.draw_divider(draw, gb)
    _flag_footer_risk(db, "divider", qa_notes)

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

    explicit_y0 = slide.get("headline_y0", _UNSET)
    if explicit_y0 is _UNSET:
        y0 = _optical_headline_y0(draw, lines, sr, cl.HEAD_Y, cl.HEAD_MAX_H)
    else:
        y0 = explicit_y0

    gb = cl.draw_headline(draw, lines, colors, y0, sr)
    db = cl.draw_divider(draw, gb)
    _flag_footer_risk(db, "divider", qa_notes)

    attribution = slide.get("attribution")
    if attribution:
        draw_body_checked(draw, [(f"\u2014 {attribution}", cl.WHITE)], db,
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

    explicit_y0 = slide.get("headline_y0", _UNSET)
    if explicit_y0 is _UNSET:
        base_y0 = cl.H - defaults.photo_headline_y0_offset
        y0 = _optical_headline_y0(draw, lines, sr, base_y0, defaults.photo_headline_y0_offset)
    else:
        y0 = explicit_y0

    gb = cl.draw_headline(draw, lines, colors, y0, sr)
    db = cl.draw_divider(draw, gb)
    _flag_footer_risk(db, "divider", qa_notes)

    cl.draw_footer(draw, brand_name=story.brand_footer, arrow=bool(slide.get("arrow", True)))
    return img, qa_notes
