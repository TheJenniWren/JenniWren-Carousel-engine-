"""
renderer_compat.py
JenniWren Carousel Production Pipeline

carousel_lib.py has no __version__ string, and per direction it isn't
getting one added -- it stays exactly as delivered. So instead of
version-number compatibility, this module checks the thing that
actually matters to the orchestrator: does the installed carousel_lib.py
still expose the exact function signatures and constants templates.py
was written against?

This is intentionally lightweight -- a signature/attribute fingerprint,
not a real dependency-resolution system. If carousel_lib.py is ever
edited (a parameter renamed, a constant removed) this catches it at
pipeline startup with a clear message, instead of failing halfway
through a render with a confusing TypeError three modules deep.

API_CONTRACT_VERSION is a label the orchestrator maintains, not
something carousel_lib.py needs to know about. Bump it in this file's
EXPECTED_FUNCTIONS/EXPECTED_CONSTANTS whenever templates.py starts
depending on a new or changed part of carousel_lib.py's API.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from types import ModuleType
from typing import List

API_CONTRACT_VERSION = "carousel_lib-api-v1"

# function_name -> required parameter names, in order. Only the
# parameters templates.py actually relies on are checked; extra
# optional parameters added to carousel_lib.py wouldn't break us and
# aren't required here.
EXPECTED_FUNCTIONS = {
    "lf": ["path", "size"],
    "mw": ["draw", "text", "font"],
    "max_sz": ["draw", "text"],
    "wrap_lines": ["draw", "segs", "font", "max_w"],
    "break_urls": ["text"],
    "draw_top_bar": ["draw", "label", "n", "total_slides"],
    "draw_headline": ["draw", "lines", "colors", "y0", "sr"],
    "draw_divider": ["draw", "gy"],
    "draw_body": ["draw", "segs", "ty"],
    "draw_footer": ["draw"],
    "new_canvas": [],
    "new_photo_fade_canvas": ["image_path"],
    "new_photo_story_canvas": ["image_path"],
    "draw_stat_callout": ["draw", "stat_text", "context_label"],
    "draw_stat_grid": ["draw", "items", "y0"],
    "draw_call_block": ["draw", "text", "ty"],
    "draw_document_card": ["draw", "img", "lines", "highlight_line_idxs", "ty"],
    "draw_timeline": ["draw", "entries", "y0"],
}

EXPECTED_CONSTANTS = [
    "W", "H", "BG", "WHITE", "PINK",
    "L_MARGIN", "R_MARGIN", "BODY_L", "BODY_R", "BODY_GAP", "BODY_MIN_SIZE",
    "HEAD_Y", "HEAD_MAX_W", "HEAD_MAX_H",
    "DIVIDER_GAP", "DIVIDER_H", "DIVIDER_W", "FOOTER_SAFE",
    "BARLOW", "BASK_REG", "BASK_ITA",
]


@dataclass
class CompatibilityReport:
    compatible: bool
    contract_version: str
    missing_functions: List[str] = field(default_factory=list)
    signature_mismatches: List[str] = field(default_factory=list)
    missing_constants: List[str] = field(default_factory=list)

    def describe(self) -> str:
        if self.compatible:
            return f"carousel_lib.py is compatible with orchestrator contract {self.contract_version}."
        lines = [
            f"carousel_lib.py is NOT compatible with orchestrator contract {self.contract_version}:"
        ]
        for fn in self.missing_functions:
            lines.append(f"  - missing function: {fn}()")
        for msg in self.signature_mismatches:
            lines.append(f"  - {msg}")
        for const in self.missing_constants:
            lines.append(f"  - missing constant: {const}")
        lines.append(
            "The orchestrator's templates.py was written against a specific "
            "carousel_lib.py API. Either restore the expected signatures, or "
            "update renderer_compat.py's EXPECTED_FUNCTIONS/EXPECTED_CONSTANTS "
            "and templates.py together to match the new API."
        )
        return "\n".join(lines)


def check_renderer_compatibility(cl_module: ModuleType) -> CompatibilityReport:
    report = CompatibilityReport(compatible=True, contract_version=API_CONTRACT_VERSION)

    for fn_name, required_params in EXPECTED_FUNCTIONS.items():
        fn = getattr(cl_module, fn_name, None)
        if fn is None or not callable(fn):
            report.missing_functions.append(fn_name)
            continue
        try:
            sig_params = list(inspect.signature(fn).parameters.keys())
        except (TypeError, ValueError):
            report.signature_mismatches.append(f"{fn_name}(): could not inspect signature")
            continue
        for i, expected_name in enumerate(required_params):
            if i >= len(sig_params) or sig_params[i] != expected_name:
                report.signature_mismatches.append(
                    f"{fn_name}(): expected parameter '{expected_name}' at position {i}, "
                    f"found {sig_params[i:i + 1] or '(nothing)'}"
                )

    for const_name in EXPECTED_CONSTANTS:
        if not hasattr(cl_module, const_name):
            report.missing_constants.append(const_name)

    report.compatible = not (
        report.missing_functions or report.signature_mismatches or report.missing_constants
    )
    return report
