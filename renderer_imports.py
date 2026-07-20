"""
renderer_imports.py
JenniWren Carousel Production Pipeline

Single point of contact between this orchestrator and the production
renderer package, `jenniwren_renderer`. Every other module in this
package imports carousel_lib / registry / qa / renderer THROUGH this
module -- never directly -- so there is exactly one place that knows
how the renderer is located, and exactly one place that has to explain
what went wrong if it isn't.

This orchestrator ships NO local copies of carousel_lib.py, renderer.py,
registry.py, or qa.py. There is exactly one authoritative copy of each,
living in the sibling `jenniwren_renderer` package. See README.md
"Project layout" and ARCHITECTURE.md for the full picture.

Resolution order:
  1. Normal import -- works if `jenniwren_renderer` is pip-installed
     (`pip install -e /path/to/jenniwren_renderer`) or otherwise
     already on PYTHONPATH/sys.path.
  2. JENNIWREN_RENDERER_PATH environment variable -- if set, its value
     is treated as the directory that CONTAINS the jenniwren_renderer
     package directory (i.e. `$JENNIWREN_RENDERER_PATH/jenniwren_renderer/`
     must exist) and is added to sys.path.
  3. Sibling-directory convention -- if this orchestrator and
     jenniwren_renderer/ are unzipped/checked out next to each other
     (the layout this project ships in), that sibling directory is
     found automatically and added to sys.path. This is what makes
     `python build_carousel.py ...` work out of the box from a fresh
     unzip, with no install step.

If none of these locate a working `jenniwren_renderer` package -- or
it's found but missing one of the four required modules -- this raises
RendererUnavailableError with an actionable message, once, here. Every
downstream module's `from renderer_imports import carousel_lib as cl`
either succeeds cleanly or fails with that same clear message; nothing
downstream needs its own try/except for this.

build_carousel.py's main() is the one place that catches
RendererUnavailableError at the CLI boundary and turns it into a clean
error message + exit code instead of a raw traceback -- see its
module docstring.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Optional

RENDERER_PACKAGE = "jenniwren_renderer"
REQUIRED_MODULES = ("carousel_lib", "registry", "qa", "renderer")
ENV_VAR = "JENNIWREN_RENDERER_PATH"


class RendererUnavailableError(ImportError):
    """Raised when the production renderer package can't be located or
    is missing one of its required modules. Deliberately a subclass of
    ImportError (not a bespoke Exception) so it's still catchable by
    generic `except ImportError` handling elsewhere, but distinguishable
    by name in logs and in build_carousel.py's explicit handler."""


def _find_package() -> Optional[object]:
    """Try each resolution strategy in order; return the imported
    jenniwren_renderer package module, or None if every strategy fails."""
    try:
        return importlib.import_module(RENDERER_PACKAGE)
    except ImportError:
        pass

    for candidate_root in _candidate_roots():
        sys_path_entry = _locate_importable_parent(candidate_root)
        if sys_path_entry is None:
            continue
        entry_str = str(sys_path_entry)
        if entry_str not in sys.path:
            sys.path.insert(0, entry_str)
        try:
            return importlib.import_module(RENDERER_PACKAGE)
        except ImportError:
            continue
    return None


def _locate_importable_parent(candidate_root: Path) -> Optional[Path]:
    """
    jenniwren_renderer ships in a standard pip-installable "project
    root == package parent" layout:

        jenniwren_renderer/                 (project root)
            pyproject.toml
            jenniwren_renderer/              (the actual package)
                __init__.py
                carousel_lib.py
                ...

    but a flat layout (package files directly under jenniwren_renderer/,
    no nested duplicate) is also accepted, since that's a perfectly
    valid way to check out just the package with no packaging metadata.
    Returns the directory that should be added to sys.path so that
    `import jenniwren_renderer` succeeds, or None if neither layout is
    found under candidate_root.
    """
    flat = candidate_root / RENDERER_PACKAGE
    if (flat / "__init__.py").is_file():
        return candidate_root  # flat layout: parent of the package dir

    nested = candidate_root / RENDERER_PACKAGE / RENDERER_PACKAGE
    if (nested / "__init__.py").is_file():
        return candidate_root / RENDERER_PACKAGE  # project-root layout

    return None


def _candidate_roots():
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        yield Path(env_value).expanduser().resolve()

    # Sibling-directory convention: .../<something>/jenniwren_build_carousel/
    # and .../<something>/jenniwren_renderer/ checked out (or unzipped) next
    # to each other. This file lives at the top of the orchestrator package,
    # so its parent's parent is "<something>".
    yield Path(__file__).resolve().parent.parent


def _missing_message(module_name: Optional[str] = None, underlying: Optional[Exception] = None) -> str:
    lines = [
        f"Could not import the production renderer package '{RENDERER_PACKAGE}'"
        + (f" (module '{module_name}')" if module_name else "") + ".",
        "",
        "This orchestrator does not ship its own copies of carousel_lib.py, "
        f"renderer.py, registry.py, or qa.py -- it imports them from the single "
        f"authoritative '{RENDERER_PACKAGE}' package. To fix this, do one of:",
        f"  1. Install it:            pip install -e /path/to/{RENDERER_PACKAGE}",
        f"  2. Point at a checkout:   export {ENV_VAR}=/path/to/parent-of-{RENDERER_PACKAGE}",
        f"  3. Place '{RENDERER_PACKAGE}/' as a sibling directory of this "
        f"orchestrator package (the layout this project ships in) and add "
        f"its parent to PYTHONPATH.",
    ]
    if underlying is not None:
        lines += ["", f"Underlying error: {underlying}"]
    return "\n".join(lines)


def _load():
    package = _find_package()
    if package is None:
        raise RendererUnavailableError(_missing_message())

    modules = {}
    for name in REQUIRED_MODULES:
        try:
            modules[name] = importlib.import_module(f"{RENDERER_PACKAGE}.{name}")
        except ImportError as exc:
            raise RendererUnavailableError(_missing_message(name, exc)) from exc
    return modules


_modules = _load()

carousel_lib = _modules["carousel_lib"]
registry = _modules["registry"]
qa = _modules["qa"]
renderer = _modules["renderer"]

# Convenience re-exports for the specific names orchestrator modules use,
# so call sites can do `from renderer_imports import TemplateDefinition`
# instead of `registry.TemplateDefinition` everywhere.
TemplateDefinition = registry.TemplateDefinition
TemplateRegistry = registry.TemplateRegistry
Severity = qa.Severity
QAIssue = qa.QAIssue
QAReport = qa.QAReport
QARule = qa.QARule
QAEngine = qa.QAEngine
RenderContext = renderer.RenderContext

__all__ = [
    "RendererUnavailableError",
    "carousel_lib", "registry", "qa", "renderer",
    "TemplateDefinition", "TemplateRegistry",
    "Severity", "QAIssue", "QAReport", "QARule", "QAEngine",
    "RenderContext",
]
