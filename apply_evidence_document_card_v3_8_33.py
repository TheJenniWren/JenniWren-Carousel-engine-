#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "carousel_lib.py"
TEMPLATE = ROOT / "document_templates.py"
LIB_BACKUP = ROOT / "carousel_lib.py.before_evidence_document_card_v3_8_33"
TEMPLATE_BACKUP = ROOT / "document_templates.py.before_evidence_document_card_v3_8_33"

NEW_DRAW_DOCUMENT_CARD = r'''def draw_document_card(draw, img, lines, highlight_line_idxs, ty,
                        card_h=510, annotation=True):
    """Evidence — Document Card v3.8.33.

    Creates a compact primary-document composition rather than a blank text box:
      - layered paper with slight editorial tilt
      - official-document masthead and date line
      - centered decision/title block
      - yellow evidence highlight
      - annotation callout and redaction lines

    Returns the y-coordinate where the card ends.
    """
    lines = lines or []
    highlight_line_idxs = set(highlight_line_idxs or [])

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

    card_x0 = L_MARGIN + 54
    card_x1 = W - R_MARGIN - 54
    card_w = card_x1 - card_x0
    card_h = max(470, int(card_h or 510))

    paper = (246, 242, 232)
    paper_back = (225, 220, 210)
    paper_edge = (194, 188, 176)
    ink = (28, 28, 28)
    muted = (92, 92, 92)
    highlight = (247, 208, 72)

    # Layered paper edges create a primary-document look without requiring an image asset.
    draw.polygon(
        [(card_x0 + 26, ty + 4), (card_x1 + 8, ty + 18),
         (card_x1 - 4, ty + card_h + 10), (card_x0 + 8, ty + card_h - 2)],
        fill=paper_back,
    )
    draw.polygon(
        [(card_x0, ty + 20), (card_x1 - 18, ty),
         (card_x1, ty + card_h - 14), (card_x0 + 18, ty + card_h)],
        fill=paper,
        outline=paper_edge,
    )

    left = card_x0 + 52
    right = card_x1 - 52
    center = (left + right) // 2

    masthead_font = lf(BARLOW, 24)
    small_font = lf(BARLOW, 19)
    title_font = lf(BARLOW, 31)
    body_font = lf(BASK_REG, 29)
    note_font = lf(BARLOW, 22)

    # Faux government masthead. It provides visual authority while remaining generic.
    masthead = "OFFICIAL RECORD"
    mb = draw.textbbox((0, 0), masthead, font=masthead_font)
    draw.text((center - (mb[2] - mb[0]) // 2, ty + 46), masthead,
              font=masthead_font, fill=ink)
    agency = "UNITED STATES GOVERNMENT"
    ab = draw.textbbox((0, 0), agency, font=small_font)
    draw.text((center - (ab[2] - ab[0]) // 2, ty + 76), agency,
              font=small_font, fill=muted)
    draw.line((left, ty + 108, right, ty + 108), fill=paper_edge, width=2)

    date_text = "DOCUMENT EXCERPT"
    db = draw.textbbox((0, 0), date_text, font=small_font)
    draw.text((center - (db[2] - db[0]) // 2, ty + 122), date_text,
              font=small_font, fill=muted)

    decision = "KEY CONTRACT TERMS"
    tb = draw.textbbox((0, 0), decision, font=title_font)
    draw.text((center - (tb[2] - tb[0]) // 2, ty + 158), decision,
              font=title_font, fill=ink)

    # Use the strongest evidence line as the focal excerpt.
    focus_idx = min(highlight_line_idxs) if highlight_line_idxs else 0
    focus_idx = min(max(focus_idx, 0), max(0, len(normalized) - 1))
    focus = normalized[focus_idx] if normalized else "Document evidence"

    max_focus_w = int(card_w * 0.60)
    focus_lines = []
    current = ""
    for word in focus.split():
        trial = f"{current} {word}".strip()
        bb = draw.textbbox((0, 0), trial, font=body_font)
        if current and bb[2] - bb[0] > max_focus_w:
            focus_lines.append(current)
            current = word
        else:
            current = trial
    if current:
        focus_lines.append(current)
    focus_lines = focus_lines[:3]

    asc, desc = body_font.getmetrics()
    line_h = int((asc + desc) * 1.16)
    focus_y = ty + 225
    max_line_w = 0
    for line in focus_lines:
        bb = draw.textbbox((0, 0), line, font=body_font)
        max_line_w = max(max_line_w, bb[2] - bb[0])

    hx0 = left + 190
    hx1 = min(right - 120, hx0 + max_line_w + 26)
    hy0 = focus_y - 4
    hy1 = focus_y + line_h * len(focus_lines) - 8
    draw.rectangle((hx0 - 10, hy0, hx1, hy1), fill=highlight)

    fy = focus_y
    for line in focus_lines:
        draw.text((hx0, fy), line, font=body_font, fill=ink)
        fy += line_h

    # Right-side annotation callout.
    if annotation:
        note_x = right - 112
        note_y = focus_y + 8
        draw.line((hx1 + 12, focus_y + 22, note_x - 10, note_y + 8), fill=ink, width=4)
        draw.polygon(((hx1 + 10, focus_y + 22),
                      (hx1 + 24, focus_y + 14),
                      (hx1 + 22, focus_y + 30)), fill=ink)
        for i, text in enumerate(("KEY", "DETAIL")):
            draw.text((note_x, note_y + i * 28), text, font=note_font, fill=ink)
        draw.line((note_x, note_y + 62, note_x + 78, note_y + 62), fill=PINK, width=5)

    # Secondary evidence lines and redaction texture.
    secondary = [v for i, v in enumerate(normalized) if i != focus_idx][:2]
    sy = ty + card_h - 132
    sec_font = lf(BASK_REG, 21)
    for line in secondary:
        text = line if len(line) <= 58 else line[:55].rstrip() + "…"
        draw.text((left + 16, sy), text, font=sec_font, fill=muted)
        sy += 27

    red_y = ty + card_h - 68
    for width in (420, 500, 455):
        draw.rectangle((left + 120, red_y, left + 120 + width, red_y + 9), fill=(175, 175, 175))
        red_y += 17

    return ty + card_h
'''

NEW_RENDER_DOCUMENT_CARD = r'''def render_document_card(slide: StorySlide, n: int, total: int, story: StoryPackage,
                         defaults: TemplateDefaults):
    """Evidence — Document Card v3.8.33."""
    require_fields(slide, "label", "doc_lines", "headline_lines", "headline_colors")
    qa_notes: List[str] = []

    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total,
                    big=bool(slide.get("big_label", False)))

    card_top = 112
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

    headline_top = card_bottom + 28
    sr = tuple(slide.get("headline_range", (82, 150)))
    headline_bottom = cl.draw_headline(draw, headline_lines, colors, headline_top, sr)
    cl.draw_divider(draw, headline_bottom + 4)

    if headline_bottom > cl.FOOTER_SAFE - 70:
        qa_notes.append(
            f"document-card conclusion extends to y={headline_bottom}; "
            "shorten the excerpt or headline."
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

    print("Evidence — Document Card v3.8.33 applied successfully.")
    print("Rebuilt the evidence card as a compact primary-document composition.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
