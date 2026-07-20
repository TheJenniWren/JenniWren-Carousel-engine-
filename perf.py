"""
perf.py
JenniWren Carousel Production Pipeline

Small, deliberately narrow performance helpers used by the orchestrator
at its OWN call sites into carousel_lib.py -- not inside carousel_lib.py
itself, which stays untouched. See ARCHITECTURE.md "Performance" for
what was and wasn't done here, and why.
"""

from __future__ import annotations

from functools import lru_cache

from renderer_imports import carousel_lib as cl


@lru_cache(maxsize=128)
def cached_lf(path: str, size: int):
    """
    Memoized wrapper around carousel_lib.lf() for the font loads the
    ORCHESTRATOR makes directly: validator.py's overflow checks and
    explainer_templates.py's sources_slide layout. The same (path, size)
    pairs recur constantly across a multi-slide carousel -- e.g. every
    default-sized body paragraph -- so caching avoids re-parsing the
    same TTF from disk on every call within a run.

    Deliberately NOT applied to carousel_lib.py's OWN internal lf()
    calls inside fit_head()/max_sz()'s per-size search loops (which is
    where most font-loading actually happens, up to ~120 calls per
    headline while searching for a fit). Caching those would mean
    monkeypatching carousel_lib.lf at runtime -- technically possible,
    but it means silently altering the behavior of a module we were
    explicitly told to leave alone as "the rendering engine." That's
    flagged as deferred technical debt in CHANGELOG.md, not solved here.
    """
    return cl.lf(path, size)
