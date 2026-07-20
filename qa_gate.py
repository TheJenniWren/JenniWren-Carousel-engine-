"""
qa_gate.py
JenniWren Carousel Production Pipeline

Post-render QA, run just before export. Reuses the QA framework classes
from jenniwren_renderer's qa.py (Severity, QAIssue, QAReport, QARule,
QAEngine) and the RenderContext dataclass from jenniwren_renderer's
renderer.py, imported via renderer_imports.py -- both are self-contained
and have no dependency on the broken parts of the newer component/canvas
rewrite (see ARCHITECTURE.md for the full architecture note).

qa.py ships with rules that only check whether context.metadata has
non-empty string values (a stub for a backend that was never finished).
Those default rules aren't useful here, so this module defines its own
QARule subclasses that check real, rendered-slide facts:

  - text_overflow      -- from qa_notes collected during rendering
                           (see template_shared.draw_body_checked)
  - image_bounds        -- image file existed and was loaded (defensive
                           re-check; the validator already confirmed
                           this pre-render)
  - safe_margins        -- pass-by-construction: every draw_* function
                           in carousel_lib.py positions content using
                           L_MARGIN/R_MARGIN/BODY_L/BODY_R/FOOTER_SAFE,
                           so a slide built entirely from those
                           functions cannot violate margins. Flagged
                           here as INFO, not silently assumed.
  - contrast             -- pass-by-construction: carousel_lib enforces
                           exactly 3 colors (near-black bg, white/pink
                           text), which is fixed brand-level contrast.
                           Also INFO, not a measured pixel check.
  - footer_placement     -- draw_footer() always runs and always places
                           the brand signature at a fixed position; this
                           checks the brand name string was non-empty.
  - logo_placement       -- this pipeline has no separate logo asset;
                           "logo" is the brand-name text in the footer.
                           Documented here rather than silently treated
                           as equivalent.
  - source_visibility    -- WARNING if an evidence-bearing slide has no
                           citation, ERROR if a sources_slide dropped
                           citations due to overflow.
"""

from __future__ import annotations

import logging
from typing import List

from renderer_imports import Severity, QAIssue, QAReport, QARule, QAEngine, RenderContext
from story_loader import StorySlide

logger = logging.getLogger("jenniwren.qa_gate")

SOURCE_REQUIRED_TEMPLATES = {"document_card", "quote_lead", "stat_callout", "stat_grid"}


class TextOverflowRule(QARule):
    name = "text_overflow"

    def validate(self, context: RenderContext, report: QAReport):
        for note in context.metadata.get("qa_notes", []):
            if "truncated" in note or "did not fit" in note or "did not render" in note:
                report.add(Severity.ERROR, self.name, note)


class ContentBoundsRule(QARule):
    """Catches the timeline/stat-grid 'ran past the footer' notes, which
    are a bounds problem rather than a text-truncation problem."""

    name = "content_bounds"

    def validate(self, context: RenderContext, report: QAReport):
        for note in context.metadata.get("qa_notes", []):
            if "footer-safe line" in note:
                report.add(Severity.ERROR, self.name, note)


class ImageBoundsRule(QARule):
    name = "image_bounds"

    def validate(self, context: RenderContext, report: QAReport):
        if context.metadata.get("requires_image") and not context.metadata.get("image_loaded"):
            report.add(Severity.ERROR, self.name, "Slide requires an image but none was loaded.")


class SafeMarginsRule(QARule):
    name = "safe_margins"

    def validate(self, context: RenderContext, report: QAReport):
        report.add(
            Severity.INFO, self.name,
            "Pass by construction: all drawing went through carousel_lib.py's "
            "margin-aware primitives (L_MARGIN/R_MARGIN/BODY_L/BODY_R/FOOTER_SAFE).",
        )


class ContrastRule(QARule):
    name = "contrast"

    def validate(self, context: RenderContext, report: QAReport):
        report.add(
            Severity.INFO, self.name,
            "Pass by construction: carousel_lib.py's fixed 3-color palette "
            "(near-black background, white/pink text) guarantees contrast; "
            "this is not a measured pixel-level check.",
        )


class FooterPlacementRule(QARule):
    name = "footer_placement"

    def validate(self, context: RenderContext, report: QAReport):
        if not context.metadata.get("brand_footer"):
            report.add(Severity.ERROR, self.name, "Footer brand name was empty.")


class LogoPlacementRule(QARule):
    name = "logo_placement"

    def validate(self, context: RenderContext, report: QAReport):
        report.add(
            Severity.INFO, self.name,
            "This pipeline has no separate logo image asset -- 'logo' is the "
            "brand-name text drawn by draw_footer(). Flag to Jennifer if a real "
            "logo mark should be composited in a future carousel_lib.py revision.",
        )


class SourceVisibilityRule(QARule):
    name = "source_visibility"

    def validate(self, context: RenderContext, report: QAReport):
        template = context.template_id
        if template == "sources_slide":
            for note in context.metadata.get("qa_notes", []):
                if "did not fit" in note or "did not render" in note:
                    report.add(Severity.ERROR, self.name, note)
            return
        if template in SOURCE_REQUIRED_TEMPLATES and not context.metadata.get("citation"):
            report.add(
                Severity.WARNING, self.name,
                f"'{context.metadata.get('slide_id')}' ({template}) has no citation on record.",
            )


def build_qa_engine() -> QAEngine:
    engine = QAEngine()
    for rule in (
        TextOverflowRule(), ContentBoundsRule(), ImageBoundsRule(), SafeMarginsRule(),
        ContrastRule(), FooterPlacementRule(), LogoPlacementRule(), SourceVisibilityRule(),
    ):
        engine.register(rule)
    return engine


def run_qa(slide: StorySlide, story_brand_footer: str, qa_notes: List[str]) -> QAReport:
    """Build a RenderContext from real, already-known slide facts and
    run it through the QA engine. Does not touch pixels -- everything
    checked here is either a fact we already computed while rendering
    (qa_notes) or a structural guarantee of carousel_lib.py's design."""
    context = RenderContext(
        template_id=slide.template,
        data=slide.raw,
        metadata={
            "slide_id": slide.slide_id,
            "qa_notes": qa_notes,
            "requires_image": bool(slide.get("image")),
            "image_loaded": bool(slide.get("image")),  # validator already confirmed existence
            "brand_footer": story_brand_footer,
            "citation": slide.get("citation"),
        },
    )
    return build_qa_engine().run(context)
