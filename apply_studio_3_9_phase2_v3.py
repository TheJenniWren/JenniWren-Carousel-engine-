#!/usr/bin/env python3
from __future__ import annotations

import json
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one target, found {count}.")
    return text.replace(old, new, 1)


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        detail = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        raise PatchError(
            f"Command failed: {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def main() -> int:
    repo = Path.cwd().resolve()
    dashboard = repo / "carousel_dashboard.py"
    if not dashboard.is_file():
        raise PatchError("Run this script from the JenniWren Studio repository root.")

    branch = run(["git", "branch", "--show-current"], repo).stdout.strip()
    if branch != "studio-3.9-dev":
        raise PatchError(
            f"Phase 2 must run on 'studio-3.9-dev'; current branch is {branch!r}."
        )

    original = dashboard.read_text(encoding="utf-8")
    backup = repo / "carousel_dashboard.py.before_studio_3_9_phase2"
    if not backup.exists():
        shutil.copy2(dashboard, backup)

    old_ids = '''SUPPORTED_TEMPLATE_IDS = (
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
'''
    new_ids = '''# Studio 3.9 authoritative production template contract.
#
# Registry confirmation:
#   Cover — Headline uses "cover_headline".
#   "headline" is not a production ID and is rejected as an unsupported alias.
TEMPLATE_ID_CONTRACT: dict[str, dict[str, Any]] = {
    "cover_headline": {"label": "Cover — Headline", "required_editorial": ("headline",)},
    "quote_lead": {"label": "Cover — Quote Lead", "required_editorial": ("quote", "attribution")},
    "photo_headline": {"label": "Cover — Photo Story", "required_editorial": ("image", "headline")},
    "stat_callout": {"label": "Data — Big Number", "required_editorial": ("statistic", "statistic_label")},
    "stat_grid": {"label": "Data — Stat Grid", "required_editorial": ("statistics",)},
    "timeline": {"label": "Explainer — Timeline", "required_editorial": ("headline", "events")},
    "call_block": {"label": "Comparison — Call Block", "required_editorial": ("statement",)},
    "document_card": {"label": "Evidence — Document Card", "required_editorial": ("headline", "excerpt")},
    "body_standard": {"label": "Interior — Standard Explainer", "required_editorial": ("headline", "body")},
    "sources_slide": {"label": "Final — Sources", "required_editorial": ("sources",)},
}

SUPPORTED_TEMPLATE_IDS = tuple(TEMPLATE_ID_CONTRACT)

UNSUPPORTED_TEMPLATE_ALIASES: dict[str, str] = {
    "headline": "cover_headline",
    "cover_headline_story": "cover_headline",
    "cover_photo_story": "photo_headline",
    "photo_story": "photo_headline",
    "big_number": "stat_callout",
    "comparison": "call_block",
    "standard_explainer": "body_standard",
    "sources": "sources_slide",
}
'''
    text = replace_once(original, old_ids, new_ids, "authoritative template IDs")

    old_labels = '''TEMPLATE_LABEL_OVERRIDES = {
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
'''
    new_labels = '''TEMPLATE_LABEL_OVERRIDES = {
    template_id: definition["label"]
    for template_id, definition in TEMPLATE_ID_CONTRACT.items()
}
'''
    text = replace_once(text, old_labels, new_labels, "template labels")

    marker = "def adapt_payload_to_renderer(payload: dict[str, Any]) -> dict[str, Any]:"
    if marker not in text:
        raise PatchError("Strict validation insertion marker was not found.")

    validation_code = r'''
def _strict_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _strict_headline_errors(value: Any, *, slide_number: int, field_name: str) -> list[str]:
    prefix = f"Slide {slide_number}: {field_name}"
    if value is None:
        return []
    if isinstance(value, str):
        return [] if value.strip() else [f"{prefix} must not be empty."]
    if not isinstance(value, list):
        return [
            f'{prefix} must be a string or an array of '
            '{"text": "...", "color": "white|pink"} objects.'
        ]
    if not value:
        return [f"{prefix} must not be empty."]

    errors: list[str] = []
    for line_index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            errors.append(
                f'{prefix} line {line_index} must be an object with "text" '
                'and optional "color".'
            )
            continue
        unknown = sorted(set(item) - {"text", "color"})
        if unknown:
            errors.append(
                f"{prefix} line {line_index} has unsupported key(s): "
                + ", ".join(unknown)
                + '. Expected only "text" and optional "color".'
            )
        if not str(item.get("text") or "").strip():
            errors.append(f'{prefix} line {line_index} is missing "text".')
        color = str(item.get("color") or "white").strip().lower()
        if color not in {"white", "pink"}:
            errors.append(
                f'{prefix} line {line_index} has invalid color "{color}". '
                'Expected "white" or "pink".'
            )
    return errors


def strict_validate_editorial_payload(
    payload: Any,
    *,
    asset_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["The imported package must be one JSON object."]

    if not str(payload.get("story") or payload.get("title") or "").strip():
        errors.append("Story title is required.")
    if not str(payload.get("source") or "").strip():
        errors.append("Primary source is required.")

    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("At least one slide is required.")
        return errors

    fallback_fields = {
        "headline": ("headline_lines",),
        "quote": ("quote_lines",),
        "image": (),
        "statistic": ("stat_text",),
        "statistic_label": ("stat_label",),
        "statistics": ("stat_items",),
        "events": ("timeline_entries",),
        "statement": ("call_text",),
        "excerpt": ("doc_lines",),
        "body": (),
        "sources": ("citations",),
        "attribution": (),
    }

    for zero_index, slide in enumerate(slides):
        slide_number = zero_index + 1
        if not isinstance(slide, dict):
            errors.append(f"Slide {slide_number}: slide data must be a JSON object.")
            continue

        template = str(slide.get("template") or "").strip()
        if not template:
            errors.append(f'Slide {slide_number}: missing required field "template".')
            continue

        if template not in TEMPLATE_ID_CONTRACT:
            expected = UNSUPPORTED_TEMPLATE_ALIASES.get(template)
            if expected:
                errors.append(
                    f'Slide {slide_number}: unsupported template ID "{template}". '
                    f'Expected: "{expected}".'
                )
            else:
                expected_ids = ", ".join(f'"{item}"' for item in SUPPORTED_TEMPLATE_IDS)
                errors.append(
                    f'Slide {slide_number}: unsupported template ID "{template}". '
                    f"Expected one of: {expected_ids}."
                )
            continue

        for field in TEMPLATE_ID_CONTRACT[template]["required_editorial"]:
            value = slide.get(field)
            if not _strict_nonempty(value):
                for fallback in fallback_fields.get(field, ()):
                    if _strict_nonempty(slide.get(fallback)):
                        value = slide.get(fallback)
                        break
            if not _strict_nonempty(value):
                errors.append(
                    f'Slide {slide_number}: missing required field "{field}".'
                )

        headline_field = None
        if template in {
            "cover_headline", "photo_headline", "stat_grid",
            "timeline", "body_standard", "document_card", "call_block",
        }:
            headline_field = "headline"
        elif template == "stat_callout":
            headline_field = "context"

        if headline_field and headline_field in slide:
            errors.extend(
                _strict_headline_errors(
                    slide.get(headline_field),
                    slide_number=slide_number,
                    field_name=headline_field,
                )
            )

        if "headline_lines" in slide:
            lines = slide.get("headline_lines")
            if not isinstance(lines, list) or not lines or any(
                not str(line or "").strip() for line in lines
            ):
                errors.append(
                    f'Slide {slide_number}: "headline_lines" must be a '
                    "non-empty array of non-empty strings."
                )
            colors = slide.get("headline_colors")
            if colors is not None:
                if not isinstance(colors, list) or len(colors) != len(lines or []):
                    errors.append(
                        f'Slide {slide_number}: "headline_colors" must contain '
                        'one value for every "headline_lines" entry.'
                    )
                elif any(str(color).lower() not in {"white", "pink"} for color in colors):
                    errors.append(
                        f'Slide {slide_number}: "headline_colors" accepts only '
                        '"white" or "pink".'
                    )

        if template == "timeline":
            events = slide.get("events", slide.get("timeline_entries"))
            if isinstance(events, list):
                if not events:
                    errors.append(f'Slide {slide_number}: "events" must not be empty.')
                for event_index, event in enumerate(events, start=1):
                    if not isinstance(event, dict):
                        errors.append(
                            f"Slide {slide_number}: Timeline event {event_index} "
                            "must be a JSON object."
                        )
                        continue
                    unknown = sorted(set(event) - {"date", "text"})
                    if unknown:
                        wrong = unknown[0]
                        if wrong in {"body", "event", "description"}:
                            errors.append(
                                f'Slide {slide_number}: Timeline event {event_index} '
                                f'uses unsupported key "{wrong}". Expected: "text".'
                            )
                        else:
                            errors.append(
                                f"Slide {slide_number}: Timeline event {event_index} "
                                f"has unsupported key(s): {', '.join(unknown)}. "
                                'Expected only "date" and "text".'
                            )
                    if not str(event.get("date") or "").strip():
                        errors.append(
                            f'Slide {slide_number}: Timeline event {event_index} '
                            'is missing "date".'
                        )
                    if not str(event.get("text") or "").strip():
                        errors.append(
                            f'Slide {slide_number}: Timeline event {event_index} '
                            'is missing "text".'
                        )

        if template == "photo_headline":
            image_name = str(slide.get("image") or "").strip()
            if image_name and asset_dir is not None:
                try:
                    candidate = safe_child(asset_dir, image_name)
                except ValueError:
                    errors.append(
                        f'Slide {slide_number}: image file "{image_name}" '
                        "uses an unsafe path."
                    )
                else:
                    if not candidate.is_file():
                        errors.append(
                            f'Slide {slide_number}: image file "{image_name}" '
                            "was not found."
                        )

    return errors


'''
    text = text.replace(marker, validation_code + marker, 1)

    old_guard = '''    template = str(slide.get("template") or "")
    if template not in TEMPLATE_SCHEMA_REGISTRY:
        return dict(slide)
'''
    new_guard = '''    template = str(slide.get("template") or "").strip()
    if template not in TEMPLATE_ID_CONTRACT:
        expected = UNSUPPORTED_TEMPLATE_ALIASES.get(template)
        if expected:
            raise ValueError(
                f'Unsupported template ID "{template}". Expected: "{expected}".'
            )
        raise ValueError(f'Unsupported template ID "{template}".')
    if template not in TEMPLATE_SCHEMA_REGISTRY:
        raise ValueError(
            f'Template ID "{template}" is valid but its renderer schema '
            "was not discovered."
        )
'''
    text = replace_once(text, old_guard, new_guard, "adapter guard")

    old_editor_default = '    template = str(slide.get("template") or "body_standard")\n'
    new_editor_default = '''    template = str(slide.get("template") or "").strip()
    if template not in TEMPLATE_ID_CONTRACT:
        raise ValueError(f'Unsupported template ID "{template or "(missing)"}".')
'''
    text = replace_once(text, old_editor_default, new_editor_default, "editor guard")

    old_prepare = '''    production_payload = adapt_payload_to_renderer(payload)
    production_payload["story"] = (
'''
    new_prepare = '''    strict_errors = strict_validate_editorial_payload(
        payload,
        asset_dir=safe_child(STORIES_DIR, PREVIEW_FOLDER),
    )
    if strict_errors:
        raise ValueError(strict_errors[0])

    production_payload = adapt_payload_to_renderer(payload)
    production_payload["story"] = (
'''
    text = replace_once(text, old_prepare, new_prepare, "prepare validation")

    old_validate_route = '''                if not isinstance(payload, dict):
                    raise ValueError("Editor state is missing.")
                report = renderer_validation_report(payload, selected_index)
'''
    new_validate_route = '''                if not isinstance(payload, dict):
                    raise ValueError("Editor state is missing.")
                strict_errors = strict_validate_editorial_payload(
                    payload,
                    asset_dir=safe_child(STORIES_DIR, PREVIEW_FOLDER),
                )
                if strict_errors:
                    raise ValueError("\\n".join(strict_errors))
                report = renderer_validation_report(payload, selected_index)
'''
    text = replace_once(text, old_validate_route, new_validate_route, "validate endpoint")

    old_save = '''        # Single authoritative adapter used by save and export.
        payload = adapt_payload_to_renderer(payload)
        errors = validate_payload(payload)
'''
    new_save = '''        strict_errors = strict_validate_editorial_payload(
            payload,
            asset_dir=safe_child(STORIES_DIR, PREVIEW_FOLDER),
        )
        if strict_errors:
            self.send_html(
                build_page(
                    folder_slug=folder_slug,
                    data=payload if isinstance(payload, dict) else default_story(),
                    message="Validation failed:\\n" + "\\n".join(strict_errors),
                ),
                HTTPStatus.BAD_REQUEST,
            )
            return

        # Single authoritative adapter used by save and export.
        payload = adapt_payload_to_renderer(payload)
        errors = validate_payload(payload)
'''
    text = replace_once(text, old_save, new_save, "save/render validation")

    # Replace the current import listener by anchored boundaries instead of
    # depending on its exact formatting.
    listener_start_marker = 'document.getElementById("import-json-button")'
    listener_end_marker = 'document.getElementById("add-slide")'
    listener_start = text.find(listener_start_marker)
    listener_end = text.find(listener_end_marker, listener_start)
    if listener_start < 0 or listener_end < 0:
        raise PatchError(
            "browser import validation: could not locate the import/add-slide boundaries."
        )

    new_import = r'''document.getElementById("import-json-button").addEventListener("click",async()=>{
  const raw=document.getElementById("import-json").value.trim();
  if(!raw){showImportStatus("Paste a carousel JSON package first.","error");return}
  try{
    const data=JSON.parse(raw);
    const response=await fetch("/validate",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({payload:data,slide_index:0})
    });
    const result=await response.json();
    if(!response.ok||!result.ok){
      throw new Error(result.error||"Validation failed.");
    }
    populateFromData(data);
    rendererState=result.report.production_payload;
    latestValidationReport=normalizeValidationReport(result.report,0);
    const storyObj=(data.story&&typeof data.story==="object") ? data.story : {};
    const suggested=(
      data.folder_slug ||
      data.slug ||
      storyObj.folder_slug ||
      storyObj.title ||
      (typeof data.story==="string" ? data.story : "") ||
      "story"
    ).toString().toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
    if(suggested)document.getElementById("folder_slug").value=suggested;
    showImportStatus(`Imported ${data.slides.length} slides. Review or edit, then Render Full Carousel.`,"success");
    selectSlide(0,{render:false});
  }catch(error){
    showImportStatus(`Import rejected: ${error.message}`,"error");
  }
});
'''
    text = text[:listener_start] + new_import + text[listener_end:]


    text = text.replace("JenniWren Studio 3.8.0", "JenniWren Studio 3.9.0", 1)
    text = text.replace("JENNIWREN STUDIO 3.8.0", "JENNIWREN STUDIO 3.9.0")
    text = text.replace(
        'print(f"JenniWren Studio 3.8.0 running on port {PORT}")',
        'print(f"JenniWren Studio 3.9.0 running on port {PORT}")',
    )

    dashboard.write_text(text, encoding="utf-8")

    contract = {
        "version": "3.9.0",
        "cover_headline_registry_confirmation": "cover_headline",
        "production_template_ids": list([
            "cover_headline", "quote_lead", "photo_headline", "stat_callout",
            "stat_grid", "timeline", "call_block", "document_card",
            "body_standard", "sources_slide",
        ]),
        "policy": "Aliases are rejected with a canonical expected ID; they are never silently converted.",
    }
    (repo / "studio_3_9_template_contract.json").write_text(
        json.dumps(contract, indent=2) + "\n",
        encoding="utf-8",
    )

    test_file = repo / "test_studio_3_9_phase2.py"
    test_file.write_text(r'''#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

import carousel_dashboard as studio


def package(slides):
    return {
        "story": "Studio 3.9 Phase 2 Test",
        "source": "JenniWren Studio internal validation test",
        "slides": slides,
    }


def assert_contains(errors, expected):
    joined = "\n".join(errors)
    assert expected in joined, f"Expected {expected!r} in:\n{joined}"


with tempfile.TemporaryDirectory() as temp:
    assets = Path(temp)
    (assets / "photo.png").write_bytes(b"asset")

    assert "cover_headline" in studio.TEMPLATE_ID_CONTRACT
    assert "headline" not in studio.TEMPLATE_ID_CONTRACT

    errors = studio.strict_validate_editorial_payload(
        package([{"template": "headline", "headline": [{"text": "TEST", "color": "white"}]}]),
        asset_dir=assets,
    )
    assert_contains(errors, 'Slide 1: unsupported template ID "headline". Expected: "cover_headline".')

    errors = studio.strict_validate_editorial_payload(
        package([{
            "template": "cover_photo_story",
            "image": "photo.png",
            "headline": [{"text": "TEST", "color": "white"}],
        }]),
        asset_dir=assets,
    )
    assert_contains(errors, 'Slide 1: unsupported template ID "cover_photo_story". Expected: "photo_headline".')

    errors = studio.strict_validate_editorial_payload(
        package([{
            "template": "timeline",
            "headline": [{"text": "TIMELINE", "color": "white"}],
            "events": [{"date": "2026", "body": "Wrong key"}],
        }]),
        asset_dir=assets,
    )
    assert_contains(errors, 'Slide 1: Timeline event 1 uses unsupported key "body". Expected: "text".')
    assert_contains(errors, 'Slide 1: Timeline event 1 is missing "text".')

    errors = studio.strict_validate_editorial_payload(
        package([{
            "template": "photo_headline",
            "image": "missing.png",
            "headline": [{"text": "PHOTO", "color": "white"}],
        }]),
        asset_dir=assets,
    )
    assert_contains(errors, 'Slide 1: image file "missing.png" was not found.')

    valid = package([
        {
            "template": "cover_headline",
            "label": "TEST",
            "headline": [
                {"text": "VALID", "color": "white"},
                {"text": "PACKAGE", "color": "pink"},
            ],
            "deck": "A valid cover.",
        },
        {
            "template": "body_standard",
            "label": "DETAILS",
            "headline": [{"text": "DETAILS", "color": "white"}],
            "body": "Valid body copy.",
        },
        {
            "template": "timeline",
            "label": "TIMELINE",
            "headline": [{"text": "WHEN", "color": "white"}],
            "events": [{"date": "2026", "text": "Valid event."}],
        },
        {
            "template": "sources_slide",
            "label": "SOURCES",
            "sources": ["JenniWren Studio internal validation test"],
        },
    ])
    assert studio.strict_validate_editorial_payload(valid, asset_dir=assets) == []
    production = studio.adapt_payload_to_renderer(valid)
    assert len(production["slides"]) == 4
    assert production["slides"][0]["template"] == "cover_headline"
    assert production["slides"][2]["timeline_entries"][0]["text"] == "Valid event."

print("PHASE 2 VALIDATION TESTS: PASS")
''', encoding="utf-8")

    py_compile.compile(str(dashboard), doraise=True)
    py_compile.compile(str(test_file), doraise=True)
    result = run([sys.executable, test_file.name], repo)

    print("Studio 3.9 Phase 2 applied.")
    print('✓ Cover — Headline ID confirmed as "cover_headline"')
    print("✓ Authoritative 10-template map created")
    print("✓ Unsupported aliases rejected")
    print("✓ Required and empty fields validated")
    print("✓ Headline arrays validated")
    print("✓ Timeline event keys validated")
    print("✓ Missing Photo Story assets validated")
    print("✓ Browser import validates before population")
    print("✓ Valid four-slide package passed")
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
        print(f"\nPHASE 2 STOPPED SAFELY\n{exc}", file=sys.stderr)
        raise SystemExit(1)
