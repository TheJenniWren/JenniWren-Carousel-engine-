#!/usr/bin/env python3
"""
Apply JenniWren Timeline v3.8.16 safely to the existing carousel_lib.py.

This patch:
- backs up the current carousel_lib.py
- replaces only draw_timeline()
- preserves every other current renderer fix
- supports Studio fields: date + text
- remains compatible with legacy fields: year + heading + desc
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

TARGET = Path("carousel_lib.py")
BACKUP = Path("carousel_lib.py.before_timeline_v3_8_16")

NEW_FUNCTION = 'def draw_timeline(draw, entries, y0, line_x=None):\n    """\n    Timeline v3.8.16\n\n    Enlarges and redistributes timeline event content while leaving the\n    surrounding slide composition unchanged.\n\n    Accepts both:\n      Studio format:\n        {"date": "JAN. 10", "text": "Event description."}\n\n      Legacy format:\n        {"year": "2018", "heading": "Optional heading.", "desc": "Description."}\n    """\n    TIMELINE_DATE_SIZE = 44\n    TIMELINE_BODY_SIZE = 38\n    TIMELINE_BODY_LINE_ADVANCE = 48\n    TIMELINE_EVENT_GAP = 56\n    TIMELINE_MAX_W = 760\n    TIMELINE_LINE_WIDTH = 4\n    TIMELINE_NODE_RADIUS = 10\n    TIMELINE_TOP_OFFSET = 46\n\n    line_x = line_x or (BODY_L + 40)\n    text_x = line_x + 70\n    text_w = min(TIMELINE_MAX_W, W - R_MARGIN - text_x)\n\n    date_font = lf(BARLOW, TIMELINE_DATE_SIZE)\n    body_font = lf(BASK_REG, TIMELINE_BODY_SIZE)\n\n    y = y0 + TIMELINE_TOP_OFFSET\n    node_centers = []\n\n    for entry in entries:\n        date_text = str(entry.get("date") or entry.get("year") or "").strip()\n        heading_text = str(entry.get("heading") or "").strip()\n        body_text = str(entry.get("text") or entry.get("desc") or "").strip()\n\n        if not body_text and heading_text:\n            body_text = heading_text\n        elif heading_text and body_text and not body_text.startswith(heading_text):\n            body_text = f"{heading_text} {body_text}"\n\n        if not date_text and not body_text:\n            continue\n\n        entry_top = y\n\n        draw.text((text_x, y), date_text, font=date_font, fill=PINK)\n        date_bbox = draw.textbbox((text_x, y), date_text, font=date_font)\n        date_height = max(1, date_bbox[3] - date_bbox[1])\n        y = date_bbox[3] + 10\n\n        desc_lines = wrap_lines(\n            draw,\n            [(body_text, WHITE)],\n            body_font,\n            text_w,\n        )\n        space_w = mw(draw, " ", body_font)\n\n        for line_words in desc_lines:\n            x = text_x\n            for index, (word, color) in enumerate(line_words):\n                draw.text((x, y), word, font=body_font, fill=color)\n                x += mw(draw, word, body_font)\n                if index < len(line_words) - 1:\n                    x += space_w\n            y += TIMELINE_BODY_LINE_ADVANCE\n\n        node_centers.append(entry_top + date_height // 2)\n        y += TIMELINE_EVENT_GAP\n\n    if node_centers:\n        draw.line(\n            [(line_x, node_centers[0]), (line_x, node_centers[-1])],\n            fill=PINK,\n            width=TIMELINE_LINE_WIDTH,\n        )\n\n        for cy in node_centers:\n            draw.ellipse(\n                [\n                    line_x - TIMELINE_NODE_RADIUS,\n                    cy - TIMELINE_NODE_RADIUS,\n                    line_x + TIMELINE_NODE_RADIUS,\n                    cy + TIMELINE_NODE_RADIUS,\n                ],\n                outline=PINK,\n                width=TIMELINE_LINE_WIDTH,\n                fill=BG,\n            )\n\n    return y\n'


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: {TARGET} was not found in the current directory.")
        print("Place this file in the repository root beside carousel_lib.py, then run it again.")
        return 1

    source = TARGET.read_text(encoding="utf-8")

    pattern = re.compile(
        r"^def draw_timeline\(.*?\n(?=^# ── EXAMPLE SLIDE BUILDS|^def _example_standard|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    match = pattern.search(source)
    if not match:
        print("ERROR: Could not locate the existing draw_timeline() function safely.")
        print("No files were changed.")
        return 1

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print(f"Backup created: {BACKUP}")
    else:
        print(f"Backup already exists: {BACKUP}")

    updated = source[:match.start()] + NEW_FUNCTION.rstrip() + "\n\n\n" + source[match.end():]
    TARGET.write_text(updated, encoding="utf-8")

    print("Timeline v3.8.16 applied successfully.")
    print("Only draw_timeline() was replaced.")
    print("Next test:")
    print("  python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
