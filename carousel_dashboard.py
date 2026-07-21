#!/usr/bin/env python3
"""
JenniWren Studio v2.7.2

Structured browser editor for the ten templates currently supported by the
JenniWren carousel renderer.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STORIES_DIR = ROOT / "stories"
OUTPUT_DIR = ROOT / "output"
RENDERER = ROOT / "render_carousel.py"
HOST = "0.0.0.0"
PORT = 8000
PREVIEW_FOLDER = "_studio_live_preview"
PREVIEW_STORY = "studio-live-preview"

TEMPLATE_SCHEMA_REGISTRY: dict[str, dict[str, Any]] = {
    "cover_headline": {
        "label": "Cover — Headline",
        "required": ["label", "headline_lines", "headline_colors"],
        "optional": ["body", "citation"],
        "defaults": {"label": "THE JENNI WREN", "headline_colors": ["white"]},
        "widgets": [
            {"editor": "headline", "renderer": "headline_lines", "label": "Headline", "type": "lines"},
            {"editor": "deck", "renderer": "body", "label": "Deck / body", "type": "body"},
            {"editor": "citation", "renderer": "citation", "label": "Citation", "type": "text"},
        ],
        "aliases": {"headline": "headline_lines", "deck": "body"},
    },
    "quote_lead": {
        "label": "Cover — Quote Lead",
        "required": ["label", "quote_lines", "quote_colors", "attribution"],
        "optional": ["citation"],
        "defaults": {"label": "QUOTE", "quote_colors": ["white"]},
        "widgets": [
            {"editor": "quote", "renderer": "quote_lines", "label": "Quote", "type": "lines"},
            {"editor": "attribution", "renderer": "attribution", "label": "Attribution", "type": "text"},
            {"editor": "citation", "renderer": "citation", "label": "Citation", "type": "text"},
        ],
        "aliases": {"quote": "quote_lines"},
    },
    "photo_headline": {
        "label": "Cover — Photo Story",
        "required": ["label", "image", "headline_lines", "headline_colors"],
        "optional": ["citation"],
        "defaults": {"label": "PHOTO STORY", "headline_colors": ["white"]},
        "widgets": [
            {"editor": "image", "renderer": "image", "label": "Image filename", "type": "text"},
            {"editor": "headline", "renderer": "headline_lines", "label": "Headline", "type": "lines"},
            {"editor": "citation", "renderer": "citation", "label": "Citation", "type": "text"},
        ],
        "aliases": {"headline": "headline_lines", "image_filename": "image"},
    },
    "stat_callout": {
        "label": "Data — Big Number",
        "required": ["label", "stat_text", "stat_label"],
        "optional": ["headline_lines", "citation"],
        "defaults": {"label": "BY THE NUMBERS"},
        "widgets": [
            {"editor": "statistic", "renderer": "stat_text", "label": "Statistic", "type": "text"},
            {"editor": "statistic_label", "renderer": "stat_label", "label": "Statistic label", "type": "text"},
            {"editor": "context", "renderer": "headline_lines", "label": "Context", "type": "lines"},
            {"editor": "citation", "renderer": "citation", "label": "Citation", "type": "text"},
        ],
        "aliases": {"statistic": "stat_text", "statistic_label": "stat_label", "context": "headline_lines"},
    },
    "stat_grid": {
        "label": "Data — Stat Grid",
        "required": ["label", "stat_items"],
        "optional": ["headline_lines", "citation"],
        "defaults": {"label": "KEY NUMBERS"},
        "widgets": [
            {"editor": "headline", "renderer": "headline_lines", "label": "Headline", "type": "lines"},
            {"editor": "statistics", "renderer": "stat_items", "label": "Statistics", "type": "stats"},
            {"editor": "citation", "renderer": "citation", "label": "Citation", "type": "text"},
        ],
        "aliases": {"headline": "headline_lines", "statistics": "stat_items"},
    },
    "timeline": {
        "label": "Explainer — Timeline",
        "required": ["label", "headline_lines", "headline_colors", "timeline_entries"],
        "optional": ["citation"],
        "defaults": {"label": "TIMELINE", "headline_colors": ["white"]},
        "widgets": [
            {"editor": "headline", "renderer": "headline_lines", "label": "Headline", "type": "lines"},
            {"editor": "events", "renderer": "timeline_entries", "label": "Timeline entries", "type": "timeline"},
            {"editor": "citation", "renderer": "citation", "label": "Citation", "type": "text"},
        ],
        "aliases": {"headline": "headline_lines", "events": "timeline_entries"},
    },
    "call_block": {
        "label": "Comparison — Call Block",
        "required": ["label", "call_text"],
        "optional": ["headline_lines", "body", "citation"],
        "defaults": {"label": "THE POINT"},
        "widgets": [
            {"editor": "headline", "renderer": "headline_lines", "label": "Optional headline", "type": "lines"},
            {"editor": "statement", "renderer": "call_text", "label": "Highlighted statement", "type": "body"},
            {"editor": "body", "renderer": "body", "label": "Supporting body", "type": "body"},
            {"editor": "citation", "renderer": "citation", "label": "Citation", "type": "text"},
        ],
        "aliases": {"headline": "headline_lines", "statement": "call_text"},
    },
    "document_card": {
        "label": "Evidence — Document Card",
        "required": ["label", "doc_lines", "headline_lines", "headline_colors"],
        "optional": ["doc_highlight", "doc_annotation", "citation", "image"],
        "defaults": {"label": "DOCUMENT EVIDENCE", "headline_colors": ["white"]},
        "widgets": [
            {"editor": "image", "renderer": "image", "label": "Document image", "type": "text"},
            {"editor": "headline", "renderer": "headline_lines", "label": "Headline", "type": "lines"},
            {"editor": "excerpt", "renderer": "doc_lines", "label": "Document excerpt", "type": "lines"},
            {"editor": "highlight", "renderer": "doc_highlight", "label": "Highlighted excerpt", "type": "text"},
            {"editor": "annotation", "renderer": "doc_annotation", "label": "Annotation", "type": "body"},
            {"editor": "citation", "renderer": "citation", "label": "Citation", "type": "text"},
        ],
        "aliases": {
            "headline": "headline_lines", "excerpt": "doc_lines",
            "highlight": "doc_highlight", "annotation": "doc_annotation",
            "image_filename": "image",
        },
    },
    "body_standard": {
        "label": "Interior — Standard Explainer",
        "required": ["label", "headline_lines", "headline_colors", "body"],
        "optional": ["citation"],
        "defaults": {"label": "WHAT HAPPENED", "headline_colors": ["white"]},
        "widgets": [
            {"editor": "headline", "renderer": "headline_lines", "label": "Headline", "type": "lines"},
            {"editor": "body", "renderer": "body", "label": "Body", "type": "body"},
            {"editor": "citation", "renderer": "citation", "label": "Citation", "type": "text"},
        ],
        "aliases": {"headline": "headline_lines"},
    },
    "sources_slide": {
        "label": "Final — Sources",
        "required": ["citations"],
        "optional": ["label"],
        "defaults": {"label": "SOURCES"},
        "widgets": [
            {"editor": "sources", "renderer": "citations", "label": "Sources", "type": "sources"},
        ],
        "aliases": {"sources": "citations"},
    },
}

TEMPLATE_LABELS = {
    template_id: schema["label"]
    for template_id, schema in TEMPLATE_SCHEMA_REGISTRY.items()
}
REQUIRED_FIELDS = {
    template_id: tuple(schema["required"])
    for template_id, schema in TEMPLATE_SCHEMA_REGISTRY.items()
}


def _body_value(value: Any) -> list[dict[str, str]]:
    if isinstance(value, list):
        result: list[dict[str, str]] = []
        for item in value:
            if isinstance(item, dict) and str(item.get("text") or "").strip():
                result.append({"text": str(item["text"]).strip()})
            elif isinstance(item, str) and item.strip():
                result.append({"text": item.strip()})
        return result
    if isinstance(value, dict):
        value = value.get("text")
    return [{"text": str(value).strip()}] if str(value or "").strip() else []


def _line_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def adapt_slide_to_renderer(slide: dict[str, Any]) -> dict[str, Any]:
    """Convert editor-friendly or AI-friendly fields to renderer-native JSON."""
    template = str(slide.get("template") or "")
    schema = TEMPLATE_SCHEMA_REGISTRY.get(template)
    if schema is None:
        return dict(slide)

    adapted = dict(schema.get("defaults") or {})
    adapted["template"] = template

    # Preserve renderer-native values first.
    allowed = set(schema["required"]) | set(schema["optional"]) | {"id", "template", "label"}
    for key in allowed:
        if key in slide:
            adapted[key] = slide[key]

    # Map editor/AI aliases into renderer keys.
    for editor_key, renderer_key in schema.get("aliases", {}).items():
        if renderer_key not in adapted and editor_key in slide:
            adapted[renderer_key] = slide[editor_key]

    # Normalize renderer data types.
    line_fields = {
        "headline_lines", "quote_lines", "doc_lines", "headline_colors", "quote_colors"
    }
    body_fields = {"body", "call_text", "doc_annotation"}

    for key in line_fields:
        if key in adapted:
            adapted[key] = _line_value(adapted[key])
    for key in body_fields:
        if key in adapted:
            adapted[key] = _body_value(adapted[key])

    if template == "timeline":
        entries = adapted.get("timeline_entries") or []
        adapted["timeline_entries"] = [
            {
                "date": str(item.get("date") or item.get("label") or "").strip(),
                "text": str(item.get("text") or item.get("event") or "").strip(),
            }
            for item in entries
            if isinstance(item, dict)
            and (
                str(item.get("date") or item.get("label") or "").strip()
                or str(item.get("text") or item.get("event") or "").strip()
            )
        ]

    if template == "stat_grid":
        items = adapted.get("stat_items") or []
        adapted["stat_items"] = [
            {
                "stat_text": str(item.get("stat_text") or item.get("value") or "").strip(),
                "stat_label": str(item.get("stat_label") or item.get("label") or "").strip(),
            }
            for item in items
            if isinstance(item, dict)
        ]

    if template == "sources_slide":
        citations = adapted.get("citations") or []
        adapted["citations"] = [
            str(item.get("citation") or item.get("text") or "").strip()
            if isinstance(item, dict) else str(item).strip()
            for item in citations
            if (
                str(item.get("citation") or item.get("text") or "").strip()
                if isinstance(item, dict) else str(item).strip()
            )
        ]

    return adapted


def adapt_payload_to_renderer(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "story": str(payload.get("story") or payload.get("title") or "").strip(),
        "source": str(payload.get("source") or "").strip(),
        "slides": [
            adapt_slide_to_renderer(slide)
            for slide in payload.get("slides", [])
            if isinstance(slide, dict)
        ],
    }



def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "story"


def safe_child(base: Path, child: str) -> Path:
    base = base.resolve()
    candidate = (base / child).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError("Unsafe path")
    return candidate


def load_story(folder_slug: str) -> dict[str, Any]:
    path = safe_child(STORIES_DIR, folder_slug) / "carousel.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}



def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def validate_payload(payload: Any) -> list[str]:
    """Return clear, user-facing validation errors."""
    errors: list[str] = []

    if not isinstance(payload, dict):
        return ["The imported package must be one JSON object."]

    payload = adapt_payload_to_renderer(payload)

    if not str(payload.get("story") or "").strip():
        errors.append("Story title is required.")

    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("At least one slide is required.")
        return errors

    for index, slide in enumerate(slides, start=1):
        prefix = f"Slide {index}"
        if not isinstance(slide, dict):
            errors.append(f"{prefix} must be a JSON object.")
            continue

        template = slide.get("template")
        if template not in TEMPLATE_LABELS:
            errors.append(
                f"{prefix}: unsupported template '{template}'. "
                f"Choose one of the 10 Studio templates."
            )
            continue

        for field in REQUIRED_FIELDS[template]:
            if not _has_content(slide.get(field)):
                friendly = field.replace("_", " ")
                errors.append(
                    f"{prefix} ({TEMPLATE_LABELS[template]}): "
                    f"missing required field '{friendly}'."
                )

        if template == "timeline":
            entries = slide.get("timeline_entries")
            if isinstance(entries, list):
                for entry_index, entry in enumerate(entries, start=1):
                    if not isinstance(entry, dict) or not (
                        str(entry.get("date") or entry.get("label") or "").strip()
                        or str(entry.get("text") or entry.get("event") or "").strip()
                    ):
                        errors.append(
                            f"{prefix}: timeline entry {entry_index} needs a date "
                            "or event description."
                        )

        if template == "stat_grid":
            items = slide.get("stat_items")
            if isinstance(items, list):
                for item_index, item in enumerate(items, start=1):
                    if not isinstance(item, dict) or not (
                        str(item.get("stat_text") or item.get("value") or "").strip()
                        or str(item.get("stat_label") or item.get("label") or "").strip()
                    ):
                        errors.append(
                            f"{prefix}: statistic {item_index} needs a value or label."
                        )

    return errors

def run_renderer(folder_slug: str) -> tuple[int, str]:
    story_dir = safe_child(STORIES_DIR, folder_slug)
    try:
        process = subprocess.run(
            [sys.executable, str(RENDERER), str(story_dir)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, f"{exc.stdout or ''}\nERROR: Render timed out after 300 seconds."
    return process.returncode, process.stdout



def render_preview_payload(
    payload: dict[str, Any],
    slide_index: int,
) -> tuple[int, str, str]:
    """Render the active slide with the exact production renderer."""
    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("At least one slide is required for preview.")

    index = max(0, min(int(slide_index), len(slides) - 1))
    selected = slides[index]
    if not isinstance(selected, dict):
        raise ValueError(f"Slide {index + 1} is invalid.")

    preview_payload = {
        "story": PREVIEW_STORY,
        "source": str(payload.get("source") or ""),
        "slides": [adapt_slide_to_renderer(selected)],
    }

    errors = validate_payload(preview_payload)
    if errors:
        raise ValueError(errors[0])

    story_dir = safe_child(STORIES_DIR, PREVIEW_FOLDER)
    story_dir.mkdir(parents=True, exist_ok=True)
    (story_dir / "carousel.json").write_text(
        json.dumps(preview_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    exit_code, log = run_renderer(PREVIEW_FOLDER)
    return exit_code, log, slugify(PREVIEW_STORY)

def image_files(output_slug: str) -> list[Path]:
    folder = safe_child(OUTPUT_DIR, output_slug)
    return sorted(folder.glob("*.png")) if folder.exists() else []


def default_story() -> dict[str, Any]:
    return {
        "story": "",
        "source": "",
        "slides": [
            {"template": "cover_headline", "label": "THE JENNI WREN", "headline_lines": [], "headline_colors": ["white"], "body": []},
            {"template": "body_standard", "label": "WHAT HAPPENED", "headline_lines": [], "headline_colors": ["white"], "body": []},
        ],
    }


def json_script_data(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def build_page(*, folder_slug: str = "", data: dict[str, Any] | None = None,
               message: str = "", build_log: str = "", output_slug: str = "") -> str:
    data = data or default_story()
    registry_json = json.dumps(TEMPLATE_SCHEMA_REGISTRY, ensure_ascii=False).replace("</", "<\\/")

    template_options = "".join(
        f'<option value="{html.escape(template_id)}">{html.escape(label)}</option>'
        for template_id, label in TEMPLATE_LABELS.items()
    )
    notice_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    log_html = (
        "<details class='panel'><summary>Build log</summary>"
        f"<pre>{html.escape(build_log)}</pre></details>" if build_log else ""
    )
    preview_html = ""
    if output_slug:
        cards = []
        for path in image_files(output_slug):
            url = "/image/{}/{}".format(urllib.parse.quote(output_slug), urllib.parse.quote(path.name))
            cards.append(
                f'<article class="preview-card"><a href="{url}" target="_blank" rel="noopener">'
                f'<img src="{url}" alt="{html.escape(path.name)}"></a>'
                f'<div>{html.escape(path.name)}</div></article>'
            )
        if cards:
            preview_html = "<section class='panel'><h2>Rendered slides</h2><div class='previews'>" + "".join(cards) + "</div></section>"

    page = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JenniWren Studio v2.7.2</title>
<style>
:root{color-scheme:dark;--pink:#ff0a72;--bg:#080808;--panel:#151515;--panel2:#0d0d0d;--border:#363636;--text:#f7f7f7;--muted:#b8b8b8;--danger:#922048}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{width:min(1180px,calc(100% - 28px));margin:24px auto 64px}header{border-top:8px solid var(--pink);padding:24px 0 14px}h1{margin:0;font-size:clamp(38px,7vw,74px);line-height:.92;letter-spacing:-.035em;text-transform:uppercase}h2,h3{margin:0}p,.help{color:var(--muted)}.panel{margin-top:20px;padding:18px;background:var(--panel);border:1px solid var(--border);border-radius:14px}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;margin:13px 0 7px;font-weight:800}input,textarea,select{width:100%;padding:12px;border:1px solid #484848;border-radius:10px;background:var(--panel2);color:var(--text);font:inherit}textarea{resize:vertical;line-height:1.42;min-height:105px}textarea.tall{min-height:150px}.actions,.toolbar,.small-actions{display:flex;flex-wrap:wrap;gap:9px}.actions{margin-top:18px}.toolbar{align-items:center;justify-content:space-between}button{border:0;border-radius:10px;padding:12px 18px;background:var(--pink);color:#fff;font:inherit;font-weight:850;cursor:pointer}button.secondary{background:#333}button.danger{background:var(--danger)}button.small{padding:7px 10px;font-size:13px}.slide{margin-top:16px;padding:16px;background:#101010;border:1px solid var(--border);border-radius:13px}.slide-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding-bottom:10px;border-bottom:1px solid #2d2d2d}.repeater{margin-top:10px}.repeat-row{display:grid;grid-template-columns:170px 1fr auto;gap:8px;align-items:end;margin-top:8px}.repeat-row.stat{grid-template-columns:1fr 1fr auto}.repeat-row.source{grid-template-columns:1fr auto}.notice{margin-top:18px;padding:14px 16px;border-left:5px solid var(--pink);background:#1b1b1b;white-space:pre-wrap}.import-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.import-status{margin-top:10px;padding:10px 12px;border-radius:9px;background:#202020;color:var(--muted);white-space:pre-wrap}.import-status.error{border-left:4px solid #ff567f;color:#fff}.import-status.success{border-left:4px solid #55d98b;color:#fff}pre{overflow-x:auto;white-space:pre-wrap;padding:14px;border:1px solid var(--border);border-radius:10px;background:#050505}.hidden{display:none}.previews{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px}.preview-card{overflow:hidden;border:1px solid var(--border);border-radius:12px;background:var(--panel2)}.preview-card img{display:block;width:100%;height:auto}.preview-card div{padding:10px 12px;color:var(--muted);font-size:14px}.editor-preview-grid{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px;align-items:start}.preview-pane{position:sticky;top:14px}.live-frame{margin-top:12px;background:#090909;border:1px solid var(--border);border-radius:12px;overflow:hidden;min-height:280px;display:flex;align-items:center;justify-content:center}.live-frame img{display:block;width:100%;height:auto}.live-empty{padding:28px;color:var(--muted);text-align:center}.preview-strip{display:flex;gap:8px;overflow-x:auto;margin-top:10px;padding-bottom:4px}.preview-thumb{flex:0 0 74px;border:2px solid transparent;border-radius:8px;overflow:hidden;background:#111;padding:0}.preview-thumb.active{border-color:var(--pink)}.preview-thumb img{display:block;width:100%;height:auto}.preview-status{margin-top:10px;color:var(--muted)}.status-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#777;margin-right:7px}.status-dot.busy{background:#ffbf47}.status-dot.good{background:#55d98b}.status-dot.bad{background:#ff567f}.slide.active{outline:2px solid var(--pink);outline-offset:2px}.dirty-badge{display:none;color:#ffbf47;font-size:12px;font-weight:800;margin-left:8px}.slide.dirty .dirty-badge{display:inline}.validation-box{margin-top:12px;padding:12px;border:1px solid var(--border);border-radius:10px;background:#101010}.validation-box.good{border-left:4px solid #55d98b}.validation-box.bad{border-left:4px solid #ff567f}.validation-title{font-weight:850;margin-bottom:6px}.validation-list{margin:0;padding-left:18px;color:var(--muted)}.preview-nav{display:grid;grid-template-columns:auto 1fr auto;gap:8px;align-items:center;margin-top:12px}.preview-nav .counter{text-align:center;font-weight:800}.save-state{margin-left:auto;color:var(--muted);font-size:13px}.import-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}.import-tab.active{background:var(--pink)}.reporting-help{font-size:13px;color:var(--muted);margin-top:6px}.field-error{border-color:#ff567f!important;box-shadow:0 0 0 1px #ff567f}.slide.collapsed .slide-body{display:none}.slide-summary{display:none;color:var(--muted);font-size:13px;margin-top:8px}.slide.collapsed .slide-summary{display:block}.drag-handle{cursor:grab;user-select:none;padding:7px 10px;background:#252525;border-radius:8px;font-weight:900}.slide.dragging{opacity:.5}.slide.drop-target{outline:2px dashed var(--pink);outline-offset:3px}.ai-builder-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.ai-choice{display:flex;gap:8px;align-items:center;margin-top:8px}.ai-plan{margin-top:12px;padding:12px;border:1px solid var(--border);border-radius:10px;background:#101010}.thumb-drag{cursor:grab}.app-error{margin:18px 0;padding:16px;border:1px solid #ff567f;border-left:6px solid #ff567f;border-radius:12px;background:#231016}.app-error h2{margin:0 0 8px}.app-error pre{margin:10px 0 0}.template-error{padding:12px;border:1px solid #ff567f;border-radius:10px;background:#211015;color:#fff}summary{cursor:pointer;font-weight:800}@media(max-width:900px){.editor-preview-grid{grid-template-columns:1fr}.preview-pane{position:static}}@media(max-width:720px){.two,.import-grid,.ai-builder-grid{grid-template-columns:1fr;gap:0}.slide-head{align-items:flex-start;flex-direction:column}.repeat-row,.repeat-row.stat{grid-template-columns:1fr}}
</style>
</head>
<body>
<main>
<header><h1>JenniWren Studio v2.7.2</h1><p>Renderer-integrated templates driven by one schema registry.</p></header>
<section id="app-error" class="app-error hidden" role="alert">
  <h2>Template registry failed</h2>
  <div id="app-error-message"></div>
  <pre id="app-error-detail"></pre>
  <p>Studio has switched to its fallback editor. See the browser console for details.</p>
</section>
<section class="panel">
<div class="toolbar"><h2>Open or Import</h2></div>
<div class="import-grid">
  <div>
    <label for="load-folder">Load existing story folder</label>
    <input id="load-folder" placeholder="musk-political-spending">
    <div class="actions">
      <button type="button" class="secondary" id="load-story">Load Existing Story</button>
    </div>
  </div>
  <div>
    <div class="import-tabs">
      <button type="button" class="small import-tab active" data-import-mode="json">AI / Carousel JSON</button>
      <button type="button" class="small secondary import-tab" data-import-mode="reporting">Reporting / Markdown</button>
    </div>
    <div id="json-import-panel">
      <label for="import-json">Import Carousel JSON</label>
      <textarea id="import-json" placeholder='Paste a complete carousel JSON package here'></textarea>
      <div class="actions">
        <button type="button" id="import-json-button">Import &amp; Fill Form</button>
      </div>
    </div>
    <div id="reporting-import-panel" class="hidden">
      <label for="import-reporting">Paste reporting, article text, or Markdown</label>
      <textarea id="import-reporting" class="tall" placeholder="Paste the article, notes, or Markdown here"></textarea>
      <label for="reporting-source">Source line</label>
      <input id="reporting-source" placeholder="Associated Press, July 21, 2026">
      <div class="reporting-help">
        Studio creates a draft cover and explainer slides from headings and paragraphs.
        Review all facts and wording before rendering.
      </div>
      <div class="actions">
        <button type="button" id="import-reporting-button">Build Draft Carousel</button>
      </div>
    </div>
  </div>
</div>
<div id="import-status" class="import-status hidden"></div>
</section>
<section class="panel">
<div class="toolbar"><h2>AI Story Builder</h2><span class="help">Local editorial draft builder</span></div>
<div class="ai-builder-grid">
  <div>
    <label for="ai-story-input">Paste AP copy, an article, Perplexity output, Claude output, or notes</label>
    <textarea id="ai-story-input" class="tall" placeholder="Paste reporting here"></textarea>
  </div>
  <div>
    <label for="ai-story-source">Source</label>
    <input id="ai-story-source" placeholder="Associated Press, July 21, 2026">
    <label for="ai-slide-count">Target slide count</label>
    <select id="ai-slide-count">
      <option value="6">6 slides</option>
      <option value="7">7 slides</option>
      <option value="8" selected>8 slides</option>
      <option value="9">9 slides</option>
      <option value="10">10 slides</option>
    </select>
    <div class="ai-choice">
      <input id="ai-include-sources" type="checkbox" checked style="width:auto">
      <label for="ai-include-sources" style="margin:0">Include sources slide</label>
    </div>
    <div class="actions"><button type="button" id="ai-build-story">Build Story Draft</button></div>
    <div id="ai-plan" class="ai-plan hidden"></div>
  </div>
</div>
</section>
<form id="studio-form" method="post" action="/render">
<div class="editor-preview-grid">
<div>
<section class="panel"><h2>Story</h2><div class="two"><div><label for="folder_slug">Story folder name</label><input id="folder_slug" name="folder_slug" value="__FOLDER__" placeholder="musk-political-spending" required></div><div><label for="story_title">Story title</label><input id="story_title" placeholder="Elon Musk's political spending" required></div></div><label for="source">Primary source</label><input id="source" placeholder="Associated Press, July 21, 2026"></section>
<section class="panel"><div class="toolbar"><h2>Slides</h2><button type="button" id="add-slide">+ Add slide</button></div><div id="slides"></div></section>
</div>
<aside class="panel preview-pane">
<div class="toolbar"><h2>Live Preview</h2><label style="margin:0;font-weight:700"><input id="auto-preview" type="checkbox" checked style="width:auto;margin-right:6px">Auto</label></div>
<div id="preview-status" class="preview-status"><span class="status-dot busy"></span>Rendering first slide…</div>
<div id="live-frame" class="live-frame"><div class="live-empty">Rendering…</div></div>
<div class="preview-nav">
  <button type="button" class="small secondary" id="preview-prev">◀ Previous</button>
  <div id="preview-counter" class="counter">Slide 1 of 1</div>
  <button type="button" class="small secondary" id="preview-next">Next ▶</button>
</div>
<div id="preview-strip" class="preview-strip"></div>
<div id="validation-box" class="validation-box"></div>
<div class="actions">
  <button type="button" id="refresh-preview">Refresh</button>
  <button type="button" class="secondary" id="open-preview">Open PNG</button>
  <span id="save-state" class="save-state">Not saved</span>
</div>
</aside>
</div>
<input type="hidden" id="payload" name="payload"><div class="actions"><button type="submit">Render Full Carousel</button><button type="submit" class="secondary" formaction="/save">Save only</button><button type="button" class="secondary" id="preview-json">Preview JSON</button></div></form>
<section id="json-panel" class="panel hidden"><h2>Generated carousel.json</h2><pre id="json-output"></pre></section>
__NOTICE____LOG____PREVIEWS__
<script id="schema-registry-data" type="application/json">__SCHEMA_REGISTRY__</script>
<script id="initial-data" type="application/json">__INITIAL_DATA__</script>
<script>
const TEMPLATE_OPTIONS=`__TEMPLATE_OPTIONS__`;
const slidesRoot=document.getElementById("slides");

function showAppError(message,detail=""){
  const panel=document.getElementById("app-error");
  const messageNode=document.getElementById("app-error-message");
  const detailNode=document.getElementById("app-error-detail");
  if(panel)panel.classList.remove("hidden");
  if(messageNode)messageNode.textContent=message;
  if(detailNode)detailNode.textContent=detail;
  console.error(message,detail);
}

window.addEventListener("error",event=>{
  showAppError(
    "Studio encountered a JavaScript error.",
    `${event.message || "Unknown error"}\n${event.filename || ""}:${event.lineno || ""}`
  );
});
window.addEventListener("unhandledrejection",event=>{
  showAppError("Studio encountered an asynchronous error.",String(event.reason || ""));
});

const FALLBACK_SCHEMA_REGISTRY={
  cover_headline:{label:"Cover — Headline",required:["label","headline_lines","headline_colors"],optional:["body","citation"],defaults:{label:"THE JENNI WREN",headline_colors:["white"]},widgets:[{editor:"headline",renderer:"headline_lines",label:"Headline",type:"lines"},{editor:"deck",renderer:"body",label:"Deck / body",type:"body"},{editor:"citation",renderer:"citation",label:"Citation",type:"text"}],aliases:{headline:"headline_lines",deck:"body"}},
  quote_lead:{label:"Cover — Quote Lead",required:["label","quote_lines","quote_colors","attribution"],optional:["citation"],defaults:{label:"QUOTE",quote_colors:["white"]},widgets:[{editor:"quote",renderer:"quote_lines",label:"Quote",type:"lines"},{editor:"attribution",renderer:"attribution",label:"Attribution",type:"text"},{editor:"citation",renderer:"citation",label:"Citation",type:"text"}],aliases:{quote:"quote_lines"}},
  photo_headline:{label:"Cover — Photo Story",required:["label","image","headline_lines","headline_colors"],optional:["citation"],defaults:{label:"PHOTO STORY",headline_colors:["white"]},widgets:[{editor:"image",renderer:"image",label:"Image filename",type:"text"},{editor:"headline",renderer:"headline_lines",label:"Headline",type:"lines"},{editor:"citation",renderer:"citation",label:"Citation",type:"text"}],aliases:{headline:"headline_lines",image_filename:"image"}},
  stat_callout:{label:"Data — Big Number",required:["label","stat_text","stat_label"],optional:["headline_lines","citation"],defaults:{label:"BY THE NUMBERS"},widgets:[{editor:"statistic",renderer:"stat_text",label:"Statistic",type:"text"},{editor:"statistic_label",renderer:"stat_label",label:"Statistic label",type:"text"},{editor:"context",renderer:"headline_lines",label:"Context",type:"lines"},{editor:"citation",renderer:"citation",label:"Citation",type:"text"}],aliases:{statistic:"stat_text",statistic_label:"stat_label",context:"headline_lines"}},
  stat_grid:{label:"Data — Stat Grid",required:["label","stat_items"],optional:["headline_lines","citation"],defaults:{label:"KEY NUMBERS"},widgets:[{editor:"headline",renderer:"headline_lines",label:"Headline",type:"lines"},{editor:"statistics",renderer:"stat_items",label:"Statistics",type:"stats"},{editor:"citation",renderer:"citation",label:"Citation",type:"text"}],aliases:{headline:"headline_lines",statistics:"stat_items"}},
  timeline:{label:"Explainer — Timeline",required:["label","headline_lines","headline_colors","timeline_entries"],optional:["citation"],defaults:{label:"TIMELINE",headline_colors:["white"]},widgets:[{editor:"headline",renderer:"headline_lines",label:"Headline",type:"lines"},{editor:"events",renderer:"timeline_entries",label:"Timeline entries",type:"timeline"},{editor:"citation",renderer:"citation",label:"Citation",type:"text"}],aliases:{headline:"headline_lines",events:"timeline_entries"}},
  call_block:{label:"Comparison — Call Block",required:["label","call_text"],optional:["headline_lines","body","citation"],defaults:{label:"THE POINT"},widgets:[{editor:"headline",renderer:"headline_lines",label:"Optional headline",type:"lines"},{editor:"statement",renderer:"call_text",label:"Highlighted statement",type:"body"},{editor:"body",renderer:"body",label:"Supporting body",type:"body"},{editor:"citation",renderer:"citation",label:"Citation",type:"text"}],aliases:{headline:"headline_lines",statement:"call_text"}},
  document_card:{label:"Evidence — Document Card",required:["label","doc_lines","headline_lines","headline_colors"],optional:["doc_highlight","doc_annotation","citation","image"],defaults:{label:"DOCUMENT EVIDENCE",headline_colors:["white"]},widgets:[{editor:"image",renderer:"image",label:"Document image",type:"text"},{editor:"headline",renderer:"headline_lines",label:"Headline",type:"lines"},{editor:"excerpt",renderer:"doc_lines",label:"Document excerpt",type:"lines"},{editor:"highlight",renderer:"doc_highlight",label:"Highlighted excerpt",type:"text"},{editor:"annotation",renderer:"doc_annotation",label:"Annotation",type:"body"},{editor:"citation",renderer:"citation",label:"Citation",type:"text"}],aliases:{headline:"headline_lines",excerpt:"doc_lines",highlight:"doc_highlight",annotation:"doc_annotation",image_filename:"image"}},
  body_standard:{label:"Interior — Standard Explainer",required:["label","headline_lines","headline_colors","body"],optional:["citation"],defaults:{label:"WHAT HAPPENED",headline_colors:["white"]},widgets:[{editor:"headline",renderer:"headline_lines",label:"Headline",type:"lines"},{editor:"body",renderer:"body",label:"Body",type:"body"},{editor:"citation",renderer:"citation",label:"Citation",type:"text"}],aliases:{headline:"headline_lines"}},
  sources_slide:{label:"Final — Sources",required:["citations"],optional:["label"],defaults:{label:"SOURCES"},widgets:[{editor:"sources",renderer:"citations",label:"Sources",type:"sources"}],aliases:{sources:"citations"}}
};

function validateRegistry(registry){
  const errors=[];
  if(!registry || typeof registry!=="object" || Array.isArray(registry)){
    return ["Registry must be a JSON object."];
  }
  for(const [template,schema] of Object.entries(registry)){
    if(!schema || typeof schema!=="object"){
      errors.push(`${template}: missing schema object`);
      continue;
    }
    if(!Array.isArray(schema.widgets) || !schema.widgets.length){
      errors.push(`${template}: missing widget definition`);
    }else{
      schema.widgets.forEach((widget,index)=>{
        if(!widget || typeof widget!=="object")errors.push(`${template}: widget ${index+1} is invalid`);
        else{
          if(!widget.renderer)errors.push(`${template}: widget ${index+1} missing renderer field`);
          if(!widget.type)errors.push(`${template}: widget ${index+1} missing type`);
          if(!widget.label)errors.push(`${template}: widget ${index+1} missing label`);
        }
      });
    }
    if(!Array.isArray(schema.required))errors.push(`${template}: required must be an array`);
    if(!schema.defaults || typeof schema.defaults!=="object")errors.push(`${template}: defaults must be an object`);
  }
  return errors;
}

function loadRegistry(){
  try{
    const node=document.getElementById("schema-registry-data");
    if(!node)throw new Error("Registry data element is missing.");
    const parsed=JSON.parse(node.textContent);
    const errors=validateRegistry(parsed);
    if(errors.length)throw new Error(errors.join("\n"));
    const templateCount=Object.keys(parsed).length;
    if(templateCount!==10){
      throw new Error(`Expected 10 templates, received ${templateCount}.`);
    }
    return parsed;
  }catch(error){
    showAppError("Template registry failed",String(error.message || error));
    return FALLBACK_SCHEMA_REGISTRY;
  }
}

function loadInitialData(){
  try{
    const node=document.getElementById("initial-data");
    if(!node)throw new Error("Initial story data element is missing.");
    const parsed=JSON.parse(node.textContent);
    return parsed && typeof parsed==="object" ? parsed : {};
  }catch(error){
    showAppError("Initial story data failed to load.",String(error.message || error));
    return {story:"",source:"",slides:[]};
  }
}

const SCHEMA_REGISTRY=loadRegistry();
const initial=loadInitialData();
const schemas={};
const REQUIRED_FIELDS={};

for(const template of Object.keys(FALLBACK_SCHEMA_REGISTRY)){
  const candidate=SCHEMA_REGISTRY[template];
  const fallback=FALLBACK_SCHEMA_REGISTRY[template];
  const schema=(candidate && Array.isArray(candidate.widgets) && candidate.widgets.length)
    ? candidate : fallback;

  if(schema===fallback && candidate!==fallback){
    showAppError(
      "Template registry entry failed",
      `${template}: missing or invalid widget definition`
    );
  }

  schemas[template]=(schema.widgets||fallback.widgets).map(widget=>[
    widget.renderer,
    widget.label,
    widget.type,
    widget.editor
  ]);
  REQUIRED_FIELDS[template]=Array.isArray(schema.required)
    ? schema.required : fallback.required;
}

function adaptSlideToRenderer(slide){
  const schema=SCHEMA_REGISTRY[slide.template];
  if(!schema)return {...slide};
  const adapted={...(schema.defaults||{}),template:slide.template};

  const allowed=new Set([
    ...(schema.required||[]),
    ...(schema.optional||[]),
    "id","template","label"
  ]);
  for(const [key,value] of Object.entries(slide)){
    if(allowed.has(key))adapted[key]=value;
  }
  for(const [editorKey,rendererKey] of Object.entries(schema.aliases||{})){
    if((adapted[rendererKey]===undefined||adapted[rendererKey]===null)&&slide[editorKey]!==undefined){
      adapted[rendererKey]=slide[editorKey];
    }
  }
  return adapted;
}

function escapeHTML(value=""){return value.replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]))}function asLines(value){return Array.isArray(value)?value.join("\n"):value||""}function asBody(value){if(Array.isArray(value))return value.map(item=>typeof item==="object"?item.text||"":item).filter(Boolean).join("\n\n");if(value&&typeof value==="object")return value.text||"";return value||""}function normalizeSlide(raw={}){return {...raw,template:raw.template||"body_standard",label:raw.label||"SLIDE"}}function removeButton(){return '<button type="button" class="small danger" data-remove-row>Delete</button>'}
function fieldHTML(type,key,label,value){if(type==="text")return `<label>${label}</label><input data-key="${key}" value="${escapeHTML(String(value||""))}">`;if(type==="lines")return `<label>${label}</label><textarea data-key="${key}" data-type="lines">${escapeHTML(asLines(value))}</textarea>`;if(type==="body")return `<label>${label}</label><textarea class="tall" data-key="${key}" data-type="body">${escapeHTML(asBody(value))}</textarea>`;if(type==="timeline"){const rows=Array.isArray(value)&&value.length?value:[{date:"",text:""}];return `<div class="repeater" data-repeater="${key}" data-type="timeline"><div class="toolbar"><label>${label}</label><button type="button" class="small secondary" data-add-row>Add Event</button></div>${rows.map(item=>`<div class="repeat-row"><input data-part="date" value="${escapeHTML(String(item.date||item.label||""))}" placeholder="Date"><input data-part="text" value="${escapeHTML(String(item.text||item.event||""))}" placeholder="Event">${removeButton()}</div>`).join("")}</div>`}if(type==="stats"){const rows=Array.isArray(value)&&value.length?value:[{stat_text:"",stat_label:""}];return `<div class="repeater" data-repeater="${key}" data-type="stats"><div class="toolbar"><label>${label}</label><button type="button" class="small secondary" data-add-row>Add statistic</button></div>${rows.map(item=>`<div class="repeat-row stat"><input data-part="stat_text" value="${escapeHTML(String(item.stat_text||item.value||""))}" placeholder="Statistic"><input data-part="stat_label" value="${escapeHTML(String(item.stat_label||item.label||""))}" placeholder="Label">${removeButton()}</div>`).join("")}</div>`}if(type==="sources"){const rows=Array.isArray(value)&&value.length?value:[""];return `<div class="repeater" data-repeater="${key}" data-type="sources"><div class="toolbar"><label>${label}</label><button type="button" class="small secondary" data-add-row>Add source</button></div>${rows.map(item=>`<div class="repeat-row source"><input data-part="citation" value="${escapeHTML(String(typeof item==="object"?item.citation||item.text||"":item))}" placeholder="Source citation">${removeButton()}</div>`).join("")}</div>`}return ""}
function genericEditorHTML(data={}){
  return `
    <div class="template-error">
      <strong>Generic fallback editor</strong>
      <p>This template could not load its registry widgets. Studio remains usable.</p>
    </div>
    <label>Headline</label>
    <textarea data-key="headline_lines" data-type="lines">${escapeHTML(asLines(data.headline_lines||data.headline||""))}</textarea>
    <label>Body</label>
    <textarea class="tall" data-key="body" data-type="body">${escapeHTML(asBody(data.body||""))}</textarea>
    <label>Citation</label>
    <input data-key="citation" value="${escapeHTML(String(data.citation||""))}">
  `;
}

function renderDynamic(slide,data={}){
  const root=slide.querySelector(".dynamic-fields");
  const select=slide.querySelector("[data-template]");
  const template=select ? select.value : "body_standard";

  try{
    const fields=schemas[template];
    if(!Array.isArray(fields) || !fields.length){
      throw new Error(`${template}: missing widget definition`);
    }
    root.innerHTML=fields.map(([key,label,type,editorKey])=>
      fieldHTML(type,key,label,data[key]??data[editorKey])
    ).join("");
  }catch(error){
    root.innerHTML=genericEditorHTML(data);
    showAppError(
      "Template editor failed",
      `${template}: ${error.message || error}`
    );
  }
}

function addSlide(data={}){
  const normalized=normalizeSlide(data);
  const article=document.createElement("article");
  article.className="slide";
  article.dataset.slide="";
  article.draggable=true;

  try{
    article.innerHTML=`<div class="slide-head">
      <div><span class="drag-handle" title="Drag to reorder">☰</span> <strong>Slide <span data-number></span><span class="dirty-badge">● Unsaved</span></strong></div>
      <div class="small-actions">
        <button type="button" class="small secondary" data-collapse>Collapse</button>
        <button type="button" class="small secondary" data-duplicate>Duplicate</button>
        <button type="button" class="small danger" data-delete>Delete</button>
      </div>
    </div>
    <div class="slide-summary" data-summary></div>
    <div class="slide-body">
      <div class="two">
        <div><label>Template</label><select data-template>${TEMPLATE_OPTIONS}</select></div>
        <div><label>Label</label><input data-label value="${escapeHTML(normalized.label)}"></div>
      </div>
      <div class="dynamic-fields"></div>
    </div>`;

    slidesRoot.appendChild(article);
    const select=article.querySelector("[data-template]");
    if(select){
      const validTemplate=SCHEMA_REGISTRY[normalized.template]
        ? normalized.template : "body_standard";
      select.value=validTemplate;
    }
    renderDynamic(article,normalized);
  }catch(error){
    article.innerHTML=`<div class="slide-head"><strong>Slide failed to initialize</strong></div>
      <div class="slide-body">${genericEditorHTML(normalized)}</div>`;
    slidesRoot.appendChild(article);
    showAppError("Slide editor failed to initialize.",String(error.message || error));
  }

  renumber();
  return article;
}
function renumber(){[...slidesRoot.querySelectorAll("[data-slide]")].forEach((slide,index)=>slide.querySelector("[data-number]").textContent=index+1)}function readRepeater(container){const type=container.dataset.type;const rows=[...container.querySelectorAll(".repeat-row")];if(type==="timeline")return rows.map(row=>({date:row.querySelector('[data-part="date"]').value.trim(),text:row.querySelector('[data-part="text"]').value.trim()})).filter(item=>item.date||item.text);if(type==="stats")return rows.map(row=>({stat_text:row.querySelector('[data-part="stat_text"]').value.trim(),stat_label:row.querySelector('[data-part="stat_label"]').value.trim()})).filter(item=>item.stat_text||item.stat_label);if(type==="sources")return rows.map(row=>row.querySelector('[data-part="citation"]').value.trim()).filter(Boolean);return []}
function readSlide(slide,index){const template=slide.querySelector("[data-template]").value;const item={template,label:slide.querySelector("[data-label]").value.trim()||`SLIDE ${index+1}`};for(const [key,,type] of schemas[template]||[]){const repeater=slide.querySelector(`[data-repeater="${key}"]`);if(repeater){item[key]=readRepeater(repeater);continue}const input=slide.querySelector(`[data-key="${key}"]`);if(!input)continue;const value=input.value.trim();if(type==="lines")item[key]=value.split(/\n+/).map(v=>v.trim()).filter(Boolean);else if(type==="body")item[key]=value?[{text:value}]:[];else if(value)item[key]=value}if(["cover_headline","photo_headline","timeline","document_card","body_standard"].includes(template))item.headline_colors=["white"];if(template==="quote_lead")item.quote_colors=["white"];return item}
function buildPayload(){return {story:document.getElementById("story_title").value.trim(),source:document.getElementById("source").value.trim(),slides:[...slidesRoot.querySelectorAll("[data-slide]")].map(readSlide).map(adaptSlideToRenderer)}}function syncPayload(){const text=JSON.stringify(buildPayload(),null,2);document.getElementById("payload").value=text;document.getElementById("json-output").textContent=text}
slidesRoot.addEventListener("change",event=>{
  if(event.target.matches("[data-template]")){
    const slide=event.target.closest("[data-slide]");
    const template=event.target.value;const schema=SCHEMA_REGISTRY[template];if(schema?.defaults?.label)slide.querySelector("[data-label]").value=schema.defaults.label;renderDynamic(slide,schema?.defaults||{});
    updateAllSummaries();
    schedulePreview();
  }
});

slidesRoot.addEventListener("click",event=>{
  const button=event.target.closest("button");
  if(!button)return;
  const slide=button.closest("[data-slide]");

  if(button.matches("[data-add-row]")){
    const repeater=button.closest("[data-repeater]");
    const type=repeater.dataset.type;
    if(type==="timeline")repeater.insertAdjacentHTML("beforeend",`<div class="repeat-row"><input data-part="date" placeholder="Date"><input data-part="text" placeholder="Event">${removeButton()}</div>`);
    if(type==="stats")repeater.insertAdjacentHTML("beforeend",`<div class="repeat-row stat"><input data-part="stat_text" placeholder="Statistic"><input data-part="stat_label" placeholder="Label">${removeButton()}</div>`);
    if(type==="sources")repeater.insertAdjacentHTML("beforeend",`<div class="repeat-row source"><input data-part="citation" placeholder="Source citation">${removeButton()}</div>`);
    markDirty(slide);schedulePreview();return;
  }

  if(button.matches("[data-remove-row]")){
    const repeater=button.closest("[data-repeater]");
    if(repeater.querySelectorAll(".repeat-row").length>1)button.closest(".repeat-row").remove();
    markDirty(slide);schedulePreview();return;
  }

  if(!slide)return;

  if(button.matches("[data-delete]")){
    if(slidesRoot.querySelectorAll("[data-slide]").length===1){
      alert("A carousel needs at least one slide.");return;
    }
    slide.remove();
  }else if(button.matches("[data-duplicate]")){
    addSlide(readSlide(slide,0));
  }else if(button.matches("[data-collapse]")){
    slide.classList.toggle("collapsed");
    button.textContent=slide.classList.contains("collapsed")?"Expand":"Collapse";
  }

  renumber();
  updateAllSummaries();
  updateThumbnailStrip();
});

function slideSummaryText(slide,index){
  const data=readSlide(slide,index);
  const headline=(data.headline_lines||data.quote_lines||[]).join(" ");
  const stat=data.stat_text||"";
  return `${data.label||`Slide ${index+1}`} • ${headline||stat||data.template}`;
}

function updateAllSummaries(){
  [...slidesRoot.querySelectorAll("[data-slide]")].forEach((slide,index)=>{
    const summary=slide.querySelector("[data-summary]");
    if(summary)summary.textContent=slideSummaryText(slide,index);
  });
}

function collapseAllExcept(activeIndex){
  [...slidesRoot.querySelectorAll("[data-slide]")].forEach((slide,index)=>{
    const collapsed=index!==activeIndex;
    slide.classList.toggle("collapsed",collapsed);
    const button=slide.querySelector("[data-collapse]");
    if(button)button.textContent=collapsed?"Expand":"Collapse";
  });
}

function hasContent(value){if(value===null||value===undefined)return false;if(typeof value==="string")return Boolean(value.trim());if(Array.isArray(value))return value.length>0;if(typeof value==="object")return Object.keys(value).length>0;return true}
function validateData(data, selectedIndex=null){
  const report={story:[],source:[],slides:[],errors:[]};
  if(!data||typeof data!=="object"||Array.isArray(data)){
    report.errors.push("The package must be one JSON object.");
    return report;
  }
  if(!String(data.story||data.title||"").trim()) report.story.push("Story title");
  if(!String(data.source||"").trim()) report.source.push("Primary source");
  if(!Array.isArray(data.slides)||!data.slides.length){
    report.errors.push("At least one slide");
    return report;
  }
  data.slides.forEach((slide,index)=>{
    const missing=[];
    if(!slide||typeof slide!=="object"||Array.isArray(slide)){
      missing.push("Valid slide data");
    } else {
      const template=slide.template;
      if(!schemas[template]) missing.push("Supported template");
      else {
        (REQUIRED_FIELDS[template]||[]).forEach(key=>{
          if(!hasContent(slide[key])) missing.push(key.replaceAll("_"," "));
        });
        if(template==="timeline" && Array.isArray(slide.timeline_entries)){
          slide.timeline_entries.forEach((entry,i)=>{
            if(!String(entry.date||"").trim()) missing.push(`Event ${i+1} date`);
            if(!String(entry.text||"").trim()) missing.push(`Event ${i+1} description`);
          });
        }
      }
    }
    report.slides.push({index,template:slide?.template||"unknown",missing});
  });
  return report;
}

function flatErrors(report){
  const errors=[];
  report.story.forEach(item=>errors.push(item));
  report.source.forEach(item=>errors.push(item));
  report.errors.forEach(item=>errors.push(item));
  report.slides.forEach(item=>item.missing.forEach(field=>errors.push(`Slide ${item.index+1}: ${field}`)));
  return errors;
}

function renderValidation(report,index){
  const box=document.getElementById("validation-box");
  const slide=report.slides[index]||{missing:[],template:""};
  const storyOk=!report.story.length;
  const sourceOk=!report.source.length;
  const missing=[...slide.missing];
  box.className=`validation-box ${storyOk&&sourceOk&&!missing.length?"good":"bad"}`;
  box.innerHTML=`
    <div class="validation-title">Slide ${index+1}</div>
    <div>${storyOk?"✓":"•"} Story</div>
    <div>${sourceOk?"✓":"•"} Source</div>
    <div>${escapeHTML(TEMPLATE_OPTIONS.includes(slide.template)?slide.template.replaceAll("_"," "):slide.template)}</div>
    ${missing.length?`<div style="margin-top:8px;font-weight:800">Missing:</div><ul class="validation-list">${missing.map(item=>`<li>${escapeHTML(item)}</li>`).join("")}</ul>`:'<div style="margin-top:8px">✓ Ready for production render</div>'}`;
}

function showImportStatus(message,type="success"){
  const box=document.getElementById("import-status");
  box.textContent=message;box.className=`import-status ${type}`;
}

let previewTimer=null;
let autosaveTimer=null;
let previewRequestId=0;
let previewUrls=[];
let selectedPreviewIndex=0;
let lastPreviewUrl="";
let lastSavedJSON="";

function setPreviewStatus(message,state=""){
  const root=document.getElementById("preview-status");
  root.innerHTML=`<span class="status-dot ${state}"></span>${escapeHTML(message)}`;
}

function updatePreviewCounter(){
  const count=slidesRoot.querySelectorAll("[data-slide]").length||1;
  document.getElementById("preview-counter").textContent=`Slide ${selectedPreviewIndex+1} of ${count}`;
}

function selectSlide(index,{scroll=false,render=true}={}){
  const slides=[...slidesRoot.querySelectorAll("[data-slide]")];
  if(!slides.length)return;
  selectedPreviewIndex=Math.max(0,Math.min(index,slides.length-1));
  slides.forEach((slide,i)=>slide.classList.toggle("active",i===selectedPreviewIndex));
  updatePreviewCounter();
  const report=validateData(buildPayload(),selectedPreviewIndex);
  renderValidation(report,selectedPreviewIndex);
  if(scroll)slides[selectedPreviewIndex].scrollIntoView({behavior:"smooth",block:"center"});
  if(render)schedulePreview();
}

function showPreview(url){
  const frame=document.getElementById("live-frame");
  lastPreviewUrl=url||"";
  if(!url){
    frame.innerHTML='<div class="live-empty">Preview not rendered yet.</div>';
    return;
  }
  frame.innerHTML=`<img src="${url}?t=${Date.now()}" alt="Live slide preview">`;
}

async function refreshLivePreview(){
  syncPayload();
  const data=buildPayload();
  const requestId=++previewRequestId;
  const report=validateData(data,selectedPreviewIndex);
  renderValidation(report,selectedPreviewIndex);
  setPreviewStatus("Rendering…","busy");

  try{
    const response=await fetch("/preview",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({payload:data,slide_index:selectedPreviewIndex})
    });
    const result=await response.json();
    if(requestId!==previewRequestId)return;
    if(!response.ok||!result.ok){
      setPreviewStatus(`Slide ${selectedPreviewIndex+1} failed: ${result.error||"Renderer error"}`,"bad");
      return;
    }
    previewUrls[selectedPreviewIndex]=result.image;
    showPreview(result.image);
    const now=new Date().toLocaleTimeString([], {hour:"numeric",minute:"2-digit",second:"2-digit"});
    setPreviewStatus(`✓ Up to date • ${now}`,"good");
    updateThumbnailStrip();
    slidesRoot.querySelectorAll("[data-slide]")[selectedPreviewIndex]?.classList.remove("dirty");
  }catch(error){
    if(requestId!==previewRequestId)return;
    setPreviewStatus(`Slide ${selectedPreviewIndex+1} failed: ${error.message}`,"bad");
  }
}

function updateThumbnailStrip(){
  const strip=document.getElementById("preview-strip");
  const count=slidesRoot.querySelectorAll("[data-slide]").length;
  strip.innerHTML=Array.from({length:count},(_,i)=>{
    const url=previewUrls[i];
    return `<button type="button" draggable="true" class="preview-thumb thumb-drag ${i===selectedPreviewIndex?"active":""}" data-preview-index="${i}">
      ${url?`<img src="${url}?t=${Date.now()}" alt="Slide ${i+1}">`:`<span style="display:block;padding:22px 4px;color:#777">${i+1}</span>`}
    </button>`;
  }).join("");
}

function schedulePreview(){
  if(!document.getElementById("auto-preview").checked)return;
  clearTimeout(previewTimer);
  previewTimer=setTimeout(refreshLivePreview,500);
}

function markDirty(slide){
  if(slide)slide.classList.add("dirty");
  document.getElementById("save-state").textContent="● Unsaved";
  scheduleAutosave();
}

function scheduleAutosave(){
  clearTimeout(autosaveTimer);
  autosaveTimer=setTimeout(autosaveDraft,2500);
}

async function autosaveDraft(){
  syncPayload();
  const data=buildPayload();
  const folder=document.getElementById("folder_slug").value.trim();
  if(!folder)return;
  const current=JSON.stringify(data);
  if(current===lastSavedJSON)return;
  document.getElementById("save-state").textContent="Saving…";
  try{
    const response=await fetch("/autosave",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({folder_slug:folder,payload:data})
    });
    const result=await response.json();
    if(!response.ok||!result.ok)throw new Error(result.error||"Autosave failed");
    lastSavedJSON=current;
    document.getElementById("save-state").textContent="✓ Saved";
  }catch(error){
    document.getElementById("save-state").textContent=`Autosave failed`;
  }
}

function populateFromData(data){
  const normalized={
    ...data,
    story:data?.story||data?.title||"",
    source:data?.source||"",
    slides:Array.isArray(data?.slides)?data.slides:[]
  };

  document.getElementById("story_title").value=normalized.story;
  document.getElementById("source").value=normalized.source;
  slidesRoot.innerHTML="";

  const incoming=normalized.slides.length
    ? normalized.slides
    : [{
        template:"cover_headline",
        label:"THE JENNI WREN",
        headline_lines:["HEADLINE HERE"],
        headline_colors:["white"],
        body:[{text:"Optional deck or supporting context."}],
        citation:"SOURCE"
      }];

  incoming.forEach((slideData,index)=>{
    try{
      addSlide(slideData);
    }catch(error){
      showAppError(
        `Slide ${index+1} failed to load.`,
        String(error.message || error)
      );
      addSlide({
        template:"body_standard",
        label:`SLIDE ${index+1}`,
        headline_lines:["EDITOR FALLBACK"],
        headline_colors:["white"],
        body:[{text:"This slide loaded with the generic fallback editor."}],
        citation:""
      });
    }
  });

  if(!slidesRoot.querySelector("[data-slide]")){
    addSlide({
      template:"body_standard",
      label:"SLIDE 1",
      headline_lines:["EDITOR FALLBACK"],
      headline_colors:["white"],
      body:[{text:"Studio restored a fallback slide."}],
      citation:""
    });
  }

  syncPayload();
  updateAllSummaries();
}

let draggedSlide=null;

slidesRoot.addEventListener("dragstart",event=>{
  const slide=event.target.closest("[data-slide]");
  if(!slide)return;
  draggedSlide=slide;
  slide.classList.add("dragging");
  event.dataTransfer.effectAllowed="move";
});

slidesRoot.addEventListener("dragover",event=>{
  event.preventDefault();
  const target=event.target.closest("[data-slide]");
  if(!target||target===draggedSlide)return;
  [...slidesRoot.querySelectorAll("[data-slide]")].forEach(item=>item.classList.remove("drop-target"));
  target.classList.add("drop-target");
});

slidesRoot.addEventListener("drop",event=>{
  event.preventDefault();
  const target=event.target.closest("[data-slide]");
  if(!draggedSlide||!target||target===draggedSlide)return;
  const slides=[...slidesRoot.querySelectorAll("[data-slide]")];
  const from=slides.indexOf(draggedSlide);
  const to=slides.indexOf(target);
  if(from<to)target.after(draggedSlide);else target.before(draggedSlide);
  renumber();updateAllSummaries();updateThumbnailStrip();
  selectSlide(Math.max(0,to),{render:false});
  markDirty(draggedSlide);
});

slidesRoot.addEventListener("dragend",()=>{
  [...slidesRoot.querySelectorAll("[data-slide]")].forEach(item=>item.classList.remove("dragging","drop-target"));
  draggedSlide=null;
});

document.getElementById("refresh-preview").addEventListener("click",refreshLivePreview);
document.getElementById("open-preview").addEventListener("click",()=>{
  if(lastPreviewUrl)window.open(lastPreviewUrl,"_blank","noopener");
});
document.getElementById("preview-prev").addEventListener("click",()=>selectSlide(selectedPreviewIndex-1,{scroll:true}));
document.getElementById("preview-next").addEventListener("click",()=>selectSlide(selectedPreviewIndex+1,{scroll:true}));
document.getElementById("preview-strip").addEventListener("click",event=>{
  const button=event.target.closest("[data-preview-index]");
  if(button)selectSlide(Number(button.dataset.previewIndex),{scroll:true});
});
let draggedThumbIndex=null;
document.getElementById("preview-strip").addEventListener("dragstart",event=>{
  const button=event.target.closest("[data-preview-index]");
  if(button)draggedThumbIndex=Number(button.dataset.previewIndex);
});
document.getElementById("preview-strip").addEventListener("dragover",event=>event.preventDefault());
document.getElementById("preview-strip").addEventListener("drop",event=>{
  event.preventDefault();
  const target=event.target.closest("[data-preview-index]");
  if(!target||draggedThumbIndex===null)return;
  const targetIndex=Number(target.dataset.previewIndex);
  const slides=[...slidesRoot.querySelectorAll("[data-slide]")];
  const moving=slides[draggedThumbIndex];
  const targetSlide=slides[targetIndex];
  if(draggedThumbIndex<targetIndex)targetSlide.after(moving);else targetSlide.before(moving);
  renumber();updateAllSummaries();updateThumbnailStrip();
  selectSlide(targetIndex,{scroll:true,render:false});
  draggedThumbIndex=null;
});

document.getElementById("studio-form").addEventListener("input",event=>{
  syncPayload();
  const slide=event.target.closest("[data-slide]");
  markDirty(slide);
  const report=validateData(buildPayload(),selectedPreviewIndex);
  renderValidation(report,selectedPreviewIndex);
  schedulePreview();
});
document.getElementById("studio-form").addEventListener("change",event=>{
  syncPayload();
  const slide=event.target.closest("[data-slide]");
  markDirty(slide);
  schedulePreview();
});
slidesRoot.addEventListener("click",event=>{
  const slide=event.target.closest("[data-slide]");
  if(slide && !event.target.closest("button")) {
    const slides=[...slidesRoot.querySelectorAll("[data-slide]")];
    selectSlide(slides.indexOf(slide),{render:false});
  }
});

function cleanReportingText(raw){
  return raw
    .replace(/\r\n?/g,"\n")
    .replace(/```[\s\S]*?```/g, block => block.replace(/```[a-z]*\n?/gi,"").replace(/```/g,""))
    .replace(/^\s*[-*_]{3,}\s*$/gm,"")
    .trim();
}

function titleFromReporting(text){
  const heading=text.match(/^\s*#\s+(.+)$/m);
  if(heading)return heading[1].trim();
  const firstLine=text.split("\n").map(line=>line.trim()).find(Boolean)||"Untitled Story";
  return firstLine.replace(/^[-*#>\s]+/,"").slice(0,120);
}

function reportingSections(text){
  const lines=text.split("\n");
  const sections=[];
  let current={heading:"",body:[]};

  function pushCurrent(){
    const body=current.body.join("\n").trim();
    if(current.heading||body)sections.push({heading:current.heading.trim(),body});
    current={heading:"",body:[]};
  }

  for(const rawLine of lines){
    const line=rawLine.trimEnd();
    const heading=line.match(/^\s*#{1,4}\s+(.+)$/);
    if(heading){
      pushCurrent();
      current.heading=heading[1];
      continue;
    }
    current.body.push(line);
  }
  pushCurrent();

  if(sections.length<=1){
    const paragraphs=text.split(/\n\s*\n+/).map(p=>p.trim()).filter(Boolean);
    return paragraphs.map((body,index)=>({
      heading:index===0?"WHAT HAPPENED":`KEY POINT ${index+1}`,
      body
    }));
  }
  return sections;
}

function sentenceSummary(text,maxChars=420){
  const compact=text.replace(/\s+/g," ").trim();
  if(compact.length<=maxChars)return compact;
  const clipped=compact.slice(0,maxChars);
  const stop=Math.max(clipped.lastIndexOf(". "),clipped.lastIndexOf("? "),clipped.lastIndexOf("! "));
  return (stop>120?clipped.slice(0,stop+1):clipped.trimEnd()+"…");
}

function buildDraftFromReporting(raw,source){
  const text=cleanReportingText(raw);
  if(!text)throw new Error("Paste reporting or Markdown first.");

  const story=titleFromReporting(text);
  const sections=reportingSections(text);
  const usable=sections.filter(section=>section.body||section.heading).slice(0,8);

  const slides=[{
    template:"cover_headline",
    label:"THE JENNI WREN",
    headline_lines:[story.toUpperCase()],
    headline_colors:["white"],
    body:usable[0]?.body?[{text:sentenceSummary(usable[0].body,220)}]:[],
    citation:source||"SOURCE"
  }];

  usable.slice(1).forEach((section,index)=>{
    slides.push({
      template:"body_standard",
      label:section.heading?section.heading.toUpperCase():`KEY POINT ${index+1}`,
      headline_lines:[(section.heading||`KEY POINT ${index+1}`).toUpperCase()],
      headline_colors:["white"],
      body:[{text:sentenceSummary(section.body||section.heading,520)}],
      citation:source||"SOURCE"
    });
  });

  if(slides.length===1 && usable[0]?.body){
    slides.push({
      template:"body_standard",
      label:"WHAT HAPPENED",
      headline_lines:["WHAT HAPPENED"],
      headline_colors:["white"],
      body:[{text:sentenceSummary(usable[0].body,520)}],
      citation:source||"SOURCE"
    });
  }

  slides.push({
    template:"sources_slide",
    label:"SOURCES",
    citations:[source||"Add source citation"]
  });

  return {story,source:source||"",slides};
}

document.querySelectorAll("[data-import-mode]").forEach(button=>{
  button.addEventListener("click",()=>{
    const mode=button.dataset.importMode;
    document.querySelectorAll("[data-import-mode]").forEach(item=>{
      item.classList.toggle("active",item===button);
      item.classList.toggle("secondary",item!==button);
    });
    document.getElementById("json-import-panel").classList.toggle("hidden",mode!=="json");
    document.getElementById("reporting-import-panel").classList.toggle("hidden",mode!=="reporting");
  });
});

document.getElementById("import-reporting-button").addEventListener("click",()=>{
  try{
    const data=buildDraftFromReporting(
      document.getElementById("import-reporting").value,
      document.getElementById("reporting-source").value.trim()
    );
    populateFromData(data);
    document.getElementById("folder_slug").value=(data.story||"story")
      .toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
    showImportStatus(
      `Draft created with ${data.slides.length} slides. Review every field before rendering.`,
      "success"
    );
    updateThumbnailStrip();
    selectSlide(0,{render:true});
  }catch(error){
    showImportStatus(error.message,"error");
  }
});


function chooseTemplateForSection(heading,body,index){
  const combined=`${heading} ${body}`.toLowerCase();
  if(index===0)return "cover_headline";
  if(/\b(\$?\d[\d,.]*\s?(million|billion|trillion|%|percent)?)\b/.test(combined) && body.length<300)return "stat_callout";
  if(/[“"][^”"]{20,}[”"]/.test(body))return "quote_lead";
  if(/\b(document|memo|letter|email|filing|order|bill|report)\b/.test(combined))return "document_card";
  if(/\b(first|then|later|after|before|timeline|date)\b/.test(combined) && body.split(/[.!?]/).filter(Boolean).length>=3)return "timeline";
  return "body_standard";
}

function extractQuotedText(body){
  const match=body.match(/[“"]([^”"]{20,260})[”"]/);
  return match?match[1]:sentenceSummary(body,260);
}

function buildEditorialStory(raw,source,targetCount,includeSources){
  const clean=cleanReportingText(raw);
  if(!clean)throw new Error("Paste reporting first.");

  const story=titleFromReporting(clean);
  let sections=reportingSections(clean).filter(item=>item.heading||item.body);
  if(!sections.length)sections=[{heading:"WHAT HAPPENED",body:clean}];

  const maxContent=Math.max(1,targetCount-(includeSources?1:0));
  sections=sections.slice(0,maxContent);
  const slides=[];

  sections.forEach((section,index)=>{
    const template=chooseTemplateForSection(section.heading,section.body,index);
    const heading=(section.heading||story||`SLIDE ${index+1}`).toUpperCase();
    const citation=source||"SOURCE";

    if(template==="cover_headline"){
      slides.push({
        template,
        label:"THE JENNI WREN",
        headline_lines:[story.toUpperCase()],
        headline_colors:["white"],
        body:section.body?[{text:sentenceSummary(section.body,220)}]:[],
        citation
      });
    }else if(template==="stat_callout"){
      const stat=(section.body.match(/\$?\d[\d,.]*\s?(?:million|billion|trillion|%|percent)?/i)||["KEY NUMBER"])[0];
      slides.push({
        template,
        label:heading,
        stat_text:stat,
        stat_label:heading,
        headline_lines:[heading],
        citation
      });
    }else if(template==="quote_lead"){
      slides.push({
        template,
        label:heading,
        quote_lines:[extractQuotedText(section.body)],
        quote_colors:["white"],
        attribution:"ADD ATTRIBUTION",
        citation
      });
    }else if(template==="document_card"){
      slides.push({
        template,
        label:heading,
        headline_lines:[heading],
        headline_colors:["white"],
        doc_lines:[sentenceSummary(section.body,420)],
        doc_highlight:sentenceSummary(section.body,110),
        doc_annotation:[{text:"Explain why this document matters."}],
        citation
      });
    }else if(template==="timeline"){
      const events=section.body.split(/(?<=[.!?])\s+/).filter(Boolean).slice(0,5).map((sentence,i)=>({
        date:`STEP ${i+1}`,
        text:sentenceSummary(sentence,150)
      }));
      slides.push({
        template,
        label:heading,
        headline_lines:[heading],
        headline_colors:["white"],
        timeline_entries:events.length?events:[{date:"DATE",text:sentenceSummary(section.body,180)}],
        citation
      });
    }else{
      slides.push({
        template:"body_standard",
        label:heading,
        headline_lines:[heading],
        headline_colors:["white"],
        body:[{text:sentenceSummary(section.body||section.heading,520)}],
        citation
      });
    }
  });

  while(slides.length<maxContent){
    slides.push({
      template:"body_standard",
      label:`KEY POINT ${slides.length+1}`,
      headline_lines:[`KEY POINT ${slides.length+1}`],
      headline_colors:["white"],
      body:[{text:"Add the next verified point from the reporting."}],
      citation:source||"SOURCE"
    });
  }

  if(includeSources){
    slides.push({
      template:"sources_slide",
      label:"SOURCES",
      citations:[source||"Add source citation"]
    });
  }

  return {story,source:source||"",slides};
}

document.getElementById("ai-build-story").addEventListener("click",()=>{
  try{
    const target=Number(document.getElementById("ai-slide-count").value||8);
    const includeSources=document.getElementById("ai-include-sources").checked;
    const data=buildEditorialStory(
      document.getElementById("ai-story-input").value,
      document.getElementById("ai-story-source").value.trim(),
      target,
      includeSources
    );
    populateFromData(data);
    document.getElementById("folder_slug").value=(data.story||"story")
      .toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
    const plan=data.slides.map((slide,i)=>`${i+1}. ${slide.template}`).join("<br>");
    const planBox=document.getElementById("ai-plan");
    planBox.innerHTML=`<strong>Suggested structure</strong><br>${plan}`;
    planBox.classList.remove("hidden");
    showImportStatus(`Built ${data.slides.length} editable slides. Review facts, wording, attribution, and citations.`,"success");
    updateAllSummaries();updateThumbnailStrip();selectSlide(0,{render:true});
  }catch(error){
    showImportStatus(error.message,"error");
  }
});

document.getElementById("load-story").addEventListener("click",()=>{
  const folder=document.getElementById("load-folder").value.trim();
  if(!folder){showImportStatus("Enter the story folder name first.","error");return}
  window.location.href=`/?folder=${encodeURIComponent(folder)}`;
});
document.getElementById("import-json-button").addEventListener("click",()=>{
  const raw=document.getElementById("import-json").value.trim();
  if(!raw){showImportStatus("Paste a carousel JSON package first.","error");return}
  try{
    const data=JSON.parse(raw);
    const report=validateData(data);
    const errors=flatErrors(report);
    if(errors.length){showImportStatus(errors.join("\n"),"error");return}
    data.slides=(data.slides||[]).map(adaptSlideToRenderer);populateFromData(data);
    const suggested=(data.folder_slug||data.slug||data.story||"story").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
    if(suggested)document.getElementById("folder_slug").value=suggested;
    showImportStatus(`Imported ${data.slides.length} slides. Review or edit, then Render Full Carousel.`,"success");
    selectSlide(0,{render:true});
  }catch(error){showImportStatus(`Invalid JSON: ${error.message}`,"error")}
});
document.getElementById("add-slide").addEventListener("click",()=>{
  addSlide({template:"body_standard",label:"NEW SLIDE",headline_lines:["HEADLINE HERE"],headline_colors:["white"],body:[{text:"Body copy appears here."}],citation:"SOURCE"});
  updateThumbnailStrip();
  selectSlide(slidesRoot.querySelectorAll("[data-slide]").length-1,{scroll:true});
});
document.getElementById("preview-json").addEventListener("click",()=>{
  syncPayload();document.getElementById("json-panel").classList.toggle("hidden")
});
document.getElementById("studio-form").addEventListener("submit",event=>{
  syncPayload();
  const report=validateData(buildPayload());
  const errors=flatErrors(report);
  if(errors.length){
    event.preventDefault();
    showImportStatus(errors.join("\n"),"error");
    window.scrollTo({top:0,behavior:"smooth"});
  }
});
document.getElementById("load-folder").value="__FOLDER__";

function initializeStudio(){
  try{
    populateFromData(initial);
    updateThumbnailStrip();
    selectSlide(0,{render:true});
  }catch(error){
    showAppError("Studio initialization failed.",String(error.message || error));
    if(!slidesRoot.querySelector("[data-slide]")){
      addSlide({
        template:"body_standard",
        label:"SLIDE 1",
        headline_lines:["EDITOR FALLBACK"],
        headline_colors:["white"],
        body:[{text:"Studio recovered with a fallback editor."}],
        citation:""
      });
      updateThumbnailStrip();
      selectSlide(0,{render:false});
    }
  }
}

initializeStudio();
</script>
</main>
</body>
</html>'''
    rendered = (
        page.replace("__FOLDER__", html.escape(folder_slug))
            .replace("__NOTICE__", notice_html)
            .replace("__LOG__", log_html)
            .replace("__PREVIEWS__", preview_html)
            .replace("__INITIAL_DATA__", json_script_data(data))
            .replace("__TEMPLATE_OPTIONS__", template_options)
            .replace("__SCHEMA_REGISTRY__", registry_json)
    )

    unresolved = [
        token
        for token in (
            "__SCHEMA_REGISTRY__",
            "__INITIAL_DATA__",
            "__TEMPLATE_OPTIONS__",
            "__FOLDER__",
        )
        if token in rendered
    ]
    if unresolved:
        raise RuntimeError(
            "Unresolved page-template placeholders: " + ", ".join(unresolved)
        )

    return rendered


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "JenniWrenStudio/2.7.2"

    def send_html(self, content: str, status: int = HTTPStatus.OK) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            query = urllib.parse.parse_qs(parsed.query)
            folder = query.get("folder", [""])[0]
            folder_slug = slugify(folder) if folder else ""
            self.send_html(build_page(folder_slug=folder_slug, data=load_story(folder_slug) if folder_slug else default_story()))
            return
        if parsed.path.startswith("/image/"):
            parts = parsed.path.split("/", 3)
            if len(parts) != 4:
                self.send_error(HTTPStatus.NOT_FOUND); return
            output_slug = urllib.parse.unquote(parts[2]); filename = urllib.parse.unquote(parts[3])
            try:
                path = safe_child(safe_child(OUTPUT_DIR, output_slug), filename)
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST); return
            if not path.is_file() or path.suffix.lower() != ".png":
                self.send_error(HTTPStatus.NOT_FOUND); return
            content = path.read_bytes()
            self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "image/png"); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(content))); self.end_headers(); self.wfile.write(content); return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path == "/preview":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            try:
                envelope = json.loads(raw)
                payload = envelope.get("payload") if isinstance(envelope, dict) else None
                slide_index = int(envelope.get("slide_index", 0)) if isinstance(envelope, dict) else 0
                if not isinstance(payload, dict):
                    raise ValueError("Preview payload is missing.")
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                self.send_json(
                    {"ok": False, "error": str(exc)},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                exit_code, log, output_slug = render_preview_payload(payload, slide_index)
            except ValueError as exc:
                self.send_json(
                    {"ok": False, "error": str(exc)},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            if exit_code != 0:
                self.send_json(
                    {
                        "ok": False,
                        "error": "Renderer could not build this slide.",
                        "log": log,
                    },
                    HTTPStatus.BAD_REQUEST,
                )
                return

            images = image_files(output_slug)
            if not images:
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            "Renderer completed but produced no PNG. "
                            f"Expected output/{output_slug}/slide01.png"
                        ),
                        "log": log,
                    },
                    HTTPStatus.BAD_REQUEST,
                )
                return

            image = (
                f"/image/{urllib.parse.quote(output_slug)}/"
                f"{urllib.parse.quote(images[0].name)}"
            )
            self.send_json(
                {
                    "ok": True,
                    "image": image,
                    "filename": images[0].name,
                    "output_slug": output_slug,
                    "log": log,
                }
            )
            return

        if self.path == "/autosave":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            try:
                envelope = json.loads(raw)
                folder_slug = slugify(str(envelope.get("folder_slug") or "story"))
                payload = envelope.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError("Draft payload is missing.")
                payload = adapt_payload_to_renderer(payload)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                self.send_json(
                    {"ok": False, "error": str(exc)},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            story_dir = safe_child(STORIES_DIR, folder_slug)
            story_dir.mkdir(parents=True, exist_ok=True)
            (story_dir / "carousel.draft.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            self.send_json({"ok": True})
            return

        if self.path not in {"/save", "/render"}:
            self.send_error(HTTPStatus.NOT_FOUND); return
        length = int(self.headers.get("Content-Length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        folder_slug = slugify(form.get("folder_slug", [""])[0])
        payload_text = form.get("payload", [""])[0]
        try:
            payload: Any = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            self.send_html(
                build_page(
                    folder_slug=folder_slug,
                    data=default_story(),
                    message=f"Validation failed: invalid JSON ({exc.msg}).",
                ),
                HTTPStatus.BAD_REQUEST,
            )
            return

        payload = adapt_payload_to_renderer(payload)
        errors = validate_payload(payload)
        if errors:
            self.send_html(
                build_page(
                    folder_slug=folder_slug,
                    data=payload if isinstance(payload, dict) else default_story(),
                    message="Validation failed:\n" + "\n".join(errors),
                ),
                HTTPStatus.BAD_REQUEST,
            )
            return
        story_dir = safe_child(STORIES_DIR, folder_slug); story_dir.mkdir(parents=True, exist_ok=True)
        (story_dir / "carousel.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if self.path == "/save":
            self.send_html(build_page(folder_slug=folder_slug, data=payload, message=f"Saved stories/{folder_slug}/carousel.json")); return
        exit_code, log = run_renderer(folder_slug); output_slug = slugify(str(payload.get("story") or folder_slug))
        self.send_html(build_page(folder_slug=folder_slug, data=payload, message=(f"Render succeeded: output/{output_slug}/" if exit_code == 0 else f"Render failed with exit code {exit_code}."), build_log=log, output_slug=output_slug), HTTPStatus.OK if exit_code == 0 else HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args: object) -> None:
        print("[studio] " + self.address_string() + " - " + (fmt % args))


def main() -> int:
    STORIES_DIR.mkdir(parents=True, exist_ok=True); OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not RENDERER.exists():
        print(f"ERROR: Missing {RENDERER.name} beside carousel_dashboard.py."); return 1
    server = ThreadingHTTPServer((HOST, PORT), StudioHandler)
    print(f"JenniWren Studio v2.7.2 running on port {PORT}")
    print("Open port 8000 from the Codespaces PORTS tab.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping JenniWren Studio.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
