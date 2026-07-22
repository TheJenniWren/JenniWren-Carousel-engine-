#!/usr/bin/env python3
"""
JenniWren Studio 3.7.1

Structured browser editor for the ten templates currently supported by the
JenniWren carousel renderer.
"""
from __future__ import annotations

import ast
import base64
import contextlib
import html
import importlib.util
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import traceback
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

SUPPORTED_TEMPLATE_IDS = (
    "cover_headline",
    "quote_lead",
    "photo_headline",
    "stat_callout",
    "stat_grid",
    "timeline",
    "call_block",
    "document_card",
    "body_standard",
    "sources_slide",
)


TEMPLATE_MODULE_FILES = (
    "cover_templates.py",
    "data_templates.py",
    "timeline_templates.py",
    "comparison_templates.py",
    "document_templates.py",
    "explainer_templates.py",
)

TEMPLATE_LABEL_OVERRIDES = {
    "cover_headline": "Cover — Headline",
    "quote_lead": "Cover — Quote Lead",
    "photo_headline": "Cover — Photo Story",
    "stat_callout": "Data — Big Number",
    "stat_grid": "Data — Stat Grid",
    "timeline": "Explainer — Timeline",
    "call_block": "Comparison — Call Block",
    "document_card": "Evidence — Document Card",
    "body_standard": "Interior — Standard Explainer",
    "sources_slide": "Final — Sources",
}

FIELD_WIDGETS: dict[str, dict[str, str]] = {
    "headline_lines": {"label": "Headline", "type": "lines"},
    "quote_lines": {"label": "Quote", "type": "lines"},
    "attribution": {"label": "Attribution", "type": "text"},
    "image": {"label": "Image filename", "type": "text"},
    "body": {"label": "Body", "type": "body"},
    "stat_text": {"label": "Statistic", "type": "text"},
    "stat_label": {"label": "Statistic label", "type": "text"},
    "stat_items": {"label": "Statistics", "type": "stats"},
    "timeline_entries": {"label": "Timeline entries", "type": "timeline"},
    "call_text": {"label": "Highlighted statement", "type": "textarea"},
    "doc_lines": {"label": "Document excerpt", "type": "lines"},
    "doc_highlight": {"label": "Highlighted line numbers", "type": "indices"},
    "doc_annotation": {"label": "Show annotation arrow", "type": "boolean"},
    "citations": {"label": "Sources", "type": "sources"},
    "citation": {"label": "Citation", "type": "text"},
}

DEFAULT_LABELS = {
    "cover_headline": "THE JENNI WREN",
    "quote_lead": "QUOTE",
    "photo_headline": "PHOTO STORY",
    "stat_callout": "BY THE NUMBERS",
    "stat_grid": "KEY NUMBERS",
    "timeline": "TIMELINE",
    "call_block": "THE POINT",
    "document_card": "DOCUMENT EVIDENCE",
    "body_standard": "WHAT HAPPENED",
    "sources_slide": "SOURCES",
}

COMMON_OPTIONAL_FIELDS = (
    "citation", "headline_lines", "headline_colors", "body", "arrow",
)


EDITORIAL_SCHEMAS: dict[str, dict[str, Any]] = {
    "cover_headline": {
        "label": "Cover — Headline",
        "required": ["headline"],
        "fields": [
            {"name": "headline", "label": "Headline", "type": "textarea"},
            {"name": "deck", "label": "Deck / body", "type": "textarea"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
    "quote_lead": {
        "label": "Cover — Quote Lead",
        "required": ["quote", "attribution"],
        "fields": [
            {"name": "quote", "label": "Quote", "type": "textarea"},
            {"name": "attribution", "label": "Attribution", "type": "text"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
    "photo_headline": {
        "label": "Cover — Photo Story",
        "required": ["image", "headline"],
        "fields": [
            {"name": "image", "label": "Image filename", "type": "text"},
            {"name": "headline", "label": "Headline", "type": "textarea"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
    "stat_callout": {
        "label": "Data — Big Number",
        "required": ["statistic", "statistic_label"],
        "fields": [
            {"name": "statistic", "label": "Statistic", "type": "text"},
            {"name": "statistic_label", "label": "Statistic label", "type": "text"},
            {"name": "context", "label": "Context / headline", "type": "textarea"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
    "stat_grid": {
        "label": "Data — Stat Grid",
        "required": ["statistics"],
        "fields": [
            {"name": "headline", "label": "Headline", "type": "textarea"},
            {"name": "statistics", "label": "Statistics", "type": "stats"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
    "timeline": {
        "label": "Explainer — Timeline",
        "required": ["headline", "events"],
        "fields": [
            {"name": "headline", "label": "Headline", "type": "textarea"},
            {"name": "events", "label": "Timeline events", "type": "timeline"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
    "call_block": {
        "label": "Comparison — Call Block",
        "required": ["statement"],
        "fields": [
            {"name": "headline", "label": "Optional headline", "type": "textarea"},
            {"name": "statement", "label": "Highlighted statement", "type": "textarea"},
            {"name": "body", "label": "Supporting body", "type": "textarea"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
    "document_card": {
        "label": "Evidence — Document Card",
        "required": ["headline", "excerpt"],
        "fields": [
            {"name": "image", "label": "Document image filename (optional)", "type": "text"},
            {"name": "headline", "label": "Headline", "type": "textarea"},
            {"name": "excerpt", "label": "Document excerpt", "type": "textarea"},
            {"name": "highlight", "label": "Highlighted line numbers", "type": "text"},
            {"name": "annotation", "label": "Show annotation arrow", "type": "boolean"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
    "body_standard": {
        "label": "Interior — Standard Explainer",
        "required": ["headline", "body"],
        "fields": [
            {"name": "headline", "label": "Headline", "type": "textarea"},
            {"name": "body", "label": "Body", "type": "textarea"},
            {"name": "citation", "label": "Citation", "type": "text"},
        ],
    },
    "sources_slide": {
        "label": "Final — Sources",
        "required": ["sources"],
        "fields": [
            {"name": "sources", "label": "Sources", "type": "sources"},
        ],
    },
}

RENDERER_DEFAULTS: dict[str, dict[str, Any]] = {
    "cover_headline": {
        "headline_range": [58, 132],
        "body_size": 62,
        "big_label": False,
        "arrow": True,
    },
    "quote_lead": {
        "headline_range": [58, 132],
        "big_label": False,
        "arrow": True,
    },
    "photo_headline": {
        "headline_range": [58, 132],
        "photo_style": "fade",
        "big_label": False,
        "arrow": True,
    },
    "stat_callout": {
        "big_label": False,
        "arrow": True,
    },
    "stat_grid": {
        "big_label": False,
        "arrow": True,
    },
    "timeline": {
        "big_label": False,
        "arrow": True,
    },
    "call_block": {
        "big_label": False,
        "arrow": True,
    },
    "document_card": {
        "doc_annotation": True,
        "big_label": False,
        "arrow": True,
    },
    "body_standard": {
        "headline_range": [58, 132],
        "body_size": 62,
        "big_label": False,
        "arrow": True,
    },
    "sources_slide": {
        "arrow": False,
    },
}

EDITORIAL_DEFAULT_LABELS = {
    "cover_headline": "THE JENNI WREN",
    "quote_lead": "QUOTE",
    "photo_headline": "PHOTO STORY",
    "stat_callout": "BY THE NUMBERS",
    "stat_grid": "KEY NUMBERS",
    "timeline": "TIMELINE",
    "call_block": "THE POINT",
    "document_card": "DOCUMENT EVIDENCE",
    "body_standard": "WHAT HAPPENED",
    "sources_slide": "SOURCES",
}

RENDERER_FIELD_TO_EDITORIAL: dict[str, dict[str, str]] = {
    "cover_headline": {
        "headline_lines": "Headline",
        "headline_colors": "Headline",
        "body": "Deck / body",
        "citation": "Citation",
        "label": "Label",
    },
    "quote_lead": {
        "quote_lines": "Quote",
        "quote_colors": "Quote",
        "attribution": "Attribution",
        "citation": "Citation",
        "label": "Label",
    },
    "photo_headline": {
        "image": "Image filename",
        "headline_lines": "Headline",
        "headline_colors": "Headline",
        "citation": "Citation",
        "label": "Label",
    },
    "stat_callout": {
        "stat_text": "Statistic",
        "stat_label": "Statistic label",
        "headline_lines": "Context",
        "headline_colors": "Context",
        "citation": "Citation",
        "label": "Label",
    },
    "stat_grid": {
        "stat_items": "Statistics",
        "headline_lines": "Headline",
        "headline_colors": "Headline",
        "citation": "Citation",
        "label": "Label",
    },
    "timeline": {
        "headline_lines": "Headline",
        "headline_colors": "Headline",
        "timeline_entries": "Timeline events",
        "citation": "Citation",
        "label": "Label",
    },
    "call_block": {
        "call_text": "Highlighted statement",
        "headline_lines": "Headline",
        "headline_colors": "Headline",
        "body": "Supporting body",
        "citation": "Citation",
        "label": "Label",
    },
    "document_card": {
        "doc_lines": "Document excerpt",
        "headline_lines": "Headline",
        "headline_colors": "Headline",
        "image": "Document image filename",
        "citation": "Citation",
        "label": "Label",
    },
    "body_standard": {
        "headline_lines": "Headline",
        "headline_colors": "Headline",
        "body": "Body",
        "citation": "Citation",
        "label": "Label",
    },
    "sources_slide": {
        "citations": "Sources",
        "label": "Label",
    },
}


def editorial_field_name(template: str, renderer_field: str) -> str:
    """Return the editorial label that produces a renderer-native field."""
    return RENDERER_FIELD_TO_EDITORIAL.get(template, {}).get(
        renderer_field,
        renderer_field.replace("_", " ").title(),
    )


def collapse_editorial_missing(
    template: str,
    renderer_fields: list[str],
) -> list[str]:
    """Collapse multiple derived renderer fields into one editorial requirement."""
    collapsed: list[str] = []
    for field in renderer_fields:
        editorial = editorial_field_name(template, field)
        if editorial not in collapsed:
            collapsed.append(editorial)
    return collapsed


def _literal_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _discover_function_contract(function: ast.FunctionDef) -> tuple[list[str], list[str]]:
    required: list[str] = []
    accessed: list[str] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "require_fields":
            for argument in node.args[1:]:
                value = _literal_string(argument)
                if value and value not in required:
                    required.append(value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "slide"
            and node.args
        ):
            value = _literal_string(node.args[0])
            if value and value not in accessed:
                accessed.append(value)
    optional = [field for field in accessed if field not in required]
    return required, optional


def _widget_for(field: str) -> dict[str, str] | None:
    if field in {"label", "headline_colors", "quote_colors", "arrow"}:
        return None
    widget = FIELD_WIDGETS.get(field, {"label": field.replace("_", " ").title(), "type": "text"})
    return {"renderer": field, **widget}


def discover_renderer_schema(root: Path) -> dict[str, dict[str, Any]]:
    """Build Studio's schema directly from production render functions."""
    registry: dict[str, dict[str, Any]] = {}
    for filename in TEMPLATE_MODULE_FILES:
        path = root / filename
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            raise RuntimeError(f"Could not inspect {filename}: {exc}") from exc
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("render_"):
                continue
            template_id = node.name.removeprefix("render_")
            required, optional = _discover_function_contract(node)
            # Citation is accepted by the story package even when a renderer does not draw it.
            if "citation" not in optional and "citation" not in required:
                optional.append("citation")
            widgets = [
                widget
                for field in [*required, *optional]
                if (widget := _widget_for(field)) is not None
            ]
            defaults: dict[str, Any] = {"label": DEFAULT_LABELS.get(template_id, template_id.upper())}
            if "headline_colors" in required or "headline_colors" in optional:
                defaults["headline_colors"] = ["white"]
            if "quote_colors" in required or "quote_colors" in optional:
                defaults["quote_colors"] = ["white"]
            if "doc_annotation" in required or "doc_annotation" in optional:
                defaults["doc_annotation"] = True
            registry[template_id] = {
                "id": template_id,
                "label": TEMPLATE_LABEL_OVERRIDES.get(template_id, template_id.replace("_", " ").title()),
                "module": filename,
                "renderer": node.name,
                "required": required,
                "optional": optional,
                "defaults": defaults,
                "widgets": widgets,
            }
    if not registry:
        raise RuntimeError("No production render functions were discovered.")
    return registry



def certify_template_engine() -> dict[str, Any]:
    """Verify one complete editor-to-renderer path for all supported templates."""
    rows: list[dict[str, Any]] = []
    for template_id in SUPPORTED_TEMPLATE_IDS:
        renderer_schema = TEMPLATE_SCHEMA_REGISTRY.get(template_id) if "TEMPLATE_SCHEMA_REGISTRY" in globals() else None
        editorial_schema = EDITORIAL_SCHEMAS.get(template_id)
        errors: list[str] = []
        if renderer_schema is None:
            errors.append("Production renderer function not discovered")
        if editorial_schema is None:
            errors.append("Editorial schema not registered")
        elif not editorial_schema.get("fields"):
            errors.append("No editor fields defined")
        rows.append({
            "id": template_id,
            "label": TEMPLATE_LABEL_OVERRIDES.get(template_id, template_id.replace("_", " ").title()),
            "renderer": renderer_schema.get("renderer") if renderer_schema else "",
            "module": renderer_schema.get("module") if renderer_schema else "",
            "field_count": len(editorial_schema.get("fields", [])) if editorial_schema else 0,
            "required": list(editorial_schema.get("required", [])) if editorial_schema else [],
            "ok": not errors,
            "errors": errors,
        })
    return {
        "ok": all(row["ok"] for row in rows),
        "supported_count": sum(1 for row in rows if row["ok"]),
        "expected_count": len(SUPPORTED_TEMPLATE_IDS),
        "templates": rows,
    }


def validate_template_engine_or_raise() -> None:
    report = certify_template_engine()
    if report["ok"]:
        return
    failures = [
        f"{row['id']}: {', '.join(row['errors'])}"
        for row in report["templates"] if not row["ok"]
    ]
    raise RuntimeError("Template Engine certification failed: " + "; ".join(failures))


def _copy_named_asset(*, filename: str, source_story_dir: Path | None, preview_story_dir: Path) -> tuple[bool, str]:
    clean_name = Path(str(filename or "").strip()).name
    if not clean_name:
        return False, "No filename supplied"
    destination = preview_story_dir / clean_name
    if destination.is_file():
        return True, str(destination)
    candidates: list[Path] = []
    if source_story_dir is not None:
        candidates += [source_story_dir/clean_name, source_story_dir/'assets'/clean_name, source_story_dir/'images'/clean_name]
    candidates += [ROOT/clean_name, ROOT/'assets'/clean_name, ROOT/'images'/clean_name]
    for candidate in candidates:
        if candidate.is_file():
            preview_story_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, destination)
            return True, str(destination)
    return False, clean_name


def bridge_story_assets(editorial_payload: dict[str, Any], preview_story_dir: Path) -> list[dict[str, Any]]:
    source_folder = str(editorial_payload.get("folder") or "").strip()
    source_story_dir = safe_child(STORIES_DIR, source_folder) if source_folder else None
    results: list[dict[str, Any]] = []
    for index, slide in enumerate(editorial_payload.get("slides", []), start=1):
        if not isinstance(slide, dict) or str(slide.get("template") or "") not in {"photo_headline", "document_card"}:
            continue
        filename = str(slide.get("image") or "").strip()
        if not filename:
            continue
        ok, detail = _copy_named_asset(filename=filename, source_story_dir=source_story_dir, preview_story_dir=preview_story_dir)
        results.append({"slide": index, "template": slide.get("template"), "filename": Path(filename).name, "ok": ok, "detail": detail})
    return results


def template_engine_sample_story() -> dict[str, Any]:
    return {
        "folder": "_studio_template_engine_test",
        "story": "JenniWren Template Engine Test",
        "source": "JenniWren Studio internal certification",
        "slides": [
            {"template":"cover_headline","label":"THE JENNI WREN","headline":"TEN TEMPLATES\nONE ENGINE","deck":"Every supported layout now follows one production pipeline.","citation":"JenniWren Studio"},
            {"template":"quote_lead","label":"QUOTE","quote":"The template engine is working.","attribution":"JenniWren Studio","citation":"Internal certification"},
            {"template":"photo_headline","label":"PHOTO STORY","image":"template-engine-test.png","headline":"PHOTO TEMPLATE","citation":"JenniWren Studio"},
            {"template":"stat_callout","label":"BY THE NUMBERS","statistic":"10","statistic_label":"SUPPORTED TEMPLATES","context":"ONE PRODUCTION ENGINE","citation":"JenniWren Studio"},
            {"template":"stat_grid","label":"KEY NUMBERS","headline":"ENGINE STATUS","statistics":[{"stat_text":"10","stat_label":"Templates"},{"stat_text":"1","stat_label":"Registry"},{"stat_text":"1","stat_label":"Adapter"},{"stat_text":"1","stat_label":"Renderer"}],"citation":"JenniWren Studio"},
            {"template":"timeline","label":"TIMELINE","headline":"HOW A SLIDE RENDERS","events":[{"date":"1","text":"Edit the visible fields"},{"date":"2","text":"Adapter builds renderer JSON"},{"date":"3","text":"Production renderer writes PNG"}],"citation":"JenniWren Studio"},
            {"template":"call_block","label":"THE POINT","headline":"ONE PIPELINE","statement":"THE EDITOR AND RENDERER NOW SPEAK THE SAME LANGUAGE.","body":"Every template travels through the same adapter and production engine.","citation":"JenniWren Studio"},
            {"template":"document_card","label":"DOCUMENT EVIDENCE","image":"template-engine-test.png","headline":"THE CONTRACT","excerpt":"EDITOR STATE\nADAPTER\nRENDERER JSON\nPRODUCTION PNG","highlight":"2, 3","annotation":True,"citation":"JenniWren Studio"},
            {"template":"body_standard","label":"WHAT HAPPENED","headline":"THE ENGINE PASSED","body":"All ten production templates are registered, editable, adaptable, and renderable.","citation":"JenniWren Studio"},
            {"template":"sources_slide","label":"SOURCES","sources":["JenniWren Studio Template Registry","JenniWren Production Renderer","Internal Template Certification"]},
        ],
    }


def ensure_template_engine_test_asset(story_dir: Path) -> Path:
    story_dir.mkdir(parents=True, exist_ok=True)
    path = story_dir / "template-engine-test.png"
    path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="))
    return path

TEMPLATE_SCHEMA_REGISTRY = discover_renderer_schema(ROOT)
EDITORIAL_SCHEMA_REGISTRY = {
    template_id: {
        **schema,
        "id": template_id,
        "defaults": {
            "label": EDITORIAL_DEFAULT_LABELS.get(template_id, template_id.upper()),
            **RENDERER_DEFAULTS.get(template_id, {}),
        },
    }
    for template_id, schema in EDITORIAL_SCHEMAS.items()
    if template_id in TEMPLATE_SCHEMA_REGISTRY
}
TEMPLATE_LABELS = {key: value["label"] for key, value in EDITORIAL_SCHEMA_REGISTRY.items()}
REQUIRED_FIELDS = {key: tuple(value["required"]) for key, value in TEMPLATE_SCHEMA_REGISTRY.items()}


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


def _index_value(value: Any) -> list[int]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[\s,]+", str(value or "").strip())
    result: list[int] = []
    for item in raw:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        # Studio displays human-friendly 1-based line numbers.
        index = max(0, number - 1)
        if index not in result:
            result.append(index)
    return result


def _editor_text(slide: dict[str, Any], key: str, fallback: str = "") -> str:
    value = slide.get(key, fallback)
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value or "").strip()


def _editor_lines(slide: dict[str, Any], key: str, renderer_key: str = "") -> list[str]:
    value = slide.get(key)
    if value is None and renderer_key:
        value = slide.get(renderer_key)
    return _line_value(value)


def adapt_slide_to_renderer(slide: dict[str, Any]) -> dict[str, Any]:
    """Convert clean editorial fields into the exact production contract."""
    template = str(slide.get("template") or "")
    if template not in TEMPLATE_SCHEMA_REGISTRY:
        return dict(slide)

    label = str(
        slide.get("label")
        or EDITORIAL_DEFAULT_LABELS.get(template)
        or template.upper()
    ).strip()

    adapted: dict[str, Any] = {
        "template": template,
        "label": label,
        **RENDERER_DEFAULTS.get(template, {}),
    }

    citation = _editor_text(slide, "citation")
    if citation:
        adapted["citation"] = citation

    if template == "cover_headline":
        lines = _editor_lines(slide, "headline", "headline_lines")
        deck = slide.get("deck", slide.get("body"))
        adapted.update({
            "headline_lines": lines,
            "headline_colors": ["white"] * len(lines),
            "body": _body_value(deck),
        })

    elif template == "quote_lead":
        lines = _editor_lines(slide, "quote", "quote_lines")
        adapted.update({
            "quote_lines": lines,
            "quote_colors": ["white"] * len(lines),
            "attribution": _editor_text(slide, "attribution"),
        })

    elif template == "photo_headline":
        lines = _editor_lines(slide, "headline", "headline_lines")
        adapted.update({
            "image": _editor_text(slide, "image"),
            "headline_lines": lines,
            "headline_colors": ["white"] * len(lines),
        })

    elif template == "stat_callout":
        context = _editor_lines(slide, "context", "headline_lines")
        adapted.update({
            "stat_text": _editor_text(slide, "statistic", _editor_text(slide, "stat_text")),
            "stat_label": _editor_text(slide, "statistic_label", _editor_text(slide, "stat_label")),
            "headline_lines": context,
            "headline_colors": ["white"] * len(context),
        })

    elif template == "stat_grid":
        headline = _editor_lines(slide, "headline", "headline_lines")
        items = slide.get("statistics", slide.get("stat_items", [])) or []
        normalized: list[list[str]] = []
        for item in items:
            if isinstance(item, dict):
                stat = str(item.get("stat_text") or item.get("value") or "").strip()
                item_label = str(item.get("stat_label") or item.get("label") or "").strip()
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                stat, item_label = str(item[0]).strip(), str(item[1]).strip()
            else:
                continue
            if stat or item_label:
                normalized.append([stat, item_label])
        adapted.update({
            "headline_lines": headline,
            "headline_colors": ["white"] * len(headline),
            "stat_items": normalized,
        })

    elif template == "timeline":
        headline = _editor_lines(slide, "headline", "headline_lines")
        events = slide.get("events", slide.get("timeline_entries", [])) or []
        adapted.update({
            "headline_lines": headline,
            "headline_colors": ["white"] * len(headline),
            "timeline_entries": [
                {
                    "date": str(item.get("date") or item.get("label") or "").strip(),
                    "text": str(item.get("text") or item.get("event") or "").strip(),
                }
                for item in events
                if isinstance(item, dict)
                and (
                    str(item.get("date") or item.get("label") or "").strip()
                    or str(item.get("text") or item.get("event") or "").strip()
                )
            ],
        })

    elif template == "call_block":
        headline = _editor_lines(slide, "headline", "headline_lines")
        adapted.update({
            "headline_lines": headline,
            "headline_colors": ["white"] * len(headline),
            "call_text": _editor_text(slide, "statement", _editor_text(slide, "call_text")),
            "body": _body_value(slide.get("body")),
        })

    elif template == "document_card":
        headline = _editor_lines(slide, "headline", "headline_lines")
        adapted.update({
            "headline_lines": headline,
            "headline_colors": ["white"] * len(headline),
            "doc_lines": _editor_lines(slide, "excerpt", "doc_lines"),
            "doc_highlight": _index_value(slide.get("highlight", slide.get("doc_highlight"))),
            "doc_annotation": bool(slide.get("annotation", slide.get("doc_annotation", True))),
        })
        image = _editor_text(slide, "image")
        if image:
            adapted["image"] = image

    elif template == "body_standard":
        headline = _editor_lines(slide, "headline", "headline_lines")
        adapted.update({
            "headline_lines": headline,
            "headline_colors": ["white"] * len(headline),
            "body": _body_value(slide.get("body")),
        })

    elif template == "sources_slide":
        sources = slide.get("sources", slide.get("citations", [])) or []
        adapted["citations"] = [
            str(item.get("citation") or item.get("text") or "").strip()
            if isinstance(item, dict) else str(item).strip()
            for item in sources
            if (
                str(item.get("citation") or item.get("text") or "").strip()
                if isinstance(item, dict) else str(item).strip()
            )
        ]

    return adapted


def renderer_slide_to_editor(slide: dict[str, Any]) -> dict[str, Any]:
    """Convert an existing renderer-native slide into clean editorial fields."""
    template = str(slide.get("template") or "body_standard")
    editor: dict[str, Any] = {
        "template": template,
        "label": str(
            slide.get("label")
            or EDITORIAL_DEFAULT_LABELS.get(template)
            or "SLIDE"
        ),
    }
    if slide.get("citation"):
        editor["citation"] = slide.get("citation")

    if template == "cover_headline":
        editor["headline"] = _line_value(slide.get("headline_lines"))
        editor["deck"] = slide.get("body", [])
    elif template == "quote_lead":
        editor["quote"] = _line_value(slide.get("quote_lines"))
        editor["attribution"] = slide.get("attribution", "")
    elif template == "photo_headline":
        editor["image"] = slide.get("image", "")
        editor["headline"] = _line_value(slide.get("headline_lines"))
    elif template == "stat_callout":
        editor["statistic"] = slide.get("stat_text", "")
        editor["statistic_label"] = slide.get("stat_label", "")
        editor["context"] = _line_value(slide.get("headline_lines"))
    elif template == "stat_grid":
        editor["headline"] = _line_value(slide.get("headline_lines"))
        editor["statistics"] = slide.get("stat_items", [])
    elif template == "timeline":
        editor["headline"] = _line_value(slide.get("headline_lines"))
        editor["events"] = slide.get("timeline_entries", [])
    elif template == "call_block":
        editor["headline"] = _line_value(slide.get("headline_lines"))
        editor["statement"] = slide.get("call_text", "")
        editor["body"] = slide.get("body", [])
    elif template == "document_card":
        editor["image"] = slide.get("image", "")
        editor["headline"] = _line_value(slide.get("headline_lines"))
        editor["excerpt"] = _line_value(slide.get("doc_lines"))
        editor["highlight"] = [
            int(value) + 1 for value in slide.get("doc_highlight", [])
            if isinstance(value, int)
        ]
        editor["annotation"] = bool(slide.get("doc_annotation", True))
    elif template == "body_standard":
        editor["headline"] = _line_value(slide.get("headline_lines"))
        editor["body"] = slide.get("body", [])
    elif template == "sources_slide":
        editor["sources"] = slide.get("citations", [])

    return editor


def renderer_payload_to_editor(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "story": str(payload.get("story") or payload.get("title") or "").strip(),
        "source": str(payload.get("source") or "").strip(),
        "slides": [
            renderer_slide_to_editor(slide)
            for slide in payload.get("slides", [])
            if isinstance(slide, dict)
        ],
    }


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


def production_validation_details(payload: Any) -> dict[str, Any]:
    """Validate renderer-native JSON and retain structured renderer-field details."""
    details: dict[str, Any] = {
        "story": [],
        "source": [],
        "errors": [],
        "slides": [],
    }

    if not isinstance(payload, dict):
        details["errors"].append("The imported package must be one JSON object.")
        return details

    production_payload = adapt_payload_to_renderer(payload)

    if not str(production_payload.get("story") or "").strip():
        details["story"].append("Story title")
    if not str(production_payload.get("source") or "").strip():
        details["source"].append("Primary source")

    slides = production_payload.get("slides")
    if not isinstance(slides, list) or not slides:
        details["errors"].append("At least one slide")
        return details

    for index, slide in enumerate(slides):
        slide_detail = {
            "index": index,
            "template": "unknown",
            "renderer_missing": [],
            "errors": [],
        }

        if not isinstance(slide, dict):
            slide_detail["errors"].append("Valid slide data")
            details["slides"].append(slide_detail)
            continue

        template = str(slide.get("template") or "unknown")
        slide_detail["template"] = template

        if template not in TEMPLATE_SCHEMA_REGISTRY:
            slide_detail["errors"].append("Supported template")
            details["slides"].append(slide_detail)
            continue

        required = TEMPLATE_SCHEMA_REGISTRY[template].get("required", [])
        for renderer_field in required:
            if not _has_content(slide.get(renderer_field)):
                slide_detail["renderer_missing"].append(renderer_field)

        if template == "timeline":
            entries = slide.get("timeline_entries")
            if isinstance(entries, list):
                for entry_index, entry in enumerate(entries, start=1):
                    if not isinstance(entry, dict):
                        slide_detail["errors"].append(f"Event {entry_index}")
                        continue
                    if not str(entry.get("date") or "").strip():
                        slide_detail["errors"].append(f"Event {entry_index} date")
                    if not str(entry.get("text") or "").strip():
                        slide_detail["errors"].append(f"Event {entry_index} description")

        if template == "stat_grid":
            items = slide.get("stat_items")
            if isinstance(items, list):
                for item_index, item in enumerate(items, start=1):
                    valid = False
                    if isinstance(item, dict):
                        valid = bool(
                            str(item.get("stat_text") or item.get("value") or "").strip()
                            or str(item.get("stat_label") or item.get("label") or "").strip()
                        )
                    elif isinstance(item, (list, tuple)) and len(item) >= 2:
                        valid = bool(str(item[0]).strip() or str(item[1]).strip())
                    if not valid:
                        slide_detail["errors"].append(f"Statistic {item_index}")

        details["slides"].append(slide_detail)

    return details


def validate_payload(payload: Any) -> list[str]:
    """
    Validate the adapted production payload, but return editorial-facing messages.
    Renderer implementation fields never leak into the interface.
    """
    details = production_validation_details(payload)
    errors: list[str] = []

    errors.extend(details["story"])
    errors.extend(details["source"])
    errors.extend(details["errors"])

    for slide in details["slides"]:
        index = slide["index"] + 1
        template = slide["template"]
        label = TEMPLATE_LABELS.get(template, template.replace("_", " ").title())

        editorial_missing = collapse_editorial_missing(
            template,
            slide["renderer_missing"],
        )
        for field in editorial_missing:
            errors.append(f"Slide {index} ({label}): missing {field}.")

        for error in slide["errors"]:
            errors.append(f"Slide {index} ({label}): missing {error}.")

    return errors


def renderer_validation_report(
    editorial_payload: dict[str, Any],
    selected_index: int = 0,
) -> dict[str, Any]:
    """
    Adapter-first validation pipeline:

        editor state
        -> production adapter
        -> renderer-native JSON
        -> renderer validation
        -> editorial-facing report
    """
    production_payload = adapt_payload_to_renderer(editorial_payload)
    details = production_validation_details(production_payload)

    production_slides = production_payload.get("slides")
    if not isinstance(production_slides, list):
        production_slides = []

    selected_index = max(
        0,
        min(int(selected_index), max(0, len(production_slides) - 1)),
    )

    slide_reports: list[dict[str, Any]] = []
    for slide_detail in details["slides"]:
        template = slide_detail["template"]
        editorial_missing = collapse_editorial_missing(
            template,
            slide_detail["renderer_missing"],
        )
        for error in slide_detail["errors"]:
            if error not in editorial_missing:
                editorial_missing.append(error)

        slide_reports.append(
            {
                "index": slide_detail["index"],
                "template": template,
                "missing": editorial_missing,
                # Kept for diagnostics/API inspection only. The browser does not render it.
                "renderer_missing": list(slide_detail["renderer_missing"]),
            }
        )

    selected_slide = (
        slide_reports[selected_index]
        if slide_reports
        else {
            "index": 0,
            "template": "unknown",
            "missing": [],
            "renderer_missing": [],
        }
    )

    missing = [
        *details["story"],
        *details["source"],
        *details["errors"],
        *selected_slide["missing"],
    ]

    return {
        "ok": not missing,
        "story": list(details["story"]),
        "source": list(details["source"]),
        "errors": list(details["errors"]),
        "slides": slide_reports,
        "missing": missing,
        "selected_index": selected_index,
        "production_payload": production_payload,
    }


def _load_production_renderer_module() -> Any:
    """Load render_carousel.py as the single production rendering engine."""
    if not RENDERER.is_file():
        raise FileNotFoundError(f"Production renderer not found: {RENDERER}")

    module_name = "_jenniwren_production_render_carousel"
    spec = importlib.util.spec_from_file_location(module_name, RENDERER)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load production renderer: {RENDERER}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    render_function = getattr(module, "render_carousel", None)
    if not callable(render_function):
        raise AttributeError(
            "render_carousel.py does not expose callable render_carousel()."
        )
    return module


def render_story_bridge(
    story_folder: Path,
    output_folder: Path,
) -> tuple[int, str]:
    """
    Direct production bridge:

        saved carousel.json
        -> render_carousel.render_carousel(story_folder, output_folder)
        -> production PNG

    No shell process and no alternate preview renderer.
    """
    story_folder = story_folder.expanduser().resolve()
    output_folder = output_folder.expanduser().resolve()
    output_folder.mkdir(parents=True, exist_ok=True)

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    log_buffer = io.StringIO()
    bridge_handler = logging.StreamHandler(log_buffer)
    bridge_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(bridge_handler)

    try:
        module = _load_production_renderer_module()
        render_function = module.render_carousel

        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            exit_code = int(
                render_function(
                    story_folder,
                    output_folder,
                    strict=False,
                )
            )

        output_parts = [
            "Bridge: direct Python invocation",
            f"Renderer module: {RENDERER}",
            "Callable: render_carousel.render_carousel",
            f"Story folder: {story_folder}",
            f"Output folder: {output_folder}",
            f"Exit code: {exit_code}",
        ]

        stdout_text = stdout_buffer.getvalue().strip()
        stderr_text = stderr_buffer.getvalue().strip()
        log_text = log_buffer.getvalue().strip()

        if log_text:
            output_parts.append("LOGGING:\n" + log_text)
        if stdout_text:
            output_parts.append("STDOUT:\n" + stdout_text)
        if stderr_text:
            output_parts.append("STDERR:\n" + stderr_text)

        return exit_code, "\n\n".join(output_parts)

    except Exception as exc:
        diagnostic = _diagnostic_from_exception(exc)
        return (
            1,
            "\n\n".join(
                [
                    "Bridge: direct Python invocation",
                    f"Renderer module: {RENDERER}",
                    f"Story folder: {story_folder}",
                    f"Output folder: {output_folder}",
                    f"Exception: {diagnostic['type']}: {diagnostic['message']}",
                    diagnostic["traceback"],
                ]
            ),
        )
    finally:
        root_logger.removeHandler(bridge_handler)
        bridge_handler.close()


def run_renderer(folder_slug: str) -> tuple[int, str]:
    """Compatibility wrapper that now uses the direct production bridge."""
    story_folder = safe_child(STORIES_DIR, folder_slug)
    output_folder = safe_child(OUTPUT_DIR, slugify(PREVIEW_STORY))
    return render_story_bridge(story_folder, output_folder)



def _diagnostic_from_exception(exc: BaseException) -> dict[str, Any]:
    return {
        "type": exc.__class__.__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }


def _detect_renderer_issues(log: str) -> list[dict[str, str]]:
    """Extract missing files, fonts, assets, imports, and JSON fields."""
    issues: list[dict[str, str]] = []
    content = str(log or "")
    patterns: list[tuple[str, str]] = [
        (r"FileNotFoundError: \[Errno 2\] No such file or directory: ['\"]([^'\"]+)['\"]", "Missing file"),
        (r"No such file or directory: ['\"]([^'\"]+)['\"]", "Missing file"),
        (r"OSError: cannot open resource", "Missing or unreadable font"),
        (r"cannot open resource", "Missing or unreadable font"),
        (r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", "Missing Python module"),
        (r"ImportError: (.+)", "Import error"),
        (r"KeyError: ['\"]([^'\"]+)['\"]", "Missing JSON field"),
        (r"missing required field ['\"]([^'\"]+)['\"]", "Missing JSON field"),
        (r"missing required field:?\s*([A-Za-z0-9_]+)", "Missing JSON field"),
        (r"Image not found:?\s*(.+)", "Missing image asset"),
        (r"Font not found:?\s*(.+)", "Missing font"),
    ]
    seen: set[tuple[str, str]] = set()
    for pattern, kind in patterns:
        for match in re.finditer(pattern, content, flags=re.IGNORECASE):
            detail = match.group(1).strip() if match.groups() else match.group(0).strip()
            key = (kind, detail)
            if key not in seen:
                seen.add(key)
                issues.append({"kind": kind, "detail": detail})
    return issues


def _renderer_environment_diagnostics() -> dict[str, Any]:
    fonts = sorted(
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
    )
    template_modules = sorted(
        path.name for path in ROOT.glob("*_templates.py") if path.is_file()
    )
    return {
        "root": str(ROOT),
        "renderer": str(RENDERER),
        "renderer_exists": RENDERER.exists(),
        "bridge": "render_carousel.render_carousel",
        "bridge_mode": "direct_python_call",
        "fonts_found": fonts,
        "template_modules": template_modules,
    }


def _execution_verdict(
    *,
    exit_code: int,
    trace: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
    renderer_log: str,
    output_folder: Path | None = None,
    image_path: Path | None = None,
) -> dict[str, Any]:
    """Return one plain-language answer to: Why was no PNG created?"""
    if image_path is not None and image_path.is_file() and image_path.stat().st_size > 0:
        return {
            "status": "success",
            "title": "PNG created successfully",
            "reason": f"The production renderer created {image_path.name}.",
            "next_action": "The preview can now display the production PNG.",
            "technical_detail": str(image_path),
        }

    failed_step = next(
        (item for item in trace if not bool(item.get("ok"))),
        None,
    )

    priority_kinds = [
        "Missing renderer",
        "Missing Python module",
        "Import error",
        "Missing or unreadable font",
        "Missing font",
        "Missing image asset",
        "Missing file",
        "Missing JSON field",
        "Missing output",
        "Invalid output",
    ]
    selected_diagnostic = None
    for kind in priority_kinds:
        selected_diagnostic = next(
            (item for item in diagnostics if item.get("kind") == kind),
            None,
        )
        if selected_diagnostic:
            break
    if selected_diagnostic is None and diagnostics:
        selected_diagnostic = diagnostics[0]

    if selected_diagnostic:
        kind = str(selected_diagnostic.get("kind") or "Renderer error")
        detail = str(selected_diagnostic.get("detail") or "No detail supplied.")
        next_actions = {
            "Missing renderer": "Restore render_carousel.py at the repository root.",
            "Missing Python module": "Install or restore the named Python dependency.",
            "Import error": "Correct the renderer import shown in the traceback.",
            "Missing or unreadable font": "Restore the required font file or correct its path.",
            "Missing font": "Restore the required font file or correct its path.",
            "Missing image asset": "Upload the named image into the story assets folder.",
            "Missing file": "Restore the missing file at the exact path shown.",
            "Missing JSON field": "Correct the adapter mapping for the named renderer field.",
            "Missing output": "Inspect the renderer output and expected output directory.",
            "Invalid output": "Inspect the generated file and renderer save step.",
        }
        return {
            "status": "failure",
            "title": kind,
            "reason": detail,
            "next_action": next_actions.get(
                kind,
                "Use the traceback and renderer output below to correct this failure.",
            ),
            "technical_detail": str(selected_diagnostic.get("traceback") or ""),
        }

    if exit_code != 0:
        return {
            "status": "failure",
            "title": f"Renderer exited with code {exit_code}",
            "reason": (
                failed_step.get("detail")
                if failed_step
                else "The renderer process stopped before creating a PNG."
            ),
            "next_action": "Read the full renderer output and traceback below.",
            "technical_detail": renderer_log,
        }

    folder = str(output_folder) if output_folder is not None else "the preview output folder"
    return {
        "status": "failure",
        "title": "Renderer finished but produced no PNG",
        "reason": f"No valid PNG was found in {folder}.",
        "next_action": "Inspect the renderer save path and output filename below.",
        "technical_detail": renderer_log,
    }


def _trace_step(trace: list[dict[str, Any]], step: str, ok: bool, detail: str = "") -> None:
    trace.append({"step": step, "ok": bool(ok), "detail": str(detail or "")})


def _trace_text(trace: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in trace:
        mark = "✓" if item.get("ok") else "✗"
        detail = str(item.get("detail") or "").strip()
        lines.append(f"{mark} {item.get('step')}" + (f": {detail}" if detail else ""))
    return "\n".join(lines)


def prepare_carousel_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Adapt the complete editorial story into one renderer-native payload."""
    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("At least one slide is required.")

    production_payload = adapt_payload_to_renderer(payload)
    production_payload["story"] = (
        str(payload.get("story") or payload.get("title") or "").strip()
        or PREVIEW_STORY
    )
    production_payload["source"] = str(payload.get("source") or "").strip()

    errors = validate_payload(production_payload)
    if errors:
        raise ValueError(errors[0])

    return production_payload


def render_carousel_payload(
    payload: dict[str, Any],
) -> tuple[
    int,
    str,
    str,
    str,
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, str]],
    dict[str, Any],
    dict[str, Any],
    list[Path],
]:
    """Render the complete active story once and return every production PNG."""
    trace: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    environment = _renderer_environment_diagnostics()

    _trace_step(
        trace,
        "Renderer file check",
        bool(environment["renderer_exists"]),
        environment["renderer"],
    )
    _trace_step(
        trace,
        "Template modules discovered",
        bool(environment["template_modules"]),
        ", ".join(environment["template_modules"]) or "None",
    )
    _trace_step(
        trace,
        "Fonts discovered",
        bool(environment["fonts_found"]),
        f"{len(environment['fonts_found'])} font file(s)",
    )

    try:
        production_payload = prepare_carousel_payload(payload)
        slide_count = len(production_payload.get("slides", []))
        _trace_step(
            trace,
            "Story adapted",
            True,
            f"{slide_count} slide(s) adapted to renderer-native JSON",
        )
    except Exception as exc:
        diagnostic = _diagnostic_from_exception(exc)
        _trace_step(trace, "Story adapted", False, diagnostic["message"])
        diagnostics.append(
            {
                "kind": diagnostic["type"],
                "detail": diagnostic["message"],
                "traceback": diagnostic["traceback"],
            }
        )
        verdict = _execution_verdict(
            exit_code=1,
            trace=trace,
            diagnostics=diagnostics,
            renderer_log=_trace_text(trace),
        )
        return (
            1,
            _trace_text(trace),
            "",
            str(time.time_ns()),
            {},
            trace,
            diagnostics,
            environment,
            verdict,
            [],
        )

    story_dir = safe_child(STORIES_DIR, PREVIEW_FOLDER)
    try:
        story_dir.mkdir(parents=True, exist_ok=True)
        carousel_path = story_dir / "carousel.json"
        carousel_path.write_text(
            json.dumps(production_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _trace_step(trace, "Story JSON written", True, str(carousel_path))
        asset_results = bridge_story_assets(payload, story_dir)
        for asset in asset_results:
            _trace_step(trace, f"Slide {asset['slide']} asset bridged", bool(asset["ok"]), asset["detail"])
        missing_assets = [asset for asset in asset_results if not asset["ok"]]
        if missing_assets:
            names = ", ".join(asset["filename"] for asset in missing_assets)
            raise FileNotFoundError(f"Missing image asset(s): {names}")
    except Exception as exc:
        diagnostic = _diagnostic_from_exception(exc)
        _trace_step(trace, "Story JSON written", False, diagnostic["message"])
        diagnostics.append(
            {
                "kind": diagnostic["type"],
                "detail": diagnostic["message"],
                "traceback": diagnostic["traceback"],
            }
        )
        verdict = _execution_verdict(
            exit_code=1,
            trace=trace,
            diagnostics=diagnostics,
            renderer_log=_trace_text(trace),
        )
        return (
            1,
            _trace_text(trace),
            "",
            str(time.time_ns()),
            production_payload,
            trace,
            diagnostics,
            environment,
            verdict,
            [],
        )

    output_slug = slugify(PREVIEW_STORY)
    preview_output = safe_child(OUTPUT_DIR, output_slug)

    try:
        removed = 0
        if preview_output.exists():
            for png in preview_output.glob("*.png"):
                png.unlink()
                removed += 1
        _trace_step(trace, "Previous PNG deck cleared", True, f"{removed} PNG(s) removed")
    except Exception as exc:
        diagnostic = _diagnostic_from_exception(exc)
        _trace_step(trace, "Previous PNG deck cleared", False, diagnostic["message"])
        diagnostics.append(
            {
                "kind": diagnostic["type"],
                "detail": diagnostic["message"],
                "traceback": diagnostic["traceback"],
            }
        )

    _trace_step(
        trace,
        "Production renderer started",
        True,
        "render_carousel.render_carousel(story_folder, output_folder)",
    )
    exit_code, renderer_log = render_story_bridge(story_dir, preview_output)
    diagnostics.extend(_detect_renderer_issues(renderer_log))

    if exit_code != 0:
        _trace_step(trace, "Production renderer finished", False, f"Exit code {exit_code}")
        verdict = _execution_verdict(
            exit_code=exit_code,
            trace=trace,
            diagnostics=diagnostics,
            renderer_log=renderer_log,
            output_folder=preview_output,
        )
        return (
            exit_code,
            _trace_text(trace) + "\n\nRenderer output:\n" + renderer_log,
            output_slug,
            str(time.time_ns()),
            production_payload,
            trace,
            diagnostics,
            environment,
            verdict,
            image_files(output_slug),
        )

    _trace_step(trace, "Production renderer finished", True, "Exit code 0")
    images = image_files(output_slug)
    expected_count = len(production_payload.get("slides", []))

    for index in range(expected_count):
        expected_name = f"slide{index + 1:02d}.png"
        path = preview_output / expected_name
        _trace_step(
            trace,
            f"Slide {index + 1} rendered",
            path.is_file() and path.stat().st_size > 0,
            expected_name if path.is_file() else f"Missing {expected_name}",
        )

    if len(images) != expected_count:
        detail = f"Expected {expected_count} PNG(s), found {len(images)} in {preview_output}"
        diagnostics.append({"kind": "Missing output", "detail": detail})
        verdict = _execution_verdict(
            exit_code=1,
            trace=trace,
            diagnostics=diagnostics,
            renderer_log=renderer_log,
            output_folder=preview_output,
        )
        return (
            1,
            _trace_text(trace),
            output_slug,
            str(time.time_ns()),
            production_payload,
            trace,
            diagnostics,
            environment,
            verdict,
            images,
        )

    _trace_step(trace, "PNG deck complete", True, f"{len(images)} PNG(s) written")
    verdict = {
        "status": "success",
        "title": "Carousel rendered successfully",
        "reason": f"The production renderer created {len(images)} slides.",
        "next_action": "Use the preview controls to review every rendered PNG.",
        "technical_detail": str(preview_output),
    }

    return (
        0,
        _trace_text(trace),
        output_slug,
        str(time.time_ns()),
        production_payload,
        trace,
        diagnostics,
        environment,
        verdict,
        images,
    )

def image_files(output_slug: str) -> list[Path]:
    folder = safe_child(OUTPUT_DIR, output_slug)
    return sorted(folder.glob("*.png")) if folder.exists() else []


def default_story() -> dict[str, Any]:
    return {
        "story": "",
        "source": "",
        "slides": [
            {
                "template": "cover_headline",
                "label": "THE JENNI WREN",
                "headline": [],
                "deck": "",
                "citation": "",
            },
            {
                "template": "body_standard",
                "label": "WHAT HAPPENED",
                "headline": [],
                "body": "",
                "citation": "",
            },
        ],
    }


def json_script_data(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def build_page(*, folder_slug: str = "", data: dict[str, Any] | None = None,
               message: str = "", build_log: str = "", output_slug: str = "") -> str:
    data = renderer_payload_to_editor(data or default_story())
    registry_json = json.dumps(EDITORIAL_SCHEMA_REGISTRY, ensure_ascii=False).replace("</", "<\\/")

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
<title>JenniWren Studio 3.7.1</title>
<style>
:root{color-scheme:dark;--pink:#ff0a72;--bg:#080808;--panel:#151515;--panel2:#0d0d0d;--border:#363636;--text:#f7f7f7;--muted:#b8b8b8;--danger:#922048}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{width:min(1180px,calc(100% - 28px));margin:24px auto 64px}header{border-top:8px solid var(--pink);padding:24px 0 14px}h1{margin:0;font-size:clamp(38px,7vw,74px);line-height:.92;letter-spacing:-.035em;text-transform:uppercase}h2,h3{margin:0}p,.help{color:var(--muted)}.panel{margin-top:20px;padding:18px;background:var(--panel);border:1px solid var(--border);border-radius:14px}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;margin:13px 0 7px;font-weight:800}input,textarea,select{width:100%;padding:12px;border:1px solid #484848;border-radius:10px;background:var(--panel2);color:var(--text);font:inherit}textarea{resize:vertical;line-height:1.42;min-height:105px}textarea.tall{min-height:150px}.actions,.toolbar,.small-actions{display:flex;flex-wrap:wrap;gap:9px}.actions{margin-top:18px}.toolbar{align-items:center;justify-content:space-between}button{border:0;border-radius:10px;padding:12px 18px;background:var(--pink);color:#fff;font:inherit;font-weight:850;cursor:pointer}button.secondary{background:#333}button.danger{background:var(--danger)}button.small{padding:7px 10px;font-size:13px}.slide{margin-top:16px;padding:16px;background:#101010;border:1px solid var(--border);border-radius:13px}.slide-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding-bottom:10px;border-bottom:1px solid #2d2d2d}.repeater{margin-top:10px}.repeat-row{display:grid;grid-template-columns:170px 1fr auto;gap:8px;align-items:end;margin-top:8px}.repeat-row.stat{grid-template-columns:1fr 1fr auto}.repeat-row.source{grid-template-columns:1fr auto}.notice{margin-top:18px;padding:14px 16px;border-left:5px solid var(--pink);background:#1b1b1b;white-space:pre-wrap}.import-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.import-status{margin-top:10px;padding:10px 12px;border-radius:9px;background:#202020;color:var(--muted);white-space:pre-wrap}.import-status.error{border-left:4px solid #ff567f;color:#fff}.import-status.success{border-left:4px solid #55d98b;color:#fff}pre{overflow-x:auto;white-space:pre-wrap;padding:14px;border:1px solid var(--border);border-radius:10px;background:#050505}.hidden{display:none}.previews{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px}.preview-card{overflow:hidden;border:1px solid var(--border);border-radius:12px;background:var(--panel2)}.preview-card img{display:block;width:100%;height:auto}.preview-card div{padding:10px 12px;color:var(--muted);font-size:14px}.editor-preview-grid{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px;align-items:start}.preview-pane{position:sticky;top:14px}.live-frame{margin-top:12px;background:#090909;border:1px solid var(--border);border-radius:12px;overflow:hidden;min-height:280px;display:flex;align-items:center;justify-content:center}.live-frame img{display:block;width:100%;height:auto}.live-empty{padding:28px;color:var(--muted);text-align:center}.preview-strip{display:flex;gap:8px;overflow-x:auto;margin-top:10px;padding-bottom:4px}.preview-thumb{flex:0 0 74px;border:2px solid transparent;border-radius:8px;overflow:hidden;background:#111;padding:0}.preview-thumb.active{border-color:var(--pink)}.preview-thumb img{display:block;width:100%;height:auto}.preview-status{margin-top:10px;color:var(--muted)}.status-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#777;margin-right:7px}.status-dot.busy{background:#ffbf47}.status-dot.good{background:#55d98b}.status-dot.bad{background:#ff567f}.slide.active{outline:2px solid var(--pink);outline-offset:2px}.dirty-badge{display:none;color:#ffbf47;font-size:12px;font-weight:800;margin-left:8px}.slide.dirty .dirty-badge{display:inline}.validation-box{margin-top:12px;padding:12px;border:1px solid var(--border);border-radius:10px;background:#101010}.validation-box.good{border-left:4px solid #55d98b}.validation-box.bad{border-left:4px solid #ff567f}.validation-title{font-weight:850;margin-bottom:6px}.validation-list{margin:0;padding-left:18px;color:var(--muted)}.preview-nav{display:grid;grid-template-columns:auto 1fr auto;gap:8px;align-items:center;margin-top:12px}.preview-nav .counter{text-align:center;font-weight:800}.save-state{margin-left:auto;color:var(--muted);font-size:13px}.import-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}.import-tab.active{background:var(--pink)}.reporting-help{font-size:13px;color:var(--muted);margin-top:6px}.field-error{border-color:#ff567f!important;box-shadow:0 0 0 1px #ff567f}.slide.collapsed .slide-body{display:none}.slide-summary{display:none;color:var(--muted);font-size:13px;margin-top:8px;line-height:1.4}.slide.collapsed .slide-summary{display:block}.slide.collapsed{padding:12px 14px}.slide.collapsed .slide-head{border-bottom:0;padding-bottom:0}.drag-handle{cursor:grab;user-select:none;padding:7px 10px;background:#252525;border-radius:8px;font-weight:900}.slide.dragging{opacity:.5}.slide.drop-target{outline:2px dashed var(--pink);outline-offset:3px}.ai-builder-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.ai-choice{display:flex;gap:8px;align-items:center;margin-top:8px}.ai-plan{margin-top:12px;padding:12px;border:1px solid var(--border);border-radius:10px;background:#101010}.thumb-drag{cursor:grab}.app-error{margin:18px 0;padding:16px;border:1px solid #ff567f;border-left:6px solid #ff567f;border-radius:12px;background:#231016}.app-error h2{margin:0 0 8px}.app-error pre{margin:10px 0 0}.template-error{padding:12px;border:1px solid #ff567f;border-radius:10px;background:#211015;color:#fff}summary{cursor:pointer;font-weight:800}@media(max-width:900px){.editor-preview-grid{grid-template-columns:1fr}.preview-pane{position:static}}@media(max-width:720px){.two,.import-grid,.ai-builder-grid{grid-template-columns:1fr;gap:0}.slide-head{align-items:flex-start;flex-direction:column}.repeat-row,.repeat-row.stat{grid-template-columns:1fr}}
.trace-panel{margin-top:10px;border:1px solid var(--line);border-radius:10px;background:#0f0f0f;padding:8px}.trace-panel summary{cursor:pointer;font-weight:800}.trace-panel pre{white-space:pre-wrap;word-break:break-word;color:#ddd;font-size:12px;line-height:1.45;margin:10px 0 0}.diagnostic-item{border-left:3px solid var(--pink);padding:8px 10px;margin:8px 0;background:#111;border-radius:6px}.diagnostic-kind{font-weight:900}.diagnostic-detail{color:#ddd;white-space:pre-wrap;word-break:break-word}.diagnostic-trace{margin-top:8px;font-size:11px;white-space:pre-wrap;word-break:break-word;color:#bbb;max-height:260px;overflow:auto}.execution-answer{margin-top:10px;border:1px solid #4a2440;border-left:4px solid var(--pink);border-radius:10px;background:#130d12;padding:12px}.execution-answer.success{border-color:#245c40;border-left-color:#35d07f;background:#0d1511}.execution-answer.failure{border-color:#7a2945;border-left-color:#ff4f7f;background:#190d12}.execution-answer.waiting{border-color:#555;border-left-color:#888;background:#111}.execution-kicker{font-size:11px;font-weight:900;letter-spacing:.08em;color:var(--pink)}.execution-title{font-size:15px;font-weight:900;margin-top:4px}.execution-reason{color:#ddd;margin-top:5px;line-height:1.4}.execution-next{color:#aaa;margin-top:7px;font-size:12px;line-height:1.4}.first-cover-box{display:flex;gap:10px;align-items:center;justify-content:space-between;margin:10px 0;padding:10px;border:1px solid #5e2850;border-radius:10px;background:#150d13}.first-cover-copy{font-size:11px;color:#bbb;line-height:1.35;margin-top:3px}.first-cover-box button{white-space:nowrap}.template-engine-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.template-engine-head p{margin:.25rem 0 0;color:var(--muted)}.template-engine-summary{margin:12px 0;font-weight:800}.template-engine-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.template-engine-card{border:1px solid var(--border);border-radius:9px;padding:9px;background:#101010}.template-engine-card.ok{border-left:3px solid #35d07f}.template-engine-card.bad{border-left:3px solid #ff4f7f}.template-engine-card strong{display:block}.template-engine-meta{font-size:11px;color:#aaa;margin-top:3px}@media(max-width:720px){.template-engine-head{display:block}.template-engine-head button{margin-top:10px}.template-engine-grid{grid-template-columns:1fr}}</style>
</head>
<body>
<main>
<header><h1>JenniWren Studio 3.7.1</h1><p>Template Engine • Safari and Codespaces port compatibility stabilized.</p></header>
<section id="app-error" class="app-error hidden" role="alert">
  <h2>Studio error</h2>
  <div id="app-error-message"></div>
  <pre id="app-error-detail"></pre>
  <p>Studio has switched to its fallback editor. See the browser console for details.</p>
</section>
<section class="panel template-engine-panel">
  <div class="template-engine-head">
    <div><h2>Template Engine</h2><p>Ten production templates. One registry, adapter, validator, and renderer.</p></div>
    <button type="button" id="test-template-engine">Test All 10 Templates</button>
  </div>
  <div class="template-engine-summary" id="template-engine-summary">Checking template engine…</div>
  <div class="template-engine-grid" id="template-engine-grid"></div>
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
<div id="preview-status" class="preview-status"><span class="status-dot"></span>Enter required fields to render.</div>
<div id="live-frame" class="live-frame"><div class="live-empty">No production PNG yet.</div></div>
<div class="preview-nav">
  <button type="button" class="small secondary" id="preview-prev">◀ Previous</button>
  <div id="preview-counter" class="counter">Slide 1 of 1</div>
  <button type="button" class="small secondary" id="preview-next">Next ▶</button>
</div>
<div id="preview-strip" class="preview-strip"></div>
<div id="validation-box" class="validation-box"></div>
<div class="first-cover-box real-story-box">
  <div>
    <strong>Real Carousel Mode</strong>
    <div class="first-cover-copy">Adapt the complete editor story, render every slide once, and load the production PNG deck.</div>
  </div>
  <button type="button" id="render-current-slide">Render Through Real Carousel Mode</button>
</div>
<div class="actions">
  <button type="button" id="refresh-preview">Reload Selected PNG</button>
  <button type="button" class="secondary" id="open-preview">Open Production PNG</button>
  <span id="save-state" class="save-state">Not saved</span>
</div>
<section class="execution-answer" id="execution-answer">
  <div class="execution-kicker">WHY NO PNG?</div>
  <div class="execution-title" id="execution-title">Ready to render the complete active story.</div>
  <div class="execution-reason" id="execution-reason">Complete the active slide, then tap Render Through Real Carousel Mode.</div>
  <div class="execution-next" id="execution-next"></div>
</section>
<details class="trace-panel" id="trace-panel">
  <summary>Production Render Trace</summary>
  <pre id="trace-output">No render attempted yet.</pre>
</details>
<details class="trace-panel" id="diagnostics-panel">
  <summary>Renderer Diagnostics</summary>
  <div id="diagnostics-output">No diagnostics yet.</div>
</details>
<details class="trace-panel" id="renderer-output-panel">
  <summary>Full Renderer Output</summary>
  <pre id="renderer-output">No renderer output yet.</pre>
</details>
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
    if(!Array.isArray(schema.fields) || !schema.fields.length){
      errors.push(`${template}: missing editorial field definition`);
    }else{
      schema.fields.forEach((field,index)=>{
        if(!field || typeof field!=="object")errors.push(`${template}: field ${index+1} is invalid`);
        else{
          if(!field.name)errors.push(`${template}: field ${index+1} missing name`);
          if(!field.type)errors.push(`${template}: field ${index+1} missing type`);
          if(!field.label)errors.push(`${template}: field ${index+1} missing label`);
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
    if(templateCount<1){throw new Error("No renderer templates were discovered.");}
    return parsed;
  }catch(error){
    showAppError("Template registry failed",String(error.message || error));
    return {};
  }
}


async function loadTemplateEngineStatus(){
  const summary=document.getElementById("template-engine-summary");
  const grid=document.getElementById("template-engine-grid");
  try{
    const response=await fetch("/template-engine");
    const report=await response.json();
    summary.textContent=report.ok?`✓ ${report.supported_count} of ${report.expected_count} templates certified`:`${report.supported_count} of ${report.expected_count} templates certified`;
    grid.innerHTML=(report.templates||[]).map(item=>`<div class="template-engine-card ${item.ok?"ok":"bad"}"><strong>${escapeHTML(item.label||item.id)}</strong><div class="template-engine-meta">${item.ok?"✓ Ready":escapeHTML((item.errors||[]).join(", "))} · ${Number(item.field_count||0)} editor fields</div></div>`).join("");
  }catch(error){ summary.textContent=`Template Engine status failed: ${error.message}`; }
}

async function testTemplateEngine(){
  const button=document.getElementById("test-template-engine");
  if(button)button.disabled=true;
  setPreviewStatus("Rendering all ten templates…","busy");
  renderExecutionAnswer({status:"waiting",title:"Testing all ten templates",reason:"Studio is rendering one production slide for every supported template.",next_action:"Wait for the ten-slide certification deck."});
  try{
    const response=await fetch("/template-engine-test",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    const result=await response.json();
    renderProductionTrace(result.trace||[],result.log||"");
    renderDiagnostics(result.diagnostics||[],result.environment||{});
    renderRawRendererOutput(result.log||"");
    renderExecutionAnswer(result.verdict||{});
    if(!response.ok||!result.ok)throw new Error(result.error||"Template Engine certification failed.");
    if(result.editorial_payload){ populateFromData(result.editorial_payload); syncEditorStateFromDOM(); }
    const token=result.render_token||Date.now();
    previewUrls=(result.images||[]).map(item=>({url:item.url,token,filename:item.filename}));
    selectedPreviewIndex=0;
    showSelectedRenderedSlide(); updateThumbnailStrip(); updatePreviewCounter();
    const now=new Date().toLocaleTimeString([],{hour:"numeric",minute:"2-digit",second:"2-digit"});
    setPreviewStatus(`✓ 10 templates certified • ${now}`,"good");
    await loadTemplateEngineStatus();
  }catch(error){ setPreviewStatus(`Template Engine test failed: ${error.message}`,"bad"); }
  finally{ if(button)button.disabled=false; }
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
for(const [template,schema] of Object.entries(SCHEMA_REGISTRY)){
  if(!Array.isArray(schema.fields)){
    showAppError("Editorial schema failed",`${template}: missing field definitions`);
    continue;
  }
  schemas[template]=schema.fields.map(field=>[
    field.name,
    field.label,
    field.type
  ]);
  REQUIRED_FIELDS[template]=Array.isArray(schema.required)?schema.required:[];
}



function escapeHTML(value=""){return value.replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]))}function asLines(value){return Array.isArray(value)?value.join("\n"):value||""}function asBody(value){if(Array.isArray(value))return value.map(item=>typeof item==="object"?item.text||"":item).filter(Boolean).join("\n\n");if(value&&typeof value==="object")return value.text||"";return value||""}function normalizeSlide(raw={}){return {...raw,template:raw.template||"body_standard",label:raw.label||"SLIDE"}}function removeButton(){return '<button type="button" class="small danger" data-remove-row>Delete</button>'}
function fieldHTML(type,key,label,value){if(type==="text")return `<label>${label}</label><input data-key="${key}" value="${escapeHTML(String(value||""))}">`;if(type==="lines")return `<label>${label}</label><textarea data-key="${key}" data-type="lines">${escapeHTML(asLines(value))}</textarea>`;if(type==="body")return `<label>${label}</label><textarea class="tall" data-key="${key}" data-type="body">${escapeHTML(asBody(value))}</textarea>`;if(type==="timeline"){const rows=Array.isArray(value)&&value.length?value:[{date:"",text:""}];return `<div class="repeater" data-repeater="${key}" data-type="timeline"><div class="toolbar"><label>${label}</label><button type="button" class="small secondary" data-add-row>Add Event</button></div>${rows.map(item=>`<div class="repeat-row"><input data-part="date" value="${escapeHTML(String(item.date||item.label||""))}" placeholder="Date"><input data-part="text" value="${escapeHTML(String(item.text||item.event||""))}" placeholder="Event">${removeButton()}</div>`).join("")}</div>`}if(type==="stats"){const rows=Array.isArray(value)&&value.length?value:[{stat_text:"",stat_label:""}];return `<div class="repeater" data-repeater="${key}" data-type="stats"><div class="toolbar"><label>${label}</label><button type="button" class="small secondary" data-add-row>Add statistic</button></div>${rows.map(item=>`<div class="repeat-row stat"><input data-part="stat_text" value="${escapeHTML(String(item.stat_text||item.value||""))}" placeholder="Statistic"><input data-part="stat_label" value="${escapeHTML(String(item.stat_label||item.label||""))}" placeholder="Label">${removeButton()}</div>`).join("")}</div>`}if(type==="sources"){const rows=Array.isArray(value)&&value.length?value:[""];return `<div class="repeater" data-repeater="${key}" data-type="sources"><div class="toolbar"><label>${label}</label><button type="button" class="small secondary" data-add-row>Add source</button></div>${rows.map(item=>`<div class="repeat-row source"><input data-part="citation" value="${escapeHTML(String(typeof item==="object"?item.citation||item.text||"":item))}" placeholder="Source citation">${removeButton()}</div>`).join("")}</div>`}if(type==="textarea")return `<label>${label}</label><textarea class="tall" data-key="${key}" data-type="editorial-text">${escapeHTML(Array.isArray(value)?asLines(value):asBody(value))}</textarea>`;if(type==="indices")return `<label>${label}</label><input data-key="${key}" data-type="indices" value="${escapeHTML(Array.isArray(value)?value.map(v=>Number(v)+1).join(", "):String(value||""))}" placeholder="Example: 2, 4">`;if(type==="boolean")return `<label class="check"><input type="checkbox" data-key="${key}" data-type="boolean" ${value!==false?"checked":""}> ${label}</label>`;return ""}
function genericEditorHTML(data={}){
  return `
    <div class="template-error">
      <strong>Generic editorial editor</strong>
      <p>This template could not load its editorial schema.</p>
    </div>
    <label>Headline</label>
    <textarea class="tall" data-key="headline" data-type="editorial-text">${escapeHTML(asLines(data.headline||data.headline_lines||""))}</textarea>
    <label>Body</label>
    <textarea class="tall" data-key="body" data-type="editorial-text">${escapeHTML(asBody(data.body||""))}</textarea>
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
    root.innerHTML=fields.map(([key,label,type])=>
      fieldHTML(type,key,label,data[key])
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
function readSlide(slide,index){
  const template=slide.querySelector("[data-template]").value;
  const item={
    template,
    label:slide.querySelector("[data-label]").value.trim()||`SLIDE ${index+1}`
  };
  for(const [key,,type] of schemas[template]||[]){
    const repeater=slide.querySelector(`[data-repeater="${key}"]`);
    if(repeater){
      item[key]=readRepeater(repeater);
      continue;
    }
    const input=slide.querySelector(`[data-key="${key}"]`);
    if(!input)continue;
    if(type==="boolean"){
      item[key]=input.checked;
      continue;
    }
    const value=input.value.trim();
    if(type==="textarea"){
      item[key]=value;
    }else if(value){
      item[key]=value;
    }
  }
  return item;
}
let editorState={
  story:"",
  source:"",
  slides:[]
};
let rendererState=null;
let latestValidationReport=null;

function cloneJSON(value){
  return JSON.parse(JSON.stringify(value));
}

function readEditorStateFromDOM(){
  return {
    story:document.getElementById("story_title").value.trim(),
    source:document.getElementById("source").value.trim(),
    slides:[...slidesRoot.querySelectorAll("[data-slide]")].map(readSlide)
  };
}

function setEditorState(nextState){
  editorState={
    story:String(nextState?.story||nextState?.title||"").trim(),
    source:String(nextState?.source||"").trim(),
    slides:Array.isArray(nextState?.slides)?cloneJSON(nextState.slides):[]
  };
  const text=JSON.stringify(editorState,null,2);
  document.getElementById("payload").value=text;
  document.getElementById("json-output").textContent=text;
  return editorState;
}

function syncEditorStateFromDOM(){
  return setEditorState(readEditorStateFromDOM());
}

function buildPayload(){
  return cloneJSON(editorState);
}

function syncPayload(){
  return syncEditorStateFromDOM();
}
slidesRoot.addEventListener("change",event=>{
  if(event.target.matches("[data-template]")){
    const slide=event.target.closest("[data-slide]");
    const template=event.target.value;const schema=SCHEMA_REGISTRY[template];if(schema?.defaults?.label)slide.querySelector("[data-label]").value=schema.defaults.label;renderDynamic(slide,{});
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
  syncEditorStateFromDOM();
  updateAllSummaries();
  updateThumbnailStrip();
});

function slideSummaryText(slide,index){
  const data=readSlide(slide,index);
  const lead=data.headline||data.quote||data.statement||data.statistic||"";
  const text=Array.isArray(lead)?lead.join(" "):String(lead);
  return `${data.label||`Slide ${index+1}`} • ${text||data.template}`;
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
function emptyValidationReport(){
  return {story:[],source:[],slides:[],errors:[],missing:[]};
}

function normalizeValidationReport(report,index=0){
  const normalized=(report&&typeof report==="object")
    ? report
    : emptyValidationReport();

  if(!Array.isArray(normalized.story))normalized.story=[];
  if(!Array.isArray(normalized.source))normalized.source=[];
  if(!Array.isArray(normalized.slides))normalized.slides=[];
  if(!Array.isArray(normalized.errors))normalized.errors=[];

  const slide=normalized.slides[index]||{missing:[],template:"unknown"};
  if(!Array.isArray(slide.missing))slide.missing=[];
  normalized.slides[index]=slide;
  normalized.missing=[
    ...normalized.story,
    ...normalized.source,
    ...normalized.errors,
    ...slide.missing
  ];
  return normalized;
}

async function validateEditorState(selectedIndex=0){
  const response=await fetch("/validate",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      payload:buildPayload(),
      slide_index:selectedIndex
    })
  });
  const result=await response.json();
  if(!response.ok||!result.ok){
    throw new Error(result.error||"Validation failed");
  }
  rendererState=result.report.production_payload;
  latestValidationReport=normalizeValidationReport(
    result.report,
    selectedIndex
  );
  return latestValidationReport;
}

function currentValidationReport(index=0){
  return normalizeValidationReport(
    latestValidationReport||emptyValidationReport(),
    index
  );
}

function flatErrors(report){
  report=normalizeValidationReport(report,0);
  const errors=[];
  report.story.forEach(item=>errors.push(item));
  report.source.forEach(item=>errors.push(item));
  report.errors.forEach(item=>errors.push(item));
  report.slides.forEach(item=>item.missing.forEach(field=>errors.push(`Slide ${item.index+1}: ${field}`)));
  return errors;
}

function renderValidation(report,index){
  report=normalizeValidationReport(report,index);
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
    ${missing.length
      ? `<div style="margin-top:8px;font-weight:800">Missing:</div>
         <ul class="validation-list">
           ${missing.map(item=>`<li>${escapeHTML(item)}</li>`).join("")}
         </ul>`
      : '<div style="margin-top:8px">✓ Ready for production render</div>'
    }`;
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

async function selectSlide(index,{scroll=false,render=true}={}){
  const slides=[...slidesRoot.querySelectorAll("[data-slide]")];
  if(!slides.length)return;
  selectedPreviewIndex=Math.max(0,Math.min(index,slides.length-1));
  slides.forEach((slide,i)=>slide.classList.toggle("active",i===selectedPreviewIndex));
  collapseAllExcept(selectedPreviewIndex);
  updateAllSummaries();
  updatePreviewCounter();

  try{
    const report=await validateEditorState(selectedPreviewIndex);
    renderValidation(report,selectedPreviewIndex);
  }catch(error){
    setPreviewStatus(`Validation failed: ${error.message}`,"bad");
  }

  if(scroll)slides[selectedPreviewIndex].scrollIntoView({behavior:"smooth",block:"center"});
  if(render)schedulePreview();
}

function showPreview(url,renderToken=""){
  const frame=document.getElementById("live-frame");
  lastPreviewUrl=url||"";
  if(!url){
    frame.innerHTML='<div class="live-empty">No production PNG yet.</div>';
    return;
  }
  const separator=url.includes("?")?"&":"?";
  const token=renderToken||Date.now();
  frame.innerHTML=`<img src="${url}${separator}render=${encodeURIComponent(token)}" alt="Production-rendered slide preview">`;
}



function renderExecutionAnswer(verdict={}){
  const panel=document.getElementById("execution-answer");
  const title=document.getElementById("execution-title");
  const reason=document.getElementById("execution-reason");
  const next=document.getElementById("execution-next");
  if(!panel||!title||!reason||!next)return;

  const status=String(verdict?.status||"waiting");
  panel.className=`execution-answer ${status}`;
  title.textContent=verdict?.title||"Renderer has not run yet.";
  reason.textContent=verdict?.reason||"Complete the required editorial fields to start a production render.";
  next.textContent=verdict?.next_action?`Next: ${verdict.next_action}`:"";
}

function renderRawRendererOutput(log=""){
  const output=document.getElementById("renderer-output");
  if(output)output.textContent=String(log||"No renderer output returned.");
}

function renderProductionTrace(trace=[],log=""){
  const output=document.getElementById("trace-output");
  const panel=document.getElementById("trace-panel");
  if(!output||!panel)return;
  const lines=[];
  for(const item of Array.isArray(trace)?trace:[]){
    const mark=item?.ok?"✓":"✗";
    const detail=String(item?.detail||"").trim();
    lines.push(`${mark} ${item?.step||"Unknown step"}${detail?`: ${detail}`:""}`);
  }
  if(log && !lines.length)lines.push(String(log));
  output.textContent=lines.length?lines.join("\n"):"No render trace returned.";
  if(lines.some(line=>line.startsWith("✗")))panel.open=true;
}


function renderDiagnostics(diagnostics=[],environment={}){
  const output=document.getElementById("diagnostics-output");
  const panel=document.getElementById("diagnostics-panel");
  if(!output||!panel)return;

  const items=[];
  if(environment&&typeof environment==="object"){
    if(environment.renderer_exists===false){
      items.push({kind:"Missing renderer",detail:environment.renderer||"render_carousel.py not found"});
    }
    if(Array.isArray(environment.fonts_found)&&!environment.fonts_found.length){
      items.push({kind:"Missing fonts",detail:"No .ttf or .otf files were discovered in the repository."});
    }
    if(Array.isArray(environment.template_modules)&&!environment.template_modules.length){
      items.push({kind:"Missing template modules",detail:"No *_templates.py files were discovered."});
    }
  }
  for(const diagnostic of Array.isArray(diagnostics)?diagnostics:[]){
    items.push(diagnostic);
  }

  if(!items.length){
    output.textContent="No renderer issues detected.";
    return;
  }

  output.innerHTML=items.map(item=>`
    <div class="diagnostic-item">
      <div class="diagnostic-kind">${escapeHTML(item.kind||"Renderer issue")}</div>
      <div class="diagnostic-detail">${escapeHTML(item.detail||"No details")}</div>
      ${item.traceback?`<pre class="diagnostic-trace">${escapeHTML(item.traceback)}</pre>`:""}
    </div>
  `).join("");
  panel.open=true;
}

async function renderRealCarousel(){
  syncEditorStateFromDOM();
  const requestId=++previewRequestId;

  try{
    const payload=buildPayload();
    const slides=Array.isArray(payload.slides)?payload.slides:[];
    if(!slides.length){
      throw new Error("Add at least one slide before rendering.");
    }

    renderExecutionAnswer({
      status:"waiting",
      title:"Rendering complete carousel",
      reason:`Studio is adapting ${slides.length} slide(s) and calling the production renderer once.`,
      next_action:"Wait for the complete PNG deck."
    });
    setPreviewStatus(`Rendering ${slides.length} slides…`,"busy");

    const response=await fetch("/preview",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({payload})
    });
    const result=await response.json();
    if(requestId!==previewRequestId)return;

    renderProductionTrace(result.trace||[],result.log||"");
    renderDiagnostics(result.diagnostics||[],result.environment||{});
    renderRawRendererOutput(result.log||"");
    renderExecutionAnswer(result.verdict||{});

    if(!response.ok||!result.ok){
      previewUrls=[];
      showPreview("");
      updateThumbnailStrip();
      setPreviewStatus(result.error||"Carousel render failed","bad");
      return;
    }

    rendererState=result.production_payload||null;
    const token=result.render_token||Date.now();
    previewUrls=(result.images||[]).map(item=>({
      url:item.url,
      token,
      filename:item.filename
    }));

    if(!previewUrls.length){
      throw new Error("The renderer returned no PNG images.");
    }

    selectedPreviewIndex=Math.max(
      0,
      Math.min(selectedPreviewIndex,previewUrls.length-1)
    );
    const active=previewUrls[selectedPreviewIndex];
    showPreview(active.url,active.token);
    updateThumbnailStrip();
    updatePreviewCounter();

    slidesRoot.querySelectorAll("[data-slide]").forEach(slide=>{
      slide.classList.remove("dirty");
    });

    const now=new Date().toLocaleTimeString([],{
      hour:"numeric",minute:"2-digit",second:"2-digit"
    });
    setPreviewStatus(
      `✓ ${previewUrls.length} production PNGs • ${now}`,
      "good"
    );
  }catch(error){
    if(requestId!==previewRequestId)return;
    previewUrls=[];
    showPreview("");
    updateThumbnailStrip();
    renderExecutionAnswer({
      status:"failure",
      title:"Carousel render failed",
      reason:error.message,
      next_action:"Open the production trace and renderer output below."
    });
    setPreviewStatus(`Carousel render failed: ${error.message}`,"bad");
  }
}

async function refreshLivePreview(){
  return renderRealCarousel();
}

function showSelectedRenderedSlide(){
  const preview=previewUrls[selectedPreviewIndex];
  const url=typeof preview==="string"?preview:(preview?.url||"");
  const token=typeof preview==="string"?Date.now():(preview?.token||Date.now());
  if(url)showPreview(url,token);
  else showPreview("");
  updatePreviewCounter();
  updateThumbnailStrip();
}

function updateThumbnailStrip(){
  const strip=document.getElementById("preview-strip");
  const count=slidesRoot.querySelectorAll("[data-slide]").length;
  strip.innerHTML=Array.from({length:count},(_,i)=>{
    const preview=previewUrls[i];
    const url=typeof preview==="string"?preview:(preview?.url||"");
    const token=typeof preview==="string"?Date.now():(preview?.token||Date.now());
    return `<button type="button" draggable="true" class="preview-thumb thumb-drag ${i===selectedPreviewIndex?"active":""}" data-preview-index="${i}">
      ${url?`<img src="${url}${url.includes("?")?"&":"?"}render=${encodeURIComponent(token)}" alt="Slide ${i+1}">`:`<span style="display:block;padding:22px 4px;color:#777">${i+1}</span>`}
    </button>`;
  }).join("");
}

function schedulePreview(){
  // Real Carousel Mode renders only on explicit Render Carousel.
  return;
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
  syncEditorStateFromDOM();
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
        headline:"",
        
        deck:"",
        citation:""
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
        headline:"EDITOR FALLBACK",
        body:"This slide loaded with the generic fallback editor.",
        citation:""
      });
    }
  });

  if(!slidesRoot.querySelector("[data-slide]")){
    addSlide({
      template:"body_standard",
      label:"SLIDE 1",
      headline:"EDITOR FALLBACK",
      body:"Studio restored a fallback slide.",
      citation:""
    });
  }

  setEditorState(readEditorStateFromDOM());
  latestValidationReport=null;
  rendererState=null;
  previewUrls=[];
  selectedPreviewIndex=0;
  updateAllSummaries();
  updatePreviewCounter();
}


slidesRoot.addEventListener("pointerdown",event=>{
  const slide=event.target.closest("[data-slide]");
  if(!slide || event.target.closest("button,input,textarea,select"))return;
  const slides=[...slidesRoot.querySelectorAll("[data-slide]")];
  const index=slides.indexOf(slide);
  if(index>=0)selectSlide(index,{scroll:false,render:true});
});

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

document.getElementById("studio-form").addEventListener("submit",event=>{
  syncEditorStateFromDOM();
  document.getElementById("payload").value=JSON.stringify(editorState);
});




document.getElementById("test-template-engine").addEventListener("click",testTemplateEngine);
document.getElementById("render-current-slide").addEventListener("click",renderRealCarousel);
document.getElementById("refresh-preview").addEventListener("click",()=>{
  showSelectedRenderedSlide();
});
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

document.getElementById("studio-form").addEventListener("input",async event=>{
  previewUrls[selectedPreviewIndex]="";
  showPreview("");
  renderExecutionAnswer({
    status:"waiting",
    title:"Preview is out of date",
    reason:"The slide changed after the last render.",
    next_action:"Pause typing or tap Refresh to run the production renderer."
  });
  syncEditorStateFromDOM();
  const slide=event.target.closest("[data-slide]");
  markDirty(slide);

  try{
    const report=await validateEditorState(selectedPreviewIndex);
    renderValidation(report,selectedPreviewIndex);
  }catch(error){
    setPreviewStatus(`Validation failed: ${error.message}`,"bad");
  }

  schedulePreview();
});

document.getElementById("studio-form").addEventListener("change",async event=>{
  syncEditorStateFromDOM();
  const slide=event.target.closest("[data-slide]");
  markDirty(slide);

  try{
    const report=await validateEditorState(selectedPreviewIndex);
    renderValidation(report,selectedPreviewIndex);
  }catch(error){
    setPreviewStatus(`Validation failed: ${error.message}`,"bad");
  }

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
    
    body:usable[0]?.body?[{text:sentenceSummary(usable[0].body,220)}]:[],
    citation:source||"SOURCE"
  }];

  usable.slice(1).forEach((section,index)=>{
    slides.push({
      template:"body_standard",
      label:section.heading?section.heading.toUpperCase():`KEY POINT ${index+1}`,
      headline_lines:[(section.heading||`KEY POINT ${index+1}`).toUpperCase()],
      
      body:[{text:sentenceSummary(section.body||section.heading,520)}],
      citation:source||"SOURCE"
    });
  });

  if(slides.length===1 && usable[0]?.body){
    slides.push({
      template:"body_standard",
      label:"WHAT HAPPENED",
      headline_lines:["WHAT HAPPENED"],
      
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
    selectSlide(0,{render:false});
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
        
        timeline_entries:events.length?events:[{date:"DATE",text:sentenceSummary(section.body,180)}],
        citation
      });
    }else{
      slides.push({
        template:"body_standard",
        label:heading,
        headline_lines:[heading],
        
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
    updateAllSummaries();updateThumbnailStrip();selectSlide(0,{render:false});
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
    populateFromData(data);
    const suggested=(data.folder_slug||data.slug||data.story||"story").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
    if(suggested)document.getElementById("folder_slug").value=suggested;
    showImportStatus(`Imported ${data.slides.length} slides. Review or edit, then Render Full Carousel.`,"success");
    selectSlide(0,{render:false});
  }catch(error){showImportStatus(`Invalid JSON: ${error.message}`,"error")}
});
document.getElementById("add-slide").addEventListener("click",()=>{
  addSlide({template:"body_standard",label:"NEW SLIDE",headline:"",body:"",citation:""});
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
loadTemplateEngineStatus();
    updateThumbnailStrip();
    selectSlide(0,{render:false});
  }catch(error){
    showAppError("Studio initialization failed.",String(error.message || error));
    if(!slidesRoot.querySelector("[data-slide]")){
      addSlide({
        template:"body_standard",
        label:"SLIDE 1",
        headline:"EDITOR FALLBACK",
        body:"Studio recovered with a fallback editor.",
        citation:""
      });
      updateThumbnailStrip();
      selectSlide(0,{render:false});
    }
  }
}

initializeStudio();
setEditorState(readEditorStateFromDOM());
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
    server_version = "JenniWrenStudio/3.7.1"

    def send_html(self, content: str, status: int = HTTPStatus.OK) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Disposition", "inline")
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

    def do_HEAD(self) -> None:
        """
        Support Safari/Codespaces preflight requests.

        Safari may probe a forwarded Codespaces URL with HEAD before GET.
        Returning 501 can make Safari treat the forwarded app as a download.
        """
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            content = build_page(data=default_story()).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", "inline")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            return

        if parsed.path == "/template-engine":
            encoded = json.dumps(
                certify_template_engine(),
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", "inline")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            return

        if parsed.path.startswith("/image/"):
            parts = parsed.path.split("/", 3)
            if len(parts) != 4:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            output_slug = urllib.parse.unquote(parts[2])
            filename = urllib.parse.unquote(parts[3])
            try:
                path = safe_child(
                    safe_child(OUTPUT_DIR, output_slug),
                    filename,
                )
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            if not path.is_file() or path.suffix.lower() != ".png":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Disposition", "inline")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.end_headers()
            return

        self.send_error(HTTPStatus.NOT_FOUND)


    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/template-engine":
            self.send_json(certify_template_engine())
            return
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
        if self.path == "/template-engine-test":
            payload = template_engine_sample_story()
            story_dir = safe_child(STORIES_DIR, PREVIEW_FOLDER)
            ensure_template_engine_test_asset(story_dir)
            (exit_code, log, output_slug, render_token, production_payload, trace, diagnostics, environment, verdict, images) = render_carousel_payload(payload)
            image_rows = [{
                "url": f"/image/{urllib.parse.quote(output_slug)}/{urllib.parse.quote(image_path.name)}",
                "filename": image_path.name,
                "size_bytes": image_path.stat().st_size,
                "modified_ns": image_path.stat().st_mtime_ns,
            } for image_path in images if image_path.is_file()]
            self.send_json({
                "ok": exit_code == 0 and len(image_rows) == len(SUPPORTED_TEMPLATE_IDS),
                "error": "" if exit_code == 0 else "Template Engine certification render failed.",
                "images": image_rows, "slide_count": len(image_rows), "render_token": render_token,
                "production_payload": production_payload, "editorial_payload": payload,
                "trace": trace, "diagnostics": diagnostics, "environment": environment,
                "verdict": verdict, "log": log, "certification": certify_template_engine(),
            }, HTTPStatus.OK if exit_code == 0 else HTTPStatus.BAD_REQUEST)
            return

        if self.path == "/validate":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            try:
                envelope = json.loads(raw)
                payload = envelope.get("payload") if isinstance(envelope, dict) else None
                selected_index = int(envelope.get("slide_index", 0)) if isinstance(envelope, dict) else 0
                if not isinstance(payload, dict):
                    raise ValueError("Editor state is missing.")
                report = renderer_validation_report(payload, selected_index)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                self.send_json(
                    {"ok": False, "error": str(exc)},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            self.send_json({"ok": True, "report": report})
            return

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
                exit_code, log, output_slug, render_token, production_payload, trace, diagnostics, environment, verdict, images = render_carousel_payload(payload)
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
                        "verdict": verdict,
                        "trace": trace,
                        "diagnostics": diagnostics,
                        "environment": environment,
                        "production_payload": production_payload,
                        "log": log,
                    },
                    HTTPStatus.BAD_REQUEST,
                )
                return

            if not images:
                self.send_json(
                    {
                        "ok": False,
                        "error": "Renderer completed but produced no PNG deck.",
                        "verdict": verdict,
                        "trace": trace,
                        "diagnostics": diagnostics,
                        "environment": environment,
                        "production_payload": production_payload,
                        "log": log,
                    },
                    HTTPStatus.BAD_REQUEST,
                )
                return

            image_rows = []
            for image_path in images:
                image_rows.append(
                    {
                        "url": (
                            f"/image/{urllib.parse.quote(output_slug)}/"
                            f"{urllib.parse.quote(image_path.name)}"
                        ),
                        "filename": image_path.name,
                        "size_bytes": image_path.stat().st_size,
                        "modified_ns": image_path.stat().st_mtime_ns,
                    }
                )

            self.send_json(
                {
                    "ok": True,
                    "images": image_rows,
                    "slide_count": len(image_rows),
                    "output_slug": output_slug,
                    "render_token": render_token,
                    "renderer": "render_carousel.py",
                    "verdict": verdict,
                    "trace": trace,
                    "diagnostics": diagnostics,
                    "environment": environment,
                    "production_payload": production_payload,
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
                # Single authoritative adapter used by autosave.
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

        # Single authoritative adapter used by save and export.
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
    print(f"JenniWren Studio 3.7.1 running on port {PORT}")
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
