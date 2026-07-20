"""
templates.py
JenniWren Carousel Production Pipeline

Thin aggregator over the template family modules (cover_templates.py,
data_templates.py, timeline_templates.py, comparison_templates.py,
document_templates.py, explainer_templates.py). This file used to
contain every render function directly; it was split up once it grew
into a god module -- see CHANGELOG.md. What stays here:

  - the single dispatch table (RENDER_FUNCS)
  - the single source of truth for required/known fields per template
    (REQUIRED_FIELDS / KNOWN_FIELDS), shared by validator.py so the two
    can't drift apart
  - TemplateRegistry wiring (reusing registry.py's existing
    TemplateRegistry/TemplateDefinition classes, unchanged)
  - render_slide(), the single entry point the orchestrator calls

TemplateError and the shared composition helpers live in
template_shared.py, imported by every family module.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from renderer_imports import TemplateDefinition, TemplateRegistry
from production_config import ProductionConfig
from story_loader import StorySlide, StoryPackage
from template_shared import TemplateError, COLOR_MAP  # re-exported for convenience/back-compat

from cover_templates import render_cover_headline, render_quote_lead, render_photo_headline
from data_templates import render_stat_callout, render_stat_grid
from timeline_templates import render_timeline
from comparison_templates import render_call_block
from document_templates import render_document_card
from explainer_templates import render_body_standard, render_sources_slide

__all__ = [
    "TemplateError", "COLOR_MAP", "RENDER_FUNCS", "REQUIRED_FIELDS", "KNOWN_FIELDS",
    "build_template_registry", "render_slide",
]

RENDER_FUNCS: Dict[str, Callable[..., Tuple[Any, List[str]]]] = {
    "cover_headline": render_cover_headline,
    "quote_lead": render_quote_lead,
    "stat_callout": render_stat_callout,
    "stat_grid": render_stat_grid,
    "timeline": render_timeline,
    "call_block": render_call_block,
    "document_card": render_document_card,
    "photo_headline": render_photo_headline,
    "body_standard": render_body_standard,
    "sources_slide": render_sources_slide,
}

# Declared once here so the pre-render validator (validator.py) and the
# render functions in the family modules can never disagree about what
# a template needs.
REQUIRED_FIELDS: Dict[str, List[str]] = {
    "cover_headline": ["label", "headline_lines", "headline_colors"],
    "quote_lead": ["label", "quote_lines", "quote_colors", "attribution"],
    "stat_callout": ["label", "stat_text", "stat_label"],
    "stat_grid": ["label", "stat_items"],
    "timeline": ["label", "headline_lines", "headline_colors", "timeline_entries"],
    "call_block": ["label", "call_text"],
    "document_card": ["label", "doc_lines", "headline_lines", "headline_colors"],
    "photo_headline": ["label", "image", "headline_lines", "headline_colors"],
    "body_standard": ["label", "headline_lines", "headline_colors", "body"],
    "sources_slide": ["citations"],
}

KNOWN_FIELDS: Dict[str, set] = {
    "cover_headline": {
        "template", "id", "label", "big_label", "headline_lines", "headline_colors",
        "headline_range", "body", "body_size", "arrow", "citation",
    },
    "quote_lead": {
        "template", "id", "label", "big_label", "quote_lines", "quote_colors",
        "attribution", "headline_range", "arrow", "citation",
    },
    "stat_callout": {
        "template", "id", "label", "big_label", "stat_text", "stat_label", "stat_y0",
        "stat_size", "stat_range", "headline_lines", "headline_colors", "headline_range",
        "arrow", "citation",
    },
    "stat_grid": {
        "template", "id", "label", "big_label", "stat_items", "headline_lines",
        "headline_colors", "headline_range", "grid_cols", "grid_cell_h", "arrow", "citation",
    },
    "timeline": {
        "template", "id", "label", "big_label", "headline_lines", "headline_colors",
        "headline_range", "timeline_entries", "arrow", "citation",
    },
    "call_block": {
        "template", "id", "label", "big_label", "headline_lines", "headline_colors",
        "headline_range", "call_text", "call_size", "body", "body_size", "arrow", "citation",
    },
    "document_card": {
        "template", "id", "label", "big_label", "doc_lines", "doc_highlight", "doc_card_h",
        "doc_annotation", "headline_lines", "headline_colors", "headline_range", "arrow", "citation",
    },
    "photo_headline": {
        "template", "id", "label", "big_label", "image", "photo_style", "fade_edge",
        "fade_start", "headline_lines", "headline_colors", "headline_range", "headline_y0",
        "arrow", "citation",
    },
    "body_standard": {
        "template", "id", "label", "big_label", "headline_lines", "headline_colors",
        "headline_range", "body", "body_size", "arrow", "citation",
    },
    "sources_slide": {"template", "id", "label", "citations", "body_size", "arrow"},
}

_DEFS = [
    TemplateDefinition(
        id="cover_headline", name="Cover Headline", family="COV",
        module="cover_templates", description="Standard editorial headline cover, optional deck.",
        supports_cover=True,
        required_components=["label", "headline", "divider", "footer", "logo", "slide_counter"],
        tags=["cover"],
    ),
    TemplateDefinition(
        id="quote_lead", name="Quote Lead", family="COV",
        module="cover_templates", description="Headline-styled direct quotation with attribution.",
        supports_cover=True,
        required_components=["label", "headline", "divider", "body", "footer", "logo", "slide_counter"],
        tags=["cover", "quote"],
    ),
    TemplateDefinition(
        id="stat_callout", name="Big Number", family="DATA",
        module="data_templates", description="Single dominant statistic with context pill.",
        required_components=["label", "stat", "footer", "logo", "slide_counter"],
        tags=["data"],
    ),
    TemplateDefinition(
        id="stat_grid", name="Stat Grid", family="DATA",
        module="data_templates", description="Grid of 2-6 (stat, label) pairs.",
        required_components=["label", "stat_grid", "footer", "logo", "slide_counter"],
        tags=["data"],
    ),
    TemplateDefinition(
        id="timeline", name="Timeline", family="DATA",
        module="timeline_templates", description="Dynamic-height vertical timeline of dated entries.",
        required_components=["label", "headline", "timeline", "footer", "logo", "slide_counter"],
        tags=["data", "timeline"],
    ),
    TemplateDefinition(
        id="call_block", name="Call Block", family="COMP",
        module="comparison_templates", description="Full-width highlighted statement bar.",
        required_components=["label", "call_block", "footer", "logo", "slide_counter"],
        tags=["comparison", "emphasis"],
    ),
    TemplateDefinition(
        id="document_card", name="Document Evidence", family="COMP",
        module="document_templates", description="Primary-source document excerpt with headline.",
        required_components=["label", "image", "headline", "divider", "footer", "logo", "slide_counter"],
        tags=["evidence"],
    ),
    TemplateDefinition(
        id="photo_headline", name="Photo Story", family="COV",
        module="cover_templates", description="Full-bleed photo with fade and headline.",
        supports_cover=True,
        required_components=["label", "image", "headline", "divider", "footer", "logo", "slide_counter"],
        tags=["photo"],
    ),
    TemplateDefinition(
        id="body_standard", name="Standard Explainer", family="COMP",
        module="explainer_templates", description="Headline + body paragraph, the default interior slide.",
        required_components=["label", "headline", "divider", "body", "footer", "logo", "slide_counter"],
        tags=["interior"],
    ),
    TemplateDefinition(
        id="sources_slide", name="Sources", family="COMP",
        module="explainer_templates", description="Closing numbered citation list.",
        required_components=["label", "sources", "footer", "logo", "slide_counter"],
        tags=["sources", "closer"],
    ),
]


def build_template_registry() -> TemplateRegistry:
    registry = TemplateRegistry()
    for d in _DEFS:
        registry.register(d)
    return registry


def render_slide(
    slide: StorySlide, total: int, story: StoryPackage, config: ProductionConfig,
) -> Tuple[Any, List[str]]:
    """
    Render one slide, dispatching by template id. Returns (PIL Image,
    qa_notes) -- qa_notes is a list of human-readable strings describing
    any rendering-time problems detected while drawing (currently: body
    text or timeline/grid content that ran past the footer-safe zone).
    Raises TemplateError on unknown templates or missing required fields.
    """
    fn = RENDER_FUNCS.get(slide.template)
    if fn is None:
        raise TemplateError(
            f"Slide '{slide.slide_id}' uses unknown template '{slide.template}'. "
            f"Known templates: {', '.join(sorted(RENDER_FUNCS))}"
        )
    return fn(slide, slide.index, total, story, config.template_defaults)
