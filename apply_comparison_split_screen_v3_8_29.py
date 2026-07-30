#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "comparison_templates.py"
BACKUP = ROOT / "comparison_templates.py.before_comparison_split_screen_v3_8_29"

NEW_FUNCTION = r'''def render_call_block(slide: StorySlide, n: int, total: int, story: StoryPackage,
                      defaults: TemplateDefaults):
    """Comparison — Split Screen v3.8.29.

    Reuses the existing Studio fields so no form/schema rewrite is required:
      headline line 1 -> left panel heading
      headline line 2 -> right panel heading
      call_text       -> left panel body
      body            -> right panel body
    """
    require_fields(slide, "label", "call_text")
    qa_notes: List[str] = []

    img, draw = cl.new_canvas()

    # --- Split canvas -----------------------------------------------------
    split_x = cl.W // 2
    draw.rectangle((0, 0, split_x, cl.H), fill=cl.WHITE)
    draw.rectangle((split_x, 0, cl.W, cl.H), fill=cl.BG)

    # Brand frame and top chrome.
    draw.rectangle((0, 0, cl.W, 8), fill=cl.PINK)
    label = str(slide.get("label") or "COMPARISON").upper()
    label_font = cl.lf(cl.BARLOW, 30)
    lb = draw.textbbox((0, 0), label, font=label_font)
    label_w = max(160, lb[2] - lb[0] + 34)
    draw.rectangle((54, 34, 54 + label_w, 82), fill=cl.PINK)
    draw.text((71, 43), label, font=label_font, fill=cl.WHITE)

    page_font = cl.lf(cl.BARLOW, 31)
    page_text = f"{n:02d} / {total:02d}"
    pb = draw.textbbox((0, 0), page_text, font=page_font)
    draw.text((cl.W - 54 - (pb[2] - pb[0]), 42), page_text, font=page_font, fill=cl.WHITE)

    headline_lines = list(slide.get("headline_lines") or [])
    left_heading = str(headline_lines[0] if len(headline_lines) > 0 else "WHAT THEY SAID").upper()
    right_heading = str(headline_lines[1] if len(headline_lines) > 1 else "WHAT REALLY HAPPENED").upper()
    left_body = str(slide.get("call_text") or "")
    right_body = str(slide.get("body") or "")

    # --- Local fitting helpers -------------------------------------------
    def fit_condensed(text, max_w, max_h, start=106, minimum=62):
        size = start
        while size >= minimum:
            font = cl.lf(cl.BARLOW, size)
            words = text.split()
            lines = []
            current = ""
            for word in words:
                trial = f"{current} {word}".strip()
                box = draw.textbbox((0, 0), trial, font=font)
                if current and box[2] - box[0] > max_w:
                    lines.append(current)
                    current = word
                else:
                    current = trial
            if current:
                lines.append(current)
            asc, desc = font.getmetrics()
            line_h = int((asc + desc) * 0.82)
            if len(lines) <= 4 and line_h * len(lines) <= max_h:
                return font, lines, line_h
            size -= 2
        font = cl.lf(cl.BARLOW, minimum)
        return font, [text], int(minimum * 0.86)

    def fit_serif(text, max_w, max_h, start=48, minimum=34):
        size = start
        while size >= minimum:
            font = cl.lf(cl.BASK_REG, size)
            words = text.split()
            lines = []
            current = ""
            for word in words:
                trial = f"{current} {word}".strip()
                box = draw.textbbox((0, 0), trial, font=font)
                if current and box[2] - box[0] > max_w:
                    lines.append(current)
                    current = word
                else:
                    current = trial
            if current:
                lines.append(current)
            asc, desc = font.getmetrics()
            line_h = int((asc + desc) * 1.12)
            if line_h * len(lines) <= max_h:
                return font, lines, line_h
            size -= 1
        font = cl.lf(cl.BASK_REG, minimum)
        return font, [text], int(minimum * 1.18)

    panel_pad = 72
    panel_w = split_x - (panel_pad * 2)

    # --- Headings ---------------------------------------------------------
    heading_y = 180
    left_h_font, left_h_lines, left_h_lh = fit_condensed(left_heading, panel_w, 360)
    right_h_font, right_h_lines, right_h_lh = fit_condensed(right_heading, panel_w, 360)

    y = heading_y
    for line in left_h_lines:
        draw.text((panel_pad, y), line, font=left_h_font, fill=cl.BG)
        y += left_h_lh
    left_heading_bottom = y

    y = heading_y
    for line in right_h_lines:
        draw.text((split_x + panel_pad, y), line, font=right_h_font, fill=cl.WHITE)
        y += right_h_lh
    right_heading_bottom = y

    divider_y = max(left_heading_bottom, right_heading_bottom) + 34
    draw.line((panel_pad, divider_y, split_x - panel_pad, divider_y), fill=cl.PINK, width=5)
    draw.line((split_x + panel_pad, divider_y, cl.W - panel_pad, divider_y), fill=cl.PINK, width=5)

    # Center VS badge.
    badge_r = 55
    badge_cx = split_x
    badge_cy = divider_y
    draw.ellipse((badge_cx - badge_r, badge_cy - badge_r,
                  badge_cx + badge_r, badge_cy + badge_r), fill=cl.PINK)
    vs_font = cl.lf(cl.BARLOW, 47)
    vs = "VS."
    vb = draw.textbbox((0, 0), vs, font=vs_font)
    draw.text((badge_cx - (vb[2] - vb[0]) / 2,
               badge_cy - (vb[3] - vb[1]) / 2 - 5),
              vs, font=vs_font, fill=cl.WHITE)

    # --- Body copy --------------------------------------------------------
    body_y = divider_y + 86
    body_max_h = cl.FOOTER_SAFE - body_y - 28

    left_b_font, left_b_lines, left_b_lh = fit_serif(left_body, panel_w, body_max_h)
    right_b_font, right_b_lines, right_b_lh = fit_serif(right_body, panel_w, body_max_h)

    y = body_y
    for line in left_b_lines:
        draw.text((panel_pad, y), line, font=left_b_font, fill=cl.BG)
        y += left_b_lh

    y = body_y
    for line in right_b_lines:
        draw.text((split_x + panel_pad, y), line, font=right_b_font, fill=cl.WHITE)
        y += right_b_lh

    # --- Custom split footer ---------------------------------------------
    footer_y = cl.H - 85
    brand_font = cl.lf(cl.BASK_ITA, 42)
    draw.text((54, footer_y - 12), story.brand_footer, font=brand_font, fill=cl.BG)

    # Pink right arrow on black panel.
    ax = cl.W - 86
    ay = footer_y + 5
    draw.rectangle((ax - 48, ay - 12, ax + 7, ay + 12), fill=cl.PINK)
    draw.polygon([(ax + 7, ay - 28), (ax + 42, ay), (ax + 7, ay + 28)], fill=cl.PINK)
    draw.rectangle((0, cl.H - 8, cl.W, cl.H), fill=cl.PINK)

    return img, qa_notes
'''


def replace_function(path: Path, function_name: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^def {re.escape(function_name)}\(.*?(?=^def |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise SystemExit(
            f"ERROR: Could not locate {function_name}() in {path.name}. No changes were written."
        )
    updated = text[:match.start()] + replacement.rstrip() + "\n\n\n" + text[match.end():]
    path.write_text(updated, encoding="utf-8")


def main() -> int:
    if not TARGET.exists():
        print("ERROR: Run this file from the repository root beside comparison_templates.py.")
        return 1

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print(f"Backup created: {BACKUP.name}")

    replace_function(TARGET, "render_call_block", NEW_FUNCTION)
    print("Comparison — Split Screen v3.8.29 applied successfully.")
    print("Existing Studio fields are reused; no dashboard schema change is required.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
