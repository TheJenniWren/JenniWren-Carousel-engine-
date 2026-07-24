"""
JenniWren Headline Engine v2
============================

A deterministic, template-agnostic headline renderer for PIL-based
JenniWren carousel templates.

Responsibilities
----------------
* Preserve editorial line breaks exactly as supplied.
* Render a separate color for every line.
* Find the largest font size that fits the supplied region.
* Measure the complete headline block before drawing.
* Vertically balance the block within the region.
* Return structured diagnostics instead of silently overflowing.

The engine does not wrap, rewrite, recolor, or otherwise edit copy.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from PIL import ImageDraw, ImageFont

Color = Tuple[int, int, int]
FontPath = Union[str, Path]


@dataclass(frozen=True)
class HeadlineMetrics:
    font_size: int
    line_height: int
    block_width: int
    block_height: int
    line_widths: Tuple[int, ...]
    top: int
    bottom: int
    left: int
    right: int


@dataclass(frozen=True)
class HeadlineDiagnostics:
    fits: bool
    used_minimum_size: bool
    width_overflow_px: int
    height_overflow_px: int
    line_count: int
    widest_line_index: int
    widest_line: str
    message: str
    metrics: HeadlineMetrics

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data


def _load_font(font_path: FontPath, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(font_path), int(size))
    except OSError as exc:
        raise RuntimeError(f"Unable to load headline font: {font_path}") from exc


def _normalize_lines(lines: Sequence[Any]) -> List[str]:
    if not lines:
        raise ValueError("Headline Engine v2 requires at least one headline line.")

    normalized: List[str] = []
    for index, line in enumerate(lines):
        if line is None:
            raise ValueError(f"Headline line {index + 1} is null.")
        text = str(line)
        if "\n" in text:
            # Preserve explicit breaks, even when a caller passes one string
            # containing multiple editorial lines.
            normalized.extend(text.split("\n"))
        else:
            normalized.append(text)

    if any(not line.strip() for line in normalized):
        raise ValueError("Headline lines may not be blank. Remove empty lines from the JSON.")
    return normalized


def _normalize_colors(
    colors: Optional[Sequence[Color]],
    line_count: int,
    default_color: Color,
) -> Tuple[List[Color], List[str]]:
    warnings: List[str] = []
    if not colors:
        return [default_color] * line_count, warnings

    normalized = list(colors)
    if len(normalized) < line_count:
        warnings.append(
            f"Only {len(normalized)} headline color(s) were supplied for {line_count} lines; "
            "remaining lines used the default color."
        )
        normalized.extend([default_color] * (line_count - len(normalized)))
    elif len(normalized) > line_count:
        warnings.append(
            f"{len(normalized)} headline colors were supplied for {line_count} lines; "
            "extra colors were ignored."
        )
        normalized = normalized[:line_count]
    return normalized, warnings


def _measure(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    font: ImageFont.FreeTypeFont,
    line_height_ratio: float,
) -> Tuple[List[int], int, int, int]:
    widths: List[int] = []
    visual_heights: List[int] = []

    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        widths.append(box[2] - box[0])
        visual_heights.append(box[3] - box[1])

    ascender, descender = font.getmetrics()
    metric_height = ascender + descender
    line_height = max(1, int(round(metric_height * line_height_ratio)))
    last_height = visual_heights[-1] if visual_heights else metric_height
    block_height = line_height * (len(lines) - 1) + last_height
    return widths, line_height, max(widths, default=0), block_height


def _position_top(region_top: int, region_bottom: int, block_height: int, balance: str) -> int:
    slack = max(0, (region_bottom - region_top) - block_height)
    mode = (balance or "center").strip().lower()

    if mode == "top":
        return region_top
    if mode == "optical":
        # Mathematical center with a small upward optical correction.
        return region_top + (slack // 2) - min(int(slack * 0.12), 20)
    if mode == "bottom":
        return region_top + slack
    if mode != "center":
        raise ValueError("headline balance must be 'top', 'center', 'optical', or 'bottom'.")
    return region_top + (slack // 2)


def render_headline(
    draw: ImageDraw.ImageDraw,
    *,
    lines: Sequence[Any],
    colors: Optional[Sequence[Color]],
    font_path: FontPath,
    region: Tuple[int, int, int, int],
    min_size: int = 72,
    max_size: int = 180,
    line_height_ratio: float = 0.88,
    align: str = "left",
    balance: str = "center",
    default_color: Color = (255, 255, 255),
) -> Tuple[int, HeadlineDiagnostics]:
    """Render a manually line-broken headline inside ``region``.

    Parameters
    ----------
    region:
        ``(left, top, right, bottom)`` in pixels. Both width and height
        are hard constraints.
    lines:
        Editorial lines. They are never word-wrapped or rewritten.
    colors:
        Parallel RGB tuples. Missing values fall back to ``default_color``.
    balance:
        ``top``, ``center``, ``optical``, or ``bottom``.

    Returns
    -------
    (bottom_y, diagnostics)
        ``bottom_y`` can be passed directly to the existing divider helper.
    """
    normalized_lines = _normalize_lines(lines)
    normalized_colors, color_warnings = _normalize_colors(
        colors, len(normalized_lines), default_color
    )

    left, top, right, bottom = map(int, region)
    available_width = right - left
    available_height = bottom - top
    if available_width <= 0 or available_height <= 0:
        raise ValueError(f"Invalid headline region: {region}")
    if min_size <= 0 or max_size < min_size:
        raise ValueError("Headline size range is invalid.")
    if not 0.5 <= line_height_ratio <= 1.5:
        raise ValueError("line_height_ratio must be between 0.5 and 1.5.")

    selected_font: Optional[ImageFont.FreeTypeFont] = None
    selected_size = min_size
    selected_widths: List[int] = []
    selected_line_height = 0
    selected_block_width = 0
    selected_block_height = 0

    # Descending search guarantees the largest fitting integer point size.
    for size in range(int(max_size), int(min_size) - 1, -1):
        font = _load_font(font_path, size)
        widths, line_height, block_width, block_height = _measure(
            draw, normalized_lines, font, line_height_ratio
        )
        if block_width <= available_width and block_height <= available_height:
            selected_font = font
            selected_size = size
            selected_widths = widths
            selected_line_height = line_height
            selected_block_width = block_width
            selected_block_height = block_height
            break

    fits = selected_font is not None
    if selected_font is None:
        # Render at the minimum size so the failure is visible and return
        # exact overflow diagnostics. The template can decide whether to
        # reject the slide before production.
        selected_font = _load_font(font_path, min_size)
        selected_size = min_size
        (
            selected_widths,
            selected_line_height,
            selected_block_width,
            selected_block_height,
        ) = _measure(draw, normalized_lines, selected_font, line_height_ratio)

    start_y = _position_top(top, bottom, selected_block_height, balance)
    alignment = (align or "left").strip().lower()
    if alignment not in {"left", "center", "right"}:
        raise ValueError("headline align must be 'left', 'center', or 'right'.")

    y = start_y
    for index, (line, color, width) in enumerate(
        zip(normalized_lines, normalized_colors, selected_widths)
    ):
        if alignment == "center":
            x = left + (available_width - width) // 2
        elif alignment == "right":
            x = right - width
        else:
            x = left
        draw.text((x, y), line, font=selected_font, fill=color)
        if index < len(normalized_lines) - 1:
            y += selected_line_height

    rendered_bottom = start_y + selected_block_height
    widest_index = max(range(len(selected_widths)), key=selected_widths.__getitem__)
    width_overflow = max(0, selected_block_width - available_width)
    height_overflow = max(0, selected_block_height - available_height)

    messages: List[str] = list(color_warnings)
    if not fits:
        messages.append(
            "Headline does not fit at the minimum size. Rewrite one or more lines, "
            "reduce the number of lines, enlarge the region, or lower min_size."
        )
    elif selected_size == min_size:
        messages.append("Headline fits, but only at the configured minimum size.")
    else:
        messages.append("Headline fits within the assigned region.")

    metrics = HeadlineMetrics(
        font_size=selected_size,
        line_height=selected_line_height,
        block_width=selected_block_width,
        block_height=selected_block_height,
        line_widths=tuple(selected_widths),
        top=start_y,
        bottom=rendered_bottom,
        left=left,
        right=right,
    )
    diagnostics = HeadlineDiagnostics(
        fits=fits,
        used_minimum_size=selected_size == min_size,
        width_overflow_px=width_overflow,
        height_overflow_px=height_overflow,
        line_count=len(normalized_lines),
        widest_line_index=widest_index,
        widest_line=normalized_lines[widest_index],
        message=" ".join(messages),
        metrics=metrics,
    )
    return rendered_bottom, diagnostics


def diagnostic_note(prefix: str, diagnostics: HeadlineDiagnostics) -> Optional[str]:
    """Convert diagnostics into a concise QA note for existing templates."""
    if diagnostics.fits and not diagnostics.used_minimum_size:
        return None
    return (
        f"{prefix}: {diagnostics.message} "
        f"size={diagnostics.metrics.font_size}px, "
        f"width_overflow={diagnostics.width_overflow_px}px, "
        f"height_overflow={diagnostics.height_overflow_px}px, "
        f"widest_line={diagnostics.widest_line!r}."
    )
