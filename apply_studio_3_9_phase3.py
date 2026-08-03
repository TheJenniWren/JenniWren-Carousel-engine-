#!/usr/bin/env python3
from __future__ import annotations

import py_compile
import shutil
import subprocess
import sys
from pathlib import Path


class PatchError(RuntimeError):
    pass


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        detail = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        raise PatchError(
            f"Command failed: {' '.join(command)}" + (f"\n{detail}" if detail else "")
        )
    return result


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one target, found {count}.")
    return text.replace(old, new, 1)


def insert_before(text: str, marker: str, insertion: str, label: str) -> str:
    if marker not in text:
        raise PatchError(f"{label}: marker not found.")
    return text.replace(marker, insertion + marker, 1)


def main() -> int:
    repo = Path.cwd().resolve()
    dashboard = repo / "carousel_dashboard.py"
    if not dashboard.is_file():
        raise PatchError("Run this script from the repository root.")

    branch = run(["git", "branch", "--show-current"], repo).stdout.strip()
    if branch != "studio-3.9-dev":
        raise PatchError(
            f"Phase 3 must run on 'studio-3.9-dev'; current branch is {branch!r}."
        )

    text = dashboard.read_text(encoding="utf-8")
    backup = repo / "carousel_dashboard.py.before_studio_3_9_phase3"
    if not backup.exists():
        shutil.copy2(dashboard, backup)

    constants_marker = 'PREVIEW_STORY = "studio-live-preview"\n'
    constants_insert = '''
PHOTO_UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PHOTO_UPLOAD_CONTENT_TYPES = {"image/png", "image/jpeg"}
PHOTO_UPLOAD_MAX_BYTES = 25 * 1024 * 1024
PHOTO_MIN_WIDTH = 1080
PHOTO_MIN_HEIGHT = 1350
'''
    if "PHOTO_UPLOAD_EXTENSIONS" not in text:
        text = insert_before(
            text,
            constants_marker + "\n",
            constants_insert + "\n",
            "photo upload constants",
        )

    old_photo_field = '{"name": "image", "label": "Image filename", "type": "text"},'
    new_photo_field = '{"name": "image", "label": "Photo", "type": "photo"},'
    if old_photo_field in text:
        text = replace_once(text, old_photo_field, new_photo_field, "Photo Story field")
    elif '"type": "photo"' not in text:
        raise PatchError("Photo Story image field was not found.")

    helper_marker = "def load_story(folder_slug: str) -> dict[str, Any]:"
    helper_code = r'''
def sanitize_photo_filename(filename: str) -> str:
    raw = Path(str(filename or "")).name
    suffix = Path(raw).suffix.lower()
    if suffix not in PHOTO_UPLOAD_EXTENSIONS:
        raise ValueError("Choose a PNG, JPG, or JPEG image.")
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", Path(raw).stem).strip("-").lower()
    if not stem:
        stem = "photo"
    return f"{stem}{suffix}"


def unique_photo_path(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    clean = sanitize_photo_filename(filename)
    candidate = safe_child(directory, clean)
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    number = 2
    while True:
        candidate = safe_child(directory, f"{stem}-{number:02d}{suffix}")
        if not candidate.exists():
            return candidate
        number += 1


def inspect_photo_upload(*, filename: str, content_type: str, content: bytes) -> tuple[str, int, int, list[str]]:
    clean = sanitize_photo_filename(filename)
    normalized_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type not in PHOTO_UPLOAD_CONTENT_TYPES:
        raise ValueError("Choose a PNG, JPG, or JPEG image.")
    if not content:
        raise ValueError("The selected photo is empty.")
    if len(content) > PHOTO_UPLOAD_MAX_BYTES:
        raise ValueError("The selected photo exceeds the 25 MB upload limit.")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            width, height = image.size
            detected = str(image.format or "").upper()
    except Exception as exc:
        raise ValueError("The selected file is not a readable PNG or JPEG image.") from exc

    expected = "PNG" if Path(clean).suffix == ".png" else "JPEG"
    if detected != expected:
        raise ValueError(
            f"The filename extension does not match the image data. Expected {expected}; detected {detected or 'unknown'}."
        )

    warnings: list[str] = []
    if width < PHOTO_MIN_WIDTH or height < PHOTO_MIN_HEIGHT:
        warnings.append(
            f"Image is {width} × {height}px. Recommended minimum: {PHOTO_MIN_WIDTH} × {PHOTO_MIN_HEIGHT}px."
        )
    if width > height:
        warnings.append("Landscape image accepted. Photo Story will crop it to the cover frame.")
    return clean, width, height, warnings


def photo_image_names(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    slides = payload.get("slides")
    if not isinstance(slides, list):
        return []
    names: list[str] = []
    for slide in slides:
        if not isinstance(slide, dict) or str(slide.get("template") or "") != "photo_headline":
            continue
        name = str(slide.get("image") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def copy_photo_assets(payload: Any, *, source_dir: Path, target_dir: Path, require_all: bool = True) -> list[str]:
    copied: list[str] = []
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in photo_image_names(payload):
        try:
            source = safe_child(source_dir, name)
            target = safe_child(target_dir, name)
        except ValueError as exc:
            raise ValueError(f'Unsafe photo filename "{name}".') from exc
        if not source.is_file():
            if require_all:
                raise ValueError(f'image file "{name}" was not found.')
            continue
        if source.resolve() != target.resolve():
            if not target.exists() or source.read_bytes() != target.read_bytes():
                shutil.copy2(source, target)
        copied.append(name)
    return copied


'''
    if "def sanitize_photo_filename" not in text:
        text = insert_before(text, helper_marker, helper_code, "photo helpers")

    load_start = text.find("def load_story(")
    load_end = text.find("\n\ndef ", load_start + 1)
    if load_start < 0 or load_end < 0:
        raise PatchError("load_story function was not found.")
    load_block = text[load_start:load_end]
    old_load_return = "    return data if isinstance(data, dict) else {}\n"
    new_load_return = '''    if not isinstance(data, dict):
        return {}
    try:
        copy_photo_assets(
            data,
            source_dir=path.parent,
            target_dir=safe_child(STORIES_DIR, PREVIEW_FOLDER),
            require_all=False,
        )
    except (OSError, ValueError):
        pass
    return data
'''
    if old_load_return in load_block:
        load_block = load_block.replace(old_load_return, new_load_return, 1)
        text = text[:load_start] + load_block + text[load_end:]
    elif "copy_photo_assets(" not in load_block:
        raise PatchError("load_story return block was not found.")

    css_anchor = ".field-error{border-color:#ff567f!important;box-shadow:0 0 0 1px #ff567f}"
    if ".photo-upload-status" not in text:
        css_extra = (
            css_anchor
            + ".photo-upload{margin-top:8px;padding:10px;border:1px solid #3d3d3d;border-radius:10px;background:#101010}"
            + ".photo-upload-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}"
            + ".photo-upload input[type=file]{display:none}"
            + ".photo-upload-status{margin-top:8px;color:var(--muted);font-size:13px;white-space:pre-wrap}"
            + ".photo-upload-status.good{color:#7ee2a8}.photo-upload-status.warn{color:#ffd27a}.photo-upload-status.bad{color:#ff7898}"
        )
        text = replace_once(text, css_anchor, css_extra, "photo upload CSS")

    old_text_branch = 'if(type==="text")return `<label>${label}</label><input data-key="${key}" value="${escapeHTML(String(value||""))}">`;'
    photo_branch = r'''if(type==="photo"){
  const filename=String(value||"");
  return `<div class="photo-upload">
    <label>${label}</label>
    <input data-key="${key}" data-photo-name value="${escapeHTML(filename)}" placeholder="No photo uploaded">
    <div class="photo-upload-row">
      <button type="button" class="small secondary" data-choose-photo>Choose Photo</button>
      <input type="file" data-photo-file accept=".png,.jpg,.jpeg,image/png,image/jpeg">
    </div>
    <div class="photo-upload-status ${filename?"good":""}" data-photo-status>${filename?`Uploaded: ${escapeHTML(filename)}`:"PNG, JPG, or JPEG. Recommended minimum 1080 × 1350px."}</div>
  </div>`;
}'''
    if 'if(type==="photo")' not in text:
        if old_text_branch not in text:
            raise PatchError("fieldHTML text branch was not found.")
        text = text.replace(old_text_branch, photo_branch + old_text_branch, 1)

    upload_js = r'''
async function uploadPhoto(file,slide){
  const status=slide.querySelector("[data-photo-status]");
  const nameInput=slide.querySelector("[data-photo-name]");
  if(!file||!status||!nameInput)return;
  status.className="photo-upload-status";
  status.textContent=`Uploading ${file.name}…`;
  try{
    const response=await fetch("/upload-photo",{
      method:"POST",
      headers:{"Content-Type":file.type||"application/octet-stream","X-Filename":encodeURIComponent(file.name)},
      body:file
    });
    const result=await response.json();
    if(!response.ok||!result.ok)throw new Error(result.error||"Photo upload failed.");
    nameInput.value=result.filename;
    const warnings=Array.isArray(result.warnings)?result.warnings:[];
    status.className=`photo-upload-status ${warnings.length?"warn":"good"}`;
    status.textContent=`Uploaded: ${result.filename}\n${result.width} × ${result.height}px${warnings.length?`\n${warnings.join("\n")}`:""}`;
    markDirty(slide);
    syncEditorStateFromDOM();
    updateAllSummaries();
    await selectSlide([...slidesRoot.querySelectorAll("[data-slide]")].indexOf(slide),{render:true});
  }catch(error){
    status.className="photo-upload-status bad";
    status.textContent=`Upload failed: ${error.message}`;
  }
}

'''
    if "async function uploadPhoto(" not in text:
        text = insert_before(text, "function renderDynamic(slide,data={}){", upload_js, "upload JS")

    click_anchor = '''  const slide=button.closest("[data-slide]");

  if(button.matches("[data-add-row]")){
'''
    click_replacement = '''  const slide=button.closest("[data-slide]");

  if(button.matches("[data-choose-photo]")){
    const input=slide?.querySelector("[data-photo-file]");
    if(input)input.click();
    return;
  }

  if(button.matches("[data-add-row]")){
'''
    if 'button.matches("[data-choose-photo]")' not in text:
        text = replace_once(text, click_anchor, click_replacement, "Choose Photo click")

    change_anchor = '''slidesRoot.addEventListener("change",event=>{
  if(event.target.matches("[data-part=\\"color\\"]")){
'''
    change_replacement = '''slidesRoot.addEventListener("change",event=>{
  if(event.target.matches("[data-photo-file]")){
    const slide=event.target.closest("[data-slide]");
    const file=event.target.files&&event.target.files[0];
    if(slide&&file)uploadPhoto(file,slide);
    event.target.value="";
    return;
  }
  if(event.target.matches("[data-part=\\"color\\"]")){
'''
    if 'event.target.matches("[data-photo-file]")' not in text:
        text = replace_once(text, change_anchor, change_replacement, "photo change handler")

    post_anchor = '''    def do_POST(self) -> None:
        if self.path == "/template-engine-test":
'''
    upload_endpoint = r'''    def do_POST(self) -> None:
        if self.path == "/upload-photo":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    raise ValueError("The selected photo is empty.")
                if length > PHOTO_UPLOAD_MAX_BYTES:
                    raise ValueError("The selected photo exceeds the 25 MB upload limit.")
                raw_name = urllib.parse.unquote(str(self.headers.get("X-Filename") or ""))
                content_type = str(self.headers.get("Content-Type") or "")
                content = self.rfile.read(length)
                clean, width, height, warnings = inspect_photo_upload(
                    filename=raw_name,
                    content_type=content_type,
                    content=content,
                )
                preview_dir = safe_child(STORIES_DIR, PREVIEW_FOLDER)
                destination = unique_photo_path(preview_dir, clean)
                destination.write_bytes(content)
            except (OSError, ValueError) as exc:
                self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json({
                "ok": True,
                "filename": destination.name,
                "width": width,
                "height": height,
                "warnings": warnings,
                "message": f"Uploaded: {destination.name}",
            })
            return

        if self.path == "/template-engine-test":
'''
    if 'self.path == "/upload-photo"' not in text:
        text = replace_once(text, post_anchor, upload_endpoint, "upload endpoint")

    autosave_anchor = '''            story_dir = safe_child(STORIES_DIR, folder_slug)
            story_dir.mkdir(parents=True, exist_ok=True)
            (story_dir / "carousel.draft.json").write_text(
'''
    autosave_replacement = '''            story_dir = safe_child(STORIES_DIR, folder_slug)
            story_dir.mkdir(parents=True, exist_ok=True)
            copy_photo_assets(
                payload,
                source_dir=safe_child(STORIES_DIR, PREVIEW_FOLDER),
                target_dir=story_dir,
                require_all=True,
            )
            (story_dir / "carousel.draft.json").write_text(
'''
    autosave_slice = text[text.find('if self.path == "/autosave"'):text.find('if self.path not in {"/save", "/render"}')]
    if "copy_photo_assets(" not in autosave_slice:
        text = replace_once(text, autosave_anchor, autosave_replacement, "autosave persistence")

    save_anchor = '''        story_dir = safe_child(STORIES_DIR, folder_slug); story_dir.mkdir(parents=True, exist_ok=True)
        (story_dir / "carousel.json").write_text'''
    save_replacement = '''        story_dir = safe_child(STORIES_DIR, folder_slug); story_dir.mkdir(parents=True, exist_ok=True)
        try:
            copy_photo_assets(
                payload,
                source_dir=safe_child(STORIES_DIR, PREVIEW_FOLDER),
                target_dir=story_dir,
                require_all=True,
            )
        except ValueError as exc:
            self.send_html(
                build_page(
                    folder_slug=folder_slug,
                    data=payload,
                    message=f"Validation failed: {exc}",
                ),
                HTTPStatus.BAD_REQUEST,
            )
            return
        (story_dir / "carousel.json").write_text'''
    save_section = text[text.find('if self.path not in {"/save", "/render"}'):]
    if "copy_photo_assets(" not in save_section:
        text = replace_once(text, save_anchor, save_replacement, "save persistence")

    dashboard.write_text(text, encoding="utf-8")

    test_path = repo / "test_studio_3_9_phase3.py"
    test_path.write_text(r'''#!/usr/bin/env python3
from __future__ import annotations

import io
import tempfile
from pathlib import Path
from PIL import Image
import carousel_dashboard as studio


def image_bytes(size=(1600, 1200), fmt="JPEG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, (40, 40, 40)).save(buffer, format=fmt)
    return buffer.getvalue()


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    preview = root / "preview"
    story = root / "story"
    preview.mkdir()
    content = image_bytes()
    clean, width, height, warnings = studio.inspect_photo_upload(
        filename="National Guard Housing.JPG",
        content_type="image/jpeg",
        content=content,
    )
    assert clean == "national-guard-housing.jpg"
    assert (width, height) == (1600, 1200)
    assert any("Landscape image accepted" in item for item in warnings)
    assert any("Recommended minimum" in item for item in warnings)
    first = studio.unique_photo_path(preview, clean)
    first.write_bytes(content)
    second = studio.unique_photo_path(preview, clean)
    assert second.name == "national-guard-housing-02.jpg"
    payload = {
        "story": "Photo Test",
        "source": "Internal",
        "slides": [{
            "template": "photo_headline",
            "image": first.name,
            "headline": [{"text": "PHOTO", "color": "white"}],
        }],
    }
    copied = studio.copy_photo_assets(
        payload,
        source_dir=preview,
        target_dir=story,
        require_all=True,
    )
    assert copied == [first.name]
    assert (story / first.name).read_bytes() == content
    try:
        studio.inspect_photo_upload(
            filename="bad.gif",
            content_type="image/gif",
            content=b"not-an-image",
        )
    except ValueError as exc:
        assert "PNG, JPG, or JPEG" in str(exc)
    else:
        raise AssertionError("GIF should have been rejected.")

print("PHASE 3 PHOTO UPLOAD TESTS: PASS")
''', encoding="utf-8")

    py_compile.compile(str(dashboard), doraise=True)
    py_compile.compile(str(test_path), doraise=True)
    result = run([sys.executable, test_path.name], repo)

    print("Studio 3.9 Phase 3 applied.")
    print("✓ Choose Photo control added")
    print("✓ PNG/JPG/JPEG validation added")
    print("✓ Filenames sanitized and collision-safe")
    print("✓ Filename writes into slide JSON")
    print("✓ Dimension and crop warnings added")
    print("✓ Assets persist through autosave, save, reload, and render")
    print("✓ Missing files produce clear validation errors")
    print(result.stdout.strip())
    print("\nRestart Studio:")
    print("fuser -k 8000/tcp 2>/dev/null || true")
    print("python carousel_dashboard.py > /tmp/jenniwren-studio.log 2>&1 &")
    print("sleep 2")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"\nPHASE 3 STOPPED SAFELY\n{exc}", file=sys.stderr)
        raise SystemExit(1)
