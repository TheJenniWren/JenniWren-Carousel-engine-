#!/usr/bin/env python3
"""
build_carousel.py
JenniWren Carousel Production Pipeline -- Orchestration Layer

Single entry point for turning a story folder into a finished set of
carousel PNGs (or JPEGs):

    python build_carousel.py stories/hegseth/
    python build_carousel.py stories/hegseth/ --output out/ --export-format jpeg
    python build_carousel.py stories/hegseth/ --skip-qa --verbose

This module coordinates the pipeline stages (load, validate, resolve
template, render, QA, export, log/manifest) and draws nothing itself.
Architecture background -- why the pipeline targets carousel_lib.py,
its relationship to the unfinished registry/canvas system, and what to
watch out for in `cov templates.py` -- lives in ARCHITECTURE.md, not
here, so this file stays focused on executable pipeline code.

This orchestrator does not ship its own copy of the renderer
(carousel_lib.py, registry.py, qa.py, renderer.py) -- it imports the
single authoritative copy from the sibling `jenniwren_renderer`
package via renderer_imports.py. If that package can't be found, the
import block below fails gracefully with an actionable message instead
of a raw traceback -- see README.md "Project layout" for how to set it
up.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

try:
    from renderer_imports import carousel_lib as cl
    from exporter import ExportError, export_image
    from manifest import ProductionManifest, SlideResult
    from production_config import ProductionConfig
    from renderer_compat import check_renderer_compatibility
    from story_loader import StoryLoadError, load_story
    from templates import TemplateError, build_template_registry, render_slide
    from validator import Severity as VSeverity
    from validator import ValidationReport, validate_story
    from qa_gate import run_qa
except ImportError as exc:
    # renderer_imports.py is the single place that explains *why* the
    # renderer couldn't be found (RendererUnavailableError, a subclass
    # of ImportError, carries a fully actionable message). Any other
    # module above importing it transitively hits the same failure, so
    # this one broad except covers all of them. This is the pipeline's
    # "fail gracefully" path: a clean one-line report + exit code,
    # instead of a raw traceback several frames deep.
    print(f"ERROR: {exc}", file=sys.stderr)
    sys.exit(1)

logger = logging.getLogger("jenniwren")


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

def configure_logging(log_path: Path, verbose: bool) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(console_handler)


def _print_validation_report(report: ValidationReport) -> None:
    for issue in report.issues:
        line = f"[{issue.severity.value}] {issue.slide_id} ({issue.rule}): {issue.message}"
        if issue.severity == VSeverity.ERROR:
            logger.error(line)
        elif issue.severity == VSeverity.WARNING:
            logger.warning(line)
        else:
            logger.info(line)


# ---------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------

def run_pipeline(config: ProductionConfig) -> ProductionManifest:
    compat = check_renderer_compatibility(cl)
    if not compat.compatible and not config.skip_compat_check:
        logger.error(compat.describe())
        raise RuntimeError(
            "carousel_lib.py failed the orchestrator's API compatibility check "
            "(see above). Re-run with --skip-compat-check to attempt the build "
            "anyway, at your own risk."
        )
    if not compat.compatible:
        logger.warning("Renderer compatibility check failed but was overridden "
                        "(--skip-compat-check). Rendering may crash or produce "
                        "incorrect output:\n%s", compat.describe())
    else:
        logger.debug(compat.describe())

    manifest = ProductionManifest(
        story=config.story_dir.name,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        templates_used=[],
        renderer_contract_version=compat.contract_version,
    )

    logger.info("Loading story package from %s", config.story_dir)
    story = load_story(config.story_dir)
    logger.info("Loaded '%s' -- %d slide(s)", story.name, len(story.slides))

    logger.info("Validating story inputs...")
    report = validate_story(story, config)
    _print_validation_report(report)
    manifest.validation_warnings = [
        f"{i.slide_id} ({i.rule}): {i.message}" for i in report.warnings()
    ]
    manifest.validation_errors = [
        f"{i.slide_id} ({i.rule}): {i.message}" for i in report.errors()
    ]

    if report.has_errors:
        logger.error(
            "Validation failed with %d error(s). Stopping before any rendering. "
            "Fix the errors above and re-run.", len(report.errors()),
        )
        return manifest

    registry = build_template_registry()
    total = len(story.slides)
    templates_used = set()

    for slide in story.slides:
        templates_used.add(slide.template)
        try:
            registry.get(slide.template)  # confirms it's a registered template
        except KeyError as exc:
            # Already caught by the validator in the normal path; this
            # is a defensive re-check in case validate_story and
            # build_template_registry ever drift apart.
            logger.error("Slide '%s': %s", slide.slide_id, exc)
            manifest.slides.append(SlideResult(
                slide.slide_id, slide.template, "failed", errors=[str(exc)],
            ))
            continue

        result = _render_and_export_one(slide, total, story, config)
        manifest.slides.append(result)

    manifest.templates_used = sorted(templates_used)
    return manifest


def _render_and_export_one(slide, total: int, story, config: ProductionConfig) -> SlideResult:
    """
    Render, QA-gate, and export a single slide. Isolated in its own
    function (rather than inlined in run_pipeline's loop) so a single
    slide's failure -- expected (TemplateError) or not (any other
    exception, e.g. a bug in a template module, a corrupt image file
    Pillow can't decode) -- can't take down the rest of the batch.
    Every failure mode returns a SlideResult instead of propagating,
    so run_pipeline always finishes the full slide list and the
    manifest always reflects exactly what happened.
    """
    logger.info("Rendering slide '%s' (%s)...", slide.slide_id, slide.template)
    try:
        image, qa_notes = render_slide(slide, total, story, config)
    except TemplateError as exc:
        logger.error("Slide '%s' failed to render: %s", slide.slide_id, exc)
        return SlideResult(slide.slide_id, slide.template, "failed", errors=[str(exc)])
    except Exception as exc:  # noqa: BLE001 -- deliberate: isolate unexpected per-slide failures
        logger.exception("Slide '%s' hit an unexpected error while rendering.", slide.slide_id)
        return SlideResult(slide.slide_id, slide.template, "failed",
                            errors=[f"Unexpected error: {exc}"])

    result = SlideResult(slide.slide_id, slide.template, status="exported")

    if config.skip_qa:
        if qa_notes:
            logger.warning("Slide '%s': QA skipped (--skip-qa); notes: %s",
                            slide.slide_id, "; ".join(qa_notes))
            result.warnings.extend(qa_notes)
    else:
        try:
            qa_report = run_qa(slide, story.brand_footer, qa_notes)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Slide '%s': QA engine failed unexpectedly.", slide.slide_id)
            return SlideResult(slide.slide_id, slide.template, "failed",
                                errors=[f"QA engine error: {exc}"])

        result.warnings = [i.message for i in qa_report.issues if i.severity.value == "WARNING"]
        critical = [i.message for i in qa_report.issues if i.severity.value == "ERROR"]
        if critical:
            logger.error(
                "Slide '%s' failed critical QA -- NOT exporting:\n  - %s",
                slide.slide_id, "\n  - ".join(critical),
            )
            result.status = "skipped_qa"
            result.errors = critical
            return result
        for w in result.warnings:
            logger.warning("Slide '%s' QA warning: %s", slide.slide_id, w)

    out_stem = config.story_output_dir / f"{slide.index:02d}_{slide.get('id') or slide.template}"
    try:
        out_path = export_image(image, out_stem, config)
    except ExportError as exc:
        logger.error(str(exc))
        result.status = "failed"
        result.errors.append(str(exc))
        return result

    result.output_file = str(out_path)
    logger.info("Exported %s", out_path)
    return result


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a JenniWren Instagram carousel from a story folder.",
    )
    parser.add_argument("story_dir", type=Path, help="Path to stories/<name>/")
    parser.add_argument("--output", type=Path, default=Path("output"),
                         help="Output root directory (default: ./output)")
    parser.add_argument("--verbose", action="store_true", help="Verbose (debug) logging")
    parser.add_argument("--skip-qa", action="store_true",
                         help="Export slides even if they fail critical QA")
    parser.add_argument("--export-format", choices=["png", "jpeg"], default="png",
                         help="Image export format (default: png)")
    parser.add_argument("--jpeg-quality", type=int, default=95,
                         help="JPEG quality if --export-format jpeg (default: 95)")
    parser.add_argument("--skip-compat-check", action="store_true",
                         help="Attempt the build even if carousel_lib.py fails the "
                              "orchestrator's API compatibility check")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    config = ProductionConfig(
        story_dir=args.story_dir,
        output_dir=args.output,
        export_format=args.export_format,
        jpeg_quality=args.jpeg_quality,
        skip_qa=args.skip_qa,
        verbose=args.verbose,
        skip_compat_check=args.skip_compat_check,
    )

    log_path = config.story_output_dir / "production_log.txt"
    configure_logging(log_path, config.verbose)

    logger.info("JenniWren Carousel Production Pipeline")
    logger.info("Story: %s", config.story_dir)
    logger.info("Output: %s", config.story_output_dir)
    logger.info("Export format: %s", config.export_format)

    try:
        manifest = run_pipeline(config)
    except StoryLoadError as exc:
        logger.error("Could not load story: %s", exc)
        return 1
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1
    except Exception:
        logger.exception("Unexpected error while building the carousel.")
        return 1

    manifest_path = manifest.write(config.story_output_dir)
    logger.info("Wrote manifest: %s", manifest_path)
    logger.info("Wrote production log: %s", log_path)

    summary = manifest.to_dict()["summary"]
    logger.info(
        "Done. %d exported, %d skipped (QA), %d failed, out of %d total slide(s).",
        summary["exported"], summary["skipped_qa"], summary["failed"], summary["total_slides"],
    )

    if manifest.validation_errors or summary["failed"] or summary["skipped_qa"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
