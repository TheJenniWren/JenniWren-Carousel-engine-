"""
JenniWren Production Engine
renderer.py

Core rendering engine that assembles a slide from a template,
layout regions, components, and story data.

v3.7.2 - Editorial Composition Engine
--------------------------------------
This revision layers an editorial layout/composition system on top of the
existing component pipeline. The renderer's job remains layout and
composition metadata only - it does not draw pixels itself and does not
duplicate any typography logic. All text measurement/fitting is delegated
to text_fitting_engine (fit_text / measure_lines) whenever a draw context
and font_loader are available on the incoming data; if they are not (as in
plain metadata-only usage), every new computation degrades gracefully and
the module behaves exactly as it did in 3.7.1.

Public API is unchanged:
    RenderContext
    Component
    Renderer
    HeadlineComponent, BodyComponent, FooterComponent, CategoryTagComponent
    create_default_renderer()

New, additive-only surface (safe for downstream code that doesn't know
about it - nothing existing is removed or renamed):
    HeaderComponent, DividerComponent, GraphicsComponent,
    SourceTagComponent, LogoComponent
    LayoutZone, SpacingScale, TEMPLATE_SPACING_PROFILES, RENDER_ORDER
    compute_layout_zones(), score_composition()
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .registry import get_registry

try:
    # Text measurement/fitting is owned entirely by the text engine; the
    # renderer never re-implements wrapping or font-size selection.
    from .text_fitting_engine import fit_text, measure_lines
except ImportError:  # pragma: no cover - defensive; renderer has no hard
    # compile-time dependency on the text engine being importable.
    fit_text = None
    measure_lines = None


# ---------------------------------------------------------------------------
# Standardized rendering order (reference constant for template modules;
# this file does not draw pixels, so it does not enforce this itself).
# ---------------------------------------------------------------------------

RENDER_ORDER: Tuple[str, ...] = (
    "background", "shapes", "images", "headline",
    "divider", "body", "callouts", "source", "logo",
)


# ---------------------------------------------------------------------------
# Vertical rhythm / spacing system
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpacingScale:
    """
    Reusable spacing constants (px, at the canonical 1080x1350 canvas)
    describing the vertical rhythm between major slide regions. Templates
    scale these proportionally to their own canvas size rather than each
    carrying their own scattered pixel values.
    """
    canvas_reference_height: int = 1350

    margin: int = 64
    header_to_headline: int = 40
    headline_to_divider: int = 28
    divider_to_body: int = 32
    body_to_footer: int = 48
    footer_to_branding: int = 20
    divider_thickness: int = 4

    def scaled(self, canvas_height: int) -> "SpacingScale":
        """Return a copy of this scale proportionally fit to canvas_height."""
        if canvas_height == self.canvas_reference_height:
            return self
        ratio = canvas_height / self.canvas_reference_height
        return SpacingScale(
            canvas_reference_height=canvas_height,
            margin=round(self.margin * ratio),
            header_to_headline=round(self.header_to_headline * ratio),
            headline_to_divider=round(self.headline_to_divider * ratio),
            divider_to_body=round(self.divider_to_body * ratio),
            body_to_footer=round(self.body_to_footer * ratio),
            footer_to_branding=round(self.footer_to_branding * ratio),
            divider_thickness=max(1, round(self.divider_thickness * ratio)),
        )


DEFAULT_SPACING = SpacingScale()


# ---------------------------------------------------------------------------
# Template-aware spacing profiles
#
# Each template family gets its own proportional allocation of the canvas
# to its zones (fractions of usable, post-margin height). Templates not
# listed fall back to "default". This does NOT change template selection
# or registry behaviour - it's only consulted after a template has already
# been resolved, purely to decide how that template's zones are sized.
# ---------------------------------------------------------------------------

TEMPLATE_SPACING_PROFILES: Dict[str, Dict[str, float]] = {
    "default": {
        "header": 0.06, "headline": 0.26, "divider": 0.02,
        "body": 0.40, "graphics": 0.00, "footer": 0.10,
        "source_tag": 0.04, "logo": 0.04,
    },
    "cover": {
        "header": 0.04, "headline": 0.42, "divider": 0.03,
        "body": 0.20, "graphics": 0.10, "footer": 0.10,
        "source_tag": 0.03, "logo": 0.08,
    },
    "quote": {
        "header": 0.02, "headline": 0.10, "divider": 0.00,
        "body": 0.58, "graphics": 0.00, "footer": 0.16,
        "source_tag": 0.06, "logo": 0.08,
    },
    "comparison": {
        "header": 0.06, "headline": 0.18, "divider": 0.02,
        "body": 0.50, "graphics": 0.10, "footer": 0.08,
        "source_tag": 0.03, "logo": 0.03,
    },
    "timeline": {
        "header": 0.06, "headline": 0.16, "divider": 0.02,
        "body": 0.10, "graphics": 0.50, "footer": 0.08,
        "source_tag": 0.03, "logo": 0.05,
    },
    "explainer": {
        "header": 0.06, "headline": 0.22, "divider": 0.02,
        "body": 0.46, "graphics": 0.10, "footer": 0.08,
        "source_tag": 0.03, "logo": 0.03,
    },
    "document": {
        "header": 0.08, "headline": 0.14, "divider": 0.02,
        "body": 0.56, "graphics": 0.00, "footer": 0.12,
        "source_tag": 0.04, "logo": 0.04,
    },
    "cta": {
        "header": 0.02, "headline": 0.30, "divider": 0.03,
        "body": 0.30, "graphics": 0.00, "footer": 0.20,
        "source_tag": 0.03, "logo": 0.12,
    },
}

ZONE_ORDER: Tuple[str, ...] = (
    "header", "headline", "divider", "body",
    "graphics", "footer", "source_tag", "logo",
)


@dataclass(frozen=True)
class LayoutZone:
    """A single named layout region on the canvas."""
    name: str
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def box(self) -> Tuple[float, float, float, float]:
        return (self.left, self.top, self.right, self.bottom)


def _resolve_profile(template_family: Optional[str]) -> Dict[str, float]:
    if not template_family:
        return TEMPLATE_SPACING_PROFILES["default"]
    return TEMPLATE_SPACING_PROFILES.get(
        template_family.lower(), TEMPLATE_SPACING_PROFILES["default"]
    )


_zone_cache: Dict[Tuple[str, int, int], Dict[str, LayoutZone]] = {}


def compute_layout_zones(
    template_family: Optional[str],
    canvas_size: Tuple[int, int],
    spacing: Optional[SpacingScale] = None,
) -> Dict[str, LayoutZone]:
    """
    Compute editorial layout zones (header, headline, divider, body,
    graphics, footer, source_tag, logo) for a template family and canvas
    size. Results are memoized per (family, width, height) so repeat
    renders of the same template/canvas combination reuse identical
    geometry instead of recomputing it.
    """
    cache_key = (template_family or "default", int(canvas_size[0]), int(canvas_size[1]))
    if cache_key in _zone_cache:
        return _zone_cache[cache_key]

    width, height = canvas_size
    scale = (spacing or DEFAULT_SPACING).scaled(height)
    profile = _resolve_profile(template_family)

    usable_top = scale.margin
    usable_bottom = height - scale.margin
    usable_height = max(0, usable_bottom - usable_top)
    left = scale.margin
    right = width - scale.margin

    gaps = {
        "header": scale.header_to_headline,
        "headline": scale.headline_to_divider,
        "divider": scale.divider_to_body,
        "body": scale.body_to_footer,
        "graphics": 0,
        "footer": scale.footer_to_branding,
        "source_tag": 0,
        "logo": 0,
    }

    zones: Dict[str, LayoutZone] = {}
    cursor = float(usable_top)
    for name in ZONE_ORDER:
        fraction = profile.get(name, 0.0)
        zone_height = usable_height * fraction
        if zone_height <= 0:
            continue
        top = cursor
        bottom = min(top + zone_height, usable_bottom)
        zones[name] = LayoutZone(name=name, left=left, top=top, right=right, bottom=bottom)
        cursor = bottom + gaps.get(name, 0)

    _zone_cache[cache_key] = zones
    return zones


# ---------------------------------------------------------------------------
# Optical alignment
#
# Subtle, capped adjustments only - large headlines sit slightly above
# true mathematical center, paragraphs get a lighter version of the same
# nudge, and the divider leans toward whichever neighboring block carries
# more visual weight.
# ---------------------------------------------------------------------------

def _optical_headline_offset(zone: LayoutZone, text_height: float) -> float:
    slack = max(0.0, zone.height - text_height)
    return -min(slack * 0.12, zone.height * 0.04)


def _optical_body_offset(zone: LayoutZone, text_height: float) -> float:
    slack = max(0.0, zone.height - text_height)
    return -min(slack * 0.06, zone.height * 0.02)


def _optical_divider_offset(headline_weight: float, body_weight: float) -> float:
    total = headline_weight + body_weight
    if total <= 0:
        return 0.0
    balance = (headline_weight - body_weight) / total
    return balance * 4.0  # small, subtle nudge in px


# ---------------------------------------------------------------------------
# Text measurement bridge (delegates entirely to text_fitting_engine)
# ---------------------------------------------------------------------------

def _measure_text_metrics(
    text: str,
    zone: Optional[LayoutZone],
    context_data: Dict[str, Any],
    start_size: int = 72,
    min_size: int = 12,
) -> Optional[Dict[str, Any]]:
    """
    Measure how ``text`` fits inside ``zone`` using text_fitting_engine,
    if the caller supplied what the text engine needs (a Pillow ImageDraw
    under data['draw'] and a font_loader callable under
    data['font_loader']). Returns None when those aren't available, so
    composition metadata degrades gracefully rather than erroring - the
    renderer never re-implements fitting/wrapping itself.
    """
    if fit_text is None or not text or zone is None:
        return None

    draw = context_data.get("draw")
    font_loader = context_data.get("font_loader")
    if draw is None or font_loader is None:
        return None

    cache = context_data.setdefault("_text_measure_cache", {})
    cache_key = (text, zone.name, round(zone.width), round(zone.height), start_size, min_size)
    if cache_key in cache:
        return cache[cache_key]

    font, lines, size = fit_text(
        draw, text, font_loader, zone.width, zone.height,
        start_size=start_size, min_size=min_size,
    )
    width, height, line_h = measure_lines(draw, lines, font, line_spacing=4)

    metrics = {
        "font": font,
        "lines": lines,
        "font_size": size,
        "width": width,
        "height": height,
        "line_height": line_h,
    }
    cache[cache_key] = metrics
    return metrics


# ---------------------------------------------------------------------------
# White space management
# ---------------------------------------------------------------------------

def _allocate_whitespace(
    zones: Dict[str, LayoutZone],
    text_metrics: Dict[str, Dict[str, Any]],
) -> Dict[str, float]:
    """
    If measured content overflows its zone, borrow slack from lower
    editorial priority zones (graphics, footer) before the text engine
    would otherwise need to drop a typography hierarchy level. Returns a
    per-zone extra-height allocation in px (can be negative for donors).
    """
    extra: Dict[str, float] = {name: 0.0 for name in zones}
    donors = ("graphics", "footer")

    for name, zone in zones.items():
        metrics = text_metrics.get(name)
        if not metrics:
            continue
        deficit = metrics["height"] - zone.height
        if deficit <= 0:
            continue
        for donor in donors:
            donor_zone = zones.get(donor)
            if not donor_zone:
                continue
            donor_metrics = text_metrics.get(donor)
            donor_used = donor_metrics["height"] if donor_metrics else 0.0
            donor_slack = max(0.0, donor_zone.height - donor_used)
            take = min(deficit, donor_slack * 0.5)
            if take > 0:
                extra[name] += take
                extra[donor] -= take
                deficit -= take
            if deficit <= 0:
                break

    return extra


def score_composition(
    zones: Dict[str, LayoutZone],
    text_metrics: Dict[str, Dict[str, Any]],
) -> float:
    """
    Lightweight internal score (higher is better) describing how well
    measured content fills its zones without overflow or excessive empty
    space. Internal diagnostics only, surfaced via
    context.metadata['composition']['score'] - never affects the public
    API or return values.
    """
    if not text_metrics:
        return 1.0

    score = 0.0
    count = 0
    for name, metrics in text_metrics.items():
        zone = zones.get(name)
        if not zone or zone.height <= 0:
            continue
        fill_ratio = min(1.0, metrics["height"] / zone.height)
        overflow_penalty = max(0.0, metrics["height"] - zone.height) / zone.height
        score += fill_ratio - overflow_penalty
        count += 1

    return score / count if count else 1.0


# ---------------------------------------------------------------------------
# Core pipeline types (unchanged public API)
# ---------------------------------------------------------------------------

@dataclass
class RenderContext:
    template_id: str
    data: Dict[str, Any]
    canvas: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Component:
    """Base class for reusable renderable components."""

    name = "component"

    def render(self, context: RenderContext):
        raise NotImplementedError


class Renderer:
    """
    Coordinates the rendering pipeline.

    Layout/composition metadata (zones, optical offsets, whitespace
    allocation, composition score) is computed around the existing
    component loop and stored under context.metadata['composition'].
    This is purely additive: template_id, data, canvas, and every
    previously-existing metadata key behave exactly as in 3.7.1.
    """

    def __init__(self):
        self.registry = get_registry()
        self.components: Dict[str, Component] = {}
        self.before_render: List[Callable[[RenderContext], None]] = []
        self.after_render: List[Callable[[RenderContext], None]] = []

    def register_component(self, component: Component):
        self.components[component.name] = component

    def add_before_hook(self, hook: Callable[[RenderContext], None]):
        self.before_render.append(hook)

    def add_after_hook(self, hook: Callable[[RenderContext], None]):
        self.after_render.append(hook)

    def render(self, template_id: str, data: Dict[str, Any]) -> RenderContext:
        template = self.registry.get(template_id)

        context = RenderContext(
            template_id=template.id,
            data=data,
        )

        for hook in self.before_render:
            hook(context)

        # --- Editorial layout zones -----------------------------------
        # Consulted only for composition metadata; template selection and
        # registry behaviour are untouched.
        template_family = getattr(template, "family", None) or getattr(template, "id", None)
        canvas_size = data.get("canvas_size", (1080, 1350))
        zones = compute_layout_zones(template_family, canvas_size)
        context.metadata["composition"] = {"zones": zones}

        for component_name in template.required_components:
            component = self.components.get(component_name)
            if component is None:
                raise RuntimeError(
                    f"Required component '{component_name}' is not registered."
                )
            component.render(context)

        # --- Optical alignment, white space, and scoring ----------------
        # Only runs when a draw/font_loader were supplied on data (i.e. an
        # actual rendering pass, not a metadata-only dry run), so behaviour
        # for existing lightweight callers is unchanged.
        text_metrics = context.metadata.get("_text_metrics", {})
        if text_metrics:
            offsets: Dict[str, float] = {}
            if "headline" in text_metrics and "headline" in zones:
                offsets["headline"] = _optical_headline_offset(
                    zones["headline"], text_metrics["headline"]["height"]
                )
            if "body" in text_metrics and "body" in zones:
                offsets["body"] = _optical_body_offset(
                    zones["body"], text_metrics["body"]["height"]
                )
            if "divider" in zones:
                offsets["divider"] = _optical_divider_offset(
                    text_metrics.get("headline", {}).get("height", 0.0),
                    text_metrics.get("body", {}).get("height", 0.0),
                )

            context.metadata["composition"]["optical_offsets"] = offsets
            context.metadata["composition"]["whitespace"] = _allocate_whitespace(
                zones, text_metrics
            )
            context.metadata["composition"]["score"] = score_composition(zones, text_metrics)

        for hook in self.after_render:
            hook(context)

        return context


# ---------------------------------------------------------------------------
# Components (unchanged four, plus additive new ones)
# ---------------------------------------------------------------------------

class HeadlineComponent(Component):
    name = "headline"

    def render(self, context: RenderContext):
        text = context.data.get("headline", "")
        context.metadata["headline"] = text

        zones = context.metadata.get("composition", {}).get("zones", {})
        metrics = _measure_text_metrics(text, zones.get("headline"), context.data, start_size=88)
        if metrics is not None:
            context.metadata.setdefault("_text_metrics", {})["headline"] = metrics
            context.metadata["headline_metrics"] = metrics


class BodyComponent(Component):
    name = "body"

    def render(self, context: RenderContext):
        text = context.data.get("body", "")
        context.metadata["body"] = text

        zones = context.metadata.get("composition", {}).get("zones", {})
        metrics = _measure_text_metrics(text, zones.get("body"), context.data, start_size=48)
        if metrics is not None:
            context.metadata.setdefault("_text_metrics", {})["body"] = metrics
            context.metadata["body_metrics"] = metrics


class FooterComponent(Component):
    name = "footer"

    def render(self, context: RenderContext):
        context.metadata["footer"] = context.data.get("footer", "")


class CategoryTagComponent(Component):
    name = "category_tag"

    def render(self, context: RenderContext):
        context.metadata["category"] = context.data.get("category", "")


class HeaderComponent(Component):
    """Optional eyebrow/kicker region above the headline."""

    name = "header"

    def render(self, context: RenderContext):
        context.metadata["header"] = context.data.get("header", "")


class DividerComponent(Component):
    """Marks that a template uses a divider rule between headline and body."""

    name = "divider"

    def render(self, context: RenderContext):
        context.metadata["divider"] = context.data.get("divider", True)


class GraphicsComponent(Component):
    """Reserves/records the graphics zone (images, charts, timeline art)."""

    name = "graphics"

    def render(self, context: RenderContext):
        context.metadata["graphics"] = context.data.get("graphics", None)


class SourceTagComponent(Component):
    name = "source_tag"

    def render(self, context: RenderContext):
        context.metadata["source_tag"] = context.data.get("source_tag", "")


class LogoComponent(Component):
    name = "logo"

    def render(self, context: RenderContext):
        context.metadata["logo"] = context.data.get("logo", True)


def create_default_renderer() -> Renderer:
    renderer = Renderer()
    renderer.register_component(HeadlineComponent())
    renderer.register_component(BodyComponent())
    renderer.register_component(FooterComponent())
    renderer.register_component(CategoryTagComponent())
    # Additive: only used if a template's required_components asks for
    # them by name. Existing templates are unaffected.
    renderer.register_component(HeaderComponent())
    renderer.register_component(DividerComponent())
    renderer.register_component(GraphicsComponent())
    renderer.register_component(SourceTagComponent())
    renderer.register_component(LogoComponent())
    return renderer
