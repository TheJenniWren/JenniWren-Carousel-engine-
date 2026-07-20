"""
story_loader.py
JenniWren Carousel Production Pipeline

Loads a story package from disk:

    stories/<name>/
        carousel.json   -- required. Slide-by-slide production spec.
        article.md      -- optional. Source article / reference copy.
        sources.md       -- optional. Citation list backing the carousel.
        images/          -- optional. Referenced by slides that need art.

This module only reads and structures data. It does not render anything
and does not know about carousel_lib.py.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jenniwren.story_loader")


class StoryLoadError(Exception):
    """Raised when a story package can't be read or parsed at all."""


@dataclass
class StorySlide:
    """
    One slide's worth of production data, taken almost verbatim from
    carousel.json. `index` is 1-based position in the carousel and is
    assigned by the loader, not read from the file, so slide order is
    always the array order in carousel.json.
    """

    index: int
    template: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def slide_id(self) -> str:
        explicit = self.raw.get("id")
        if explicit:
            return str(explicit)
        return f"{self.index:02d}_{self.template}"

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)


@dataclass
class StoryPackage:
    name: str
    story_dir: Path
    brand_footer: str
    slides: List[StorySlide]
    article_text: Optional[str]
    sources_text: Optional[str]
    images_dir: Path

    def resolve_image(self, relative_path: str) -> Path:
        """
        Resolve an image path referenced in carousel.json relative to
        the story folder (not just images/), since slides may point at
        `images/foo.jpg` explicitly.
        """
        candidate = (self.story_dir / relative_path).resolve()
        return candidate


def _read_optional_text(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


def load_story(story_dir: Path) -> StoryPackage:
    """
    Load a story package from `story_dir`. Raises StoryLoadError for
    anything that prevents even attempting a build (missing folder,
    missing/unparseable carousel.json). Softer problems (missing
    article.md, missing images referenced by a slide, etc.) are left
    for the validator to report -- this function just loads what's
    there.
    """
    story_dir = Path(story_dir)

    if not story_dir.exists() or not story_dir.is_dir():
        raise StoryLoadError(f"Story folder not found: {story_dir}")

    carousel_json_path = story_dir / "carousel.json"
    if not carousel_json_path.exists():
        raise StoryLoadError(f"Missing carousel.json in {story_dir}")

    try:
        raw = json.loads(carousel_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StoryLoadError(f"carousel.json is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise StoryLoadError("carousel.json must contain a JSON object at the top level.")

    slides_raw = raw.get("slides")
    if not isinstance(slides_raw, list) or not slides_raw:
        raise StoryLoadError("carousel.json must contain a non-empty 'slides' array.")

    slides: List[StorySlide] = []
    for i, slide_raw in enumerate(slides_raw, start=1):
        if not isinstance(slide_raw, dict):
            raise StoryLoadError(f"Slide {i} in carousel.json is not an object.")
        template = slide_raw.get("template")
        if not template:
            raise StoryLoadError(f"Slide {i} in carousel.json is missing a 'template' field.")
        slides.append(StorySlide(index=i, template=str(template), raw=slide_raw))

    story_name = raw.get("story") or story_dir.name
    brand_footer = raw.get("brand_footer", "TheJenniWren")

    article_text = _read_optional_text(story_dir / "article.md")
    sources_text = _read_optional_text(story_dir / "sources.md")

    if article_text is None:
        logger.warning("No article.md found in %s -- proceeding without reference copy.", story_dir)
    if sources_text is None:
        logger.warning("No sources.md found in %s -- citation validation will be limited.", story_dir)

    return StoryPackage(
        name=str(story_name),
        story_dir=story_dir,
        brand_footer=str(brand_footer),
        slides=slides,
        article_text=article_text,
        sources_text=sources_text,
        images_dir=story_dir / "images",
    )
