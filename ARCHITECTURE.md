# Architecture

## Why the orchestrator targets `carousel_lib.py`

This bundle contains **two different, non-interoperable rendering systems**:

1. **`carousel_lib.py`** -- a hand-built PIL library with the JenniWren
   brand's actual rendering logic: font-size search (`fit_head`,
   `max_sz`), per-word white/pink color mixing, the 44pt body floor,
   stat/timeline/document-card templates, and so on. `DESIGN_RULES.md`
   calls this the canonical pipeline and instructs every session to
   build on it as-is.

2. **`registry.py` / `component_registry.py` / `renderer.py` /
   `canvas.py` / `layout.py` / `brand.py` / `typography.py` / `qa.py`
   plus a family of `*Spec`/`*Component` files (`headline.py`,
   `body.py`, `image.py`, `footer.py`, ...)** -- a class-based rewrite
   attempt. As shipped, it does not run:
   - `footer_renderer.py` imports `logo_renderer.py` and
     `shape_renderer.py`, neither of which exist anywhere in this
     bundle.
   - Every `*_renderer.py` (`text_renderer.py`, `image_renderer.py`,
     `footer_renderer.py`) reads `spec.region.bounds`, but
     `layout.py`'s `Region` dataclass only has `x`/`y`/`width`/`height`
     -- there is no `.bounds` attribute anywhere.
   - `registry.py`'s `TemplateDefinition.module` values (e.g.
     `"templates.cov_01"`) don't correspond to any importable path --
     there's no `templates` package, and the file that would need to
     be `cov_01.py` inside one doesn't match either.
   - It never implements the brand-specific rendering rules (per-word
     color mixing, the font-size search algorithm, the actual
     stat/timeline/document templates) that make a JenniWren slide
     look like a JenniWren slide -- it's a generic Pillow
     `multiline_text` wrapper underneath.

By explicit direction across two review passes, this orchestrator is
built on system (1), unmodified, and treats system (2) as an unused,
future-refactor target -- not a dependency.

### What was reused from system (2), and why it's safe

Two pieces of system (2) have **no dependency on the broken parts**
and are reused here rather than reinvented:

- **`registry.py`'s `TemplateRegistry` / `TemplateDefinition`** --
  plain dataclasses with no imports beyond `dataclasses`/`typing`.
  Used in `templates.py` to register the ten working templates. The
  `module` field on each `TemplateDefinition` here points at this
  orchestrator's own family modules (`cover_templates`,
  `data_templates`, etc.), not at the nonexistent `templates.cov_01`
  paths from the original stub definitions.
- **`qa.py`'s `QAReport` / `QAIssue` / `QARule` / `QAEngine`**, plus
  **`renderer.py`'s `RenderContext`** -- also self-contained. `qa.py`
  ships with default rules that only check whether
  `context.metadata` has non-empty string values (a stub for a
  backend that was never finished); those aren't used. `qa_gate.py`
  defines its own `QARule` subclasses that check real, computed facts
  about a rendered slide instead (see below).

Everything else in system (2) is untouched and unused. If a future
session wants to actually finish that rewrite, the missing pieces are:
`logo_renderer.py`, `shape_renderer.py`, a `.bounds` property (or
rename) on `layout.Region`, real `templates/` package paths matching
`registry.py`'s `module` field, and -- the larger piece -- porting
`carousel_lib.py`'s actual brand-specific drawing algorithms into the
component/spec classes, since the current ones don't attempt that.
None of this is required for the current pipeline to work; it's listed
here only as a migration note for if/when someone picks that project
back up.

### `cov templates.py` -- flagged, not fixed

`cov templates.py` (shipped alongside `carousel_lib.py`, presumably
meant to be an earlier draft of this orchestrator's template layer)
calls several `carousel_lib` functions with parameter names that don't
match the real `carousel_lib.py` in this bundle:

| Call in `cov templates.py` | Real `carousel_lib.py` signature |
|---|---|
| `new_photo_fade_canvas(image_path, fade=..., fade_frac=...)` | `new_photo_fade_canvas(image_path, fade_edge=..., fade_start=...)` |
| `draw_stat_callout(draw, stat_text, y0, stat_size=..., label_lines=...)` | `draw_stat_callout(draw, stat_text, context_label, y0=200, stat_size=None, stat_range=...)` |
| `draw_call_block(draw, items, ty, item_fsz=..., gap=..., numbered=...)` | `draw_call_block(draw, text, ty, bg=PINK, text_color=WHITE, fsz=40, pad=28)` |
| `draw_document_card(draw, x, y, w, h, title=..., body_text=..., meta=...)` | `draw_document_card(draw, img, lines, highlight_line_idxs, ty, card_h=520, annotation=True)` |

Calling `carousel_lib.py` through any of these would raise a
`TypeError` immediately. Every template composition function in this
orchestrator (`cover_templates.py`, `data_templates.py`, etc.) was
written directly against `carousel_lib.py`'s actual signatures,
confirmed by inspection -- none of them were copied from
`cov templates.py`. `renderer_compat.py`'s API contract check (below)
is partly a hedge against this class of drift.

Recommendation, still open: repair or retire `cov templates.py` so a
future session doesn't copy from it by habit.

## Module map

```
jenniwren_renderer/                (separate package -- see "Package split" below)
  jenniwren_renderer/
    carousel_lib.py           UNMODIFIED -- the renderer
    registry.py, qa.py, renderer.py   reused pieces of system (2); import paths
                               made package-relative (from .renderer import ...),
                               otherwise unmodified
  DESIGN_RULES.md             UNMODIFIED -- brand spec

jenniwren_build_carousel/          (this orchestrator)
  build_carousel.py       CLI entry point + pipeline coordination only
  renderer_imports.py     Locates and imports jenniwren_renderer; the only
                           module that knows how (see "Package split" below)
  story_loader.py         Loads a story folder into typed objects
  validator.py            Pre-render validation
  templates.py            Thin registry/dispatcher over the family modules below
    cover_templates.py       COV family: cover_headline, quote_lead, photo_headline
    data_templates.py        DATA family: stat_callout, stat_grid
    timeline_templates.py    DATA family: timeline
    comparison_templates.py  COMP family: call_block
    document_templates.py    COMP family: document_card
    explainer_templates.py   COMP family: body_standard, sources_slide
    template_shared.py       Helpers shared by every family module
  qa_gate.py               Post-render QA gate before export
  production_config.py     ProductionConfig, QAThresholds, TemplateDefaults
  renderer_compat.py       API compatibility check against the imported carousel_lib
  manifest.py              ProductionManifest / SlideResult
  exporter.py              PNG/JPEG export
  perf.py                  Narrow, orchestrator-level font-load memoization
```

## Package split -- one authoritative renderer, imported not copied

Earlier revisions of this project shipped `carousel_lib.py`,
`registry.py`, `qa.py`, and `renderer.py` as local copies inside the
orchestrator package, alongside the code that used them. That worked,
but it meant two directories could silently drift: an edit to "the"
`carousel_lib.py` in one place wouldn't reach a copy sitting in the
other, with no error until someone noticed the output looked wrong.

`carousel_lib.py`, `registry.py`, `qa.py`, and `renderer.py` now live
in exactly one place: the sibling `jenniwren_renderer` package. This
orchestrator does not contain a copy of any of them. Every module that
needs one imports it through **`renderer_imports.py`**
(`from renderer_imports import carousel_lib as cl`, etc.) rather than
importing `carousel_lib`/`registry`/`qa`/`renderer` directly --
`renderer_imports.py` is the single place that knows how to locate the
renderer package (pip-installed, `JENNIWREN_RENDERER_PATH`, or a
sibling-directory checkout) and the single place that has to explain
what went wrong if it can't be found.

This was a mechanical, behavior-preserving change with two small
exceptions inside the renderer package itself: `qa.py`'s
`from renderer import RenderContext` and `renderer.py`'s
`from registry import get_registry` were changed to relative imports
(`from .renderer import ...`, `from .registry import ...`) because
they now live inside a real Python package instead of a flat directory
of same-level files. No drawing logic, template logic, or QA rule
logic was touched in either file.

If the renderer package genuinely can't be found at pipeline startup,
`build_carousel.py` catches that specifically and prints one clean,
actionable message (what's missing, three ways to fix it) instead of
propagating a raw `ImportError` traceback -- see `renderer_imports.py`
and README.md "Project layout" for the exact resolution order and
error format.

## Renderer assumptions

The orchestrator assumes the imported `carousel_lib` continues to
expose:

- The exact function names, parameter names/order, and constants
  listed in `renderer_compat.py`'s `EXPECTED_FUNCTIONS` /
  `EXPECTED_CONSTANTS`. This is checked at the start of every pipeline
  run (`check_renderer_compatibility`), before a story is even loaded.
  A failure here means "this orchestrator's templates.py was written
  against a carousel_lib.py that no longer exists" -- it fails loudly
  with a diff of what's missing/mismatched, rather than a confusing
  `TypeError` three frames into a render. This is a separate check
  from renderer *availability* (handled by `renderer_imports.py`,
  above): compatibility assumes the renderer was found and asks
  whether it's the right shape.
- `draw_body()`'s documented silent-truncation behavior (it stops
  drawing once text would cross `FOOTER_SAFE`, with no error). The
  orchestrator works around this by reproducing `draw_body()`'s own
  wrap/line-height math immediately before and after calling it
  (`template_shared.draw_body_checked`), so truncation is *detected*,
  not fixed at the source.
- Fonts available at the fixed paths `carousel_lib.py` hard-codes
  (`/home/claude/fonts/...`). The orchestrator doesn't check for these
  itself; if they're missing, `carousel_lib.lf()` will raise, and that
  exception surfaces as a per-slide `failed` result in the manifest
  rather than crashing the whole run (see `_render_and_export_one` in
  `build_carousel.py`).

## Migration path for future versions

If `carousel_lib.py` is ever revised (new template functions, changed
signatures, an actual `__version__`):

1. Update `renderer_compat.py`'s `EXPECTED_FUNCTIONS` /
   `EXPECTED_CONSTANTS` and bump `API_CONTRACT_VERSION`.
2. Update the affected family module(s) in lockstep -- e.g. if
   `draw_stat_callout`'s signature changes, only `data_templates.py`
   needs to change, not the other five family modules.
3. Add/update the corresponding case in `tests/test_pipeline.py`.
4. If the change is additive (a new drawing primitive, not a change to
   an existing one), consider whether it's worth a new template family
   module rather than growing an existing one back into a god module.

If the registry/canvas rewrite (system 2 above) is ever finished and
adopted as the real renderer instead of `carousel_lib.py`, that's a
genuine architecture change, not a refinement -- it would mean
replacing every family module's implementation (not just their
call sites), and should go through the same explicit
"do you want a redesign or a refinement" conversation this project has
already had twice.
