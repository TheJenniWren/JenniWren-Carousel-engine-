#!/usr/bin/env python3
from __future__ import annotations
import json, py_compile, shutil, subprocess, sys
from pathlib import Path

class PatchError(RuntimeError): pass

def run(command, cwd):
    r=subprocess.run(command,cwd=cwd,text=True,capture_output=True)
    if r.returncode:
        detail='\n'.join(p.strip() for p in (r.stdout,r.stderr) if p.strip())
        raise PatchError(f"Command failed: {' '.join(command)}"+(f"\n{detail}" if detail else ""))
    return r

def insert_before(text, marker, insertion, label):
    if marker not in text: raise PatchError(f"{label}: marker not found.")
    return text.replace(marker,insertion+marker,1)

def replace_once(text, old, new, label):
    c=text.count(old)
    if c!=1: raise PatchError(f"{label}: expected exactly one target, found {c}.")
    return text.replace(old,new,1)

def main():
    repo=Path.cwd().resolve(); dashboard=repo/'carousel_dashboard.py'
    if not dashboard.is_file(): raise PatchError('Run this script from the repository root.')
    branch=run(['git','branch','--show-current'],repo).stdout.strip()
    if branch!='studio-3.9-dev': raise PatchError(f"Phase 4 must run on 'studio-3.9-dev'; current branch is {branch!r}.")
    text=dashboard.read_text(encoding='utf-8')
    backup=repo/'carousel_dashboard.py.before_studio_3_9_phase4'
    if not backup.exists(): shutil.copy2(dashboard,backup)

    component_contract='''EDITOR_COMPONENT_CONTRACT: dict[str, dict[str, Any]] = {
    "label": {"kind": "label", "label": "Label", "max_chars": 42},
    "headline": {"kind": "headline", "label": "Headline", "multiline": True, "colors": ("white", "pink"), "reorderable": True, "max_lines": 8, "max_chars_per_line": 42},
    "body": {"kind": "body", "label": "Body", "auto_grow": True, "counter": True},
    "deck": {"kind": "body", "label": "Deck / body", "auto_grow": True, "counter": True},
    "photo": {"kind": "photo", "label": "Photo", "extensions": ("png", "jpg", "jpeg"), "replaceable": True, "removable": True, "preview": True},
    "citation": {"kind": "citation", "label": "Citation", "max_chars": 300},
    "sources": {"kind": "sources", "label": "Sources", "reorderable": True, "max_items": 20},
}

TEMPLATE_COMPONENT_CONFIG: dict[str, tuple[str, ...]] = {
    "cover_headline": ("label", "headline", "deck", "citation"),
    "photo_headline": ("label", "photo", "headline", "deck", "citation"),
    "quote_lead": ("label", "headline", "body", "citation"),
    "stat_callout": ("label", "headline", "body", "citation"),
    "stat_grid": ("label", "headline", "body", "citation"),
    "timeline": ("label", "headline", "body", "citation"),
    "call_block": ("label", "headline", "body", "citation"),
    "document_card": ("label", "headline", "body", "citation"),
    "body_standard": ("label", "headline", "body", "citation"),
    "sources_slide": ("label", "sources"),
}

EDITOR_CHARACTER_LIMITS: dict[str, dict[str, int]] = {
    "cover_headline": {"deck": 240, "citation": 300},
    "photo_headline": {"deck": 240, "citation": 300},
    "quote_lead": {"body": 560, "citation": 300},
    "stat_callout": {"body": 360, "citation": 300},
    "stat_grid": {"body": 520, "citation": 300},
    "timeline": {"body": 900, "citation": 300},
    "call_block": {"body": 520, "citation": 300},
    "document_card": {"body": 520, "citation": 300},
    "body_standard": {"body": 700, "citation": 300},
    "sources_slide": {},
}

'''
    if 'EDITOR_COMPONENT_CONTRACT' not in text:
        text=insert_before(text,'TEMPLATE_LABEL_OVERRIDES = {',component_contract,'editor component contract')

    # CSS
    css_anchor='.photo-upload-status.bad{color:#ff7898}'
    css_extra='''.component-shell{position:relative;margin-top:10px}.component-meta{display:flex;justify-content:space-between;gap:12px;align-items:center;margin:5px 0 7px;color:var(--muted);font-size:12px}.character-counter{font-variant-numeric:tabular-nums}.character-counter.over{color:#ff7898;font-weight:700}.component-label input{font-weight:700;letter-spacing:.02em}.component-citation input{font-size:13px}.component-body textarea{resize:none;overflow:hidden;min-height:110px}.photo-preview{display:block;width:100%;max-height:250px;object-fit:cover;border-radius:9px;margin:10px 0;border:1px solid #393939;background:#070707}.photo-actions{display:flex;gap:8px;flex-wrap:wrap}.drag-handle{cursor:grab;touch-action:none;user-select:none;min-width:34px}.drag-handle:active{cursor:grabbing}.editor-row-dragging{opacity:.45;outline:1px dashed var(--pink)}.editor-row-drop{box-shadow:0 -3px 0 var(--pink)}.source-count{font-size:12px;color:var(--muted)}'''
    if '.component-shell' not in text:
        if css_anchor not in text: raise PatchError('Phase 3 photo CSS anchor was not found.')
        text=text.replace(css_anchor,css_anchor+css_extra,1)

    # Photo preview/remove in existing widget
    old='''    <div class="photo-upload-row">\n      <button type="button" class="small secondary" data-choose-photo>Choose Photo</button>\n      <input type="file" data-photo-file accept=".png,.jpg,.jpeg,image/png,image/jpeg">\n    </div>\n    <div class="photo-upload-status ${filename?"good":""}" data-photo-status>${filename?`Uploaded: ${escapeHTML(filename)}`:"PNG, JPG, or JPEG. Recommended minimum 1080 × 1350px."}</div>\n'''
    new='''    ${filename?`<img class="photo-preview" data-photo-preview src="/photo-asset?name=${encodeURIComponent(filename)}" alt="Selected photo preview">`:""}\n    <div class="photo-actions">\n      <button type="button" class="small secondary" data-choose-photo>${filename?"Replace Photo":"Choose Photo"}</button>\n      ${filename?`<button type="button" class="small danger" data-remove-photo>Remove Photo</button>`:""}\n      <input type="file" data-photo-file accept=".png,.jpg,.jpeg,image/png,image/jpeg">\n    </div>\n    <div class="photo-upload-status ${filename?"good":""}" data-photo-status>${filename?`Uploaded: ${escapeHTML(filename)}`:"PNG, JPG, or JPEG. Recommended minimum 1080 × 1350px."}</div>\n'''
    if 'data-remove-photo' not in text:
        text=replace_once(text,old,new,'photo reusable controls')

    # GET endpoint for preview
    if 'self.path.startswith("/photo-asset?")' not in text:
        get_old='''    def do_GET(self) -> None:\n'''
        get_new='''    def do_GET(self) -> None:\n        if self.path.startswith("/photo-asset?"):\n            try:\n                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)\n                name = str((query.get("name") or [""])[0]).strip()\n                if not name:\n                    raise ValueError("Photo filename is required.")\n                path = safe_child(safe_child(STORIES_DIR, PREVIEW_FOLDER), name)\n                if not path.is_file():\n                    raise FileNotFoundError(name)\n                suffix = path.suffix.lower()\n                content_type = "image/png" if suffix == ".png" else "image/jpeg" if suffix in {".jpg", ".jpeg"} else None\n                if not content_type:\n                    raise ValueError("Unsupported photo format.")\n                content = path.read_bytes()\n            except (OSError, ValueError):\n                self.send_error(HTTPStatus.NOT_FOUND, "Photo asset not found")\n                return\n            self.send_response(HTTPStatus.OK)\n            self.send_header("Content-Type", content_type)\n            self.send_header("Content-Length", str(len(content)))\n            self.send_header("Cache-Control", "no-store")\n            self.end_headers()\n            self.wfile.write(content)\n            return\n\n'''
        text=replace_once(text,get_old,get_new,'photo preview endpoint')

    # JS framework
    js_marker='async function uploadPhoto(file,slide){'
    framework=r'''
const EDITOR_CHARACTER_LIMITS={
  cover_headline:{deck:240,citation:300},photo_headline:{deck:240,citation:300},
  quote_lead:{body:560,citation:300},stat_callout:{body:360,citation:300},
  stat_grid:{body:520,citation:300},timeline:{body:900,citation:300},
  call_block:{body:520,citation:300},document_card:{body:520,citation:300},
  body_standard:{body:700,citation:300},sources_slide:{}
};
function editorTemplateId(slide){return slide?.querySelector("[data-template]")?.value||slide?.querySelector('select[name$="[template]"]')?.value||""}
function editorFieldKey(control){return control?.dataset?.key||control?.getAttribute("data-key")||""}
function characterLimit(slide,key){return Number(EDITOR_CHARACTER_LIMITS?.[editorTemplateId(slide)]?.[key]||0)}
function autoGrowTextarea(textarea){if(!(textarea instanceof HTMLTextAreaElement))return;textarea.style.height="auto";textarea.style.height=`${Math.max(textarea.scrollHeight,110)}px`}
function ensureCounter(control,slide){const key=editorFieldKey(control),limit=characterLimit(slide,key);if(!limit)return;const shell=control.closest("div");if(!shell)return;shell.classList.add("component-shell");let meta=shell.querySelector(":scope > .component-meta");if(!meta){meta=document.createElement("div");meta.className="component-meta";shell.appendChild(meta)}let counter=meta.querySelector(".character-counter");if(!counter){counter=document.createElement("span");counter.className="character-counter";meta.appendChild(counter)}const count=String(control.value||"").length;counter.textContent=`${count} / ${limit}`;counter.classList.toggle("over",count>limit)}
function findReorderRow(control){return control.closest("[data-row]")||control.closest(".dynamic-row")||control.closest(".line-row")||control.parentElement}
function enhanceHeadlineRows(slide){[...slide.querySelectorAll('[data-part="text"]')].forEach(control=>{const row=findReorderRow(control);if(!row||row.dataset.editorEnhanced==="true")return;row.dataset.editorEnhanced="true";row.draggable=true;const handle=document.createElement("button");handle.type="button";handle.className="small secondary drag-handle";handle.dataset.dragHandle="true";handle.textContent="↕";row.insertBefore(handle,row.firstChild)})}
function enhanceEditorComponents(root=document){root.querySelectorAll("[data-slide]").forEach(slide=>{slide.querySelectorAll("textarea").forEach(t=>{t.closest("div")?.classList.add("component-body");autoGrowTextarea(t);ensureCounter(t,slide)});slide.querySelectorAll('input[data-key="label"]').forEach(i=>i.closest("div")?.classList.add("component-label"));slide.querySelectorAll('input[data-key="citation"]').forEach(i=>{i.closest("div")?.classList.add("component-citation");ensureCounter(i,slide)});enhanceHeadlineRows(slide);const rows=slide.querySelectorAll('[data-list="sources"] [data-row], [data-source-row]');if(rows.length){let c=slide.querySelector(".source-count");if(!c){c=document.createElement("div");c.className="source-count";rows[0].parentElement?.insertAdjacentElement("beforebegin",c)}if(c)c.textContent=`${rows.length} source${rows.length===1?"":"s"}`}})}
let draggedEditorRow=null;document.addEventListener("dragstart",e=>{const h=e.target.closest?.("[data-drag-handle]"),r=h?findReorderRow(h):null;if(!r)return;draggedEditorRow=r;r.classList.add("editor-row-dragging")});document.addEventListener("dragover",e=>{const r=e.target.closest?.('[data-editor-enhanced="true"]');if(!draggedEditorRow||!r||r===draggedEditorRow)return;e.preventDefault();r.classList.add("editor-row-drop")});document.addEventListener("drop",e=>{const r=e.target.closest?.('[data-editor-enhanced="true"]');if(!draggedEditorRow||!r||r===draggedEditorRow)return;e.preventDefault();const before=e.clientY<r.getBoundingClientRect().top+r.getBoundingClientRect().height/2;r.parentElement?.insertBefore(draggedEditorRow,before?r:r.nextSibling);r.classList.remove("editor-row-drop");const s=r.closest("[data-slide]");if(s){markDirty(s);syncEditorStateFromDOM();updateAllSummaries()}});document.addEventListener("dragend",()=>{document.querySelectorAll(".editor-row-drop").forEach(r=>r.classList.remove("editor-row-drop"));draggedEditorRow?.classList.remove("editor-row-dragging");draggedEditorRow=null});document.addEventListener("input",e=>{if(e.target instanceof HTMLTextAreaElement)autoGrowTextarea(e.target);const s=e.target.closest?.("[data-slide]");if(s)ensureCounter(e.target,s)});new MutationObserver(()=>enhanceEditorComponents()).observe(document.body,{childList:true,subtree:true});window.addEventListener("DOMContentLoaded",()=>enhanceEditorComponents());

'''
    if 'function enhanceEditorComponents' not in text:
        text=insert_before(text,js_marker,framework,'editor JS framework')

    click='''  if(button.matches("[data-choose-photo]")){\n    const input=slide?.querySelector("[data-photo-file]");\n    if(input)input.click();\n    return;\n  }\n'''
    click2=click+'''\n  if(button.matches("[data-remove-photo]")){\n    const nameInput=slide?.querySelector("[data-photo-name]");\n    const status=slide?.querySelector("[data-photo-status]");\n    slide?.querySelector("[data-photo-preview]")?.remove();\n    if(nameInput)nameInput.value="";\n    button.remove();\n    const choose=slide?.querySelector("[data-choose-photo]");\n    if(choose)choose.textContent="Choose Photo";\n    if(status){status.className="photo-upload-status";status.textContent="No photo selected. PNG, JPG, or JPEG required."}\n    if(slide){markDirty(slide);syncEditorStateFromDOM();updateAllSummaries()}\n    return;\n  }\n'''
    if 'button.matches("[data-remove-photo]")' not in text:
        text=replace_once(text,click,click2,'photo remove action')

    upload='''    nameInput.value=result.filename;\n    const warnings=Array.isArray(result.warnings)?result.warnings:[];\n'''
    upload2='''    nameInput.value=result.filename;\n    let preview=slide.querySelector("[data-photo-preview]");\n    if(!preview){preview=document.createElement("img");preview.className="photo-preview";preview.dataset.photoPreview="true";preview.alt="Selected photo preview";nameInput.closest(".photo-upload")?.insertBefore(preview,nameInput.nextSibling)}\n    preview.src=`/photo-asset?name=${encodeURIComponent(result.filename)}&v=${Date.now()}`;\n    const choose=slide.querySelector("[data-choose-photo]");if(choose)choose.textContent="Replace Photo";\n    if(!slide.querySelector("[data-remove-photo]")){const remove=document.createElement("button");remove.type="button";remove.className="small danger";remove.dataset.removePhoto="true";remove.textContent="Remove Photo";slide.querySelector(".photo-actions")?.insertBefore(remove,slide.querySelector("[data-photo-file]"))}\n    const warnings=Array.isArray(result.warnings)?result.warnings:[];\n'''
    if 'preview.src=`/photo-asset?name=' not in text:
        text=replace_once(text,upload,upload2,'photo preview refresh')

    dashboard.write_text(text,encoding='utf-8')
    (repo/'studio_3_9_editor_component_contract.json').write_text(json.dumps({
      'version':'3.9.0','phase':4,
      'components':{'headline':['multi-line','color picker','drag reorder','add/remove'],'body':['auto-grow','counter','template-aware limits'],'photo':['upload','replace','remove','preview','validation'],'citation':['reusable'],'label':['reusable'],'sources':['repeatable','count','reorder foundation']}
    },indent=2)+'\n',encoding='utf-8')
    test=repo/'test_studio_3_9_phase4.py'
    test.write_text('''from pathlib import Path\nimport carousel_dashboard as studio\nassert studio.EDITOR_COMPONENT_CONTRACT["headline"]["reorderable"] is True\nassert studio.EDITOR_COMPONENT_CONTRACT["body"]["auto_grow"] is True\nassert studio.EDITOR_COMPONENT_CONTRACT["photo"]["removable"] is True\nassert studio.TEMPLATE_COMPONENT_CONFIG["cover_headline"] == ("label","headline","deck","citation")\ns=Path("carousel_dashboard.py").read_text()\nfor x in ("enhanceEditorComponents","data-remove-photo","photo-asset?name=","draggedEditorRow"): assert x in s,x\nprint("PHASE 4 EDITOR FRAMEWORK TESTS: PASS")\n''',encoding='utf-8')
    py_compile.compile(str(dashboard),doraise=True); py_compile.compile(str(test),doraise=True)
    result=run([sys.executable,test.name],repo)
    print('Studio 3.9 Phase 4 applied.')
    print('✓ Reusable component contract created')
    print('✓ Headline multi-line/color/reorder framework added')
    print('✓ Auto-growing body fields and counters added')
    print('✓ Template-aware character limits added')
    print('✓ Photo upload/replace/remove/preview component completed')
    print('✓ Label and citation components standardized')
    print('✓ Sources count/reorder foundation added')
    print(result.stdout.strip())
    print('\nRestart Studio:')
    print('fuser -k 8000/tcp 2>/dev/null || true')
    print('python carousel_dashboard.py > /tmp/jenniwren-studio.log 2>&1 &')
    print('sleep 2')
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except PatchError as e:
        print(f'\nPHASE 4 STOPPED SAFELY\n{e}',file=sys.stderr); raise SystemExit(1)
