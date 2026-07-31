#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "carousel_lib.py"
TEMPLATE = ROOT / "document_templates.py"
DASHBOARD = ROOT / "carousel_dashboard.py"

BACKUPS = {
    LIB: ROOT / "carousel_lib.py.before_evidence_document_card_v3_8_34",
    TEMPLATE: ROOT / "document_templates.py.before_evidence_document_card_v3_8_34",
    DASHBOARD: ROOT / "carousel_dashboard.py.before_evidence_document_card_v3_8_34",
}

NEW_DRAW_DOCUMENT_CARD = r'''def draw_document_card(draw, img, lines, highlight_line_idxs, ty,
                        card_h=472, annotation=True):
    """Evidence — Document Card v3.8.34."""
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
    card_h = max(438, int(card_h or 472))

    paper = (246, 242, 232)
    paper_back = (227, 221, 211)
    paper_edge = (194, 188, 176)
    ink = (28, 28, 28)
    muted = (92, 92, 92)
    highlight = (247, 208, 72)

    draw.polygon(
        [(card_x0 + 22, ty + 6), (card_x1 + 6, ty + 18),
         (card_x1 - 2, ty + card_h + 10), (card_x0 + 10, ty + card_h - 2)],
        fill=paper_back,
    )
    draw.polygon(
        [(card_x0, ty + 18), (card_x1 - 20, ty),
         (card_x1, ty + card_h - 16), (card_x0 + 18, ty + card_h)],
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

    masthead = "OFFICIAL RECORD"
    mb = draw.textbbox((0, 0), masthead, font=masthead_font)
    draw.text((center - (mb[2] - mb[0]) // 2, ty + 42), masthead,
              font=masthead_font, fill=ink)
    agency = "UNITED STATES GOVERNMENT"
    ab = draw.textbbox((0, 0), agency, font=small_font)
    draw.text((center - (ab[2] - ab[0]) // 2, ty + 72), agency,
              font=small_font, fill=muted)
    draw.line((left, ty + 104, right, ty + 104), fill=paper_edge, width=2)

    date_text = "DOCUMENT EXCERPT"
    db = draw.textbbox((0, 0), date_text, font=small_font)
    draw.text((center - (db[2] - db[0]) // 2, ty + 118), date_text,
              font=small_font, fill=muted)

    decision = "KEY CONTRACT TERMS"
    tb = draw.textbbox((0, 0), decision, font=title_font)
    draw.text((center - (tb[2] - tb[0]) // 2, ty + 152), decision,
              font=title_font, fill=ink)

    focus_idx = min(highlight_line_idxs) if highlight_line_idxs else 0
    focus_idx = min(max(focus_idx, 0), max(0, len(normalized) - 1))
    focus = normalized[focus_idx] if normalized else "Document evidence"

    max_focus_w = int(card_w * 0.50)
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
    line_h = int((asc + desc) * 1.14)
    focus_y = ty + 220
    max_line_w = 0
    for line in focus_lines:
        bb = draw.textbbox((0, 0), line, font=body_font)
        max_line_w = max(max_line_w, bb[2] - bb[0])

    hx0 = left + 170
    hx1 = min(right - 175, hx0 + max_line_w + 26)
    hy0 = focus_y - 5
    hy1 = focus_y + line_h * len(focus_lines) - 6
    draw.rectangle((hx0 - 10, hy0, hx1, hy1), fill=highlight)

    fy = focus_y
    for line in focus_lines:
        draw.text((hx0, fy), line, font=body_font, fill=ink)
        fy += line_h

    if annotation:
        note_x = right - 145
        note_y = focus_y + 10
        anchor_y = focus_y + min(20, (hy1 - hy0) // 2)
        draw.line((hx1 + 18, anchor_y, note_x - 16, note_y + 14), fill=ink, width=4)
        draw.polygon(((hx1 + 16, anchor_y),
                      (hx1 + 30, anchor_y - 8),
                      (hx1 + 30, anchor_y + 8)), fill=ink)
        for i, text in enumerate(("KEY", "DETAIL")):
            draw.text((note_x, note_y + i * 28), text, font=note_font, fill=ink)
        draw.line((note_x, note_y + 64, note_x + 76, note_y + 64), fill=PINK, width=5)

    secondary = [v for i, v in enumerate(normalized) if i != focus_idx][:3]
    sy = ty + card_h - 122
    sec_font = lf(BASK_REG, 21)
    for line in secondary:
        text = line if len(line) <= 58 else line[:55].rstrip() + "…"
        draw.text((left + 16, sy), text, font=sec_font, fill=muted)
        sy += 27

    red_y = ty + card_h - 58
    for width in (408, 492, 446):
        draw.rectangle((left + 116, red_y, left + 116 + width, red_y + 9), fill=(175, 175, 175))
        red_y += 17

    return ty + card_h
'''

NEW_RENDER_DOCUMENT_CARD = r'''def render_document_card(slide: StorySlide, n: int, total: int, story: StoryPackage,
                         defaults: TemplateDefaults):
    """Evidence — Document Card v3.8.34."""
    require_fields(slide, "label", "doc_lines", "headline_lines", "headline_colors")
    qa_notes: List[str] = []

    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total,
                    big=bool(slide.get("big_label", False)))

    card_top = 122
    requested_h = int(slide.get("doc_card_h", 472) or 472)
    highlight_idxs = set(slide.get("doc_highlight", []) or [])

    card_bottom = cl.draw_document_card(
        draw, img, slide.get("doc_lines") or [], highlight_idxs, card_top,
        card_h=requested_h,
        annotation=bool(slide.get("doc_annotation", True)),
    )

    headline_lines = list(slide.get("headline_lines") or [])
    colors = colors_from_names(slide.get("headline_colors"), slide.slide_id)
    default_range = tuple(getattr(defaults, "document_headline_range", (82, 150)))
    scaled_range = (
        max(60, int(default_range[0] * 0.90)),
        max(72, int(default_range[1] * 0.90)),
    )
    sr = tuple(slide.get("headline_range", scaled_range))

    headline_top = card_bottom + 18
    headline_bottom = cl.draw_headline(draw, headline_lines, colors, headline_top, sr)
    divider_bottom = cl.draw_divider(draw, headline_bottom, gap=6)

    def normalize_body_segments(value):
        if not value:
            return []
        segs = []

        def add(text, color="white"):
            text = str(text or "").strip()
            if text:
                segs.append((text, cl.PINK if str(color).lower() == "pink" else cl.WHITE))

        def parse_inline(text, base_color="white"):
            text = str(text or "")
            pattern = re.compile(r"(<pink>.*?</pink>|\[\[pink:.*?\]\])", re.I | re.S)
            pos = 0
            for match in pattern.finditer(text):
                if match.start() > pos:
                    add(text[pos:match.start()], base_color)
                token = match.group(0)
                add(token[6:-7] if token.lower().startswith("<pink>") else token[7:-2], "pink")
                pos = match.end()
            if pos < len(text):
                add(text[pos:], base_color)

        def walk(node, inherited="white"):
            if node is None:
                return
            if isinstance(node, str):
                parse_inline(node, inherited)
            elif isinstance(node, dict):
                color = str(node.get("color") or inherited).lower()
                if "text" in node:
                    parse_inline(node.get("text"), color)
                else:
                    for key in ("segments", "content", "children", "body"):
                        if key in node:
                            walk(node.get(key), color)
                            break
            elif isinstance(node, (list, tuple)):
                if len(node) == 2 and isinstance(node[0], str) and isinstance(node[1], str):
                    parse_inline(node[0], node[1])
                else:
                    for child in node:
                        walk(child, inherited)
            else:
                parse_inline(str(node), inherited)

        walk(value)
        return segs

    body_segments = normalize_body_segments(slide.get("body") or slide.get("supporting_body"))
    if body_segments:
        body_top = divider_bottom + 18
        max_bottom = cl.FOOTER_SAFE - 8
        max_w = cl.W - cl.L_MARGIN - cl.R_MARGIN

        chosen = None
        for size in range(min(42, int(slide.get("body_size", 40) or 40)), 37, -1):
            font = cl.lf(cl.BASK_REG, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 1.22)
            wrapped = cl.wrap_lines(draw, body_segments, font, max_w)
            if wrapped and len(wrapped) <= 4 and body_top + lh * len(wrapped) <= max_bottom:
                chosen = (font, wrapped, lh)
                break

        if chosen is None:
            font = cl.lf(cl.BASK_REG, 38)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 1.20)
            chosen = (font, cl.wrap_lines(draw, body_segments, font, max_w), lh)

        font, wrapped, lh = chosen
        max_lines_fit = max(0, int((max_bottom - body_top) // max(1, lh)))
        visible = wrapped[:max_lines_fit]
        if len(visible) < len(wrapped):
            qa_notes.append("document_card supporting body exceeded the available space above the footer.")

        y = body_top
        space_w = cl.mw(draw, " ", font)
        for line in visible:
            x = cl.L_MARGIN
            for i, (word, fill) in enumerate(line):
                draw.text((x, y), word, font=font, fill=fill)
                x += cl.mw(draw, word, font)
                if i < len(line) - 1:
                    x += space_w
            y += lh

    cl.draw_footer(draw, brand_name=story.brand_footer,
                   arrow=bool(slide.get("arrow", True)))
    return img, qa_notes
'''


def replace_function(path: Path, name: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^def {re.escape(name)}\(.*?(?=^def |^# ─|\Z)", re.M | re.S)
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"ERROR: Could not locate {name}() in {path.name}. No files changed.")
    path.write_text(text[:match.start()] + replacement.rstrip() + "\n\n\n" + text[match.end():], encoding="utf-8")
    print(f"Updated {name}() in {path.name}.")


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"ERROR: Could not patch {label} in {path.name}. Expected block not found.")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"Patched {label} in {path.name}.")


def main() -> int:
    if any(not path.exists() for path in (LIB, TEMPLATE, DASHBOARD)):
        print("ERROR: Run this file from the repository root beside carousel_lib.py, document_templates.py, and carousel_dashboard.py.")
        return 1

    for src, backup in BACKUPS.items():
        if not backup.exists():
            shutil.copy2(src, backup)
            print(f"Backup created: {backup.name}")

    replace_function(LIB, "draw_document_card", NEW_DRAW_DOCUMENT_CARD)
    replace_function(TEMPLATE, "render_document_card", NEW_RENDER_DOCUMENT_CARD)

    replace_once(
        DASHBOARD,
        '            {"name": "excerpt", "label": "Document excerpt", "type": "textarea"},\n            {"name": "highlight", "label": "Highlighted line numbers", "type": "text"},\n            {"name": "annotation", "label": "Show annotation arrow", "type": "boolean"},\n            {"name": "citation", "label": "Citation", "type": "text"},\n',
        '            {"name": "excerpt", "label": "Document excerpt", "type": "textarea"},\n            {"name": "highlight", "label": "Highlighted line numbers", "type": "text"},\n            {"name": "annotation", "label": "Show annotation arrow", "type": "boolean"},\n            {"name": "body", "label": "Supporting body", "type": "textarea"},\n            {"name": "citation", "label": "Citation", "type": "text"},\n',
        "document_card editorial schema",
    )

    replace_once(
        DASHBOARD,
        '    "document_card": {\n        "doc_lines": "Document excerpt",\n        "headline_lines": "Headline",\n        "headline_colors": "Headline",\n        "image": "Document image filename",\n        "citation": "Citation",\n        "label": "Label",\n    },\n',
        '    "document_card": {\n        "doc_lines": "Document excerpt",\n        "headline_lines": "Headline",\n        "headline_colors": "Headline",\n        "image": "Document image filename",\n        "body": "Supporting body",\n        "citation": "Citation",\n        "label": "Label",\n    },\n',
        "document_card field map",
    )

    replace_once(
        DASHBOARD,
        '        adapted.update({\n            "headline_lines": headline,\n            "headline_colors": headline_colors,\n            "doc_lines": _editor_lines(slide, "excerpt", "doc_lines"),\n            "doc_highlight": _index_value(slide.get("highlight", slide.get("doc_highlight"))),\n            "doc_annotation": bool(slide.get("annotation", slide.get("doc_annotation", True))),\n        })\n',
        '        adapted.update({\n            "headline_lines": headline,\n            "headline_colors": headline_colors,\n            "doc_lines": _editor_lines(slide, "excerpt", "doc_lines"),\n            "doc_highlight": _index_value(slide.get("highlight", slide.get("doc_highlight"))),\n            "doc_annotation": bool(slide.get("annotation", slide.get("doc_annotation", True))),\n            "body": _body_value(slide.get("body")),\n        })\n',
        "document_card editor-to-renderer adapter",
    )

    replace_once(
        DASHBOARD,
        '    elif template == "document_card":\n        editor["image"] = slide.get("image", "")\n        editor["headline"] = _headline_editor_value(slide)\n        editor["excerpt"] = _line_value(slide.get("doc_lines"))\n        editor["highlight"] = [\n            int(value) + 1 for value in slide.get("doc_highlight", [])\n            if isinstance(value, int)\n        ]\n        editor["annotation"] = bool(slide.get("doc_annotation", True))\n',
        '    elif template == "document_card":\n        editor["image"] = slide.get("image", "")\n        editor["headline"] = _headline_editor_value(slide)\n        editor["excerpt"] = _line_value(slide.get("doc_lines"))\n        editor["highlight"] = [\n            int(value) + 1 for value in slide.get("doc_highlight", [])\n            if isinstance(value, int)\n        ]\n        editor["annotation"] = bool(slide.get("doc_annotation", True))\n        editor["body"] = slide.get("body", [])\n',
        "document_card renderer-to-editor adapter",
    )

    print("Evidence — Document Card v3.8.34 applied successfully.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
