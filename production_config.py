"""
production_config.py
JenniWren Carousel Production Pipeline

Centralized run configuration. Canvas geometry and brand colors are
still NOT duplicated here -- they're read live from carousel_lib.py so
config can never silently drift out of sync with the renderer.

This module now also centralizes the constants that used to be
scattered across validator.py and templates.py: QA thresholds (what
counts as a "narrow" headline, how many pink lines are required, etc)
and per-template defaults (font sizes, ranges, spacing) used whenever
a slide doesn't specify its own value. Nothing here changes
carousel_lib.py's own internal constants (margins, floors, palette) --
those remain sourced live from carousel_lib.py, per the "single source
of truth" rule below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from renderer_imports import carousel_lib as cl


@dataclass(frozen=True)
class QAThresholds:
    """Editorial/QA judgment calls that live above carousel_lib.py's own
    hard-coded floors (BODY_MIN_SIZE, FOOTER_SAFE, etc, which stay in
    carousel_lib.py where they're enforced). These are validator-level
    heuristics, so they belong in orchestrator config, not the renderer.
    """
    narrow_headline_pt: int = 95        # DESIGN_RULES.md Section 5
    narrow_headline_pct: int = 72       # DESIGN_RULES.md Section 5
    max_headline_lines: int = 4         # DESIGN_RULES.md Section 5
    min_pink_lines: int = 2             # DESIGN_RULES.md Section 2 (hard rule)


@dataclass(frozen=True)
class TemplateDefaults:
    """Default sizes/ranges/spacing used by template composition
    functions when a slide doesn't override them in carousel.json.
    Every one of these was previously an inline literal in templates.py;
    centralizing them here means a production-wide style tweak (e.g.
    "make body copy a touch bigger by default") is a one-line config
    change instead of a hunt through render functions.
    """
    headline_range: Tuple[int, int] = (100, 180)
    stat_headline_range: Tuple[int, int] = (60, 100)
    grid_headline_range: Tuple[int, int] = (70, 120)
    call_headline_range: Tuple[int, int] = (80, 140)
    document_headline_range: Tuple[int, int] = (60, 110)

    stat_range: Tuple[int, int] = (200, 420)

    body_size: int = 46
    quote_attribution_size: int = 42
    call_block_size: int = 40
    sources_body_size: int = 32

    grid_cols: int = 2
    grid_cell_h: int = 210

    doc_card_h: int = 520

    photo_fade_edge: str = "bottom"
    photo_fade_start: float = 0.35
    photo_headline_y0_offset: int = 430   # headline starts at H - this


@dataclass(frozen=True)
class ProductionConfig:
    story_dir: Path
    output_dir: Path
    export_format: str = "png"          # "png" or "jpeg"
    jpeg_quality: int = 95
    skip_qa: bool = False
    verbose: bool = False
    skip_compat_check: bool = False

    qa: QAThresholds = field(default_factory=QAThresholds)
    template_defaults: TemplateDefaults = field(default_factory=TemplateDefaults)

    # Read-only mirror of carousel_lib's canvas geometry, exposed here
    # for convenience/logging -- not an independent source of truth.
    canvas_width: int = cl.W
    canvas_height: int = cl.H
    background_color: tuple = cl.BG
    accent_color: tuple = cl.PINK

    def __post_init__(self):
        if self.export_format not in ("png", "jpeg"):
            raise ValueError(f"Unsupported export_format: {self.export_format!r}")

    @property
    def story_output_dir(self) -> Path:
        return self.output_dir / self.story_dir.name


def default_config(story_dir: Path, output_dir: Path) -> ProductionConfig:
    """Convenience constructor for tests/scripts that don't need to go
    through the CLI argument parser."""
    return ProductionConfig(story_dir=story_dir, output_dir=output_dir)
