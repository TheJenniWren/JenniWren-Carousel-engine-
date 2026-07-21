#!/usr/bin/env python3
"""
JenniWren Carousel Dashboard

A lightweight browser interface for the repository-native JenniWren carousel
renderer.

Run:
    python carousel_dashboard.py

Then open port 8000 from the Codespaces PORTS tab.

Features:
- Build carousel.json through structured story and slide forms
- Add, duplicate, delete, and reorder slides
- Save it under stories/<slug>/carousel.json
- Render through render_carousel.py
- Preview generated PNG slides in the browser
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


def slugify(value: str) -> str:
    """Convert a title or folder name into a safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "story"


def safe_child(base: Path, child: str) -> Path:
    """Resolve a child path while preventing directory traversal."""
    base_resolved = base.resolve()
    candidate = (base_resolved / child).resolve()

    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise ValueError("Unsafe path")

    return candidate


def load_story_payload(folder_slug: str) -> str:
    """Return existing carousel.json text for a story folder."""
    path = safe_child(STORIES_DIR, folder_slug) / "carousel.json"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def run_renderer(folder_slug: str) -> tuple[int, str]:
    """Run render_carousel.py for one story folder."""
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
        output = exc.stdout or ""
        return 124, f"{output}\nERROR: Render timed out after 300 seconds."

    return process.returncode, process.stdout


def output_images(output_slug: str) -> list[Path]:
    """Return rendered PNGs for a story output folder."""
    folder = safe_child(OUTPUT_DIR, output_slug)
    if not folder.exists():
        return []
    return sorted(folder.glob("*.png"))


def _slide_form_data(payload: str) -> tuple[str, str, list[dict[str, str]]]:
    """Convert an existing carousel payload into structured form values."""
    story_title = ""
    source = ""
    slides: list[dict[str, str]] = []

    if payload.strip():
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {}

        if isinstance(data, dict):
            story_title = str(data.get("story") or data.get("title") or "")
            source = str(data.get("source") or "")

            raw_slides = data.get("slides")
            if isinstance(raw_slides, list):
                for index, raw_slide in enumerate(raw_slides, start=1):
                    if not isinstance(raw_slide, dict):
                        continue

                    headline = raw_slide.get("headline")
                    if not headline:
                        headline_lines = raw_slide.get("headline_lines")
                        if isinstance(headline_lines, list):
                            headline = "\n".join(str(line) for line in headline_lines)
                        else:
                            headline = ""

                    body = raw_slide.get("body", "")
                    if isinstance(body, list):
                        body_parts: list[str] = []
                        for block in body:
                            if isinstance(block, dict):
                                text = block.get("text")
                                if text:
                                    body_parts.append(str(text))
                            elif block:
                                body_parts.append(str(block))
                        body = "\n\n".join(body_parts)
                    elif isinstance(body, dict):
                        body = str(body.get("text") or "")
                    else:
                        body = str(body or "")

                    slides.append(
                        {
                            "template": str(raw_slide.get("template") or ""),
                            "label": str(raw_slide.get("label") or f"SLIDE {index}"),
                            "headline": str(headline or ""),
                            "body": body,
                            "citation": str(raw_slide.get("citation") or ""),
                            "image_filename": str(
                                raw_slide.get("image_filename")
                                or raw_slide.get("image")
                                or ""
                            ),
                        }
                    )

    if not slides:
        slides = [
            {
                "template": "cover_headline",
                "label": "THE JENNI WREN",
                "headline": "",
                "body": "",
                "citation": "",
                "image_filename": "",
            },
            {
                "template": "signature",
                "label": "WHAT HAPPENED",
                "headline": "",
                "body": "",
                "citation": "",
                "image_filename": "",
            },
        ]

    return story_title, source, slides


def build_page(
    *,
    folder_slug: str = "",
    payload: str = "",
    message: str = "",
    build_log: str = "",
    output_slug: str = "",
) -> str:
    """Build the Phase 2 structured dashboard page."""
    story_title, source, form_slides = _slide_form_data(payload)

    slide_cards: list[str] = []
    for index, slide in enumerate(form_slides):
        slide_cards.append(
            """
            <article class="editor-slide" data-slide>
                <div class="slide-toolbar">
                    <strong>Slide <span data-slide-number>{number}</span></strong>
                    <div class="slide-actions">
                        <button type="button" class="mini secondary" data-move-up>↑</button>
                        <button type="button" class="mini secondary" data-move-down>↓</button>
                        <button type="button" class="mini secondary" data-duplicate>Duplicate</button>
                        <button type="button" class="mini danger" data-remove>Delete</button>
                    </div>
                </div>

                <div class="field-grid">
                    <div>
                        <label>Template</label>
                        <select data-field="template">
                            {template_options}
                        </select>
                    </div>
                    <div>
                        <label>Label</label>
                        <input data-field="label" value="{label}" placeholder="WHAT HAPPENED">
                    </div>
                </div>

                <label>Headline</label>
                <textarea class="headline-box" data-field="headline" placeholder="One headline line per row">{headline}</textarea>

                <label>Body</label>
                <textarea class="body-box" data-field="body" placeholder="Slide body copy">{body}</textarea>

                <div class="field-grid">
                    <div>
                        <label>Citation</label>
                        <input data-field="citation" value="{citation}" placeholder="AP, July 18, 2026">
                    </div>
                    <div>
                        <label>Image filename</label>
                        <input data-field="image_filename" value="{image_filename}" placeholder="photo.jpg">
                    </div>
                </div>
            </article>
            """.format(
                number=index + 1,
                template_options=_template_options(slide["template"]),
                label=html.escape(slide["label"]),
                headline=html.escape(slide["headline"]),
                body=html.escape(slide["body"]),
                citation=html.escape(slide["citation"]),
                image_filename=html.escape(slide["image_filename"]),
            )
        )

    slides_html = ""
    if output_slug:
        cards: list[str] = []
        for image_path in output_images(output_slug):
            image_url = "/image/{}/{}".format(
                urllib.parse.quote(output_slug),
                urllib.parse.quote(image_path.name),
            )
            cards.append(
                """
                <article class="slide-card">
                    <a href="{url}" target="_blank" rel="noopener">
                        <img src="{url}" alt="{name}">
                    </a>
                    <div class="slide-name">{name}</div>
                </article>
                """.format(url=image_url, name=html.escape(image_path.name))
            )

        if cards:
            slides_html = """
            <section class="results">
                <h2>Rendered slides</h2>
                <div class="slides">{cards}</div>
            </section>
            """.format(cards="".join(cards))

    message_html = (
        '<div class="notice">{}</div>'.format(html.escape(message))
        if message
        else ""
    )
    log_html = (
        """
        <details class="results">
            <summary>Build log</summary>
            <pre>{}</pre>
        </details>
        """.format(html.escape(build_log))
        if build_log
        else ""
    )

    page_template = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JenniWren Studio</title>
<style>
:root {
    color-scheme: dark;
    --pink:#ff0a72;
    --bg:#090909;
    --panel:#151515;
    --panel2:#0d0d0d;
    --border:#343434;
    --text:#f7f7f7;
    --muted:#b8b8b8;
    --danger:#8f1d46;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
main { width:min(1180px,calc(100% - 28px)); margin:24px auto 64px; }
header { border-top:8px solid var(--pink); padding:24px 0 14px; }
h1 { margin:0; font-size:clamp(36px,7vw,72px); line-height:.92; letter-spacing:-.03em; text-transform:uppercase; }
h2 { margin:0 0 14px; }
p { color:var(--muted); }
.panel,.results { margin-top:20px; padding:18px; background:var(--panel); border:1px solid var(--border); border-radius:14px; }
label { display:block; margin:13px 0 7px; font-weight:800; }
input,textarea,select { width:100%; border:1px solid #484848; border-radius:10px; background:var(--panel2); color:var(--text); padding:12px; font:inherit; }
textarea { resize:vertical; line-height:1.4; }
.headline-box { min-height:92px; font-weight:750; }
.body-box { min-height:140px; }
.field-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.actions,.slide-actions { display:flex; flex-wrap:wrap; gap:9px; }
.actions { margin-top:18px; }
button { border:0; border-radius:10px; padding:12px 18px; background:var(--pink); color:#fff; font:inherit; font-weight:850; cursor:pointer; }
button.secondary { background:#333; }
button.danger { background:var(--danger); }
button.mini { padding:7px 10px; font-size:13px; }
.editor-slide { margin-top:16px; padding:16px; background:#101010; border:1px solid var(--border); border-radius:13px; }
.slide-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; border-bottom:1px solid #2d2d2d; padding-bottom:10px; }
.notice { margin-top:18px; padding:14px 16px; border-left:5px solid var(--pink); background:#1b1b1b; white-space:pre-wrap; }
pre { overflow-x:auto; white-space:pre-wrap; padding:14px; background:#050505; border:1px solid var(--border); border-radius:10px; }
.slides { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:18px; }
.slide-card { overflow:hidden; background:var(--panel2); border:1px solid var(--border); border-radius:12px; }
.slide-card img { display:block; width:100%; height:auto; }
.slide-name { padding:10px 12px; color:var(--muted); font-size:14px; }
.help { margin-bottom:0; font-size:14px; }
code { color:#ff79b5; }
summary { cursor:pointer; font-weight:800; }
.hidden-json { display:none; }
@media (max-width:700px) {
    .field-grid { grid-template-columns:1fr; gap:0; }
    .slide-toolbar { align-items:flex-start; flex-direction:column; }
}
</style>
</head>
<body>
<main>
<header>
    <h1>JenniWren Studio</h1>
    <p>Build the carousel with forms. The dashboard creates the JSON for you.</p>
</header>

<form id="studio-form" method="post" action="/render">
<section class="panel">
    <h2>Story</h2>

    <div class="field-grid">
        <div>
            <label for="folder_slug">Story folder name</label>
            <input id="folder_slug" name="folder_slug" value="__FOLDER__" placeholder="musk-political-spending" required>
        </div>
        <div>
            <label for="story_title">Story title</label>
            <input id="story_title" value="__STORY__" placeholder="Elon Musk's political spending" required>
        </div>
    </div>

    <label for="source">Source</label>
    <input id="source" value="__SOURCE__" placeholder="Associated Press, July 18, 2026">

    <p class="help">The first slide is the cover. Add, duplicate, delete, or reorder slides below.</p>
</section>

<section class="panel">
    <div class="slide-toolbar">
        <h2>Slides</h2>
        <button type="button" id="add-slide">+ Add slide</button>
    </div>

    <div id="slide-editor">
        __EDITOR_SLIDES__
    </div>
</section>

<input type="hidden" id="payload" name="payload">

<div class="actions">
    <button type="submit">Save &amp; Render</button>
    <button type="submit" class="secondary" formaction="/save">Save only</button>
    <button type="button" class="secondary" id="show-json">Preview JSON</button>
</div>
</form>

<section id="json-panel" class="results hidden-json">
    <h2>Generated carousel.json</h2>
    <pre id="json-preview"></pre>
</section>

__MESSAGE__
__LOG__
__RENDERED__

<template id="slide-template">
<article class="editor-slide" data-slide>
    <div class="slide-toolbar">
        <strong>Slide <span data-slide-number></span></strong>
        <div class="slide-actions">
            <button type="button" class="mini secondary" data-move-up>↑</button>
            <button type="button" class="mini secondary" data-move-down>↓</button>
            <button type="button" class="mini secondary" data-duplicate>Duplicate</button>
            <button type="button" class="mini danger" data-remove>Delete</button>
        </div>
    </div>

    <div class="field-grid">
        <div>
            <label>Template</label>
            <select data-field="template">__ALL_TEMPLATE_OPTIONS__</select>
        </div>
        <div>
            <label>Label</label>
            <input data-field="label" placeholder="WHAT HAPPENED">
        </div>
    </div>

    <label>Headline</label>
    <textarea class="headline-box" data-field="headline" placeholder="One headline line per row"></textarea>

    <label>Body</label>
    <textarea class="body-box" data-field="body" placeholder="Slide body copy"></textarea>

    <div class="field-grid">
        <div>
            <label>Citation</label>
            <input data-field="citation" placeholder="AP, July 18, 2026">
        </div>
        <div>
            <label>Image filename</label>
            <input data-field="image_filename" placeholder="photo.jpg">
        </div>
    </div>
</article>
</template>

<script>
const editor = document.getElementById("slide-editor");
const form = document.getElementById("studio-form");
const payloadInput = document.getElementById("payload");
const jsonPanel = document.getElementById("json-panel");
const jsonPreview = document.getElementById("json-preview");

function renumberSlides() {
    [...editor.querySelectorAll("[data-slide]")].forEach((slide, index) => {
        slide.querySelector("[data-slide-number]").textContent = index + 1;
    });
}

function field(slide, name) {
    return slide.querySelector(`[data-field="${name}"]`).value.trim();
}

function buildPayload() {
    const slides = [...editor.querySelectorAll("[data-slide]")].map((slide, index) => {
        const headline = field(slide, "headline");
        const body = field(slide, "body");
        const citation = field(slide, "citation");
        const imageFilename = field(slide, "image_filename");

        const item = {
            template: field(slide, "template"),
            label: field(slide, "label") || `SLIDE ${index + 1}`,
            headline_lines: headline
                .split(/\n+/)
                .map(line => line.trim())
                .filter(Boolean),
            headline_colors: ["white"],
            body: body ? [{text: body}] : []
        };

        if (citation) item.citation = citation;
        if (imageFilename) item.image_filename = imageFilename;
        return item;
    });

    return {
        story: document.getElementById("story_title").value.trim(),
        source: document.getElementById("source").value.trim(),
        slides
    };
}

function syncPayload() {
    const payload = buildPayload();
    payloadInput.value = JSON.stringify(payload, null, 2);
    jsonPreview.textContent = payloadInput.value;
}

document.getElementById("add-slide").addEventListener("click", () => {
    const fragment = document.getElementById("slide-template").content.cloneNode(true);
    editor.appendChild(fragment);
    renumberSlides();
});

editor.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) return;

    const slide = button.closest("[data-slide]");
    if (!slide) return;

    if (button.matches("[data-remove]")) {
        if (editor.querySelectorAll("[data-slide]").length === 1) {
            alert("A carousel needs at least one slide.");
            return;
        }
        slide.remove();
    }

    if (button.matches("[data-duplicate]")) {
        slide.after(slide.cloneNode(true));
    }

    if (button.matches("[data-move-up]") && slide.previousElementSibling) {
        editor.insertBefore(slide, slide.previousElementSibling);
    }

    if (button.matches("[data-move-down]") && slide.nextElementSibling) {
        editor.insertBefore(slide.nextElementSibling, slide);
    }

    renumberSlides();
});

document.getElementById("show-json").addEventListener("click", () => {
    syncPayload();
    jsonPanel.classList.toggle("hidden-json");
});

form.addEventListener("submit", event => {
    syncPayload();

    if (!buildPayload().slides.length) {
        event.preventDefault();
        alert("Add at least one slide.");
    }
});

renumberSlides();
syncPayload();
</script>
</main>
</body>
</html>
"""

    return (
        page_template
        .replace("__FOLDER__", html.escape(folder_slug))
        .replace("__STORY__", html.escape(story_title))
        .replace("__SOURCE__", html.escape(source))
        .replace("__EDITOR_SLIDES__", "".join(slide_cards))
        .replace("__MESSAGE__", message_html)
        .replace("__LOG__", log_html)
        .replace("__RENDERED__", slides_html)
        .replace("__ALL_TEMPLATE_OPTIONS__", _template_options("signature"))
    )


def _template_options(selected: str) -> str:
    """Return the current Phase 2 template menu."""
    templates = [
        ("cover_headline", "Cover — Headline"),
        ("cover_feature", "Cover — Feature"),
        ("cover_quote", "Cover — Quote Lead"),
        ("cover_primary_source", "Cover — Primary Source"),
        ("cover_political_stakes", "Cover — Political Stakes"),
        ("cover_big_number", "Cover — Big Number"),
        ("cover_compare", "Cover — Contrast / Compare"),
        ("cover_newspaper", "Cover — Newspaper Front Page"),
        ("signature", "Interior — Signature"),
        ("timeline", "Interior — Timeline"),
        ("quote", "Interior — Quote"),
        ("document_evidence", "Interior — Document Evidence"),
        ("big_number", "Interior — Big Number"),
        ("split", "Interior — Split"),
        ("comparison", "Interior — Comparison"),
        ("investigation_tracker", "Interior — Investigation Tracker"),
        ("decision_tree", "Interior — Decision Tree"),
        ("network_map", "Interior — Network Map"),
        ("org_chart", "Interior — Org Chart"),
        ("follow_connection", "Interior — Follow the Connection"),
        ("cta", "Final — CTA"),
    ]

    parts: list[str] = []
    for value, label in templates:
        selected_attr = " selected" if value == selected else ""
        parts.append(
            '<option value="{}"{}>{}</option>'.format(
                html.escape(value),
                selected_attr,
                html.escape(label),
            )
        )
    return "".join(parts)


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the dashboard."""

    server_version = "JenniWrenDashboard/1.0"

    def send_html(self, content: str, status: int = HTTPStatus.OK) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            query = urllib.parse.parse_qs(parsed.query)
            folder_slug = query.get("folder", [""])[0]
            payload = load_story_payload(folder_slug) if folder_slug else ""

            self.send_html(
                build_page(
                    folder_slug=folder_slug,
                    payload=payload,
                )
            )
            return

        if parsed.path.startswith("/image/"):
            parts = parsed.path.split("/", 3)
            if len(parts) != 4:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            output_slug = urllib.parse.unquote(parts[2])
            filename = urllib.parse.unquote(parts[3])

            try:
                image_path = safe_child(
                    safe_child(OUTPUT_DIR, output_slug),
                    filename,
                )
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return

            if not image_path.is_file() or image_path.suffix.lower() != ".png":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            data = image_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path not in {"/save", "/render"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        form = urllib.parse.parse_qs(raw_body)

        requested_folder = form.get("folder_slug", [""])[0]
        payload = form.get("payload", [""])[0]
        folder_slug = slugify(requested_folder)

        try:
            parsed_payload: Any = json.loads(payload)

            if not isinstance(parsed_payload, dict):
                raise ValueError("The root JSON value must be an object.")

            slides = parsed_payload.get("slides")
            if not isinstance(slides, list) or not slides:
                raise ValueError(
                    "The JSON must contain a non-empty 'slides' array."
                )

        except (json.JSONDecodeError, ValueError) as exc:
            self.send_html(
                build_page(
                    folder_slug=folder_slug,
                    payload=payload,
                    message=f"JSON validation failed: {exc}",
                ),
                HTTPStatus.BAD_REQUEST,
            )
            return

        story_dir = safe_child(STORIES_DIR, folder_slug)
        story_dir.mkdir(parents=True, exist_ok=True)

        formatted_payload = (
            json.dumps(parsed_payload, indent=2, ensure_ascii=False) + "\n"
        )
        (story_dir / "carousel.json").write_text(
            formatted_payload,
            encoding="utf-8",
        )

        if self.path == "/save":
            self.send_html(
                build_page(
                    folder_slug=folder_slug,
                    payload=formatted_payload,
                    message=f"Saved stories/{folder_slug}/carousel.json",
                )
            )
            return

        exit_code, build_log = run_renderer(folder_slug)
        output_slug = slugify(
            str(parsed_payload.get("story") or folder_slug)
        )

        if exit_code == 0:
            message = f"Render succeeded: output/{output_slug}/"
            status = HTTPStatus.OK
        else:
            message = f"Render failed with exit code {exit_code}."
            status = HTTPStatus.BAD_REQUEST

        self.send_html(
            build_page(
                folder_slug=folder_slug,
                payload=formatted_payload,
                message=message,
                build_log=build_log,
                output_slug=output_slug,
            ),
            status,
        )

    def log_message(self, format_string: str, *args: object) -> None:
        print(
            "[dashboard] "
            + self.address_string()
            + " - "
            + (format_string % args)
        )


def main() -> int:
    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not RENDERER.exists():
        print(
            f"ERROR: {RENDERER.name} must be in the same folder "
            "as carousel_dashboard.py."
        )
        return 1

    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)

    print(f"JenniWren Carousel Dashboard running on port {PORT}")
    print("Open the Codespaces PORTS tab and open port 8000.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
