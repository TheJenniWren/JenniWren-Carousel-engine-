#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

VERSION = 'v3.8.37'


def pick_file(candidates: list[str]) -> Path:
    """Resolve a target file from cwd first, then beside this patch script."""
    roots = [Path.cwd(), Path(__file__).resolve().parent]
    for root in roots:
        for name in candidates:
            path = root / name
            if path.exists():
                return path
    raise SystemExit(f"ERROR: Could not find any of: {', '.join(candidates)}")


COVER = pick_file(["cover_templates.py", "cover_templates(1).py"])
DASHBOARD = pick_file(["carousel_dashboard.py"])

BACKUPS = {
    COVER: COVER.with_name(COVER.name + f".before_cover_quote_lead_{VERSION}"),
    DASHBOARD: DASHBOARD.with_name(DASHBOARD.name + f".before_cover_quote_lead_{VERSION}"),
}

NEW_RENDER = r'''def render_quote_lead(slide: StorySlide, n: int, total: int, story: StoryPackage,
                      defaults: TemplateDefaults):
    """Cover — Quote Lead v3.8.37.

    Layout hierarchy:
      1. Oversized quote treatment
      2. Attribution block
      3. Divider around y≈850
      4. Context headline
      5. Context body / why-it-matters copy

    Supported inline emphasis tokens:
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

    def line_width(line, font):
        if not line:
            return 0
        space_w = cl.mw(draw, " ", font)
        total_w = 0
        for idx, (word, _fill) in enumerate(line):
            total_w += cl.mw(draw, word, font)
            if idx < len(line) - 1:
                total_w += space_w
        return total_w

    def wrap_plain(text, font, max_w):
        lines = []
        current = ""
        for word in str(text or "").split():
            trial = f"{current} {word}".strip()
            bb = draw.textbbox((0, 0), trial, font=font)
            if current and bb[2] - bb[0] > max_w:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        return lines

    # ---- Quote block -------------------------------------------------
    quote_source = slide.get("quote_lines") or []
    quote_segments = normalize_segments(" ".join(str(v) for v in quote_source), cl.WHITE)
    if not quote_segments:
        quote_segments = [("Quote", cl.WHITE)]

    quote_x = int(slide.get("quote_x", 128))
    quote_y = int(slide.get("quote_y", 190))
    quote_w = int(slide.get("quote_w", 878))
    quote_max_bottom = int(slide.get("quote_max_bottom", 640))

    open_font = cl.lf(cl.BASK_REG, 210)
    close_font = cl.lf(cl.BASK_REG, 190)

    draw.text((40, 140), "“", font=open_font, fill=cl.PINK)

    quote_font = None
    quote_lines = None
    quote_lh = None
    # Larger, more dominant fit pass than v3.8.36.
    for size in range(116, 66, -2):
        font = cl.lf(cl.BASK_REG, size)
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * 0.94)
        lines = wrap_rich(quote_segments, font, quote_w)
        bottom = quote_y + len(lines) * lh
        if len(lines) <= 5 and bottom <= quote_max_bottom:
            quote_font, quote_lines, quote_lh = font, lines, lh
            break

    if quote_font is None:
        quote_font = cl.lf(cl.BASK_REG, 64)
        asc, desc = quote_font.getmetrics()
        quote_lh = int((asc + desc) * 0.95)
        quote_lines = wrap_rich(quote_segments, quote_font, quote_w)

    quote_bottom = draw_rich_lines(quote_lines, quote_font, quote_x, quote_y, quote_lh)
    last_line_w = line_width(quote_lines[-1], quote_font) if quote_lines else 0
    close_x_try = quote_x + last_line_w + 18
    if close_x_try <= cl.W - cl.R_MARGIN - 70:
        close_x = close_x_try
        close_y = quote_bottom - int(close_font.size * 0.92)
    else:
        close_x = quote_x + max(0, last_line_w - 40)
        close_y = quote_bottom - 8
    draw.text((close_x, close_y), "”", font=close_font, fill=cl.PINK)

    # ---- Attribution -------------------------------------------------
    attribution = str(slide.get("attribution") or "").strip().upper()
    attr_y = quote_bottom + 28
    attr_font = cl.lf(cl.BARLOW, 44)
    draw.text((quote_x, attr_y), f"– {attribution}", font=attr_font, fill=cl.PINK)

    attr_bottom = attr_y + 52
    detail = str(slide.get("attribution_detail") or "").strip()
    if detail:
        detail_font = cl.lf(cl.BARLOW, 26)
        detail_lines = []
        for raw in [part.strip() for part in detail.split("\n") if part.strip()]:
            detail_lines.extend(wrap_plain(raw, detail_font, cl.W - quote_x - cl.R_MARGIN))
        dy = attr_y + 52
        for line in detail_lines[:3]:
            draw.text((quote_x, dy), line, font=detail_font, fill=cl.WHITE)
            dy += 30
        attr_bottom = dy

    # ---- Divider / context ------------------------------------------
    divider_y = max(850, attr_bottom + 36)
    draw.line((cl.L_MARGIN, divider_y, cl.W - cl.R_MARGIN, divider_y), fill=cl.PINK, width=5)

    context_lines = list(slide.get("context_headline_lines") or [])
    context_colors = list(slide.get("context_headline_colors") or [])
    if not context_colors:
        context_colors = ["white"] * len(context_lines)

    context_y = divider_y + 28
    context_bottom = context_y
    if context_lines:
        max_w = cl.W - cl.L_MARGIN - cl.R_MARGIN - 90
        chosen_font = None
        chosen_lh = None
        for size in range(78, 52, -2):
            font = cl.lf(cl.BARLOW, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 0.82)
            ok = True
            for line in context_lines:
                bb = draw.textbbox((0, 0), str(line).upper(), font=font)
                if bb[2] - bb[0] > max_w:
                    ok = False
                    break
            if ok:
                chosen_font = font
                chosen_lh = lh
                break
        if chosen_font is None:
            chosen_font = cl.lf(cl.BARLOW, 52)
            asc, desc = chosen_font.getmetrics()
            chosen_lh = int((asc + desc) * 0.82)
        cy = context_y
        for idx, line in enumerate(context_lines[:3]):
            color_name = str(context_colors[idx] if idx < len(context_colors) else "white").lower()
            fill = cl.PINK if color_name == "pink" else cl.WHITE
            draw.text((cl.L_MARGIN, cy), str(line).upper(), font=chosen_font, fill=fill)
            cy += chosen_lh
        context_bottom = cy

    body_segments = normalize_segments(slide.get("context_body"), cl.WHITE)
    if body_segments:
        body_y = context_bottom + 18
        body_w = cl.W - cl.L_MARGIN - cl.R_MARGIN - 40
        chosen = None
        for size in range(42, 37, -1):
            font = cl.lf(cl.BASK_REG, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 1.14)
            lines = wrap_rich(body_segments, font, body_w)
            if 2 <= len(lines) <= 4 and body_y + len(lines) * lh <= cl.FOOTER_SAFE - 10:
                chosen = (font, lines, lh)
                break
        if chosen is None:
            font = cl.lf(cl.BASK_REG, 38)
            asc, desc = font.getmetrics()
            chosen = (font, wrap_rich(body_segments, font, body_w), int((asc + desc) * 1.14))
        body_font, body_lines, body_lh = chosen
        draw_rich_lines(body_lines[:4], body_font, cl.L_MARGIN, body_y, body_lh)

    cl.draw_footer(
        draw,
        brand_name=story.brand_footer,
        arrow=bool(slide.get("arrow", True)),
    )
    return img, qa_notes
'''


QUOTE_SCHEMA = '''    "quote_lead": {
        "label": "Cover — Quote Lead",
        "required": ["quote", "attribution"],
        "fields": [
            {"name": "quote", "label": "Quote", "type": "textarea"},
            {"name": "attribution", "label": "Attribution", "type": "text"},
            {"name": "attribution_detail", "label": "Role / source / date", "type": "text"},
            {"name": "context_headline", "label": "Context headline", "type": "headline"},
            {"name": "context_body", "label": "Context body", "type": "textarea"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
'''

QUOTE_FIELD_MAP = '''    "quote_lead": {
        "quote_lines": "Quote",
        "quote_colors": "Quote",
        "attribution": "Attribution",
        "attribution_detail": "Role / source / date",
        "context_headline_lines": "Context headline",
        "context_headline_colors": "Context headline",
        "context_body": "Context body",
        "citation": "Citation",
        "label": "Label",
    },
'''

QUOTE_EDITOR_TO_RENDERER = '''    elif template == "quote_lead":
        lines = _editor_lines(slide, "quote", "quote_lines")
        context_lines, context_colors = _editor_headline(slide, "context_headline", "context_headline_lines")
        adapted.update({
            "quote_lines": lines,
            "quote_colors": ["white"] * len(lines),
            "attribution": _editor_text(slide, "attribution"),
            "attribution_detail": _editor_text(slide, "attribution_detail"),
            "context_headline_lines": context_lines,
            "context_headline_colors": context_colors,
            "context_body": _body_value(slide.get("context_body")),
        })
'''

QUOTE_RENDERER_TO_EDITOR = '''    elif template == "quote_lead":
        editor["quote"] = _line_value(slide.get("quote_lines"))
        editor["attribution"] = slide.get("attribution", "")
        editor["attribution_detail"] = slide.get("attribution_detail", "")
        editor["context_headline"] = _headline_editor_value({
            "headline_lines": slide.get("context_headline_lines", []),
            "headline_colors": slide.get("context_headline_colors", []),
        })
        editor["context_body"] = slide.get("context_body", [])
'''


def ensure_backup(path: Path, backup: Path) -> None:
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"Backup created: {backup.name}")


def replace_function(path: Path, name: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^def {re.escape(name)}\(.*?(?=^def |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"ERROR: Could not locate {name}() in {path.name}. No files changed.")
    updated = text[:match.start()] + replacement.rstrip() + "\n\n\n" + text[match.end():]
    path.write_text(updated, encoding="utf-8")
    print(f"Updated {name}() in {path.name}.")


def ensure_import_re(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if re.search(r"^import re$", text, re.MULTILINE):
        return
    marker = "from __future__ import annotations\n\n"
    if marker not in text:
        raise SystemExit(f"ERROR: Could not locate import block in {path.name}.")
    path.write_text(text.replace(marker, marker + "import re\n\n", 1), encoding="utf-8")
    print(f"Added import re to {path.name}.")


def replace_regex_block(path: Path, pattern: str, replacement: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if count == 0:
        if replacement.strip() in text:
            print(f"{label} already present in {path.name}.")
            return
        raise SystemExit(f"ERROR: Could not patch {label} in {path.name}.")
    path.write_text(new_text, encoding="utf-8")
    print(f"Patched {label} in {path.name}.")


def main() -> int:
    ensure_backup(COVER, BACKUPS[COVER])
    ensure_backup(DASHBOARD, BACKUPS[DASHBOARD])

    ensure_import_re(COVER)
    replace_function(COVER, "render_quote_lead", NEW_RENDER)

    replace_regex_block(
        DASHBOARD,
        r'    "quote_lead": \{\n        "label": "Cover — Quote Lead",\n        "required": \["quote", "attribution"\],\n        "fields": \[\n.*?\n        \],\n    \},\n',
        QUOTE_SCHEMA,
        "quote_lead editorial schema",
    )

    replace_regex_block(
        DASHBOARD,
        r'    "quote_lead": \{\n        "quote_lines": "Quote",\n.*?\n    \},\n',
        QUOTE_FIELD_MAP,
        "quote_lead field map",
    )

    replace_regex_block(
        DASHBOARD,
        r'    elif template == "quote_lead":\n        lines = _editor_lines\(slide, "quote", "quote_lines"\)\n        adapted\.update\(\{\n.*?\n        \}\)\n',
        QUOTE_EDITOR_TO_RENDERER,
        "quote_lead editor-to-renderer adapter",
    )

    replace_regex_block(
        DASHBOARD,
        r'    elif template == "quote_lead":\n        editor\["quote"\] = _line_value\(slide\.get\("quote_lines"\)\)\n        editor\["attribution"\] = slide\.get\("attribution", ""\)\n',
        QUOTE_RENDERER_TO_EDITOR,
        "quote_lead renderer-to-editor adapter",
    )

    print(f"Cover — Quote Lead {VERSION} applied successfully.")
    print("Updated hierarchy: oversized quote → attribution → divider → context headline → context body.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
