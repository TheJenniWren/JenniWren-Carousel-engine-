#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COVER = ROOT / "cover_templates.py"
DASHBOARD = ROOT / "carousel_dashboard.py"

BACKUPS = {
    COVER: ROOT / "cover_templates.py.before_cover_quote_lead_v3_8_36",
    DASHBOARD: ROOT / "carousel_dashboard.py.before_cover_quote_lead_v3_8_36",
}

NEW_RENDER = r'''def render_quote_lead(slide: StorySlide, n: int, total: int, story: StoryPackage,
                      defaults: TemplateDefaults):
    """Cover — Quote Lead v3.8.36.

    Dedicated quote-cover hierarchy:
      1. oversized opening quotation mark
      2. fitted Libre Baskerville quote
      3. closing quotation mark
      4. attribution + optional role/source/date
      5. divider
      6. contextual headline + short explanatory deck

    Inline pink emphasis is supported with either:
      <pink>important words</pink>
      [[pink:important words]]
    """
    require_fields(slide, "label", "quote_lines", "attribution")
    qa_notes: List[str] = []

    img, draw = cl.new_canvas()
    cl.draw_top_bar(
        draw,
        slide.get("label"),
        n,
        total,
        big=bool(slide.get("big_label", False)),
    )

    def normalize_segments(value, default_fill=cl.WHITE):
        segments = []

        def add(text, fill):
            text = str(text or "")
            if text.strip():
                segments.append((text.strip(), fill))

        def parse_inline(text, base_fill):
            text = str(text or "")
            pattern = re.compile(r"(<pink>.*?</pink>|\[\[pink:.*?\]\])", re.IGNORECASE | re.DOTALL)
            pos = 0
            for match in pattern.finditer(text):
                if match.start() > pos:
                    add(text[pos:match.start()], base_fill)
                token = match.group(0)
                if token.lower().startswith("<pink>"):
                    add(token[6:-7], cl.PINK)
                else:
                    add(token[7:-2], cl.PINK)
                pos = match.end()
            if pos < len(text):
                add(text[pos:], base_fill)

        def walk(node, inherited_fill=default_fill):
            if node is None:
                return
            if isinstance(node, str):
                parse_inline(node, inherited_fill)
                return
            if isinstance(node, dict):
                color = str(node.get("color") or "white").lower()
                fill = cl.PINK if color == "pink" else inherited_fill
                if "text" in node:
                    parse_inline(node.get("text"), fill)
                    return
                for key in ("segments", "content", "children", "body"):
                    if key in node:
                        walk(node.get(key), fill)
                        return
                return
            if isinstance(node, (list, tuple)):
                for child in node:
                    walk(child, inherited_fill)
                return
            parse_inline(str(node), inherited_fill)

        walk(value)
        return segments

    def wrap_rich(segments, font, max_w):
        words = []
        for text, fill in segments:
            for word in str(text).split():
                words.append((word, fill))
        lines = []
        current = []
        current_w = 0.0
        space_w = cl.mw(draw, " ", font)
        for word, fill in words:
            word_w = cl.mw(draw, word, font)
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
        return lines

    def draw_rich_lines(lines, font, x, y, line_h):
        space_w = cl.mw(draw, " ", font)
        for line in lines:
            cx = x
            for idx, (word, fill) in enumerate(line):
                draw.text((cx, y), word, font=font, fill=fill)
                cx += cl.mw(draw, word, font)
                if idx < len(line) - 1:
                    cx += space_w
            y += line_h
        return y

    # --- Quote block -----------------------------------------------------
    quote_source = slide.get("quote_lines") or []
    quote_segments = normalize_segments(" ".join(str(v) for v in quote_source), cl.WHITE)
    if not quote_segments:
        quote_segments = [("Quote", cl.WHITE)]

    quote_x = cl.L_MARGIN + 122
    quote_y = 170
    quote_w = cl.W - quote_x - cl.R_MARGIN - 36
    quote_limit = 710

    opening_font = cl.lf(cl.BASK_REG, 170)
    draw.text((cl.L_MARGIN - 6, 112), "“", font=opening_font, fill=cl.PINK)

    quote_font = None
    quote_lines = None
    quote_lh = None
    for size in range(76, 43, -2):
        font = cl.lf(cl.BASK_REG, size)
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * 1.02)
        lines = wrap_rich(quote_segments, font, quote_w)
        if len(lines) <= 6 and quote_y + len(lines) * lh <= quote_limit:
            quote_font, quote_lines, quote_lh = font, lines, lh
            break

    if quote_font is None:
        quote_font = cl.lf(cl.BASK_REG, 44)
        asc, desc = quote_font.getmetrics()
        quote_lh = int((asc + desc) * 1.00)
        quote_lines = wrap_rich(quote_segments, quote_font, quote_w)

    quote_bottom = draw_rich_lines(quote_lines, quote_font, quote_x, quote_y, quote_lh)

    closing_font = cl.lf(cl.BASK_REG, 145)
    closing_x = cl.W - cl.R_MARGIN - 120
    closing_y = min(quote_bottom - 74, quote_limit - 84)
    draw.text((closing_x, closing_y), "”", font=closing_font, fill=cl.PINK)

    # --- Attribution -----------------------------------------------------
    attr_y = quote_bottom + 18
    attribution = str(slide.get("attribution") or "").strip().upper()
    attr_font = cl.lf(cl.BARLOW, 34)
    draw.text((quote_x, attr_y), f"– {attribution}", font=attr_font, fill=cl.PINK)

    detail = str(slide.get("attribution_detail") or "").strip()
    if detail:
        detail_font = cl.lf(cl.BARLOW, 22)
        detail_w = cl.W - quote_x - cl.R_MARGIN
        detail_lines = []
        current = ""
        for word in detail.split():
            trial = f"{current} {word}".strip()
            bb = draw.textbbox((0, 0), trial, font=detail_font)
            if current and bb[2] - bb[0] > detail_w:
                detail_lines.append(current)
                current = word
            else:
                current = trial
        if current:
            detail_lines.append(current)
        dy = attr_y + 43
        for line in detail_lines[:2]:
            draw.text((quote_x, dy), line, font=detail_font, fill=cl.WHITE)
            dy += 28
        attr_bottom = dy
    else:
        attr_bottom = attr_y + 44

    # --- Context block ---------------------------------------------------
    divider_y = max(attr_bottom + 18, 790)
    draw.line((cl.L_MARGIN, divider_y, cl.W - cl.R_MARGIN, divider_y), fill=cl.PINK, width=5)

    context_lines = list(slide.get("context_headline_lines") or [])
    context_colors = list(slide.get("context_headline_colors") or [])
    if not context_colors:
        context_colors = ["white"] * len(context_lines)

    context_y = divider_y + 26
    context_bottom = context_y
    if context_lines:
        max_w = cl.W - cl.L_MARGIN - cl.R_MARGIN - 200
        size = 64
        while size >= 44:
            font = cl.lf(cl.BARLOW, size)
            ok = True
            for line in context_lines:
                bb = draw.textbbox((0, 0), str(line).upper(), font=font)
                if bb[2] - bb[0] > max_w:
                    ok = False
                    break
            if ok:
                break
            size -= 2
        font = cl.lf(cl.BARLOW, size)
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * 0.82)
        cy = context_y
        for idx, line in enumerate(context_lines[:3]):
            color_name = str(context_colors[idx] if idx < len(context_colors) else "white").lower()
            fill = cl.PINK if color_name == "pink" else cl.WHITE
            draw.text((cl.L_MARGIN, cy), str(line).upper(), font=font, fill=fill)
            cy += lh
        context_bottom = cy

    body_segments = normalize_segments(slide.get("context_body"), cl.WHITE)
    if body_segments:
        body_y = context_bottom + 14
        body_w = cl.W - cl.L_MARGIN - cl.R_MARGIN - 180
        chosen = None
        for size in range(38, 29, -1):
            font = cl.lf(cl.BASK_REG, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 1.13)
            lines = wrap_rich(body_segments, font, body_w)
            if len(lines) <= 4 and body_y + len(lines) * lh <= cl.FOOTER_SAFE - 12:
                chosen = (font, lines, lh)
                break
        if chosen is None:
            font = cl.lf(cl.BASK_REG, 30)
            asc, desc = font.getmetrics()
            chosen = (font, wrap_rich(body_segments, font, body_w), int((asc + desc) * 1.10))
        body_font, body_lines, body_lh = chosen
        draw_rich_lines(body_lines[:4], body_font, cl.L_MARGIN, body_y, body_lh)

    cl.draw_footer(
        draw,
        brand_name=story.brand_footer,
        arrow=bool(slide.get("arrow", True)),
    )
    return img, qa_notes
'''


def replace_function(path: Path, name: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^def {re.escape(name)}\(.*?(?=^def |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"ERROR: Could not locate {name}() in {path.name}. No files changed.")
    updated = text[:match.start()] + replacement.rstrip() + "\n\n\n" + text[match.end():]
    path.write_text(updated, encoding="utf-8")
    print(f"Updated {name}() in {path.name}.")


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"ERROR: Could not patch {label} in {path.name}. Expected block not found.")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"Patched {label} in {path.name}.")


def main() -> int:
    if not COVER.exists() or not DASHBOARD.exists():
        print("ERROR: Run this file from the repository root beside cover_templates.py and carousel_dashboard.py.")
        return 1

    for src, backup in BACKUPS.items():
        if not backup.exists():
            shutil.copy2(src, backup)
            print(f"Backup created: {backup.name}")

    cover_text = COVER.read_text(encoding="utf-8")
    if "import re\n" not in cover_text:
        marker = "from __future__ import annotations\n\n"
        if marker not in cover_text:
            raise SystemExit("ERROR: Could not locate cover_templates.py import block.")
        COVER.write_text(cover_text.replace(marker, marker + "import re\n\n", 1), encoding="utf-8")

    replace_function(COVER, "render_quote_lead", NEW_RENDER)

    replace_once(
        DASHBOARD,
        '    "quote_lead": {\n        "label": "Cover — Quote Lead",\n        "required": ["quote", "attribution"],\n        "fields": [\n            {"name": "quote", "label": "Quote", "type": "textarea"},\n            {"name": "attribution", "label": "Attribution", "type": "text"},\n            {"name": "citation", "label": "Citation", "type": "text"},\n        ],\n    },\n',
        '    "quote_lead": {\n        "label": "Cover — Quote Lead",\n        "required": ["quote", "attribution"],\n        "fields": [\n            {"name": "quote", "label": "Quote", "type": "textarea"},\n            {"name": "attribution", "label": "Attribution", "type": "text"},\n            {"name": "attribution_detail", "label": "Role / source / date", "type": "text"},\n            {"name": "context_headline", "label": "Context headline", "type": "headline"},\n            {"name": "context_body", "label": "Context body", "type": "textarea"},\n            {"name": "citation", "label": "Citation", "type": "text"},\n        ],\n    },\n',
        "quote_lead editorial schema",
    )

    replace_once(
        DASHBOARD,
        '    "quote_lead": {\n        "quote_lines": "Quote",\n        "quote_colors": "Quote",\n        "attribution": "Attribution",\n        "citation": "Citation",\n        "label": "Label",\n    },\n',
        '    "quote_lead": {\n        "quote_lines": "Quote",\n        "quote_colors": "Quote",\n        "attribution": "Attribution",\n        "attribution_detail": "Role / source / date",\n        "context_headline_lines": "Context headline",\n        "context_headline_colors": "Context headline",\n        "context_body": "Context body",\n        "citation": "Citation",\n        "label": "Label",\n    },\n',
        "quote_lead field map",
    )

    replace_once(
        DASHBOARD,
        '    elif template == "quote_lead":\n        lines = _editor_lines(slide, "quote", "quote_lines")\n        adapted.update({\n            "quote_lines": lines,\n            "quote_colors": ["white"] * len(lines),\n            "attribution": _editor_text(slide, "attribution"),\n        })\n',
        '    elif template == "quote_lead":\n        lines = _editor_lines(slide, "quote", "quote_lines")\n        context_lines, context_colors = _editor_headline(slide, "context_headline", "context_headline_lines")\n        adapted.update({\n            "quote_lines": lines,\n            "quote_colors": ["white"] * len(lines),\n            "attribution": _editor_text(slide, "attribution"),\n            "attribution_detail": _editor_text(slide, "attribution_detail"),\n            "context_headline_lines": context_lines,\n            "context_headline_colors": context_colors,\n            "context_body": _body_value(slide.get("context_body")),\n        })\n',
        "quote_lead editor-to-renderer adapter",
    )

    replace_once(
        DASHBOARD,
        '    elif template == "quote_lead":\n        editor["quote"] = _line_value(slide.get("quote_lines"))\n        editor["attribution"] = slide.get("attribution", "")\n',
        '    elif template == "quote_lead":\n        editor["quote"] = _line_value(slide.get("quote_lines"))\n        editor["attribution"] = slide.get("attribution", "")\n        editor["attribution_detail"] = slide.get("attribution_detail", "")\n        editor["context_headline"] = _headline_editor_value({\n            "headline_lines": slide.get("context_headline_lines", []),\n            "headline_colors": slide.get("context_headline_colors", []),\n        })\n        editor["context_body"] = slide.get("context_body", [])\n',
        "quote_lead renderer-to-editor adapter",
    )

    print("Cover — Quote Lead v3.8.36 applied successfully.")
    print("Rebuilt the quote cover hierarchy and added attribution detail, context headline, and context body fields.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
