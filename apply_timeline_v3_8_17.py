#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

TARGET = Path("carousel_lib.py")
BACKUP = Path("carousel_lib.py.before_timeline_v3_8_17")
NEW_FUNCTION = 'def draw_timeline(draw, entries, y0, line_x=None):\n    """Timeline v3.8.17 with fixed vertical distribution."""\n    TIMELINE_DATE_SIZE = 48\n    TIMELINE_BODY_SIZE = 42\n    TIMELINE_BODY_LINE_ADVANCE = 52\n    TIMELINE_MAX_W = 800\n    TIMELINE_LINE_WIDTH = 5\n    TIMELINE_NODE_RADIUS = 11\n    TIMELINE_TOP_OFFSET = 70\n    TIMELINE_BOTTOM_BUFFER = 90\n\n    line_x = line_x or (BODY_L + 50)\n    text_x = line_x + 78\n    text_w = min(TIMELINE_MAX_W, W - R_MARGIN - text_x)\n\n    date_font = lf(BARLOW, TIMELINE_DATE_SIZE)\n    body_font = lf(BASK_REG, TIMELINE_BODY_SIZE)\n\n    normalized = []\n    for entry in entries:\n        date_text = str(entry.get("date") or entry.get("year") or "").strip()\n        heading_text = str(entry.get("heading") or "").strip()\n        body_text = str(entry.get("text") or entry.get("desc") or "").strip()\n\n        if not body_text and heading_text:\n            body_text = heading_text\n        elif heading_text and body_text and not body_text.startswith(heading_text):\n            body_text = f"{heading_text} {body_text}"\n\n        if date_text or body_text:\n            normalized.append((date_text, body_text))\n\n    if not normalized:\n        return y0\n\n    start_y = y0 + TIMELINE_TOP_OFFSET\n    end_y = FOOTER_SAFE - TIMELINE_BOTTOM_BUFFER\n\n    if len(normalized) == 1:\n        anchors = [start_y]\n    else:\n        span = max(1, end_y - start_y)\n        anchors = [\n            round(start_y + span * i / (len(normalized) - 1))\n            for i in range(len(normalized))\n        ]\n\n    node_centers = []\n\n    for anchor_y, (date_text, body_text) in zip(anchors, normalized):\n        draw.text((text_x, anchor_y), date_text, font=date_font, fill=PINK)\n        date_bbox = draw.textbbox((text_x, anchor_y), date_text, font=date_font)\n        date_height = max(1, date_bbox[3] - date_bbox[1])\n        body_y = date_bbox[3] + 10\n\n        lines = wrap_lines(draw, [(body_text, WHITE)], body_font, text_w)\n        space_w = mw(draw, " ", body_font)\n\n        for line_words in lines:\n            x = text_x\n            for idx, (word, color) in enumerate(line_words):\n                draw.text((x, body_y), word, font=body_font, fill=color)\n                x += mw(draw, word, body_font)\n                if idx < len(line_words) - 1:\n                    x += space_w\n            body_y += TIMELINE_BODY_LINE_ADVANCE\n\n        node_centers.append(anchor_y + date_height // 2)\n\n    draw.line(\n        [(line_x, node_centers[0]), (line_x, node_centers[-1])],\n        fill=PINK,\n        width=TIMELINE_LINE_WIDTH,\n    )\n\n    for cy in node_centers:\n        draw.ellipse(\n            [\n                line_x - TIMELINE_NODE_RADIUS,\n                cy - TIMELINE_NODE_RADIUS,\n                line_x + TIMELINE_NODE_RADIUS,\n                cy + TIMELINE_NODE_RADIUS,\n            ],\n            outline=PINK,\n            width=TIMELINE_LINE_WIDTH,\n            fill=BG,\n        )\n\n    return end_y\n'

def main() -> int:
    if not TARGET.exists():
        print("ERROR: carousel_lib.py was not found.")
        return 1

    source = TARGET.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^def draw_timeline\(.*?\n(?=^# ── EXAMPLE SLIDE BUILDS|^def _example_standard|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(source)

    if not match:
        print("ERROR: Could not locate draw_timeline(). No files changed.")
        return 1

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print(f"Backup created: {BACKUP}")

    updated = source[:match.start()] + NEW_FUNCTION.rstrip() + "\n\n\n" + source[match.end():]
    TARGET.write_text(updated, encoding="utf-8")

    print("Timeline v3.8.17 applied successfully.")
    print("Only draw_timeline() was replaced.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
