#!/usr/bin/env python3
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
