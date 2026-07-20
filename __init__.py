"""
jenniwren_renderer
===================

The single authoritative implementation of the JenniWren carousel
rendering engine: carousel_lib.py (the renderer), plus registry.py, qa.py,
and renderer.py (the small, self-contained pieces of the unfinished
component/canvas rewrite that the orchestrator reuses -- see the
orchestrator's ARCHITECTURE.md for why).

This package intentionally contains no orchestration logic (no story
loading, no CLI, no validation, no export). It is imported, not run
directly. Consumers -- currently the jenniwren_build_carousel
orchestrator -- should treat every module here as read-only.

DESIGN_RULES.md, the brand spec these modules implement, lives
alongside them in this package's directory (not shipped as a file you
import, but kept here since it documents this code, not the
orchestrator's).
"""

from . import carousel_lib, registry, qa, renderer  # noqa: F401  (re-exported for convenience)

__all__ = ["carousel_lib", "registry", "qa", "renderer"]
