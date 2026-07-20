#!/usr/bin/env python3
"""Repository-native launcher for the JenniWren Carousel Engine."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from exporter import ExportError, export_image
from production_config import ProductionConfig
from story_loader import StoryLoaderError, load_story
from templates import TemplateError, render_slide

LOGGER = logging.getLogger("jenniwren.launcher")


def _safe_slug(value: str) -> str:
    cleaned = []
    previous_dash = False
    for char in value.strip().lower():
        if char.isalnum():
            cleaned.append(char)
            previous_dash = False
        elif not previous_dash:
            cleaned.append("-")
            previous_dash = True
    return "".join(cleaned).strip("-") or "carousel"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render_carousel.py",
        description="Render a JenniWren carousel story directory to image files.",
    )
    parser.add_argument("story_dir", type=Path, help="Directory containing carousel.json.")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output directory. Default: output/<story-name-slug>.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Stop immediately when a slide returns QA notes.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress informational logging; errors are still shown.",
    )
    return parser


def _configure_logging(quiet: bool) -> None:
    logging.basicConfig(
        level=logging.WARNING if quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def render_carousel(
    story_dir: Path,
    output_dir: Path | None = None,
    *,
    strict: bool = False,
) -> int:
    story_dir = story_dir.expanduser().resolve()

    if not story_dir.exists():
        LOGGER.error("Story directory does not exist: %s", story_dir)
        return 1
    if not story_dir.is_dir():
        LOGGER.error("Story path is not a directory: %s", story_dir)
        return 1
    if not (story_dir / "carousel.json").exists():
        LOGGER.error("Missing required file: %s", story_dir / "carousel.json")
        return 1

    try:
        story = load_story(story_dir)
    except (StoryLoaderError, OSError, ValueError) as exc:
        LOGGER.error("Could not load story: %s", exc)
        return 1

    config = ProductionConfig()
    total = len(story.slides)
    if total == 0:
        LOGGER.error("Story contains no slides.")
        return 1

    if output_dir is None:
        repo_root = Path(__file__).resolve().parent
        output_dir = repo_root / "output" / _safe_slug(story.name)
    else:
        output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Story: %s", story.name)
    LOGGER.info("Slides: %d", total)
    LOGGER.info("Output: %s", output_dir)

    failures: list[str] = []
    qa_count = 0

    for slide in story.slides:
        template_id = slide.template
        slide_number = slide.index
        output_stem = output_dir / f"slide{slide_number:02d}"

        LOGGER.info(
            "Rendering slide %02d/%02d [%s]",
            slide_number, total, template_id,
        )

        try:
            image, qa_notes = render_slide(
                slide=slide,
                total=total,
                story=story,
                config=config,
            )

            notes = list(qa_notes or [])
            if notes:
                qa_count += 1
                for note in notes:
                    LOGGER.warning(
                        "Slide %02d [%s] QA: %s",
                        slide_number, template_id, note,
                    )
                if strict:
                    failures.append(
                        f"slide {slide_number:02d} [{template_id}] stopped by strict QA"
                    )
                    break

            exported_path = export_image(image, output_stem, config)
            LOGGER.info("Saved %s", exported_path)

        except (TemplateError, ExportError, OSError, ValueError, KeyError) as exc:
            message = f"slide {slide_number:02d} [{template_id}]: {exc}"
            failures.append(message)
            LOGGER.error("Failed %s", message)
        except Exception as exc:
            message = (
                f"slide {slide_number:02d} [{template_id}]: "
                f"{type(exc).__name__}: {exc}"
            )
            failures.append(message)
            LOGGER.exception("Unexpected failure on %s", message)

    print()
    print("JenniWren carousel build")
    print(f"Story:  {story.name}")
    print(f"Slides: {total}")
    print(f"Output: {output_dir}")
    print(f"QA:     {qa_count} slide(s) returned notes" if qa_count else "QA:     no renderer notes")

    if failures:
        print(f"Result:  FAILED ({len(failures)} issue(s))")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("Result:  SUCCESS")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.quiet)
    return render_carousel(args.story_dir, args.output, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
