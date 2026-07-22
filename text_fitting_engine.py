"""
text_fitting_engine.py

Editorial composition engine for Pillow-based editorial graphics.

Version 3.7.2 replaces the old "shrink one point at a time, take the first
layout that fits" algorithm with an editorial composition engine:

    * Fixed editorial font sizes (a curated type scale) instead of a
      pixel-by-pixel shrink loop.
    * Multiple candidate line-break layouts per size (greedy fill,
      reduced-width fills, and a balanced/raggedness-minimizing DP wrap).
    * A scoring function that rewards balanced line lengths, semantic
      (punctuation-aware) breaks, good paragraph shape, and optical
      symmetry, while penalizing widows/orphans.
    * Semantic-aware tokenization that keeps names, dates, numbers,
      quoted phrases, and abbreviations from being split across a
      line break.

Public API is unchanged and fully backward compatible:

    wrap_text(text, font, max_width, draw)
    measure_lines(draw, lines, font, line_spacing=4)
    fit_text(draw, text, font_loader, max_width, max_height,
             start_size=72, min_size=12, line_spacing=4)
    draw_fitted_text(draw, box, text, font_loader, fill="#000000",
                      align="center", valign="middle",
                      start_size=72, min_size=12, line_spacing=4)
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Sequence, Tuple

from PIL import ImageDraw

FontLoader = Callable[[int], Any]


# ---------------------------------------------------------------------------
# Semantic tokenization
#
# We identify spans of text that should never be broken across a line
# (quoted phrases, dates, numbers, abbreviations, short Title-Case name
# sequences) and glue them into single wrap-atomic tokens before any
# line-breaking logic runs.
# ---------------------------------------------------------------------------

_QUOTED_RE = re.compile(r'"[^"]*"|\'[^\']*\'')

_MONTH_DATE_RE = re.compile(
    r"\b(?:Jan\.?|Feb\.?|Mar\.?|Apr\.?|May|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|"
    r"Oct\.?|Nov\.?|Dec\.?|January|February|March|April|June|July|August|"
    r"September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?"
    r"(?:,\s*\d{2,4})?\b"
)
_NUMERIC_DATE_RE = re.compile(r"\b\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b")
_NUMBER_RE = re.compile(r"\b\$?\d[\d,]*(?:\.\d+)?%?\b")
_ABBREV_RE = re.compile(
    r"\b(?:[A-Z]\.){2,}|"
    r"\b(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|vs|Rep|Sen|Gov|Gen|Lt|Col|Capt|Rev)\.\s?\S+"
)
# Short runs of Title-Case words: a lightweight heuristic for proper names
# ("Nancy Pelosi", "Joe Biden Jr.") so first/last names stay together.
_TITLE_SEQUENCE_RE = re.compile(
    r"\b[A-Z][a-zA-Z'\u2019.-]*(?:\s+[A-Z][a-zA-Z'\u2019.-]*){1,3}\b"
)

_PROTECTED_PATTERNS = (
    _QUOTED_RE,
    _NUMERIC_DATE_RE,
    _MONTH_DATE_RE,
    _NUMBER_RE,
    _ABBREV_RE,
    _TITLE_SEQUENCE_RE,
)

_NBSP = "\u00A0"


def _protected_spans(text: str) -> List[Tuple[int, int]]:
    """Find and merge character spans that must not be split by wrapping."""
    spans: List[Tuple[int, int]] = []
    for pattern in _PROTECTED_PATTERNS:
        for match in pattern.finditer(text):
            if match.end() > match.start():
                spans.append((match.start(), match.end()))

    if not spans:
        return []

    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _semantic_tokens(text: str) -> List[str]:
    """
    Split text into wrap-atomic tokens.

    Protected spans (quotes, dates, numbers, abbreviations, name-like
    sequences) have their internal spaces swapped for a non-breaking
    marker so a plain ``str.split()`` keeps them whole, then the marker
    is restored for display.
    """
    text = text.strip()
    if not text:
        return []

    spans = _protected_spans(text)
    if not spans:
        return text.split()

    pieces: List[str] = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            pieces.append(text[cursor:start])
        pieces.append(text[start:end].replace(" ", _NBSP))
        cursor = end
    if cursor < len(text):
        pieces.append(text[cursor:])

    joined = "".join(pieces)
    return [tok.replace(_NBSP, " ") for tok in joined.split()]


# ---------------------------------------------------------------------------
# Low level measurement helpers
# ---------------------------------------------------------------------------

def _text_width(draw: ImageDraw.ImageDraw, s: str, font: Any) -> float:
    if not s:
        return 0.0
    return draw.textbbox((0, 0), s, font=font)[2]


# ---------------------------------------------------------------------------
# Candidate line-break generation
# ---------------------------------------------------------------------------

def _pack_greedy(
    tokens: Sequence[str],
    font: Any,
    draw: ImageDraw.ImageDraw,
    target_width: float,
) -> List[str]:
    """Greedily fill each line up to ``target_width`` (max fill)."""
    if not tokens:
        return [""]

    lines: List[str] = []
    current = tokens[0]
    for token in tokens[1:]:
        test = f"{current} {token}"
        if _text_width(draw, test, font) <= target_width:
            current = test
        else:
            lines.append(current)
            current = token
    lines.append(current)
    return lines


def _pack_balanced(
    tokens: Sequence[str],
    font: Any,
    draw: ImageDraw.ImageDraw,
    max_width: float,
) -> List[str]:
    """
    Break tokens into lines that minimize raggedness (sum of squared
    leftover space per line), subject to no line exceeding max_width.
    This is a small dynamic-programming paragraph balancer in the spirit
    of TeX's line-breaking, simplified for editorial short-form copy.
    """
    n = len(tokens)
    if n == 0:
        return [""]

    widths = [_text_width(draw, tok, font) for tok in tokens]
    space_w = _text_width(draw, "M M", font) - _text_width(draw, "MM", font)
    space_w = space_w if space_w > 0 else 1.0

    INF = float("inf")
    dp = [INF] * (n + 1)
    dp[0] = 0.0
    breaks = [0] * (n + 1)

    for j in range(1, n + 1):
        line_width = -space_w
        for i in range(j, 0, -1):
            line_width += widths[i - 1] + space_w
            fits = line_width <= max_width
            if not fits and i < j:
                break  # adding more tokens only makes this line wider
            cost = 0.0 if not fits else (max_width - line_width) ** 2
            candidate = dp[i - 1] + cost
            if candidate < dp[j]:
                dp[j] = candidate
                breaks[j] = i - 1

    cuts = [n]
    idx = n
    while idx > 0:
        idx = breaks[idx]
        cuts.append(idx)
    cuts.reverse()

    return [" ".join(tokens[cuts[k]:cuts[k + 1]]) for k in range(len(cuts) - 1)]


def _generate_candidate_linesets(
    tokens: Sequence[str],
    font: Any,
    draw: ImageDraw.ImageDraw,
    max_width: float,
) -> List[List[str]]:
    """Produce a diverse set of valid line-break layouts to score."""
    candidates: List[List[str]] = [
        _pack_greedy(tokens, font, draw, max_width),
        _pack_balanced(tokens, font, draw, max_width),
    ]

    # Reduced target widths encourage more (and more evenly broken) lines,
    # giving the scorer real alternatives for multi-line headlines.
    for fraction in (0.92, 0.85, 0.78, 0.70, 0.62):
        candidates.append(_pack_greedy(tokens, font, draw, max_width * fraction))

    seen = set()
    unique: List[List[str]] = []
    for lines in candidates:
        key = tuple(lines)
        if key not in seen:
            seen.add(key)
            unique.append(lines)
    return unique


# ---------------------------------------------------------------------------
# Editorial scoring
# ---------------------------------------------------------------------------

_BREAK_PUNCTUATION = (",", ".", ";", ":", "\u2014", "\u2013", "-", "?", "!")


def _score_layout(
    lines: Sequence[str],
    font: Any,
    draw: ImageDraw.ImageDraw,
    max_width: float,
    max_height: float,
    line_spacing: int,
) -> float:
    """
    Score a candidate layout. Higher is better. Layouts that overflow the
    bounding box are rejected outright (``-inf``).
    """
    if not lines:
        return float("-inf")

    w, h, _ = measure_lines(draw, lines, font, line_spacing)
    if w > max_width + 0.5 or h > max_height + 0.5:
        return float("-inf")

    line_widths = [_text_width(draw, ln, font) for ln in lines]
    n = len(lines)

    # --- balanced line lengths: low variance among the "body" lines
    # (all but the last, which is naturally allowed to be shorter). ---
    if n > 1:
        body = line_widths[:-1]
        mean_body = sum(body) / len(body)
        variance = sum((x - mean_body) ** 2 for x in body) / len(body)
        balance_score = -variance / (max_width ** 2 + 1.0)
    else:
        balance_score = 0.0

    # --- paragraph shape / fullness: reward good use of the available
    # width without needing to touch its edge every line. ---
    fullness_score = sum(lw / max_width for lw in line_widths) / n

    # --- widow / orphan avoidance ---
    widow_penalty = 0.0
    last_word_count = len(lines[-1].split())
    if n > 1:
        if last_word_count == 1:
            widow_penalty += 6.0
        elif line_widths[-1] < 0.25 * max_width:
            widow_penalty += 2.0
        if n > 2 and len(lines[0].split()) == 1:
            widow_penalty += 3.0  # orphaned opening line

    # --- semantic, punctuation-aware breaks: reward line breaks that
    # land right after a natural clause boundary. ---
    semantic_bonus = 0.0
    for ln in lines[:-1]:
        stripped = ln.rstrip()
        if stripped and stripped[-1] in _BREAK_PUNCTUATION:
            semantic_bonus += 1.5

    # --- mild preference for compact stacks; long stacks read poorly
    # in editorial layouts. ---
    shape_penalty = max(0, n - 3) * 1.0

    # --- optical symmetry: penalize large jumps in width between
    # consecutive lines (jagged silhouettes). ---
    symmetry_penalty = 0.0
    for i in range(1, n):
        jump = abs(line_widths[i] - line_widths[i - 1]) / max_width
        if jump > 0.5:
            symmetry_penalty += (jump - 0.5) * 2.0

    return (
        balance_score * 10.0
        + fullness_score * 4.0
        + semantic_bonus
        - widow_penalty
        - shape_penalty
        - symmetry_penalty
    )


def _relieve_widow(
    lines: List[str],
    font: Any,
    draw: ImageDraw.ImageDraw,
    max_width: float,
) -> List[str]:
    """
    If the winning layout still ends in a single-word widow, try pulling
    the last word of the preceding line down to build a more balanced
    closing pair. Only applied if the result still fits max_width.
    """
    if len(lines) < 2 or len(lines[-1].split()) != 1:
        return lines

    prev_words = lines[-2].split()
    if len(prev_words) < 2:
        return lines

    pulled_word = prev_words[-1]
    new_prev = " ".join(prev_words[:-1])
    new_last = f"{pulled_word} {lines[-1]}"

    if _text_width(draw, new_last, font) <= max_width:
        return lines[:-2] + [new_prev, new_last]
    return lines


# ---------------------------------------------------------------------------
# Editorial type scale
# ---------------------------------------------------------------------------

# A curated set of "nice" editorial point sizes, largest first. fit_text()
# steps through these (bounded by start_size/min_size) rather than shrinking
# one point at a time, matching the fixed-scale approach editorial systems
# typically use for headline hierarchy.
_EDITORIAL_SCALE = [
    96, 88, 80, 72, 64, 60, 56, 52, 48, 44, 40, 36,
    32, 28, 26, 24, 22, 20, 18, 16, 14, 12, 10, 8,
]


def _editorial_sizes(start_size: int, min_size: int) -> List[int]:
    """Return the editorial scale clamped to [min_size, start_size]."""
    sizes = [s for s in _EDITORIAL_SCALE if min_size <= s <= start_size]
    if start_size not in sizes:
        sizes.append(start_size)
    if min_size not in sizes:
        sizes.append(min_size)
    return sorted(set(sizes), reverse=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def wrap_text(text: str, font: Any, max_width: float, draw: ImageDraw.ImageDraw) -> List[str]:
    """
    Wrap text to fit a pixel width (legacy simple API, preserved for
    callers that use it directly rather than going through fit_text /
    draw_fitted_text).

    Uses semantic-aware tokenization so names, dates, numbers, quoted
    phrases, and abbreviations are never split across a line break, then
    packs tokens greedily to fill each line.
    """
    tokens = _semantic_tokens(text)
    if not tokens:
        return [""]
    return _pack_greedy(tokens, font, draw, max_width)


def measure_lines(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    font: Any,
    line_spacing: int = 4,
) -> Tuple[float, float, float]:
    """Return width and height of wrapped lines (unchanged from 3.7.1)."""
    width = 0.0
    line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        width = max(width, w)
    height = len(lines) * line_h + (len(lines) - 1) * line_spacing
    return width, height, line_h


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_loader: FontLoader,
    max_width: float,
    max_height: float,
    start_size: int = 72,
    min_size: int = 12,
    line_spacing: int = 4,
) -> Tuple[Any, List[str], int]:
    """
    Compose text into the best-fitting editorial layout.

    Steps through a fixed editorial type scale (largest first). At each
    size, generates several candidate line-break layouts (greedy fill,
    balance-minimizing DP wrap, and reduced-width fills) and scores them
    on balanced line lengths, semantic/punctuation-aware breaks, widow
    and orphan avoidance, paragraph shape, and optical symmetry. The
    first size with at least one layout that fits the box wins; among
    that size's candidates, the highest-scoring layout is chosen and a
    final widow-relief pass is applied.

    Returns:
        font, lines, font_size  (return shape unchanged from 3.7.1)
    """
    fallback: Tuple[Any, List[str], int] | None = None

    for size in _editorial_sizes(start_size, min_size):
        font = font_loader(size)
        tokens = _semantic_tokens(text)

        if not tokens:
            return font, [""], size

        candidates = _generate_candidate_linesets(tokens, font, draw, max_width)

        best_lines = None
        best_score = float("-inf")
        for lines in candidates:
            score = _score_layout(lines, font, draw, max_width, max_height, line_spacing)
            if score > best_score:
                best_score = score
                best_lines = lines

        if best_lines is not None:
            best_lines = _relieve_widow(best_lines, font, draw, max_width)
            return font, best_lines, size

        if fallback is None:
            fallback = (font, _pack_greedy(tokens, font, draw, max_width), size)

    # Nothing fit within bounds even at min_size: fall back to a simple
    # greedy wrap at the smallest editorial size, matching legacy
    # graceful-degradation behaviour.
    if fallback is not None:
        return fallback

    font = font_loader(min_size)
    lines = wrap_text(text, font, max_width, draw)
    return font, lines, min_size


def draw_fitted_text(
    draw: ImageDraw.ImageDraw,
    box: Tuple[float, float, float, float],
    text: str,
    font_loader: FontLoader,
    fill: str = "#000000",
    align: str = "center",
    valign: str = "middle",
    start_size: int = 72,
    min_size: int = 12,
    line_spacing: int = 4,
) -> Dict[str, Any]:
    """
    Draw text composed by fit_text() inside a bounding box.

    box = (left, top, right, bottom)

    Returns
    -------
    dict with font_size, lines, width, height (unchanged from 3.7.1)
    """
    left, top, right, bottom = box

    max_width = right - left
    max_height = bottom - top

    font, lines, size = fit_text(
        draw,
        text,
        font_loader,
        max_width,
        max_height,
        start_size=start_size,
        min_size=min_size,
        line_spacing=line_spacing,
    )

    w, h, line_h = measure_lines(draw, lines, font, line_spacing)

    if valign == "top":
        y = top
    elif valign == "bottom":
        y = bottom - h
    else:
        y = top + (max_height - h) / 2

    for line in lines:
        tw = draw.textbbox((0, 0), line, font=font)[2]

        if align == "left":
            x = left
        elif align == "right":
            x = right - tw
        else:
            x = left + (max_width - tw) / 2

        draw.text((x, y), line, font=font, fill=fill)
        y += line_h + line_spacing

    return {
        "font_size": size,
        "lines": lines,
        "width": w,
        "height": h,
    }
