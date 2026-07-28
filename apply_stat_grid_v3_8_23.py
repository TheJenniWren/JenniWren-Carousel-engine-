from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent
LIB_PATH = ROOT / "carousel_lib.py"
DATA_PATH = ROOT / "data_templates.py"


def backup(path: Path, suffix: str) -> None:
    backup_path = path.with_name(path.name + suffix)
    if not backup_path.exists():
        shutil.copy2(path, backup_path)
        print(f"Backup created: {backup_path.name}")
    else:
        print(f"Backup already exists: {backup_path.name}")


def replace_once(path: Path, pattern: str, replacement: str, label: str, flags=0) -> None:
    text = path.read_text()
    new_text, count = re.subn(pattern, replacement, text, flags=flags)
    if count != 1:
        print(f"\nERROR: Could not safely replace {label} in {path.name}.")
        print("No changes were written.")
        sys.exit(1)
    path.write_text(new_text)
    print(f"Updated {label} in {path.name}.")


backup(LIB_PATH, ".before_stat_grid_v3_8_23")
backup(DATA_PATH, ".before_stat_grid_v3_8_23")

new_draw_stat_grid = '''def draw_stat_grid(draw, items, y0, cols=2, cell_h=245):
    """
    Stat Grid v3.8.23

    Goals:
    - larger statistic values
    - larger statistic labels
    - cleaner spacing
    - grid sits lower on the slide
    - supports both Studio tuple input and dict-style input

    Supported item shapes:
    - ("$292M", "Housing contract")
    - {"stat_text": "$292M", "label": "Housing contract"}
    - {"value": "$292M", "label": "Housing contract"}
    - {"statistic": "$292M", "label": "Housing contract"}
    """
    items = items or []
    if not items:
        return y0

    normalized = []
    for item in items:
        if isinstance(item, dict):
            stat_text = str(
                item.get("stat_text")
                or item.get("statistic")
                or item.get("value")
                or item.get("number")
                or ""
            ).strip()
            label_text = str(
                item.get("label")
                or item.get("stat_label")
                or item.get("title")
                or ""
            ).strip()
        elif isinstance(item, (list, tuple)):
            stat_text = str(item[0]).strip() if len(item) > 0 else ""
            label_text = str(item[1]).strip() if len(item) > 1 else ""
        else:
            stat_text = str(item).strip()
            label_text = ""

        normalized.append({
            "stat_text": stat_text,
            "label": label_text,
        })

    items = normalized
    cols = max(1, int(cols or 2))
    rows = max(1, (len(items) + cols - 1) // cols)

    grid_w = W - L_MARGIN - R_MARGIN
    col_w = grid_w / cols

    divider_color = (68, 68, 68)

    value_font_max = 96
    value_font_min = 60
    label_font_size = 38

    for idx, item in enumerate(items):
        row = idx // cols
        col = idx % cols

        cell_x = int(L_MARGIN + col * col_w)
        cell_y = int(y0 + row * cell_h)
        inner_x = cell_x
        inner_y = cell_y + 18
        inner_w = int(col_w - 26)

        stat_text = item.get("stat_text", "")
        label_text = item.get("label", "")

        value_font = f(BARLOW, value_font_max)
        while value_font.size > value_font_min:
            bbox = draw.textbbox((0, 0), stat_text, font=value_font)
            if (bbox[2] - bbox[0]) <= inner_w:
                break
            value_font = f(BARLOW, value_font.size - 2)

        draw.text((inner_x, inner_y), stat_text, font=value_font, fill=PINK)
        value_bbox = draw.textbbox((inner_x, inner_y), stat_text, font=value_font)
        label_y = value_bbox[3] + 18

        label_font = f(BARLOW, label_font_size)
        label_lines = wrap_lines(draw, [(label_text, WHITE)], label_font, inner_w)

        asc, desc = label_font.getmetrics()
        label_lh = int((asc + desc) * 1.05)

        for lwords in label_lines[:2]:
            x = inner_x
            for i, (word, col_) in enumerate(lwords):
                draw.text((x, label_y), word, font=label_font, fill=col_)
                x += mw(draw, word, label_font)
                if i < len(lwords) - 1:
                    x += mw(draw, " ", label_font)
            label_y += label_lh

        if col < cols - 1 and idx + 1 < len(items):
            vx = int(cell_x + col_w - 16)
            draw.line(
                [(vx, cell_y), (vx, cell_y + cell_h - 30)],
                fill=divider_color,
                width=2,
            )

    for r in range(rows - 1):
        hy = int(y0 + (r + 1) * cell_h - 20)
        draw.line(
            [(L_MARGIN, hy), (W - R_MARGIN, hy)],
            fill=divider_color,
            width=2,
        )

    return int(y0 + rows * cell_h)
'''

new_render_stat_grid = '''def render_stat_grid(slide: StorySlide, n: int, total: int, story: StoryPackage,
                     defaults: TemplateDefaults):
    require_fields(slide, "label", "stat_items")
    qa_notes: List[str] = []

    img, draw = cl.new_canvas()
    cl.draw_top_bar(draw, slide.get("label"), n, total, big=bool(slide.get("big_label", False)))

    y0 = cl.HEAD_Y
    headline_lines = slide.get("headline_lines")
    if headline_lines:
        colors = colors_from_names(
            slide.get("headline_colors", ["white"] * len(headline_lines)),
            slide.slide_id
        )
        sr = tuple(slide.get("headline_range", (108, 210)))
        y0 = cl.draw_headline(draw, headline_lines, colors, cl.HEAD_Y, sr) + 105
    else:
        y0 = cl.HEAD_Y + 150

    raw_items = slide.get("stat_items") or []
    items = []
    for item in raw_items:
        if isinstance(item, dict):
            items.append(item)
        elif isinstance(item, (list, tuple)):
            items.append({
                "stat_text": str(item[0]) if len(item) > 0 else "",
                "label": str(item[1]) if len(item) > 1 else "",
            })
        else:
            items.append({
                "stat_text": str(item),
                "label": "",
            })

    grid_bottom = cl.draw_stat_grid(
        draw,
        items,
        y0,
        cols=slide.get("grid_cols", defaults.grid_cols),
        cell_h=slide.get("grid_cell_h", 245),
    )

    if grid_bottom > cl.FOOTER_SAFE:
        qa_notes.append(
            f"stat_grid extends to y={grid_bottom}, past the footer-safe line "
            f"(y={cl.FOOTER_SAFE}) -- reduce grid_cell_h or item count."
        )

    cl.draw_footer(
        draw,
        brand_name=story.brand_footer,
        arrow=bool(slide.get("arrow", True)),
    )
    return img, qa_notes
'''

replace_once(
    LIB_PATH,
    r"def draw_stat_grid\(draw, items, y0, cols=2, cell_h=.*?(?=\n# — CALL BLOCK)",
    new_draw_stat_grid,
    "draw_stat_grid()",
    flags=re.S,
)

replace_once(
    DATA_PATH,
    r"def render_stat_grid\(slide: StorySlide, n: int, total: int, story: StoryPackage,\n\s*defaults: TemplateDefaults\):.*?return img, qa_notes\n",
    new_render_stat_grid + "\n",
    "render_stat_grid()",
    flags=re.S,
)

print("\nStat Grid v3.8.23 applied successfully.")
print("What changed:")
print("- larger headline range")
print("- grid starts lower on the slide")
print("- larger pink statistic values")
print("- larger white labels")
print("- tuple and dict stat_items both supported")
print("\nNow run:")
print("python render_carousel.py stories/_studio_live_preview")
