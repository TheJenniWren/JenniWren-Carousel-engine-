#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

VERSION = 'v3.8.38'


def pick_file(candidates: list[str]) -> Path:
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
    """Cover — Quote Lead v3.8.38.

    Clean replacement modeled on the black Quote Lead reference.

    Hierarchy:
      1. Oversized Barlow Condensed quote block
      2. Pink attribution name
      3. White role / source / date detail
      4. Divider near y≈850
      5. Context headline
      6. Context body using the lower slide area

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

    def _segments(value, default_fill=cl.WHITE, uppercase=False):
        out = []

        def add(text, fill):
            text = str(text or "")
            if uppercase:
                text = text.upper()
            if text.strip():
                out.append((text.strip(), fill))

        def parse_inline(text, base_fill):
            text = str(text or "")
            pattern = re.compile(r'(<pink>.*?</pink>|\[\[pink:.*?\]\])', re.IGNORECASE | re.DOTALL)
            pos = 0
            for m in pattern.finditer(text):
                if m.start() > pos:
                    add(text[pos:m.start()], base_fill)
                token = m.group(0)
                if token.lower().startswith('<pink>'):
                    add(token[6:-7], cl.PINK)
                else:
                    add(token[7:-2], cl.PINK)
                pos = m.end()
            if pos < len(text):
                add(text[pos:], base_fill)

        def walk(node, inherited_fill=default_fill):
            if node is None:
                return
            if isinstance(node, str):
                parse_inline(node, inherited_fill)
                return
            if isinstance(node, dict):
                fill = cl.PINK if str(node.get('color') or '').lower() == 'pink' else inherited_fill
                if 'text' in node:
                    parse_inline(node.get('text'), fill)
                    return
                for key in ('segments', 'content', 'children', 'body'):
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
        return out

    def _plain_text(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            if 'text' in value:
                return str(value.get('text') or '')
            for key in ('segments', 'content', 'children', 'body'):
                if key in value:
                    return _plain_text(value.get(key))
            return ""
        if isinstance(value, (list, tuple)):
            return ' '.join(_plain_text(v) for v in value if _plain_text(v).strip())
        return str(value)

    def _wrap_rich(segments, font, max_w):
        words = []
        for text, fill in segments:
            for word in str(text).split():
                words.append((word, fill))
        if not words:
            return []
        lines = []
        current = []
        cur_w = 0.0
        sp = cl.mw(draw, ' ', font)
        for word, fill in words:
            ww = cl.mw(draw, word, font)
            need = ww if not current else sp + ww
            if current and cur_w + need > max_w:
                lines.append(current)
                current = [(word, fill)]
                cur_w = ww
            else:
                if current:
                    cur_w += sp
                current.append((word, fill))
                cur_w += ww
        if current:
            lines.append(current)
        return lines

    def _line_width(line, font):
        if not line:
            return 0
        sp = cl.mw(draw, ' ', font)
        total_w = 0
        for i, (word, _fill) in enumerate(line):
            total_w += cl.mw(draw, word, font)
            if i < len(line) - 1:
                total_w += sp
        return total_w

    def _draw_rich_lines(lines, font, x, y, line_h):
        sp = cl.mw(draw, ' ', font)
        for line in lines:
            cx = x
            for i, (word, fill) in enumerate(line):
                draw.text((cx, y), word, font=font, fill=fill)
                cx += cl.mw(draw, word, font)
                if i < len(line) - 1:
                    cx += sp
            y += line_h
        return y

    def _wrap_plain_lines(text, font, max_w):
        text = str(text or '').strip()
        if not text:
            return []
        lines = []
        current = ''
        for word in text.split():
            trial = f'{current} {word}'.strip()
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
    quote_source = slide.get('quote_lines') or []
    if not isinstance(quote_source, (list, tuple)):
        quote_source = [quote_source]

    explicit_lines = []
    for item in quote_source:
        segs = _segments(item, cl.WHITE, uppercase=True)
        if segs:
            explicit_lines.append(segs)
    if not explicit_lines:
        explicit_lines = [[('QUOTE', cl.WHITE)]]

    quote_x = int(slide.get('quote_x', 128))
    quote_y = int(slide.get('quote_y', 190))
    quote_w = int(slide.get('quote_w', 884))
    quote_max_bottom = int(slide.get('quote_max_bottom', 670))

    open_font = cl.lf(cl.BASK_REG, 180)
    close_font = cl.lf(cl.BASK_REG, 165)
    open_x = int(slide.get('open_quote_x', 42))
    open_y = int(slide.get('open_quote_y', 150))
    draw.text((open_x, open_y), '“', font=open_font, fill=cl.PINK)

    quote_font = None
    quote_lines = None
    quote_lh = None

    # Preserve deliberate editorial stacking when 2+ explicit lines were supplied.
    if len(explicit_lines) > 1:
        for size in range(118, 70, -2):
            font = cl.lf(cl.BARLOW, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 0.82)
            widths_ok = all(_line_width(line, font) <= quote_w for line in explicit_lines)
            bottom_ok = quote_y + len(explicit_lines) * lh <= quote_max_bottom
            if widths_ok and bottom_ok:
                quote_font, quote_lines, quote_lh = font, explicit_lines, lh
                break
        if quote_font is None:
            quote_font = cl.lf(cl.BARLOW, 70)
            asc, desc = quote_font.getmetrics()
            quote_lh = int((asc + desc) * 0.82)
            quote_lines = explicit_lines
    else:
        merged = explicit_lines[0]
        # Fit to a large stacked quote occupying roughly the upper 60–65%.
        for size in range(130, 72, -2):
            font = cl.lf(cl.BARLOW, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 0.82)
            lines = _wrap_rich(merged, font, quote_w)
            bottom = quote_y + len(lines) * lh
            if 3 <= len(lines) <= 5 and bottom <= quote_max_bottom:
                quote_font, quote_lines, quote_lh = font, lines, lh
                break
        if quote_font is None:
            quote_font = cl.lf(cl.BARLOW, 78)
            asc, desc = quote_font.getmetrics()
            quote_lh = int((asc + desc) * 0.82)
            quote_lines = _wrap_rich(merged, quote_font, quote_w)

    quote_bottom = _draw_rich_lines(quote_lines, quote_font, quote_x, quote_y, quote_lh)
    last_w = _line_width(quote_lines[-1], quote_font) if quote_lines else 0
    close_x_try = quote_x + last_w + 12
    if close_x_try <= cl.W - cl.R_MARGIN - 40:
        close_x = close_x_try
        close_y = quote_bottom - int(close_font.size * 0.80)
    else:
        close_x = min(cl.W - cl.R_MARGIN - 80, quote_x + max(0, last_w - 40))
        close_y = quote_bottom - 8
    draw.text((close_x, close_y), '”', font=close_font, fill=cl.PINK)

    # ---- Attribution -------------------------------------------------
    attribution = str(slide.get('attribution') or '').strip().upper()
    attr_font = cl.lf(cl.BARLOW, 48)
    attr_y = quote_bottom + 28
    draw.text((quote_x, attr_y), f'– {attribution}', font=attr_font, fill=cl.PINK)

    detail_raw = str(slide.get('attribution_detail') or '').strip()
    detail_font = cl.lf(cl.BARLOW, 26)
    detail_y = attr_y + 54
    detail_max_w = cl.W - quote_x - cl.R_MARGIN - 24
    detail_lines = []
    if detail_raw:
        for raw_line in [part.strip() for part in detail_raw.split('\n') if part.strip()]:
            wrapped = _wrap_plain_lines(raw_line, detail_font, detail_max_w)
            detail_lines.extend(wrapped if wrapped else [raw_line])
        for line in detail_lines[:3]:
            draw.text((quote_x, detail_y), line, font=detail_font, fill=cl.WHITE)
            detail_y += 30
    attr_bottom = detail_y if detail_lines else attr_y + 56

    # ---- Divider / context ------------------------------------------
    divider_y = max(850, attr_bottom + 36)
    draw.line((cl.L_MARGIN, divider_y, cl.W - cl.R_MARGIN, divider_y), fill=cl.PINK, width=5)

    context_lines = list(slide.get('context_headline_lines') or [])
    context_colors = list(slide.get('context_headline_colors') or [])
    if not context_colors:
        context_colors = ['white'] * len(context_lines)

    context_y = divider_y + 30
    context_bottom = context_y
    if context_lines:
        max_w = cl.W - cl.L_MARGIN - cl.R_MARGIN - 42
        chosen_font = None
        chosen_lh = None
        for size in range(78, 52, -2):
            font = cl.lf(cl.BARLOW, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 0.82)
            ok = True
            for line in context_lines[:3]:
                bb = draw.textbbox((0, 0), str(line).upper(), font=font)
                if bb[2] - bb[0] > max_w:
                    ok = False
                    break
            if ok:
                chosen_font = font
                chosen_lh = lh
                break
        if chosen_font is None:
            chosen_font = cl.lf(cl.BARLOW, 54)
            asc, desc = chosen_font.getmetrics()
            chosen_lh = int((asc + desc) * 0.82)
        cy = context_y
        for idx, line in enumerate(context_lines[:3]):
            color_name = str(context_colors[idx] if idx < len(context_colors) else 'white').lower()
            fill = cl.PINK if color_name == 'pink' else cl.WHITE
            draw.text((cl.L_MARGIN, cy), str(line).upper(), font=chosen_font, fill=fill)
            cy += chosen_lh
        context_bottom = cy

    body_segments = _segments(slide.get('context_body'), cl.WHITE, uppercase=False)
    if body_segments:
        body_y = context_bottom + 18
        body_w = cl.W - cl.L_MARGIN - cl.R_MARGIN - 10
        chosen = None
        for size in range(42, 37, -1):
            font = cl.lf(cl.BASK_REG, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 1.15)
            lines = _wrap_rich(body_segments, font, body_w)
            if 2 <= len(lines) <= 5 and body_y + len(lines) * lh <= cl.FOOTER_SAFE - 8:
                chosen = (font, lines, lh)
                break
        if chosen is None:
            font = cl.lf(cl.BASK_REG, 38)
            asc, desc = font.getmetrics()
            chosen = (font, _wrap_rich(body_segments, font, body_w), int((asc + desc) * 1.15))
        body_font, body_lines, body_lh = chosen
        _draw_rich_lines(body_lines[:5], body_font, cl.L_MARGIN, body_y, body_lh)

    cl.draw_footer(
        draw,
        brand_name=story.brand_footer,
        arrow=bool(slide.get('arrow', True)),
    )
    return img, qa_notes
'''

QUOTE_SCHEMA = '''    "quote_lead": {
        "label": "Cover — Quote Lead",
        "required": ["quote", "attribution"],
        "fields": [
            {"name": "quote", "label": "Quote", "type": "textarea"},
            {"name": "attribution", "label": "Attribution", "type": "text"},
            {"name": "attribution_detail", "label": "Role / source / date", "type": "textarea"},
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
    text = path.read_text(encoding='utf-8')
    pattern = re.compile(rf'^def {re.escape(name)}\(.*?(?=^def |\Z)', re.MULTILINE | re.DOTALL)
    m = pattern.search(text)
    if not m:
        raise SystemExit(f"ERROR: Could not locate {name}() in {path.name}. No files changed.")
    updated = text[:m.start()] + replacement.rstrip() + '\n\n\n' + text[m.end():]
    path.write_text(updated, encoding='utf-8')
    print(f"Updated {name}() in {path.name}.")


def ensure_import_re(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    if re.search(r'^import re$', text, re.MULTILINE):
        return
    marker = 'from __future__ import annotations\n\n'
    if marker not in text:
        raise SystemExit(f"ERROR: Could not locate import block in {path.name}.")
    path.write_text(text.replace(marker, marker + 'import re\n\n', 1), encoding='utf-8')
    print(f"Added import re to {path.name}.")


def replace_regex_block(path: Path, pattern: str, replacement: str, label: str) -> None:
    text = path.read_text(encoding='utf-8')
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if count == 0:
        if replacement.strip() in text:
            print(f"{label} already present in {path.name}.")
            return
        raise SystemExit(f"ERROR: Could not patch {label} in {path.name}.")
    path.write_text(new_text, encoding='utf-8')
    print(f"Patched {label} in {path.name}.")


def main() -> int:
    ensure_backup(COVER, BACKUPS[COVER])
    ensure_backup(DASHBOARD, BACKUPS[DASHBOARD])

    ensure_import_re(COVER)
    replace_function(COVER, 'render_quote_lead', NEW_RENDER)

    replace_regex_block(
        DASHBOARD,
        r'    "quote_lead": \{\n        "label": "Cover — Quote Lead",\n        "required": \["quote", "attribution"\],\n        "fields": \[\n.*?\n        \],\n    \},\n',
        QUOTE_SCHEMA,
        'quote_lead editorial schema',
    )

    replace_regex_block(
        DASHBOARD,
        r'    "quote_lead": \{\n        "quote_lines": "Quote",\n.*?\n    \},\n',
        QUOTE_FIELD_MAP,
        'quote_lead field map',
    )

    replace_regex_block(
        DASHBOARD,
        r'    elif template == "quote_lead":\n        lines = _editor_lines\(slide, "quote", "quote_lines"\)\n.*?\n        \}\)\n',
        QUOTE_EDITOR_TO_RENDERER,
        'quote_lead editor-to-renderer adapter',
    )

    replace_regex_block(
        DASHBOARD,
        r'    elif template == "quote_lead":\n        editor\["quote"\] = _line_value\(slide\.get\("quote_lines"\)\)\n.*?(?=\n    elif template ==|\n    else:)',
        QUOTE_RENDERER_TO_EDITOR.rstrip(),
        'quote_lead renderer-to-editor adapter',
    )

    print(f"Cover — Quote Lead {VERSION} applied successfully.")
    print('Rebuilt as a clean replacement around the black Quote Lead reference.')
    print('Run: python render_carousel.py stories/_studio_live_preview')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
