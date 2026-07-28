#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

TARGET = Path("carousel_lib.py")
BACKUP = Path("carousel_lib.py.before_stat_grid_v3_8_22")

NEW_FUNCTION = '''def draw_stat_grid(draw, items, y0, cols=2, cell_h=250):
    """Stat Grid v3.8.22: larger type with tuple/dict compatibility."""
    items = list(items or [])
    if not items:
        return y0

    cols = max(1, int(cols or 2))
    rows = (len(items) + cols - 1) // cols

    grid_left = L_MARGIN
    grid_right = W - R_MARGIN
    grid_w = grid_right - grid_left
    col_w = grid_w / cols

    available_h = max(1, FOOTER_SAFE - y0 - 60)
    cell_h = min(max(int(cell_h or 250), 250), max(250, available_h // rows))

    stat_font = lf(BARLOW, 96)
    label_font = lf(BARLOW, 42)

    divider = (82, 82, 82)
    divider_w = 4

    def normalize_item(item):
        # Studio currently passes each statistic to this helper as a tuple.
        # Retain dictionary support for direct renderer calls and older payloads.
        if isinstance(item, dict):
            stat_text = (
                item.get("stat_text")
                or item.get("statistic")
                or item.get("value")
                or ""
            )
            label_text = item.get("stat_label") or item.get("label") or ""
            return str(stat_text).strip(), str(label_text).strip()

        if isinstance(item, (tuple, list)):
            stat_text = item[0] if len(item) > 0 else ""
            label_text = item[1] if len(item) > 1 else ""
            return str(stat_text).strip(), str(label_text).strip()

        return str(item).strip(), ""

    for idx, item in enumerate(items):
        stat_text, label_text = normalize_item(item)

        row = idx // cols
        col = idx % cols
        cell_x0 = int(grid_left + col * col_w)
        cell_x1 = int(grid_left + (col + 1) * col_w)
        cell_y0 = int(y0 + row * cell_h)
        cell_y1 = int(cell_y0 + cell_h)

        text_x = cell_x0 + 18
        stat_y = cell_y0 + 24
        label_y = stat_y + 104

        draw.text((text_x, stat_y), stat_text, font=stat_font, fill=PINK)

        label_w = max(80, cell_x1 - text_x - 18)
        label_lines = wrap_lines(draw, [(label_text, WHITE)], label_font, label_w)
        asc, desc = label_font.getmetrics()
        label_lh = int((asc + desc) * 1.05)

        ly = label_y
        for words in label_lines:
            x = text_x
            for i, (word, color) in enumerate(words):
                draw.text((x, ly), word, font=label_font, fill=color)
                x += mw(draw, word, label_font)
                if i < len(words) - 1:
                    x += mw(draw, " ", label_font)
            ly += label_lh

        if col < cols - 1 and idx + 1 < len(items):
            x = int(cell_x1)
            draw.line((x, cell_y0 + 10, x, cell_y1 - 20), fill=divider, width=divider_w)

    for row in range(rows - 1):
        y = int(y0 + (row + 1) * cell_h)
        draw.line((grid_left, y, grid_right, y), fill=divider, width=divider_w)

    return int(y0 + rows * cell_h)
'''


def main() -> int:
    if not TARGET.exists():
        print("ERROR: carousel_lib.py was not found.")
        return 1

    source = TARGET.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^def draw_stat_grid\(.*?(?=^def |^# —|^# ─|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(source)

    if not match:
        print("ERROR: Could not locate draw_stat_grid(). No files changed.")
        return 1

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print(f"Backup created: {BACKUP}")

    updated = source[:match.start()] + NEW_FUNCTION.rstrip() + "\n\n" + source[match.end():]
    TARGET.write_text(updated, encoding="utf-8")

    print("Stat Grid v3.8.22 applied successfully.")
    print("Fixed Studio tuple compatibility; retained v3.8.21 sizing.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
