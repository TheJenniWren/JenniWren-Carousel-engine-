#!/usr/bin/env python3
"""
JenniWren Studio v2.1

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

TEMPLATE_LABELS = {
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
<title>JenniWren Studio v2.1</title>
<style>
:root{color-scheme:dark;--pink:#ff0a72;--bg:#080808;--panel:#151515;--panel2:#0d0d0d;--border:#363636;--text:#f7f7f7;--muted:#b8b8b8;--danger:#922048}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{width:min(1180px,calc(100% - 28px));margin:24px auto 64px}header{border-top:8px solid var(--pink);padding:24px 0 14px}h1{margin:0;font-size:clamp(38px,7vw,74px);line-height:.92;letter-spacing:-.035em;text-transform:uppercase}h2,h3{margin:0}p,.help{color:var(--muted)}.panel{margin-top:20px;padding:18px;background:var(--panel);border:1px solid var(--border);border-radius:14px}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;margin:13px 0 7px;font-weight:800}input,textarea,select{width:100%;padding:12px;border:1px solid #484848;border-radius:10px;background:var(--panel2);color:var(--text);font:inherit}textarea{resize:vertical;line-height:1.42;min-height:105px}textarea.tall{min-height:150px}.actions,.toolbar,.small-actions{display:flex;flex-wrap:wrap;gap:9px}.actions{margin-top:18px}.toolbar{align-items:center;justify-content:space-between}button{border:0;border-radius:10px;padding:12px 18px;background:var(--pink);color:#fff;font:inherit;font-weight:850;cursor:pointer}button.secondary{background:#333}button.danger{background:var(--danger)}button.small{padding:7px 10px;font-size:13px}.slide{margin-top:16px;padding:16px;background:#101010;border:1px solid var(--border);border-radius:13px}.slide-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding-bottom:10px;border-bottom:1px solid #2d2d2d}.repeater{margin-top:10px}.repeat-row{display:grid;grid-template-columns:170px 1fr auto;gap:8px;align-items:end;margin-top:8px}.repeat-row.stat{grid-template-columns:1fr 1fr auto}.repeat-row.source{grid-template-columns:1fr auto}.notice{margin-top:18px;padding:14px 16px;border-left:5px solid var(--pink);background:#1b1b1b;white-space:pre-wrap}pre{overflow-x:auto;white-space:pre-wrap;padding:14px;border:1px solid var(--border);border-radius:10px;background:#050505}.hidden{display:none}.previews{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px}.preview-card{overflow:hidden;border:1px solid var(--border);border-radius:12px;background:var(--panel2)}.preview-card img{display:block;width:100%;height:auto}.preview-card div{padding:10px 12px;color:var(--muted);font-size:14px}summary{cursor:pointer;font-weight:800}@media(max-width:720px){.two{grid-template-columns:1fr;gap:0}.slide-head{align-items:flex-start;flex-direction:column}.repeat-row,.repeat-row.stat{grid-template-columns:1fr}}
</style>
</head>
<body>
<main>
<header><h1>JenniWren Studio v2.1</h1><p>Ten renderer-native templates with fields that change automatically.</p></header>
<form id="studio-form" method="post" action="/render">
<section class="panel"><h2>Story</h2><div class="two"><div><label for="folder_slug">Story folder name</label><input id="folder_slug" name="folder_slug" value="__FOLDER__" placeholder="musk-political-spending" required></div><div><label for="story_title">Story title</label><input id="story_title" placeholder="Elon Musk's political spending" required></div></div><label for="source">Primary source</label><input id="source" placeholder="Associated Press, July 21, 2026"></section>
<section class="panel"><div class="toolbar"><h2>Slides</h2><button type="button" id="add-slide">+ Add slide</button></div><div id="slides"></div></section>
<input type="hidden" id="payload" name="payload"><div class="actions"><button type="submit">Save &amp; Render</button><button type="submit" class="secondary" formaction="/save">Save only</button><button type="button" class="secondary" id="preview-json">Preview JSON</button></div></form>
<section id="json-panel" class="panel hidden"><h2>Generated carousel.json</h2><pre id="json-output"></pre></section>
__NOTICE____LOG____PREVIEWS__
<script id="initial-data" type="application/json">__INITIAL_DATA__</script>
<script>
const TEMPLATE_OPTIONS=`__TEMPLATE_OPTIONS__`;const slidesRoot=document.getElementById("slides");const initial=JSON.parse(document.getElementById("initial-data").textContent);
const schemas={cover_headline:[["headline_lines","Headline","lines"],["body","Deck / body","body"],["citation","Citation","text"]],quote_lead:[["quote_lines","Quote","lines"],["attribution","Attribution","text"],["citation","Citation","text"]],photo_headline:[["image","Image filename","text"],["headline_lines","Headline","lines"],["citation","Citation","text"]],stat_callout:[["stat_text","Statistic","text"],["stat_label","Statistic label","text"],["headline_lines","Optional context headline","lines"],["citation","Citation","text"]],stat_grid:[["headline_lines","Headline","lines"],["stat_items","Statistics","stats"],["citation","Citation","text"]],timeline:[["headline_lines","Headline","lines"],["timeline_entries","Timeline entries","timeline"],["citation","Citation","text"]],call_block:[["headline_lines","Optional headline","lines"],["call_text","Highlighted statement","body"],["body","Supporting body","body"],["citation","Citation","text"]],document_card:[["headline_lines","Headline","lines"],["doc_lines","Document excerpt","lines"],["doc_highlight","Highlighted excerpt","text"],["doc_annotation","Annotation","body"],["citation","Citation","text"]],body_standard:[["headline_lines","Headline","lines"],["body","Body","body"],["citation","Citation","text"]],sources_slide:[["citations","Sources","sources"]]};
function escapeHTML(value=""){return value.replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]))}function asLines(value){return Array.isArray(value)?value.join("\n"):value||""}function asBody(value){if(Array.isArray(value))return value.map(item=>typeof item==="object"?item.text||"":item).filter(Boolean).join("\n\n");if(value&&typeof value==="object")return value.text||"";return value||""}function normalizeSlide(raw={}){return {...raw,template:raw.template||"body_standard",label:raw.label||"SLIDE"}}function removeButton(){return '<button type="button" class="small danger" data-remove-row>Delete</button>'}
function fieldHTML(type,key,label,value){if(type==="text")return `<label>${label}</label><input data-key="${key}" value="${escapeHTML(String(value||""))}">`;if(type==="lines")return `<label>${label}</label><textarea data-key="${key}" data-type="lines">${escapeHTML(asLines(value))}</textarea>`;if(type==="body")return `<label>${label}</label><textarea class="tall" data-key="${key}" data-type="body">${escapeHTML(asBody(value))}</textarea>`;if(type==="timeline"){const rows=Array.isArray(value)&&value.length?value:[{date:"",text:""}];return `<div class="repeater" data-repeater="${key}" data-type="timeline"><div class="toolbar"><label>${label}</label><button type="button" class="small secondary" data-add-row>Add entry</button></div>${rows.map(item=>`<div class="repeat-row"><input data-part="date" value="${escapeHTML(String(item.date||item.label||""))}" placeholder="Date"><input data-part="text" value="${escapeHTML(String(item.text||item.event||""))}" placeholder="Event">${removeButton()}</div>`).join("")}</div>`}if(type==="stats"){const rows=Array.isArray(value)&&value.length?value:[{stat_text:"",stat_label:""}];return `<div class="repeater" data-repeater="${key}" data-type="stats"><div class="toolbar"><label>${label}</label><button type="button" class="small secondary" data-add-row>Add statistic</button></div>${rows.map(item=>`<div class="repeat-row stat"><input data-part="stat_text" value="${escapeHTML(String(item.stat_text||item.value||""))}" placeholder="Statistic"><input data-part="stat_label" value="${escapeHTML(String(item.stat_label||item.label||""))}" placeholder="Label">${removeButton()}</div>`).join("")}</div>`}if(type==="sources"){const rows=Array.isArray(value)&&value.length?value:[""];return `<div class="repeater" data-repeater="${key}" data-type="sources"><div class="toolbar"><label>${label}</label><button type="button" class="small secondary" data-add-row>Add source</button></div>${rows.map(item=>`<div class="repeat-row source"><input data-part="citation" value="${escapeHTML(String(typeof item==="object"?item.citation||item.text||"":item))}" placeholder="Source citation">${removeButton()}</div>`).join("")}</div>`}return ""}
function renderDynamic(slide,data){const root=slide.querySelector(".dynamic-fields");const template=slide.querySelector("[data-template]").value;root.innerHTML=(schemas[template]||[]).map(([key,label,type])=>fieldHTML(type,key,label,data[key])).join("")}
function addSlide(data={}){const normalized=normalizeSlide(data);const article=document.createElement("article");article.className="slide";article.dataset.slide="";article.innerHTML=`<div class="slide-head"><strong>Slide <span data-number></span></strong><div class="small-actions"><button type="button" class="small secondary" data-up>↑</button><button type="button" class="small secondary" data-down>↓</button><button type="button" class="small secondary" data-duplicate>Duplicate</button><button type="button" class="small danger" data-delete>Delete</button></div></div><div class="two"><div><label>Template</label><select data-template>${TEMPLATE_OPTIONS}</select></div><div><label>Label</label><input data-label value="${escapeHTML(normalized.label)}"></div></div><div class="dynamic-fields"></div>`;slidesRoot.appendChild(article);article.querySelector("[data-template]").value=normalized.template;renderDynamic(article,normalized);renumber()}
function renumber(){[...slidesRoot.querySelectorAll("[data-slide]")].forEach((slide,index)=>slide.querySelector("[data-number]").textContent=index+1)}function readRepeater(container){const type=container.dataset.type;const rows=[...container.querySelectorAll(".repeat-row")];if(type==="timeline")return rows.map(row=>({date:row.querySelector('[data-part="date"]').value.trim(),text:row.querySelector('[data-part="text"]').value.trim()})).filter(item=>item.date||item.text);if(type==="stats")return rows.map(row=>({stat_text:row.querySelector('[data-part="stat_text"]').value.trim(),stat_label:row.querySelector('[data-part="stat_label"]').value.trim()})).filter(item=>item.stat_text||item.stat_label);if(type==="sources")return rows.map(row=>row.querySelector('[data-part="citation"]').value.trim()).filter(Boolean);return []}
function readSlide(slide,index){const template=slide.querySelector("[data-template]").value;const item={template,label:slide.querySelector("[data-label]").value.trim()||`SLIDE ${index+1}`};for(const [key,,type] of schemas[template]||[]){const repeater=slide.querySelector(`[data-repeater="${key}"]`);if(repeater){item[key]=readRepeater(repeater);continue}const input=slide.querySelector(`[data-key="${key}"]`);if(!input)continue;const value=input.value.trim();if(type==="lines")item[key]=value.split(/\n+/).map(v=>v.trim()).filter(Boolean);else if(type==="body")item[key]=value?[{text:value}]:[];else if(value)item[key]=value}if(["cover_headline","photo_headline","timeline","document_card","body_standard"].includes(template))item.headline_colors=["white"];if(template==="quote_lead")item.quote_colors=["white"];return item}
function buildPayload(){return {story:document.getElementById("story_title").value.trim(),source:document.getElementById("source").value.trim(),slides:[...slidesRoot.querySelectorAll("[data-slide]")].map(readSlide)}}function syncPayload(){const text=JSON.stringify(buildPayload(),null,2);document.getElementById("payload").value=text;document.getElementById("json-output").textContent=text}
slidesRoot.addEventListener("change",event=>{if(event.target.matches("[data-template]")){const slide=event.target.closest("[data-slide]");renderDynamic(slide,{})}});slidesRoot.addEventListener("click",event=>{const button=event.target.closest("button");if(!button)return;const slide=button.closest("[data-slide]");if(button.matches("[data-add-row]")){const repeater=button.closest("[data-repeater]");const type=repeater.dataset.type;if(type==="timeline")repeater.insertAdjacentHTML("beforeend",`<div class="repeat-row"><input data-part="date" placeholder="Date"><input data-part="text" placeholder="Event">${removeButton()}</div>`);if(type==="stats")repeater.insertAdjacentHTML("beforeend",`<div class="repeat-row stat"><input data-part="stat_text" placeholder="Statistic"><input data-part="stat_label" placeholder="Label">${removeButton()}</div>`);if(type==="sources")repeater.insertAdjacentHTML("beforeend",`<div class="repeat-row source"><input data-part="citation" placeholder="Source citation">${removeButton()}</div>`);return}if(button.matches("[data-remove-row]")){const repeater=button.closest("[data-repeater]");if(repeater.querySelectorAll(".repeat-row").length>1)button.closest(".repeat-row").remove();return}if(!slide)return;if(button.matches("[data-delete]")){if(slidesRoot.querySelectorAll("[data-slide]").length===1){alert("A carousel needs at least one slide.");return}slide.remove()}else if(button.matches("[data-duplicate]"))addSlide(readSlide(slide,0));else if(button.matches("[data-up]")&&slide.previousElementSibling)slidesRoot.insertBefore(slide,slide.previousElementSibling);else if(button.matches("[data-down]")&&slide.nextElementSibling)slidesRoot.insertBefore(slide.nextElementSibling,slide);renumber()});document.getElementById("add-slide").addEventListener("click",()=>addSlide({template:"body_standard"}));document.getElementById("preview-json").addEventListener("click",()=>{syncPayload();document.getElementById("json-panel").classList.toggle("hidden")});document.getElementById("studio-form").addEventListener("submit",event=>{syncPayload();if(!document.getElementById("story_title").value.trim()){event.preventDefault();alert("Enter a story title.")}});document.getElementById("story_title").value=initial.story||initial.title||"";document.getElementById("source").value=initial.source||"";(initial.slides&&initial.slides.length?initial.slides:[{template:"cover_headline"}]).forEach(addSlide);syncPayload();
</script>
</main>
</body>
</html>'''
    return (page.replace("__FOLDER__", html.escape(folder_slug))
                .replace("__NOTICE__", notice_html)
                .replace("__LOG__", log_html)
                .replace("__PREVIEWS__", preview_html)
                .replace("__INITIAL_DATA__", json_script_data(data))
                .replace("__TEMPLATE_OPTIONS__", template_options))


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "JenniWrenStudio/2.1"

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
        if self.path not in {"/save", "/render"}:
            self.send_error(HTTPStatus.NOT_FOUND); return
        length = int(self.headers.get("Content-Length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        folder_slug = slugify(form.get("folder_slug", [""])[0])
        payload_text = form.get("payload", [""])[0]
        try:
            payload: Any = json.loads(payload_text)
            if not isinstance(payload, dict): raise ValueError("Payload must be a JSON object.")
            if not str(payload.get("story") or "").strip(): raise ValueError("Story title is required.")
            slides = payload.get("slides")
            if not isinstance(slides, list) or not slides: raise ValueError("At least one slide is required.")
            unsupported = [slide.get("template") for slide in slides if not isinstance(slide, dict) or slide.get("template") not in TEMPLATE_LABELS]
            if unsupported: raise ValueError(f"Unsupported template: {unsupported[0]}")
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_html(build_page(folder_slug=folder_slug, data=default_story(), message=f"Validation failed: {exc}"), HTTPStatus.BAD_REQUEST); return
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
    print(f"JenniWren Studio v2.1 running on port {PORT}")
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
