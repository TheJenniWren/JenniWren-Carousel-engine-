#!/usr/bin/env python3
"""
JenniWren Carousel Dashboard

A lightweight browser interface for the repository-native JenniWren carousel
renderer.

Run:
    python carousel_dashboard.py

Then open port 8000 from the Codespaces PORTS tab.

Features:
- Paste or edit a complete carousel.json payload
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


def build_page(
    *,
    folder_slug: str = "",
    payload: str = "",
    message: str = "",
    build_log: str = "",
    output_slug: str = "",
) -> str:
    """Build the complete dashboard page."""
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
                """.format(
                    url=image_url,
                    name=html.escape(image_path.name),
                )
            )

        if cards:
            slides_html = """
            <section class="results">
                <h2>Rendered slides</h2>
                <div class="slides">{cards}</div>
            </section>
            """.format(cards="".join(cards))

    message_html = ""
    if message:
        message_html = '<div class="notice">{}</div>'.format(html.escape(message))

    log_html = ""
    if build_log:
        log_html = """
        <section class="results">
            <h2>Build log</h2>
            <pre>{}</pre>
        </section>
        """.format(html.escape(build_log))

    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JenniWren Carousel Dashboard</title>
<style>
:root {{
    color-scheme: dark;
    --pink: #ff0a72;
    --background: #090909;
    --panel: #151515;
    --panel-2: #0d0d0d;
    --border: #343434;
    --text: #f7f7f7;
    --muted: #b8b8b8;
}}

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: var(--background);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}

main {{
    width: min(1180px, calc(100% - 28px));
    margin: 24px auto 64px;
}}

header {{
    border-top: 8px solid var(--pink);
    padding: 24px 0 14px;
}}

h1 {{
    margin: 0;
    max-width: 850px;
    font-size: clamp(34px, 7vw, 72px);
    line-height: 0.92;
    letter-spacing: -0.03em;
    text-transform: uppercase;
}}

h2 {{
    margin-top: 0;
}}

p {{
    color: var(--muted);
}}

.panel,
.results {{
    margin-top: 20px;
    padding: 18px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 14px;
}}

label {{
    display: block;
    margin-bottom: 8px;
    font-weight: 800;
}}

input,
textarea {{
    width: 100%;
    border: 1px solid #484848;
    border-radius: 10px;
    background: var(--panel-2);
    color: var(--text);
    padding: 12px;
    font: inherit;
}}

textarea {{
    min-height: 460px;
    resize: vertical;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 14px;
    line-height: 1.45;
}}

.actions {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 14px;
}}

button {{
    border: 0;
    border-radius: 10px;
    padding: 12px 18px;
    background: var(--pink);
    color: white;
    font: inherit;
    font-weight: 850;
    cursor: pointer;
}}

button.secondary {{
    background: #333;
}}

.notice {{
    margin-top: 18px;
    padding: 14px 16px;
    border-left: 5px solid var(--pink);
    background: #1b1b1b;
    white-space: pre-wrap;
}}

pre {{
    margin: 0;
    overflow-x: auto;
    white-space: pre-wrap;
    padding: 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: #050505;
}}

.slides {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 18px;
}}

.slide-card {{
    overflow: hidden;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 12px;
}}

.slide-card img {{
    display: block;
    width: 100%;
    height: auto;
}}

.slide-name {{
    padding: 10px 12px;
    color: var(--muted);
    font-size: 14px;
}}

code {{
    color: #ff79b5;
}}

.help {{
    margin-bottom: 0;
    font-size: 14px;
}}

@media (max-width: 700px) {{
    textarea {{
        min-height: 360px;
    }}
}}
</style>
</head>
<body>
<main>
<header>
    <h1>JenniWren Carousel Dashboard</h1>
    <p>Paste a complete <code>carousel.json</code>, save it, and render the PNGs.</p>
</header>

<section class="panel">
    <form method="post" action="/render">
        <label for="folder_slug">Story folder name</label>
        <input
            id="folder_slug"
            name="folder_slug"
            value="{folder_slug}"
            placeholder="musk-political-spending"
            required
        >

        <div style="height: 16px"></div>

        <label for="payload">carousel.json</label>
        <textarea
            id="payload"
            name="payload"
            spellcheck="false"
            required
        >{payload}</textarea>

        <div class="actions">
            <button type="submit">Save &amp; Render</button>
            <button class="secondary" type="submit" formaction="/save">Save only</button>
        </div>
    </form>

    <p class="help">
        Story files are saved under
        <code>stories/&lt;folder-name&gt;/carousel.json</code>.
    </p>
</section>

{message}
{build_log}
{slides}
</main>
</body>
</html>
""".format(
        folder_slug=html.escape(folder_slug),
        payload=html.escape(payload),
        message=message_html,
        build_log=log_html,
        slides=slides_html,
    )


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
