# JenniWren Carousel Production Pipeline -- build_carousel.py

## What this is

A production orchestrator built **on top of `carousel_lib.py` exactly as
it is** -- this package no longer ships its own copy of it. `carousel_lib.py`
(and the small reused pieces of the unfinished registry/canvas rewrite:
`registry.py`, `qa.py`, `renderer.py`) live in exactly one place, the
sibling `jenniwren_renderer` package, and this orchestrator imports
them from there. `build_carousel.py` loads a story folder, validates
it, checks that the imported renderer still matches the API the
templates were written against, renders every slide, runs a QA gate,
and exports PNGs (or JPEGs) plus a `manifest.json` and
`production_log.txt`.

```
python build_carousel.py stories/hegseth/
python build_carousel.py stories/hegseth/ --output out/ --export-format jpeg
python build_carousel.py stories/hegseth/ --skip-qa --verbose
```

Full architecture discussion -- why this targets `carousel_lib.py`,
what's dead code vs. reused in the unfinished registry/canvas rewrite,
the `cov templates.py` signature-mismatch hazard, module map, renderer
assumptions -- lives in **`ARCHITECTURE.md`**. What changed in the most
recent refinement pass, and why, is in **`CHANGELOG.md`**.

## Project layout

This is now two packages, not one:

```
<some parent directory>/
    jenniwren_renderer/              <- the renderer -- ONE authoritative copy
        pyproject.toml
        DESIGN_RULES.md
        jenniwren_renderer/
            __init__.py
            carousel_lib.py           <- the rendering engine
            registry.py                <- reused (TemplateRegistry/TemplateDefinition)
            qa.py                       <- reused (QAReport/QARule/QAEngine)
            renderer.py                 <- reused (RenderContext)

    jenniwren_build_carousel/        <- this orchestrator -- imports the renderer, doesn't copy it
        build_carousel.py
        renderer_imports.py           <- the ONLY module that knows how to find jenniwren_renderer
        story_loader.py, validator.py, templates.py, ...
        stories/
        tests/
```

**`renderer_imports.py`** is the single point of contact with the
renderer package. Every other orchestrator module imports
`carousel_lib`/`registry`/`qa`/`renderer` through it
(`from renderer_imports import carousel_lib as cl`), never directly --
so there's exactly one place that knows how the renderer is located,
and exactly one place that explains what went wrong if it isn't.

`renderer_imports.py` looks for `jenniwren_renderer` in this order,
and fails gracefully (a clean one-line message + exit code, not a raw
traceback) if none of them work:

1. **Normal import** -- works if `jenniwren_renderer` is pip-installed:
   ```
   cd jenniwren_renderer && pip install -e .
   ```
2. **`JENNIWREN_RENDERER_PATH` environment variable** -- point it at
   the directory that *contains* `jenniwren_renderer/`:
   ```
   export JENNIWREN_RENDERER_PATH=/path/to/parent-of-jenniwren_renderer
   ```
3. **Sibling-directory convention** -- if `jenniwren_renderer/` and
   `jenniwren_build_carousel/` are unzipped/checked out next to each
   other (the layout this project ships in), it's found automatically
   with no install step and no environment variable. This is what
   makes `python build_carousel.py ...` work out of the box from a
   fresh unzip.

If `jenniwren_renderer` genuinely can't be found by any of the three,
running `build_carousel.py` prints one clear, actionable error
(what's missing and all three ways to fix it) and exits with status 1
-- it does not fall back to a bundled copy, because there isn't one.


## Before you run it

`carousel_lib.py` (in `jenniwren_renderer/`) loads fonts from fixed paths:

```
/home/claude/fonts/barlow/BarlowCondensed-ExtraBold.ttf
/home/claude/fonts/baskerville/static/LibreBaskerville-Regular.ttf
/home/claude/fonts/baskerville/static/LibreBaskerville-Italic.ttf   (falls back to Lora Italic)
```

If those aren't present, `carousel_lib.lf()` will raise when a slide
tries to render -- the pipeline catches this per-slide (it won't crash
the whole run) and records it as a `failed` slide in the manifest, but
you obviously won't get real output. Put the real fonts at those paths
before trusting any visual result.

## Story folder format

```
stories/<name>/
    carousel.json   -- required
    article.md      -- optional, reference copy only, not rendered
    sources.md       -- optional, cross-checked loosely against citations
    images/          -- referenced by photo_headline / document_card slides
```

`carousel.json`:

```json
{
  "story": "hegseth",
  "brand_footer": "TheJenniWren",
  "slides": [
    {
      "template": "cover_headline",
      "label": "BREAKING",
      "big_label": true,
      "headline_lines": ["LINE ONE", "LINE TWO PINK"],
      "headline_colors": ["white", "pink"],
      "body": [{"text": "Optional deck copy.", "color": "white"}],
      "citation": "Source, date"
    }
  ]
}
```

See `stories/example/carousel.json` for one example of every template.
Ten templates are wired up, grouped into family modules by
`carousel_lib.py` capability -- see the module table below. Each
template's required/optional fields are declared once, in
`templates.py`'s `REQUIRED_FIELDS` / `KNOWN_FIELDS`, and the validator
and every render function read from that same declaration so they
can't drift apart.

Every slide accepts `"arrow": false` to suppress the next-slide arrow
(set it on your last slide) and an optional `"id"` to control its
output filename stem.

## Pipeline stages

1. **Renderer compatibility check** (`renderer_compat.py`) -- before a
   story is even loaded, confirms the installed `carousel_lib.py`
   still exposes the exact function signatures and constants the
   templates were written against. Fails fast with a clear diff if
   not; `--skip-compat-check` overrides it.
2. **Load** (`story_loader.py`) -- parse `carousel.json`, read
   `article.md` / `sources.md`, resolve image paths.
3. **Validate** (`validator.py`) -- required fields, invalid template
   IDs, unrecognized fields (typo protection), missing images, missing
   citations, brand-palette compliance, max headline length, and
   *overflow risk* -- pre-render, using `carousel_lib.max_sz` /
   `wrap_lines` directly. Thresholds come from `ProductionConfig.qa`.
   **Any ERROR here stops the run before a single pixel is drawn.**
4. **Resolve template** (`templates.py`) -- template IDs looked up
   through `registry.py`'s existing `TemplateRegistry` /
   `TemplateDefinition` classes (reused unchanged).
5. **Render** (family modules under `templates.py`) -- each template
   is a thin function written directly against `carousel_lib.py`'s
   verified signatures. `template_shared.draw_body_checked()`
   reproduces `draw_body()`'s own wrap/line-height math immediately
   beforehand, so the pipeline can *detect* the silent text truncation
   `draw_body()` is documented to do.
6. **QA gate** (`qa_gate.py`) -- reuses `qa.py`'s `QAReport` /
   `QARule` / `QAEngine` and `renderer.py`'s `RenderContext` unchanged.
   Checks text overflow, content bounds, image bounds, and source
   visibility as real, computed facts; contrast/margins are flagged
   INFO as "pass by construction." **A slide with any QA ERROR is not
   exported** (`--skip-qa` overrides this, exporting it anyway with
   the issue recorded in the manifest).
7. **Export** (`exporter.py`) + **manifest** (`manifest.py`) --
   `manifest.json` and `production_log.txt` are always written, even
   on a failed run.

A single slide's failure -- whether it's an expected validation
problem, a QA rejection, or an unexpected exception in a template or
the QA engine -- never aborts the rest of the batch; it's recorded and
the pipeline moves on to the next slide.

Exit code is `0` only if every slide validated, rendered, and passed
QA; `1` otherwise (`--skip-qa` no longer counts QA failures against
the exit code, since you explicitly overrode them).

## Module map

| File | Purpose |
|---|---|
| `build_carousel.py` | CLI entry point / pipeline coordination only |
| `story_loader.py` | Loads a story folder into typed objects |
| `validator.py` | Pre-render validation |
| `templates.py` | Thin template registry/dispatcher |
| `template_shared.py` | Helpers shared by every template family module |
| `cover_templates.py` | COV: `cover_headline`, `quote_lead`, `photo_headline` |
| `data_templates.py` | DATA: `stat_callout`, `stat_grid` |
| `timeline_templates.py` | DATA: `timeline` |
| `comparison_templates.py` | COMP: `call_block` |
| `document_templates.py` | COMP: `document_card` |
| `explainer_templates.py` | COMP: `body_standard`, `sources_slide` |
| `qa_gate.py` | Post-render QA gate before export |
| `production_config.py` | Run configuration: paths, export format, QA thresholds, template defaults |
| `renderer_compat.py` | API compatibility check against the imported `carousel_lib` |
| `renderer_imports.py` | Locates and imports the `jenniwren_renderer` package; the only module that knows how |
| `manifest.py` | `ProductionManifest` / `SlideResult` |
| `exporter.py` | PNG/JPEG export |
| `perf.py` | Orchestrator-level font-load memoization |
| `tests/test_pipeline.py` | Test suite -- `python -m unittest discover -s tests -v` |
| `ARCHITECTURE.md` | Full architecture discussion |
| `CHANGELOG.md` | What changed in the refinement pass, and why |

Not in this package: `carousel_lib.py`, `registry.py`, `qa.py`,
`renderer.py`, `DESIGN_RULES.md` -- all live in `jenniwren_renderer/`,
imported via `renderer_imports.py`. See "Project layout" above.

## CLI flags

```
positional:
  story_dir              Path to stories/<name>/

options:
  --output DIR            Output root directory (default: ./output)
  --verbose                Verbose (debug) logging
  --skip-qa                Export slides even if they fail critical QA
  --export-format {png,jpeg}   Image export format (default: png)
  --jpeg-quality N          JPEG quality if --export-format jpeg (default: 95)
  --skip-compat-check       Attempt the build even if carousel_lib.py fails
                            the API compatibility check
```

## Running tests

```
python -m unittest discover -s tests -v
```

17 tests covering invalid template IDs, missing images, overflow
detection (pre-render risk + post-render exact truncation), malformed
story packages, successful end-to-end rendering, and renderer
compatibility checks (both the real `carousel_lib.py` and a
deliberately broken stand-in).
