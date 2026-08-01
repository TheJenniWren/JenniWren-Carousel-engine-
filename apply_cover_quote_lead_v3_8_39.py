#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path

VERSION = "v3.8.39"


def pick_file(candidates: list[str]) -> Path:
    for root in (Path.cwd(), Path(__file__).resolve().parent):
        for name in candidates:
            path = root / name
            if path.exists():
                return path
    raise SystemExit(f"ERROR: Could not find any of: {', '.join(candidates)}")


COVER = pick_file(["cover_templates.py", "cover_templates(1).py"])
BACKUP = COVER.with_name(COVER.name + f".before_cover_quote_lead_{VERSION}")

NEW_RENDER = r'''def render_quote_lead(slide: StorySlide, n: int, total: int, story: StoryPackage,
                      defaults: TemplateDefaults):
    """Cover — Quote Lead v3.8.39.

    Fixed-band black Quote Lead layout. This intentionally avoids the overly
    conservative generic fitter used in v3.8.38.
    """
    require_fields(slide, "label", "quote_lines", "attribution")
    qa_notes: List[str] = []

    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total,
                    big=bool(slide.get("big_label", False)))

    def normalize(value, default_fill=cl.WHITE, uppercase=False):
        out = []

        def add(text, fill):
            text = str(text or "")
            if uppercase:
                text = text.upper()
            if text.strip():
                out.append((text.strip(), fill))

        def parse_inline(text, fill):
            text = str(text or "")
            pattern = re.compile(r'(<pink>.*?</pink>|\[\[pink:.*?\]\])', re.I | re.S)
            pos = 0
            for match in pattern.finditer(text):
                if match.start() > pos:
                    add(text[pos:match.start()], fill)
                token = match.group(0)
                if token.lower().startswith('<pink>'):
                    add(token[6:-7], cl.PINK)
                else:
                    add(token[7:-2], cl.PINK)
                pos = match.end()
            if pos < len(text):
                add(text[pos:], fill)

        def walk(node, fill=default_fill):
            if node is None:
                return
            if isinstance(node, str):
                parse_inline(node, fill)
                return
            if isinstance(node, dict):
                node_fill = cl.PINK if str(node.get("color") or "").lower() == "pink" else fill
                if "text" in node:
                    parse_inline(node.get("text"), node_fill)
                    return
                for key in ("segments", "content", "children", "body"):
                    if key in node:
                        walk(node.get(key), node_fill)
                        return
                return
            if isinstance(node, (list, tuple)):
                for child in node:
                    walk(child, fill)
                return
            parse_inline(str(node), fill)

        walk(value)
        return out

    def wrap_rich(segments, font, max_w):
        words = []
        for text, fill in segments:
            words.extend((word, fill) for word in str(text).split())
        lines, current, current_w = [], [], 0
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

    def line_width(line, font):
        if not line:
            return 0
        space_w = cl.mw(draw, " ", font)
        return sum(cl.mw(draw, word, font) for word, _ in line) + space_w * (len(line) - 1)

    def draw_rich(lines, font, x, y, line_h):
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

    def wrap_plain(text, font, max_w):
        lines, current = [], ""
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

    # Fixed visual bands, modeled on the black reference.
    quote_x = 205
    quote_y = 178
    quote_w = 790
    quote_band_bottom = 690
    divider_y = 855

    quote_source = slide.get("quote_lines") or []
    if not isinstance(quote_source, (list, tuple)):
        quote_source = [quote_source]

    explicit = [normalize(item, cl.WHITE, uppercase=True) for item in quote_source]
    explicit = [line for line in explicit if line]
    if not explicit:
        explicit = [[("QUOTE", cl.WHITE)]]

    # Opening mark is a separate graphic element, not part of the text flow.
    draw.text((42, 132), "“", font=cl.lf(cl.BASK_REG, 205), fill=cl.PINK)

    quote_font = None
    quote_lines = None
    quote_lh = None

    if len(explicit) > 1:
        # Preserve user-supplied editorial line breaks exactly.
        for size in range(150, 88, -2):
            font = cl.lf(cl.BARLOW, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 0.78)
            if (all(line_width(line, font) <= quote_w for line in explicit)
                    and quote_y + len(explicit) * lh <= quote_band_bottom):
                quote_font, quote_lines, quote_lh = font, explicit, lh
                break
    else:
        merged = explicit[0]
        # Force a dominant 4–6-line composition instead of shrinking prematurely.
        for size in range(154, 92, -2):
            font = cl.lf(cl.BARLOW, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 0.78)
            lines = wrap_rich(merged, font, quote_w)
            if (4 <= len(lines) <= 6
                    and quote_y + len(lines) * lh <= quote_band_bottom):
                quote_font, quote_lines, quote_lh = font, lines, lh
                break

    if quote_font is None:
        quote_font = cl.lf(cl.BARLOW, 96)
        asc, desc = quote_font.getmetrics()
        quote_lh = int((asc + desc) * 0.78)
        quote_lines = explicit if len(explicit) > 1 else wrap_rich(explicit[0], quote_font, quote_w)

    quote_bottom = draw_rich(quote_lines, quote_font, quote_x, quote_y, quote_lh)

    # Closing mark sits beside the last line, matching the reference.
    close_font = cl.lf(cl.BASK_REG, 178)
    last_w = line_width(quote_lines[-1], quote_font)
    close_x = min(cl.W - cl.R_MARGIN - 78, quote_x + last_w + 12)
    close_y = quote_bottom - int(close_font.size * 0.79)
    draw.text((close_x, close_y), "”", font=close_font, fill=cl.PINK)

    # Attribution block fills the remaining upper band.
    attribution = str(slide.get("attribution") or "").strip().upper()
    attr_y = quote_bottom + 20
    attr_font = cl.lf(cl.BARLOW, 46)
    draw.text((quote_x, attr_y), f"– {attribution}", font=attr_font, fill=cl.PINK)

    detail = str(slide.get("attribution_detail") or "").strip()
    detail_y = attr_y + 50
    if detail:
        detail_font = cl.lf(cl.BARLOW, 25)
        for raw in [part.strip() for part in detail.split("\n") if part.strip()]:
            for line in wrap_plain(raw, detail_font, cl.W - quote_x - cl.R_MARGIN):
                draw.text((quote_x, detail_y), line, font=detail_font, fill=cl.WHITE)
                detail_y += 29

    draw.line((cl.L_MARGIN, divider_y, cl.W - cl.R_MARGIN, divider_y), fill=cl.PINK, width=5)

    # Context headline.
    context_lines = list(slide.get("context_headline_lines") or [])
    context_colors = list(slide.get("context_headline_colors") or [])
    if not context_colors:
        context_colors = ["white"] * len(context_lines)

    context_y = divider_y + 26
    context_bottom = context_y
    if context_lines:
        context_font = None
        context_lh = None
        max_w = cl.W - cl.L_MARGIN - cl.R_MARGIN - 40
        for size in range(76, 50, -2):
            font = cl.lf(cl.BARLOW, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 0.80)
            if all(draw.textbbox((0, 0), str(line).upper(), font=font)[2] <= max_w
                   for line in context_lines[:3]):
                context_font, context_lh = font, lh
                break
        if context_font is None:
            context_font = cl.lf(cl.BARLOW, 52)
            asc, desc = context_font.getmetrics()
            context_lh = int((asc + desc) * 0.80)

        cy = context_y
        for idx, line in enumerate(context_lines[:3]):
            fill = cl.PINK if str(context_colors[idx] if idx < len(context_colors) else "white").lower() == "pink" else cl.WHITE
            draw.text((cl.L_MARGIN, cy), str(line).upper(), font=context_font, fill=fill)
            cy += context_lh
        context_bottom = cy

    # Context body uses the lower slide down to the footer-safe area.
    body_segments = normalize(slide.get("context_body"), cl.WHITE, uppercase=False)
    if body_segments:
        body_y = context_bottom + 14
        body_w = cl.W - cl.L_MARGIN - cl.R_MARGIN - 14
        chosen = None
        for size in range(40, 35, -1):
            font = cl.lf(cl.BASK_REG, size)
            asc, desc = font.getmetrics()
            lh = int((asc + desc) * 1.12)
            lines = wrap_rich(body_segments, font, body_w)
            if 3 <= len(lines) <= 5 and body_y + len(lines) * lh <= cl.FOOTER_SAFE - 6:
                chosen = font, lines, lh
                break
        if chosen is None:
            font = cl.lf(cl.BASK_REG, 36)
            asc, desc = font.getmetrics()
            chosen = font, wrap_rich(body_segments, font, body_w), int((asc + desc) * 1.12)
        body_font, body_lines, body_lh = chosen
        draw_rich(body_lines[:5], body_font, cl.L_MARGIN, body_y, body_lh)

    cl.draw_footer(draw, brand_name=story.brand_footer,
                   arrow=bool(slide.get("arrow", True)))
    return img, qa_notes
'''


def main() -> int:
    if not BACKUP.exists():
        shutil.copy2(COVER, BACKUP)
        print(f"Backup created: {BACKUP.name}")

    text = COVER.read_text(encoding="utf-8")
    if not re.search(r"^import re$", text, re.M):
        marker = "from __future__ import annotations\n\n"
        if marker not in text:
            raise SystemExit(f"ERROR: Could not locate import block in {COVER.name}.")
        text = text.replace(marker, marker + "import re\n\n", 1)

    pattern = re.compile(r"^def render_quote_lead\(.*?(?=^def |\Z)", re.M | re.S)
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"ERROR: Could not locate render_quote_lead() in {COVER.name}.")

    updated = text[:match.start()] + NEW_RENDER.rstrip() + "\n\n\n" + text[match.end():]
    COVER.write_text(updated, encoding="utf-8")

    print(f"Cover — Quote Lead {VERSION} applied successfully.")
    print("Replaced the generic fitter with a fixed-band black-reference layout.")
    print("Studio field mapping from v3.8.38 remains unchanged.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
