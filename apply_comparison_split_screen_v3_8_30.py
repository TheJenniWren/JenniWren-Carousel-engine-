#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "comparison_templates.py"
BACKUP = ROOT / "comparison_templates.py.before_comparison_split_screen_v3_8_30"

NEW_FUNCTION = r'''def render_call_block(slide: StorySlide, n: int, total: int, story: StoryPackage,
                      defaults: TemplateDefaults):
    """Comparison — Split Screen v3.8.30.

    Focused changes:
      1. Parse Studio rich-text body segments correctly.
      2. Widen both text columns.
      3. Use one balanced headline size across both panels.
      4. Improve body wrapping and vertical placement.

    Existing Studio field mapping remains unchanged:
      headline line 1 -> left panel heading
      headline line 2 -> right panel heading
      call_text       -> left panel body
      body            -> right panel body
    """
    require_fields(slide, "label", "call_text")
    qa_notes: List[str] = []

    img, draw = cl.new_canvas()
    split_x = cl.W // 2

    # --- Split canvas -----------------------------------------------------
    draw.rectangle((0, 0, split_x, cl.H), fill=cl.WHITE)
    draw.rectangle((split_x, 0, cl.W, cl.H), fill=cl.BG)
    draw.rectangle((0, 0, cl.W, 8), fill=cl.PINK)

    # --- Top chrome -------------------------------------------------------
    label = str(slide.get("label") or "COMPARISON").upper()
    label_font = cl.lf(cl.BARLOW, 30)
    lb = draw.textbbox((0, 0), label, font=label_font)
    label_w = max(160, lb[2] - lb[0] + 34)
    draw.rectangle((54, 34, 54 + label_w, 82), fill=cl.PINK)
    draw.text((71, 43), label, font=label_font, fill=cl.WHITE)

    page_font = cl.lf(cl.BARLOW, 31)
    page_text = f"{n:02d} / {total:02d}"
    pb = draw.textbbox((0, 0), page_text, font=page_font)
    draw.text((cl.W - 54 - (pb[2] - pb[0]), 42), page_text,
              font=page_font, fill=cl.WHITE)

    headline_lines = list(slide.get("headline_lines") or [])
    left_heading = str(headline_lines[0] if len(headline_lines) > 0 else "WHAT THEY SAID").upper()
    right_heading = str(headline_lines[1] if len(headline_lines) > 1 else "WHAT REALLY HAPPENED").upper()

    # --- Studio rich-text normalization ----------------------------------
    def normalize_segments(value, default_color="white"):
        """Return [(text, color_name), ...] for strings, dicts, lists, or tuples."""
        out = []

        def walk(node, inherited_color=default_color):
            if node is None:
                return
            if isinstance(node, str):
                if node:
                    out.append((node, inherited_color))
                return
            if isinstance(node, dict):
                color = str(node.get("color") or inherited_color).lower()
                if "text" in node:
                    walk(node.get("text"), color)
                    return
                for key in ("segments", "content", "children", "body"):
                    if key in node:
                        walk(node.get(key), color)
                        return
                # Last-resort readable fallback, never stringify the whole dict.
                for candidate in node.values():
                    if isinstance(candidate, str):
                        walk(candidate, color)
                        return
                return
            if isinstance(node, (list, tuple)):
                # A two-item tuple may be (text, color).
                if (len(node) == 2 and isinstance(node[0], str)
                        and isinstance(node[1], str)
                        and node[1].lower() in {"white", "pink", "black"}):
                    out.append((node[0], node[1].lower()))
                    return
                for child in node:
                    walk(child, inherited_color)
                return
            walk(str(node), inherited_color)

        walk(value)
        return [(text, color) for text, color in out if str(text).strip()]

    left_segments = normalize_segments(slide.get("call_text"), "black")
    right_segments = normalize_segments(slide.get("body"), "white")

    # Ensure segment boundaries read naturally when Studio stores sentences separately.
    def token_stream(segments):
        tokens = []
        for text, color_name in segments:
            color_name = str(color_name).lower()
            fill = cl.PINK if color_name == "pink" else (cl.BG if color_name == "black" else cl.WHITE)
            words = str(text).split()
            for word in words:
                tokens.append((word, fill))
        return tokens

    # --- Shared fitting helpers ------------------------------------------
    panel_pad = 48
    gutter = 34
    left_x0 = panel_pad
    left_x1 = split_x - gutter
    right_x0 = split_x + gutter
    right_x1 = cl.W - panel_pad
    panel_w = min(left_x1 - left_x0, right_x1 - right_x0)

    def wrap_plain(text, font, max_w):
        words = str(text).split()
        lines, current = [], ""
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
        return lines

    def headline_layout(text, size):
        font = cl.lf(cl.BARLOW, size)
        lines = wrap_plain(text, font, panel_w)
        asc, desc = font.getmetrics()
        line_h = int((asc + desc) * 0.80)
        return font, lines, line_h

    # One shared size keeps the two sides visually balanced.
    headline_size = 100
    while headline_size >= 62:
        lfnt, llines, llh = headline_layout(left_heading, headline_size)
        rfnt, rlines, rlh = headline_layout(right_heading, headline_size)
        tallest = max(len(llines) * llh, len(rlines) * rlh)
        if len(llines) <= 4 and len(rlines) <= 4 and tallest <= 292:
            break
        headline_size -= 2

    left_h_font, left_h_lines, left_h_lh = headline_layout(left_heading, headline_size)
    right_h_font, right_h_lines, right_h_lh = headline_layout(right_heading, headline_size)

    # --- Headings ---------------------------------------------------------
    heading_y = 174
    y = heading_y
    for line in left_h_lines:
        draw.text((left_x0, y), line, font=left_h_font, fill=cl.BG)
        y += left_h_lh
    left_heading_bottom = y

    y = heading_y
    for line in right_h_lines:
        draw.text((right_x0, y), line, font=right_h_font, fill=cl.WHITE)
        y += right_h_lh
    right_heading_bottom = y

    divider_y = max(left_heading_bottom, right_heading_bottom) + 30
    draw.line((left_x0, divider_y, left_x1, divider_y), fill=cl.PINK, width=5)
    draw.line((right_x0, divider_y, right_x1, divider_y), fill=cl.PINK, width=5)

    # Center VS badge.
    badge_r = 52
    badge_cx = split_x
    badge_cy = divider_y
    draw.ellipse((badge_cx - badge_r, badge_cy - badge_r,
                  badge_cx + badge_r, badge_cy + badge_r), fill=cl.PINK)
    vs_font = cl.lf(cl.BARLOW, 45)
    vb = draw.textbbox((0, 0), "VS.", font=vs_font)
    draw.text((badge_cx - (vb[2] - vb[0]) / 2,
               badge_cy - (vb[3] - vb[1]) / 2 - 5),
              "VS.", font=vs_font, fill=cl.WHITE)

    # --- Rich body wrapping ----------------------------------------------
    body_y = divider_y + 78
    body_max_h = cl.FOOTER_SAFE - body_y - 22

    def fit_rich(tokens, max_w, max_h, start=46, minimum=32):
        size = start
        while size >= minimum:
            font = cl.lf(cl.BASK_REG, size)
            space_w = draw.textlength(" ", font=font)
            lines, current, current_w = [], [], 0.0
            for word, fill in tokens:
                word_w = draw.textlength(word, font=font)
                needed = word_w if not current else space_w + word_w
                if current and current_w + needed > max_w:
                    lines.append(current)
                    current = [(word, fill)]
                    current_w = word_w
                else:
                    if current:
                        current_w += space_w
                    current.append((word, fill))
                    current_w += word_w
            if current:
                lines.append(current)
            asc, desc = font.getmetrics()
            line_h = int((asc + desc) * 1.10)
            if line_h * len(lines) <= max_h:
                return font, lines, line_h
            size -= 1
        font = cl.lf(cl.BASK_REG, minimum)
        return font, lines, int(minimum * 1.18)

    left_tokens = token_stream(left_segments)
    right_tokens = token_stream(right_segments)
    left_b_font, left_b_lines, left_b_lh = fit_rich(left_tokens, panel_w, body_max_h)
    right_b_font, right_b_lines, right_b_lh = fit_rich(right_tokens, panel_w, body_max_h)

    def draw_rich_lines(lines, font, line_h, x0, y0, default_fill):
        space_w = draw.textlength(" ", font=font)
        y = y0
        for line in lines:
            x = x0
            for word_index, (word, fill) in enumerate(line):
                actual_fill = fill if fill is not None else default_fill
                draw.text((x, y), word, font=font, fill=actual_fill)
                x += draw.textlength(word, font=font)
                if word_index < len(line) - 1:
                    x += space_w
            y += line_h
        return y

    draw_rich_lines(left_b_lines, left_b_font, left_b_lh, left_x0, body_y, cl.BG)
    draw_rich_lines(right_b_lines, right_b_font, right_b_lh, right_x0, body_y, cl.WHITE)

    # --- Custom split footer ---------------------------------------------
    footer_y = cl.H - 85
    brand_font = cl.lf(cl.BASK_ITA, 42)
    draw.text((54, footer_y - 12), story.brand_footer, font=brand_font, fill=cl.BG)

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
    print("Comparison — Split Screen v3.8.30 applied successfully.")
    print("Fixed Studio body parsing, widened both panels, balanced the headline scale,")
    print("and improved body wrapping and vertical placement.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
