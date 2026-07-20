"""
exporter.py
JenniWren Carousel Production Pipeline

Turns a rendered PIL Image into a file on disk. Split out of
build_carousel.py so export-format details (PNG vs JPEG, quality,
suffixing) live in one place instead of inline in the pipeline loop --
see CHANGELOG.md.
"""

from __future__ import annotations

import logging
from pathlib import Path

from production_config import ProductionConfig

logger = logging.getLogger("jenniwren.exporter")


class ExportError(Exception):
    """Raised when a rendered slide can't be written to disk."""


def export_image(image, output_stem: Path, config: ProductionConfig) -> Path:
    """output_stem has no extension -- the correct one is appended based
    on config.export_format. Raises ExportError on any filesystem
    problem so the caller can record a clear per-slide failure instead
    of the whole run crashing on an OSError three frames down."""
    try:
        output_stem.parent.mkdir(parents=True, exist_ok=True)
        if config.export_format == "jpeg":
            path = output_stem.with_suffix(".jpg")
            image.convert("RGB").save(path, format="JPEG", quality=config.jpeg_quality, optimize=True)
        else:
            path = output_stem.with_suffix(".png")
            image.save(path, format="PNG", optimize=True)
    except OSError as exc:
        raise ExportError(f"Could not write {output_stem} ({config.export_format}): {exc}") from exc
    return path
