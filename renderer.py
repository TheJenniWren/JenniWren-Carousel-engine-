"""
JenniWren Production Engine
renderer.py

Core rendering engine that assembles a slide from a template,
layout regions, components, and story data.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from .registry import get_registry


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

        for component_name in template.required_components:
            component = self.components.get(component_name)
            if component is None:
                raise RuntimeError(
                    f"Required component '{component_name}' is not registered."
                )
            component.render(context)

        for hook in self.after_render:
            hook(context)

        return context


class HeadlineComponent(Component):
    name = "headline"

    def render(self, context: RenderContext):
        context.metadata["headline"] = context.data.get("headline", "")


class BodyComponent(Component):
    name = "body"

    def render(self, context: RenderContext):
        context.metadata["body"] = context.data.get("body", "")


class FooterComponent(Component):
    name = "footer"

    def render(self, context: RenderContext):
        context.metadata["footer"] = context.data.get("footer", "")


class CategoryTagComponent(Component):
    name = "category_tag"

    def render(self, context: RenderContext):
        context.metadata["category"] = context.data.get("category", "")


def create_default_renderer() -> Renderer:
    renderer = Renderer()
    renderer.register_component(HeadlineComponent())
    renderer.register_component(BodyComponent())
    renderer.register_component(FooterComponent())
    renderer.register_component(CategoryTagComponent())
    return renderer
