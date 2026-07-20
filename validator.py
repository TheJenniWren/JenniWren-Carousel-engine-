"""
validator.py
JenniWren Carousel Production Pipeline

Pre-render validation. Everything here can be checked WITHOUT drawing
a single pixel, so a bad story package fails fast with a clear report
instead of dying halfway through a render loop.

Checks performed (per the build spec):
  - required fields per template
  - missing images
  - missing citations
  - invalid template IDs
  - invalid component references (unrecognized fields on a slide)
  - maximum copy lengths
  - brand compliance (palette, minimum pink-line rule)
  - overflow risk (headline narrowness + body text truncation risk)

Overflow/narrowness checks reuse carousel_lib.py's own measurement
functions (max_sz, wrap_lines) rather than re-implementing font-metrics
math -- if carousel_lib's sizing logic ever changes, this validator
stays correct automatically. Thresholds (what counts as "narrow", how
many pink lines are required, etc) come from ProductionConfig.qa
rather than being hard-coded here -- see production_config.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from PIL import Image, ImageDraw

from renderer_imports import carousel_lib as cl
from perf import cached_lf
from production_config import ProductionConfig, QAThresholds, default_config
from story_loader import StoryPackage, StorySlide
from templates import RENDER_FUNCS, REQUIRED_FIELDS, KNOWN_FIELDS, COLOR_MAP

logger = logging.getLogger("jenniwren.validator")


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class ValidationIssue:
    severity: Severity
    slide_id: str
    rule: str
    message: str


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)

    def add(self, severity: Severity, slide_id: str, rule: str, message: str) -> None:
        """Pure data collection -- logging is the caller's job (see
        build_carousel.py's _print_validation_report), so issues are
        reported exactly once instead of once here and once there."""
        self.issues.append(ValidationIssue(severity, slide_id, rule, message))

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]


def _check_template_id(slide: StorySlide, report: ValidationReport) -> bool:
    if slide.template not in RENDER_FUNCS:
        report.add(
            Severity.ERROR, slide.slide_id, "invalid_template_id",
            f"Unknown template '{slide.template}'. Known templates: "
            f"{', '.join(sorted(RENDER_FUNCS))}",
        )
        return False
    return True


def _check_required_fields(slide: StorySlide, report: ValidationReport) -> None:
    for f in REQUIRED_FIELDS.get(slide.template, []):
        if slide.get(f) in (None, "", []):
            report.add(
                Severity.ERROR, slide.slide_id, "missing_required_field",
                f"Missing required field '{f}' for template '{slide.template}'.",
            )


def _check_unknown_fields(slide: StorySlide, report: ValidationReport) -> None:
    known = KNOWN_FIELDS.get(slide.template)
    if known is None:
        return
    for key in slide.raw.keys():
        if key not in known:
            report.add(
                Severity.WARNING, slide.slide_id, "unrecognized_field",
                f"Field '{key}' is not used by template '{slide.template}' -- "
                f"likely a typo or leftover from a different template.",
            )


def _check_missing_images(slide: StorySlide, story: StoryPackage, report: ValidationReport) -> None:
    image_field = slide.get("image")
    if not image_field:
        return
    path = story.resolve_image(image_field)
    if not path.exists():
        report.add(
            Severity.ERROR, slide.slide_id, "missing_image",
            f"Referenced image not found: {path}",
        )


def _check_citations(slide: StorySlide, story: StoryPackage, report: ValidationReport) -> None:
    if slide.template == "sources_slide":
        citations = slide.get("citations") or []
        if not citations:
            report.add(Severity.ERROR, slide.slide_id, "missing_citations",
                        "sources_slide has no citations.")
        return

    # Evidence-bearing templates should carry a citation; DemCast/JenniWren
    # editorial practice treats sourcing as non-optional for these slide
    # types even though carousel_lib itself has no opinion on it.
    if slide.template in ("document_card", "quote_lead", "stat_callout", "stat_grid"):
        if not slide.get("citation"):
            report.add(
                Severity.WARNING, slide.slide_id, "missing_citation",
                f"'{slide.template}' slide has no 'citation' field. Confirm the "
                f"claim is sourced in sources.md even if it's not printed on-slide.",
            )


def _check_brand_compliance(slide: StorySlide, report: ValidationReport, qa: QAThresholds) -> None:
    for color_field in ("headline_colors", "quote_colors"):
        colors = slide.get(color_field)
        if not colors:
            continue
        bad = [c for c in colors if str(c).lower() not in COLOR_MAP]
        if bad:
            report.add(
                Severity.ERROR, slide.slide_id, "brand_palette",
                f"'{color_field}' contains non-brand color(s) {bad}. Only "
                f"'white' and 'pink' are permitted (DESIGN_RULES.md Section 2).",
            )
        pink_count = sum(1 for c in colors if str(c).lower() == "pink")
        if pink_count < qa.min_pink_lines:
            report.add(
                Severity.WARNING, slide.slide_id, "min_pink_lines",
                f"'{color_field}' has only {pink_count} pink line(s); "
                f"DESIGN_RULES.md requires a minimum of {qa.min_pink_lines} pink "
                f"lines per headline.",
            )

    for lines_field in ("headline_lines", "quote_lines"):
        lines = slide.get(lines_field)
        if lines and len(lines) > qa.max_headline_lines:
            report.add(
                Severity.WARNING, slide.slide_id, "headline_too_long",
                f"'{lines_field}' has {len(lines)} lines; DESIGN_RULES.md "
                f"recommends splitting {qa.max_headline_lines}+ line headlines "
                f"across two slides.",
            )


def _check_overflow_risk(
    slide: StorySlide, report: ValidationReport, qa: QAThresholds, probe_draw: ImageDraw.ImageDraw,
) -> None:
    """Reuses carousel_lib.max_sz / wrap_lines to predict narrow headlines
    and truncated body text before any pixels are drawn. probe_draw is a
    throwaway ImageDraw shared across every slide in a run -- text-metric
    calls don't depend on the underlying image's size or content, only on
    font metrics, so one small (10x10) probe surface is reused for the
    whole story instead of allocating a full 1080x1350 canvas per slide."""
    for lines_field in ("headline_lines", "quote_lines"):
        lines = slide.get(lines_field)
        if not lines:
            continue
        for line in lines:
            size, width = cl.max_sz(probe_draw, line)
            pct = int(width / cl.HEAD_MAX_W * 100)
            if size < qa.narrow_headline_pt or pct < qa.narrow_headline_pct:
                report.add(
                    Severity.WARNING, slide.slide_id, "narrow_headline",
                    f"Line '{line}' fits at only {size}pt ({pct}% of width) -- "
                    f"below the ~{qa.narrow_headline_pt}pt / ~{qa.narrow_headline_pct}% "
                    f"guidance in DESIGN_RULES.md Section 5. Consider rewriting "
                    f"unless this is a deliberate short punch-line.",
                )

    body = slide.get("body")
    if body:
        fsz = max(slide.get("body_size", 46), cl.BODY_MIN_SIZE)
        font = cached_lf(cl.BASK_REG, fsz)
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * 1.32)
        max_w = cl.W - cl.BODY_L - cl.BODY_R
        segs = [(cl.break_urls(seg.get("text", "")), cl.WHITE) for seg in body]
        wrapped = cl.wrap_lines(probe_draw, segs, font, max_w)
        # Body drawing for cover/standard templates starts at roughly
        # HEAD_Y plus a headline block plus divider plus BODY_GAP; we
        # don't know the exact headline height pre-render, so this is a
        # conservative worst-case estimate using the tallest plausible
        # headline block (HEAD_MAX_H) as the starting offset.
        approx_start_y = cl.HEAD_Y + cl.HEAD_MAX_H + cl.DIVIDER_GAP + cl.DIVIDER_H + cl.BODY_GAP
        needed_h = len(wrapped) * lh
        if approx_start_y + needed_h > cl.FOOTER_SAFE:
            report.add(
                Severity.WARNING, slide.slide_id, "body_overflow_risk",
                f"Body copy ({len(wrapped)} wrapped lines at {fsz}pt) may run past "
                f"the footer-safe zone in the worst case (tallest headline). "
                f"draw_body() truncates silently -- verify the rendered slide.",
            )


def validate_story(story: StoryPackage, config: Optional[ProductionConfig] = None) -> ValidationReport:
    """config is optional so callers (and tests) that don't care about
    non-default QA thresholds can call validate_story(story) directly;
    production runs always pass the real ProductionConfig so validation
    thresholds match whatever the run was configured with."""
    if config is None:
        config = default_config(story.story_dir, story.story_dir)
    qa = config.qa

    report = ValidationReport()

    if not story.sources_text:
        report.add(
            Severity.WARNING, "(story)", "missing_sources_file",
            "No sources.md found for this story -- citation claims can't be "
            "cross-checked against a source list.",
        )

    # One small, shared probe surface for every text-metric call in this
    # validation pass -- see _check_overflow_risk's docstring.
    probe_draw = ImageDraw.Draw(Image.new("RGB", (10, 10), cl.BG))

    seen_ids = set()
    for slide in story.slides:
        if slide.slide_id in seen_ids:
            report.add(Severity.ERROR, slide.slide_id, "duplicate_slide_id",
                        "Duplicate slide id within this carousel.")
        seen_ids.add(slide.slide_id)

        if not _check_template_id(slide, report):
            continue  # nothing else is checkable against an unknown template

        _check_required_fields(slide, report)
        _check_unknown_fields(slide, report)
        _check_missing_images(slide, story, report)
        _check_citations(slide, story, report)
        _check_brand_compliance(slide, report, qa)

        # Overflow checks assume required fields are present; skip them
        # for a slide that's already missing fields to avoid noisy
        # secondary errors on top of the real problem.
        if not any(i.slide_id == slide.slide_id and i.rule == "missing_required_field"
                   for i in report.issues):
            _check_overflow_risk(slide, report, qa, probe_draw)

    return report
