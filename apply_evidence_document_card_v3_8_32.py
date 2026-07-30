#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "carousel_lib.py"
TEMPLATE = ROOT / "document_templates.py"
LIB_BACKUP = ROOT / "carousel_lib.py.before_evidence_document_card_v3_8_32"
TEMPLATE_BACKUP = ROOT / "document_templates.py.before_evidence_document_card_v3_8_32"

NEW_DRAW_DOCUMENT_CARD = r'''def draw_document_card(draw, img, lines, highlight_line_idxs, ty,
                        card_h=520, annotation=True):
    """Evidence — Document Card v3.8.32.

    Renders a clean editorial evidence card with:
      - aged-paper document surface
      - subtle drop shadow and border
      - automatic line wrapping
      - pink evidence highlights
      - optional annotation arrow

    Returns the y-coordinate where the card ends.
    """
    lines = lines or []
    highlight_line_idxs = set(highlight_line_idxs or [])

    # Normalize Studio values without serializing dictionaries into the slide.
    normalized = []
    for item in lines:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("line") or item.get("content") or "")
        elif isinstance(item, (list, tuple)):
            text = str(item[0]) if item else ""
        else:
            text = str(item)
        if text.strip():
            normalized.append(text.strip())

    card_x0 = L_MARGIN + 22
    card_x1 = W - R_MARGIN - 22
    card_w = card_x1 - card_x0
    shadow = 14

    doc_font_size = 34
    doc_font = lf(BASK_REG, doc_font_size)
    doc_color = (28, 28, 28)
    paper = (242, 238, 228)
    paper_edge = (205, 198, 184)
    shadow_fill = (18, 18, 18)
    pad_x = 54
    pad_top = 70
    text_w = card_w - (pad_x * 2)

    # Wrap each supplied document line while preserving its source-line index,
    # so highlighting remains tied to the editor-selected evidence line.
    wrapped = []
    for source_idx, raw_line in enumerate(normalized):
        words = raw_line.split()
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), trial, font=doc_font)
            if current and bbox[2] - bbox[0] > text_w:
                wrapped.append((current, source_idx))
                current = word
            else:
                current = trial
        if current:
            wrapped.append((current, source_idx))

    asc, desc = doc_font.getmetrics()
    line_h = int((asc + desc) * 1.20)
    needed_h = pad_top + max(1, len(wrapped)) * line_h + 62
    card_h = max(card_h, needed_h)

    # Keep the card inside the available evidence zone.
    max_card_h = max(360, FOOTER_SAFE - ty - 235)
    if card_h > max_card_h:
        while doc_font_size > 25 and card_h > max_card_h:
            doc_font_size -= 1
            doc_font = lf(BASK_REG, doc_font_size)
            wrapped = []
            for source_idx, raw_line in enumerate(normalized):
                words = raw_line.split()
                current = ""
                for word in words:
                    trial = f"{current} {word}".strip()
                    bbox = draw.textbbox((0, 0), trial, font=doc_font)
                    if current and bbox[2] - bbox[0] > text_w:
                        wrapped.append((current, source_idx))
                        current = word
                    else:
                        current = trial
                if current:
                    wrapped.append((current, source_idx))
            asc, desc = doc_font.getmetrics()
            line_h = int((asc + desc) * 1.18)
            card_h = pad_top + max(1, len(wrapped)) * line_h + 62
        card_h = min(card_h, max_card_h)

    # Shadow, paper, and restrained editorial border.
    draw.rounded_rectangle(
        (card_x0 + shadow, ty + shadow, card_x1 + shadow, ty + card_h + shadow),
        radius=8, fill=shadow_fill
    )
    draw.rounded_rectangle(
        (card_x0, ty, card_x1, ty + card_h),
        radius=8, fill=paper, outline=paper_edge, width=2
    )

    # Document marker and source-rule detail.
    marker_font = lf(BARLOW, 25)
    draw.text((card_x0 + pad_x, ty + 24), "OFFICIAL DOCUMENT", font=marker_font, fill=PINK)
    draw.line(
        (card_x0 + pad_x, ty + 55, card_x1 - pad_x, ty + 55),
        fill=(150, 143, 130), width=2
    )

    y = ty + pad_top
    first_highlight_y = None
    for text, source_idx in wrapped:
        bbox = draw.textbbox((0, 0), text, font=doc_font)
        text_width = bbox[2] - bbox[0]
        if source_idx in highlight_line_idxs:
            highlight_y0 = y + 3
            highlight_y1 = y + line_h - 8
            draw.rounded_rectangle(
                (card_x0 + pad_x - 9, highlight_y0,
                 min(card_x1 - pad_x + 8, card_x0 + pad_x + text_width + 12), highlight_y1),
                radius=4, fill=(255, 135, 180)
            )
            if first_highlight_y is None:
                first_highlight_y = (highlight_y0 + highlight_y1) // 2
        draw.text((card_x0 + pad_x, y), text, font=doc_font, fill=doc_color)
        y += line_h

    # Small evidence tag at the bottom of the paper card.
    tag_font = lf(BARLOW, 23)
    tag = "HIGHLIGHTED EVIDENCE"
    tag_box = draw.textbbox((0, 0), tag, font=tag_font)
    tag_w = tag_box[2] - tag_box[0] + 28
    tag_y0 = ty + card_h - 45
    draw.rectangle((card_x1 - pad_x - tag_w, tag_y0,
                    card_x1 - pad_x, tag_y0 + 30), fill=PINK)
    draw.text((card_x1 - pad_x - tag_w + 14, tag_y0 + 3), tag,
              font=tag_font, fill=WHITE)

    if annotation and first_highlight_y is not None:
        # Compact callout arrow pointing directly to the highlighted evidence.
        ax0 = card_x0 - 8
        ax1 = card_x0 + pad_x - 18
        ay = first_highlight_y
        draw.line((ax0 - 34, ay + 30, ax1, ay), fill=PINK, width=5)
        draw.polygon(((ax1, ay), (ax1 - 15, ay - 8), (ax1 - 10, ay + 12)), fill=PINK)

    return ty + card_h
'''

NEW_RENDER_DOCUMENT_CARD = r'''def render_document_card(slide: StorySlide, n: int, total: int, story: StoryPackage,
                         defaults: TemplateDefaults):
    """Evidence — Document Card v3.8.32 baseline renderer."""
    require_fields(slide, "label", "doc_lines", "headline_lines", "headline_colors")
    qa_notes: List[str] = []

    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total,
                    big=bool(slide.get("big_label", False)))

    card_top = 132
    requested_h = int(slide.get("doc_card_h", 500) or 500)
    highlight_idxs = set(slide.get("doc_highlight", []) or [])

    card_bottom = cl.draw_document_card(
        draw,
        img,
        slide.get("doc_lines") or [],
        highlight_idxs,
        card_top,
        card_h=requested_h,
        annotation=bool(slide.get("doc_annotation", True)),
    )

    headline_lines = list(slide.get("headline_lines") or [])
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)

    headline_top = card_bottom + 46
    available_h = cl.FOOTER_SAFE - headline_top - 24
    sr = tuple(slide.get("headline_range", (74, 136)))

    # Let the shared headline engine fit the conclusion beneath the evidence.
    headline_bottom = cl.draw_headline(
        draw, headline_lines, colors, headline_top, sr
    )
    cl.draw_divider(draw, headline_bottom)

    if headline_bottom > cl.FOOTER_SAFE:
        qa_notes.append(
            f"document-card conclusion extends to y={headline_bottom}, "
            f"past footer-safe y={cl.FOOTER_SAFE}; shorten the excerpt or headline."
        )

    cl.draw_footer(
        draw,
        brand_name=story.brand_footer,
        arrow=bool(slide.get("arrow", True)),
    )
    return img, qa_notes
'''


def replace_function(path: Path, name: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^def {re.escape(name)}\(.*?(?=^def |^# ─|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"ERROR: Could not locate {name}() in {path.name}. No files changed.")
    updated = text[:match.start()] + replacement.rstrip() + "\n\n\n" + text[match.end():]
    path.write_text(updated, encoding="utf-8")
    print(f"Updated {name}() in {path.name}.")


def main() -> int:
    if not LIB.exists() or not TEMPLATE.exists():
        print("ERROR: Run this file from the repository root beside carousel_lib.py and document_templates.py.")
        return 1

    if not LIB_BACKUP.exists():
        shutil.copy2(LIB, LIB_BACKUP)
        print(f"Backup created: {LIB_BACKUP.name}")
    if not TEMPLATE_BACKUP.exists():
        shutil.copy2(TEMPLATE, TEMPLATE_BACKUP)
        print(f"Backup created: {TEMPLATE_BACKUP.name}")

    replace_function(LIB, "draw_document_card", NEW_DRAW_DOCUMENT_CARD)
    replace_function(TEMPLATE, "render_document_card", NEW_RENDER_DOCUMENT_CARD)

    print("Evidence — Document Card v3.8.32 applied successfully.")
    print("Changed only draw_document_card() and render_document_card().")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
