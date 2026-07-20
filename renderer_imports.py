"""
Compatibility imports for the JenniWren Carousel Engine.

Supports both:
1. An installed ``jenniwren_renderer`` package.
2. Renderer modules stored directly in the repository root.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Dict

RENDERER_PACKAGE = "jenniwren_renderer"
REQUIRED_MODULES = ("carousel_lib", "registry", "qa", "renderer")


class RendererUnavailableError(ImportError):
    """Raised when the production renderer modules cannot be imported."""


def _load_packaged() -> Dict[str, ModuleType]:
    modules: Dict[str, ModuleType] = {}
    for name in REQUIRED_MODULES:
        modules[name] = importlib.import_module(f"{RENDERER_PACKAGE}.{name}")
    return modules


def _load_flat() -> Dict[str, ModuleType]:
    modules: Dict[str, ModuleType] = {}
    for name in REQUIRED_MODULES:
        modules[name] = importlib.import_module(name)
    return modules


def _load() -> Dict[str, ModuleType]:
    packaged_error: Exception | None = None
    flat_error: Exception | None = None

    try:
        return _load_packaged()
    except (ImportError, ModuleNotFoundError) as exc:
        packaged_error = exc

    try:
        return _load_flat()
    except (ImportError, ModuleNotFoundError) as exc:
        flat_error = exc

    raise RendererUnavailableError(
        "Could not import the JenniWren production renderer. "
        "Tried both the installed 'jenniwren_renderer' package and the "
        "local flat-module repository layout.\n"
        f"Package import error: {packaged_error}\n"
        f"Local import error: {flat_error}"
    ) from flat_error


_modules = _load()

carousel_lib = _modules["carousel_lib"]
registry = _modules["registry"]
qa = _modules["qa"]
renderer = _modules["renderer"]

TemplateDefinition = registry.TemplateDefinition
TemplateRegistry = registry.TemplateRegistry

Severity = qa.Severity
QAIssue = qa.QAIssue
QAReport = qa.QAReport
QARule = qa.QARule
QAEngine = qa.QAEngine

RendererContext = renderer.RendererContext

__all__ = [
    "RendererUnavailableError",
    "carousel_lib",
    "registry",
    "qa",
    "renderer",
    "TemplateDefinition",
    "TemplateRegistry",
    "Severity",
    "QAIssue",
    "QAReport",
    "QARule",
    "QAEngine",
    "RendererContext",
]
