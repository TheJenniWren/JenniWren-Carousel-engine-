# Changelog

## Pass 3 -- Eliminate duplicate renderer files

Task: stop shipping local copies of `carousel_lib.py`, `renderer.py`,
`registry.py`, and `qa.py` inside the orchestrator; import them from a
single authoritative package instead; fail gracefully if that package
isn't available; document the new layout and import paths; make sure
tests run against the shared modules, not duplicates.

### What changed

- **New package: `jenniwren_renderer/`**, a sibling of this
  orchestrator, containing the one authoritative copy of
  `carousel_lib.py`, `registry.py`, `qa.py`, and `renderer.py`, plus
  `DESIGN_RULES.md` (the spec they implement) and a `pyproject.toml`
  so it can be `pip install -e`'d. Ships as a standard
  project-root/package-name layout (`jenniwren_renderer/jenniwren_renderer/`)
  so it's installable; a flat layout (files directly under
  `jenniwren_renderer/`, no nesting) is also accepted by the
  orchestrator's lookup logic, for a no-packaging-metadata checkout.
- **Removed from the orchestrator**: `carousel_lib.py`, `renderer.py`,
  `registry.py`, `qa.py`. There is now exactly one copy of each, in
  `jenniwren_renderer/`.
- **New `renderer_imports.py`** in the orchestrator: the single module
  that locates and imports `jenniwren_renderer`, in this order --
  normal package import (pip-installed), `JENNIWREN_RENDERER_PATH`
  environment variable, sibling-directory auto-detection. Re-exports
  `carousel_lib`, `registry`, `qa`, `renderer` (as modules) plus the
  specific names orchestrator code uses directly (`TemplateDefinition`,
  `TemplateRegistry`, `Severity`, `QAIssue`, `QAReport`, `QARule`,
  `QAEngine`, `RenderContext`). Raises `RendererUnavailableError` (an
  `ImportError` subclass) with a message listing all three ways to fix
  it if the package can't be found anywhere.
- **Every orchestrator module that used to `import carousel_lib as cl`,
  `from registry import ...`, `from qa import ...`, or
  `from renderer import ...` directly** now imports the same names from
  `renderer_imports` instead: `comparison_templates.py`,
  `cover_templates.py`, `data_templates.py`, `document_templates.py`,
  `explainer_templates.py`, `perf.py`, `production_config.py`,
  `template_shared.py`, `timeline_templates.py`, `validator.py`,
  `templates.py`, `qa_gate.py`, `tests/test_pipeline.py`. Purely a
  change of where the name comes from -- no call site behavior changed
  (`cl.new_canvas()` is still `cl.new_canvas()`, etc).
- **`build_carousel.py`**: its whole top-of-file import block is now
  wrapped in a single `try/except ImportError`. If the renderer package
  (or, in principle, any other startup import) can't be resolved, it
  prints one clean message to stderr and exits with status 1 --
  instead of a raw traceback several frames into `renderer_imports.py`.
  This is the "fail gracefully" behavior the task asked for.
- **Two mechanical import fixes inside the renderer package itself**
  (not a behavior change): `qa.py`'s `from renderer import RenderContext`
  and `renderer.py`'s `from registry import get_registry` became
  relative imports (`from .renderer import ...`, `from .registry import
  ...`), because they now live inside a real Python package instead of
  a flat directory of same-level files. No drawing, template, or QA
  rule logic was touched.
- **`tests/test_pipeline.py`**: its one `import carousel_lib as cl`
  became `from renderer_imports import carousel_lib as cl` -- the test
  suite now exercises the exact same shared-package import path
  production code does, rather than a duplicate. All 17 tests still
  pass, run against the shared renderer.
- **`README.md`**: new "Project layout" section documenting the
  two-package structure, the three renderer-resolution strategies and
  their exact commands/environment variables, and the "fails gracefully,
  no bundled fallback" behavior. Module table updated to remove the
  four renderer files and add `renderer_imports.py`.
- **`ARCHITECTURE.md`**: new "Package split" section explaining why the
  duplicate-copy risk existed and how `renderer_imports.py` removes it;
  module map updated to show the two-package layout; "Renderer
  assumptions" section now distinguishes renderer *availability*
  (`renderer_imports.py`'s job) from renderer *compatibility*
  (`renderer_compat.py`'s job, unchanged from Pass 2).

### Verification

- `python -m unittest discover -s tests -v` -- 17/17 pass, against the
  shared `jenniwren_renderer` package (confirmed by temporarily
  renaming the local files away before this pass existed -- there's
  nothing left to accidentally import locally now).
- Full pipeline run against `stories/example/` from the orchestrator
  directory, with `jenniwren_renderer/` present as a sibling and no
  environment variable set (the auto-detected, zero-config path) --
  6/6 slides exported, exit 0.
- Same run with the orchestrator copied to an isolated directory with
  no sibling renderer present and no environment variable -- fails
  with a single clean stderr message and exit 1, no traceback.
- Same isolated setup with `JENNIWREN_RENDERER_PATH` pointed at the
  renderer's parent directory -- resolves correctly, 6/6 slides
  exported, exit 0.
- `pip install -e jenniwren_renderer` was written and packaged
  correctly (verified the package metadata and importability
  manually), but could not be exercised end-to-end in this sandbox,
  which has no network access to fetch `setuptools` as a PEP 517 build
  dependency. The sibling-directory and environment-variable paths
  were fully exercised instead and are the documented zero-install
  option for exactly this reason.

### Remaining technical debt from this pass

- The `pip install -e` path is written to spec (standard
  project-root/package-name layout, `pyproject.toml` with setuptools
  backend) but unverified end-to-end here, as noted above. Worth a
  real install test in an environment with network access before
  calling that specific path production-verified.
- `renderer_imports.py`'s broad `except ImportError` in
  `build_carousel.py` will also catch an unrelated, genuine bug in one
  of the orchestrator's own modules if that bug happens to manifest as
  an `ImportError` (e.g. a typo'd import unrelated to the renderer).
  The error message in that case would show the real underlying
  `ImportError` text, so it's still informative, but it's technically a
  slightly wider net than "renderer specifically unavailable." Judged
  an acceptable tradeoff for keeping the fail-gracefully logic in one
  place rather than special-casing every possible import failure.

---

# Changelog -- Pass 2: Refinement Pass

This pass refined the existing orchestration package per the review
brief: keep `carousel_lib.py` as the renderer, keep the orchestrator a
coordination layer, no redesign, no migration to the unfinished
registry/canvas system. Nothing in `carousel_lib.py`, `registry.py`,
`qa.py`, or `renderer.py` was changed.

## Files added

| File | Why |
|---|---|
| `ARCHITECTURE.md` | Architecture discussion moved out of `build_carousel.py`'s module docstring, per review item 5, and expanded with a module map, renderer assumptions, and a migration path. |
| `CHANGELOG.md` | This file. |
| `template_shared.py` | Helpers shared by every template family module (`TemplateError`, color/require/body-check/image-resolve helpers), split out of the old monolithic `templates.py`. |
| `cover_templates.py` | COV family: `cover_headline`, `quote_lead`, `photo_headline`. |
| `data_templates.py` | DATA family (non-timeline): `stat_callout`, `stat_grid`. |
| `timeline_templates.py` | DATA family: `timeline`, split into its own module since its layout logic (a dated vertical sequence) is meaningfully different from a single stat or a grid. |
| `comparison_templates.py` | COMP family (emphasis/comparison): `call_block`. |
| `document_templates.py` | COMP family (evidence): `document_card`. |
| `explainer_templates.py` | COMP family (interior slides): `body_standard`, `sources_slide`. |
| `renderer_compat.py` | Lightweight API compatibility check between the orchestrator and `carousel_lib.py` (review item 4). No `__version__` was added to `carousel_lib.py` itself -- see "Renderer version checking" below. |
| `manifest.py` | `SlideResult` / `ProductionManifest` dataclasses, split out of `build_carousel.py` (review item 1). |
| `exporter.py` | PNG/JPEG export logic, split out of `build_carousel.py` (review item 1). |
| `perf.py` | `cached_lf()`, a narrow memoization wrapper for the font loads the *orchestrator itself* makes (see "Performance" below). |
| `tests/test_pipeline.py` | New test suite (review item 9): invalid template IDs, missing images, overflow detection (both pre-render risk estimate and post-render exact truncation), malformed story packages, successful end-to-end rendering, and renderer compatibility checks against both the real `carousel_lib.py` and a deliberately broken stand-in. 17 tests, all passing. |

## Files modified

| File | Change | Why |
|---|---|---|
| `templates.py` | Reduced from ~530 lines containing every render function to a thin aggregator: the dispatch table (`RENDER_FUNCS`), the shared `REQUIRED_FIELDS`/`KNOWN_FIELDS` declarations, `TemplateRegistry` wiring, and `render_slide()`. | Review item 2 -- it had become a god module. |
| `production_config.py` | Added `QAThresholds` (narrow-headline pt/pct, max headline lines, min pink lines) and `TemplateDefaults` (headline ranges, font sizes, grid/card dimensions, photo fade defaults) dataclasses on `ProductionConfig`. Added `default_config()` convenience constructor for tests. | Review item 3 -- these were previously module-level constants in `validator.py` and inline literals scattered across `templates.py`'s render functions. |
| `validator.py` | Reads thresholds from `config.qa` instead of module constants; `validate_story()` now takes an optional `config` parameter. Replaced the per-slide full 1080x1350 `Image.new()` probe canvas with a single small (10x10) probe `ImageDraw` shared across the whole validation pass -- text-metric calls don't depend on canvas size (verified), so the large allocation was pure waste. Uses `perf.cached_lf()` instead of calling `carousel_lib.lf()` directly. | Review items 3 and 8. |
| `build_carousel.py` | Removed the `SlideResult`/`ProductionManifest` dataclasses (-> `manifest.py`) and the `_export()` function (-> `exporter.py`). Removed the long architecture docstring (-> `ARCHITECTURE.md`); the module docstring is now a short pointer. Added a renderer compatibility check at the start of `run_pipeline()`, before the story is even loaded, with a `--skip-compat-check` escape hatch. Split the per-slide render/QA/export logic into `_render_and_export_one()`, which now catches broad `Exception` (not just `TemplateError`) around rendering and around the QA engine call, and catches `ExportError` around export -- a bug in one slide's template code, a corrupt image file, or a QA rule crashing no longer takes down the rest of the batch; it's recorded as a `failed` `SlideResult` and the pipeline continues. | Review items 1, 4, 7. |
| `qa_gate.py` | No functional change -- confirmed it still only depends on `qa.py`/`renderer.py` (both self-contained) and doesn't need config threading, since its checks are pass/fail on computed facts rather than tunable numeric thresholds. | Review item 6 (API call audit). |
| `README.md` | Updated file table, module list, and CLI flags (`--skip-compat-check`) to match the new structure; points to `ARCHITECTURE.md` for the architecture discussion instead of repeating it. | Review item 10. |

## API call audit (review item 6)

Every call into `carousel_lib.py`, `registry.py`, and `qa.py` was
re-checked against the current source after the split (function names,
parameter names/order, return values) -- confirmed unchanged from the
prior pass, since the split moved code between files without altering
any call sites. `renderer_compat.py` now also does this check
automatically, at runtime, on every pipeline run, rather than relying
solely on a one-time manual audit. Re-confirmed `cov templates.py`'s
signature mismatches are not relied on anywhere in this codebase (see
`ARCHITECTURE.md`).

## Renderer version checking (review item 4) -- design decision

`carousel_lib.py` has no `__version__` string, and it wasn't given
one -- the constraint was "do not redesign the renderer," and even a
one-line addition felt like the wrong side of that line given
`carousel_lib.py` is meant to stay exactly as delivered. Instead,
`renderer_compat.py` fingerprints the actual API surface the
orchestrator depends on (function names, parameter names/order for the
parameters actually used, and required module-level constants) and
checks it against the live `carousel_lib` module at the start of every
run. This catches the same class of problem a version check would
(orchestrator built against an API that no longer matches), without
requiring carousel_lib.py to know anything about the orchestrator.

## Performance (review item 8) -- what was done and what was deferred

Done:
- `validator.py`'s per-slide 1080x1350 probe canvas replaced with a
  single shared 10x10 probe, reused across the whole validation pass
  (confirmed via a direct test that `ImageDraw` text-metric calls are
  independent of the underlying image's size).
- `perf.cached_lf()` memoizes the font loads the orchestrator itself
  makes directly (validator's overflow check, `explainer_templates`'s
  sources-slide layout), so repeated (path, size) pairs across a
  multi-slide carousel don't re-parse the same TTF from disk.

Deliberately not done (documented as technical debt, not silently
skipped):
- The majority of font-loading actually happens *inside*
  `carousel_lib.py`'s own `fit_head()`/`max_sz()` size-search loops
  (up to ~120 `lf()` calls per headline while searching for a fit).
  Caching those would require monkeypatching `carousel_lib.lf` at
  runtime. That's within reach technically, but it means altering the
  runtime behavior of a module we were explicitly told to leave alone
  as "the rendering engine" -- so it was left as-is. If this becomes a
  real bottleneck (it wasn't observed to be one at carousel-scale batch
  sizes), the fix would live in `carousel_lib.py` itself, as a
  `functools.lru_cache` on `lf()`, decided by whoever owns that file.
- `template_shared.draw_body_checked()` still wraps the body text
  twice: once to know the expected line count for the truncation
  check, once again inside `carousel_lib.draw_body()` itself (which
  doesn't expose its internal wrap as a separate step). This is a
  small, bounded cost (one extra `wrap_lines()` call per body-bearing
  slide) traded against actually catching silent truncation, which is
  the more important property. Not optimized away.

## Remaining technical debt (for a future version)

1. **`cov templates.py` is still broken.** Not touched this pass
   (out of scope -- it isn't called from anywhere in the working
   pipeline), but it remains a hazard for a future session that copies
   from it out of habit. Recommend repairing or deleting it.
2. **The registry/canvas rewrite (system 2 in `ARCHITECTURE.md`) is
   still unfinished and unused.** Two small pieces of it
   (`TemplateRegistry`/`TemplateDefinition`, the QA framework classes)
   are reused; the rest (`component_registry.py`, `canvas.py`,
   `layout.py`, `brand.py`, `typography.py`, and the `*Spec`/component
   files) remains dead code in this repo. Whether to finish it, delete
   it, or leave it as a future option is a product decision, not an
   engineering one -- flagged, not resolved.
3. **No real `__version__` on `carousel_lib.py`.** The compatibility
   check in `renderer_compat.py` is a reasonable substitute given the
   "don't touch the renderer" constraint, but a real version string
   (even just bumped by hand on breaking changes) would be a more
   conventional signal if that constraint is ever relaxed.
4. **Font-loading inside `carousel_lib.py`'s own size-search loops is
   uncached**, as discussed above -- deferred deliberately, not an
   oversight.
5. **`comparison_templates.py` currently has one template
   (`call_block`).** The module split anticipated a real two-panel
   "promise vs. reality" comparison template (the kind
   `cov_templates.py`'s COV-12 docstring gestures at) that doesn't
   exist against `carousel_lib.py` yet. If/when one gets built, it
   belongs in this module.
