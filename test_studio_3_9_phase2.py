#!/usr/bin/env python3
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
