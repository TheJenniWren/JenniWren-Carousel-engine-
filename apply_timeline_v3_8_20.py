#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

TARGET = Path("carousel_lib.py")
BACKUP = Path("carousel_lib.py.before_timeline_v3_8_20")

NEW_FUNCTION = '''def draw_timeline(draw, entries, y0, line_x=None):
    """Timeline v3.8.20 with stronger body weight and slightly higher placement."""
    TIMELINE_DATE_SIZE = 48
    TIMELINE_BODY_SIZE = 46
    TIMELINE_BODY_LINE_ADVANCE = 56
    TIMELINE_MAX_W = 800
    TIMELINE_LINE_WIDTH = 5
    TIMELINE_NODE_RADIUS = 11
    TIMELINE_TOP_OFFSET = 52
    TIMELINE_MAX_SPAN = 380

    line_x = line_x or (BODY_L + 50)
    text_x = line_x + 78
    text_w = min(TIMELINE_MAX_W, W - R_MARGIN - text_x)

    date_font = lf(BARLOW, TIMELINE_DATE_SIZE)
    body_font = lf(BASK_REG, TIMELINE_BODY_SIZE)

    normalized = []
    for entry in entries:
        date_text = str(entry.get("date") or entry.get("year") or "").strip()
        heading_text = str(entry.get("heading") or "").strip()
        body_text = str(entry.get("text") or entry.get("desc") or "").strip()

        if not body_text and heading_text:
            body_text = heading_text
        elif heading_text and body_text and not body_text.startswith(heading_text):
            body_text = f"{heading_text} {body_text}"

        if date_text or body_text:
            normalized.append((date_text, body_text))

    if not normalized:
        return y0

    start_y = y0 + TIMELINE_TOP_OFFSET
    available_to_footer = max(1, FOOTER_SAFE - 120 - start_y)
    span = min(TIMELINE_MAX_SPAN, available_to_footer)

    if len(normalized) == 1:
        anchors = [start_y]
    else:
        anchors = [
            round(start_y + span * i / (len(normalized) - 1))
            for i in range(len(normalized))
        ]

    node_centers = []

    for anchor_y, (date_text, body_text) in zip(anchors, normalized):
        draw.text((text_x, anchor_y), date_text, font=date_font, fill=PINK)
        date_bbox = draw.textbbox((text_x, anchor_y), date_text, font=date_font)
        date_height = max(1, date_bbox[3] - date_bbox[1])
        body_y = date_bbox[3] + 8

        lines = wrap_lines(draw, [(body_text, WHITE)], body_font, text_w)
        space_w = mw(draw, " ", body_font)

        for line_words in lines:
            x = text_x
            for idx, (word, color) in enumerate(line_words):
                draw.text((x, body_y), word, font=body_font, fill=color)
                x += mw(draw, word, body_font)
                if idx < len(line_words) - 1:
                    x += space_w
            body_y += TIMELINE_BODY_LINE_ADVANCE

        node_centers.append(anchor_y + date_height // 2)

    draw.line(
        [(line_x, node_centers[0]), (line_x, node_centers[-1])],
        fill=PINK,
        width=TIMELINE_LINE_WIDTH,
    )

    for cy in node_centers:
        draw.ellipse(
            [
                line_x - TIMELINE_NODE_RADIUS,
                cy - TIMELINE_NODE_RADIUS,
                line_x + TIMELINE_NODE_RADIUS,
                cy + TIMELINE_NODE_RADIUS,
            ],
            outline=PINK,
            width=TIMELINE_LINE_WIDTH,
            fill=BG,
        )

    return start_y + span
'''


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

    print("Timeline v3.8.20 applied successfully.")
    print("Only draw_timeline() was replaced.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
