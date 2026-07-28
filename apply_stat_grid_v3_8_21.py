#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

CAROUSEL = Path('carousel_lib.py')
DATA = Path('data_templates.py')
CAROUSEL_BACKUP = Path('carousel_lib.py.before_stat_grid_v3_8_21')
DATA_BACKUP = Path('data_templates.py.before_stat_grid_v3_8_21')

NEW_DRAW = '''def draw_stat_grid(draw, items, y0, cols=2, cell_h=250):
    """Stat Grid v3.8.21: larger statistics, labels, and stronger dividers."""
    items = list(items or [])
    if not items:
        return y0

    cols = max(1, int(cols or 2))
    rows = (len(items) + cols - 1) // cols

    grid_left = L_MARGIN
    grid_right = W - R_MARGIN
    grid_w = grid_right - grid_left
    col_w = grid_w / cols

    # Use more of the available vertical field without crowding the footer.
    available_h = max(1, FOOTER_SAFE - y0 - 60)
    cell_h = min(max(int(cell_h or 250), 250), max(250, available_h // rows))

    stat_font = lf(BARLOW, 96)
    label_font = lf(BARLOW, 42)

    divider = (82, 82, 82)
    divider_w = 4

    for idx, item in enumerate(items):
        row = idx // cols
        col = idx % cols
        cell_x0 = int(grid_left + col * col_w)
        cell_x1 = int(grid_left + (col + 1) * col_w)
        cell_y0 = int(y0 + row * cell_h)
        cell_y1 = int(cell_y0 + cell_h)

        stat_text = str(
            item.get('stat_text')
            or item.get('statistic')
            or item.get('value')
            or ''
        ).strip()
        label_text = str(
            item.get('stat_label')
            or item.get('label')
            or ''
        ).strip()

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
                    x += mw(draw, ' ', label_font)
            ly += label_lh

        if col < cols - 1 and idx + 1 < len(items):
            x = int(cell_x1)
            draw.line((x, cell_y0 + 10, x, cell_y1 - 20), fill=divider, width=divider_w)

    for row in range(rows - 1):
        y = int(y0 + (row + 1) * cell_h)
        draw.line((grid_left, y, grid_right, y), fill=divider, width=divider_w)

    return int(y0 + rows * cell_h)
'''


def replace_function(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(
        rf'^def {re.escape(name)}\(.*?(?=^def |^# —|^# ─|\Z)',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError(f'Could not locate {name}() safely.')
    return text[:match.start()] + replacement.rstrip() + '\n\n' + text[match.end():]


def patch_data_templates(text: str) -> str:
    # Increase only the Stat Grid headline range and reduce the gap beneath it.
    old_range = 'sr = tuple(slide.get("headline_range", defaults.grid_headline_range))'
    new_range = 'sr = tuple(slide.get("headline_range", (104, 132)))'
    if old_range in text:
        text = text.replace(old_range, new_range, 1)
    elif new_range not in text:
        raise RuntimeError('Could not locate the Stat Grid headline range line safely.')

    old_gap = 'y0 = cl.draw_headline(draw, headline_lines, colors, cl.HEAD_Y, sr) + 60'
    new_gap = 'y0 = cl.draw_headline(draw, headline_lines, colors, cl.HEAD_Y, sr) + 72'
    if old_gap in text:
        text = text.replace(old_gap, new_gap, 1)
    elif new_gap not in text:
        raise RuntimeError('Could not locate the Stat Grid headline gap line safely.')

    old_cell = 'cell_h=slide.get("grid_cell_h", defaults.grid_cell_h),'
    new_cell = 'cell_h=slide.get("grid_cell_h", 250),'
    if old_cell in text:
        text = text.replace(old_cell, new_cell, 1)
    elif new_cell not in text:
        raise RuntimeError('Could not locate the Stat Grid cell-height line safely.')

    return text


def main() -> int:
    if not CAROUSEL.exists() or not DATA.exists():
        print('ERROR: carousel_lib.py and data_templates.py must both be beside this patch file.')
        return 1

    carousel_text = CAROUSEL.read_text(encoding='utf-8')
    data_text = DATA.read_text(encoding='utf-8')

    if not CAROUSEL_BACKUP.exists():
        shutil.copy2(CAROUSEL, CAROUSEL_BACKUP)
        print(f'Backup created: {CAROUSEL_BACKUP}')
    if not DATA_BACKUP.exists():
        shutil.copy2(DATA, DATA_BACKUP)
        print(f'Backup created: {DATA_BACKUP}')

    try:
        carousel_text = replace_function(carousel_text, 'draw_stat_grid', NEW_DRAW)
        data_text = patch_data_templates(data_text)
    except Exception as exc:
        print(f'ERROR: {exc}')
        print('No source files were written.')
        return 1

    CAROUSEL.write_text(carousel_text, encoding='utf-8')
    DATA.write_text(data_text, encoding='utf-8')

    print('Stat Grid v3.8.21 applied successfully.')
    print('Changed only draw_stat_grid() plus Stat Grid headline/cell sizing.')
    print('Run: python render_carousel.py stories/_studio_live_preview')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
