#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB_PATH = ROOT / "carousel_lib.py"
BACKUP = ROOT / "carousel_lib.py.before_stat_grid_v3_8_28"

NEW_DRAW_STAT_GRID = '''def draw_stat_grid(draw, items, y0, cols=2, cell_h=285):
    """Stat Grid v3.8.28: center each statistic block inside its grid cell."""
    items = items or []
    if not items:
        return y0

    normalized = []
    for item in items:
        if isinstance(item, dict):
            stat_text = str(
                item.get("stat_text")
                or item.get("statistic")
                or item.get("value")
                or item.get("number")
                or ""
            ).strip()
            label_text = str(
                item.get("label")
                or item.get("stat_label")
                or item.get("title")
                or ""
            ).strip()
        elif isinstance(item, (list, tuple)):
            stat_text = str(item[0]).strip() if len(item) > 0 else ""
            label_text = str(item[1]).strip() if len(item) > 1 else ""
        else:
            stat_text = str(item).strip()
            label_text = ""

        normalized.append((stat_text, label_text))

    cols = max(1, int(cols or 2))
    rows = max(1, (len(normalized) + cols - 1) // cols)

    GRID_LEFT = L_MARGIN
    GRID_RIGHT = W - R_MARGIN
    grid_w = GRID_RIGHT - GRID_LEFT
    col_w = grid_w / cols
    divider_color = (82, 82, 82)

    VALUE_MAX = 138
    VALUE_MIN = 82
    LABEL_SIZE = 50
    VALUE_TO_LABEL_GAP = 8
    CELL_TOP_PAD = 22
    CELL_SIDE_PAD = 20

    for idx, (stat_text, label_text) in enumerate(normalized):
        row = idx // cols
        col = idx % cols

        cell_left = int(GRID_LEFT + col * col_w)
        cell_right = int(GRID_LEFT + (col + 1) * col_w)
        cell_center = (cell_left + cell_right) // 2
        cell_y = int(y0 + row * cell_h)
        inner_y = cell_y + CELL_TOP_PAD
        inner_w = int(col_w - 2 * CELL_SIDE_PAD)

        value_font = lf(BARLOW, VALUE_MAX)
        while value_font.size > VALUE_MIN:
            bbox = draw.textbbox((0, 0), stat_text, font=value_font)
            if bbox[2] - bbox[0] <= inner_w:
                break
            value_font = lf(BARLOW, value_font.size - 2)

        value_bbox = draw.textbbox((0, 0), stat_text, font=value_font)
        value_w = value_bbox[2] - value_bbox[0]
        value_x = int(cell_center - value_w / 2 - value_bbox[0])
        draw.text((value_x, inner_y), stat_text, font=value_font, fill=PINK)

        placed_value_bbox = draw.textbbox((value_x, inner_y), stat_text, font=value_font)
        label_y = placed_value_bbox[3] + VALUE_TO_LABEL_GAP

        label_font = lf(BARLOW, LABEL_SIZE)
        label_lines = wrap_lines(draw, [(label_text, WHITE)], label_font, inner_w)
        asc, desc = label_font.getmetrics()
        label_lh = int((asc + desc) * 1.02)

        for line_words in label_lines[:2]:
            line_text = " ".join(word for word, _ in line_words)
            line_bbox = draw.textbbox((0, 0), line_text, font=label_font)
            line_w = line_bbox[2] - line_bbox[0]
            x = int(cell_center - line_w / 2 - line_bbox[0])

            for word_index, (word, color) in enumerate(line_words):
                draw.text((x, label_y), word, font=label_font, fill=color)
                x += mw(draw, word, label_font)
                if word_index < len(line_words) - 1:
                    x += mw(draw, " ", label_font)
            label_y += label_lh

        if col < cols - 1 and idx + 1 < len(normalized):
            divider_x = int(cell_right)
            draw.line(
                [(divider_x, cell_y + 4), (divider_x, cell_y + cell_h - 28)],
                fill=divider_color,
                width=3,
            )

    for row in range(rows - 1):
        divider_y = int(y0 + (row + 1) * cell_h - 14)
        draw.line(
            [(GRID_LEFT, divider_y), (GRID_RIGHT, divider_y)],
            fill=divider_color,
            width=3,
        )

    return int(y0 + rows * cell_h)
'''


def replace_function(path: Path, function_name: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^def {re.escape(function_name)}\(.*?(?=^def |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"ERROR: Could not locate {function_name}() in {path.name}. No files changed.")

    updated = text[:match.start()] + replacement.rstrip() + "\n\n\n" + text[match.end():]
    path.write_text(updated, encoding="utf-8")
    print(f"Updated {function_name}() in {path.name}.")


def main() -> int:
    if not LIB_PATH.exists():
        print("ERROR: Run this file from the repository root beside carousel_lib.py.")
        return 1

    if not BACKUP.exists():
        shutil.copy2(LIB_PATH, BACKUP)
        print(f"Backup created: {BACKUP.name}")

    replace_function(LIB_PATH, "draw_stat_grid", NEW_DRAW_STAT_GRID)

    print("Stat Grid v3.8.28 applied successfully.")
    print("Centered every statistic and label within its own grid cell.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
