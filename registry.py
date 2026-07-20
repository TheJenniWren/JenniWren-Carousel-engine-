"""
JenniWren Production Engine
registry.py

Central registry of all carousel templates.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TemplateDefinition:
    id: str
    name: str
    family: str
    module: str
    description: str
    supports_cover: bool = False
    required_components: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


class TemplateRegistry:
    def __init__(self):
        self._templates: Dict[str, TemplateDefinition] = {}

    def register(self, template: TemplateDefinition):
        if template.id in self._templates:
            raise ValueError(f"Template '{template.id}' already registered.")
        self._templates[template.id] = template

    def get(self, template_id: str) -> TemplateDefinition:
        if template_id not in self._templates:
            raise KeyError(f"Unknown template: {template_id}")
        return self._templates[template_id]

    def list(self) -> List[TemplateDefinition]:
        return list(self._templates.values())

    def by_family(self, family: str) -> List[TemplateDefinition]:
        return [t for t in self._templates.values() if t.family == family]


registry = TemplateRegistry()

DEFAULT_TEMPLATES = [
    TemplateDefinition(
        id="COV-01",
        name="Political Stakes Cover",
        family="COV",
        module="templates.cov_01",
        description="Primary editorial cover slide.",
        supports_cover=True,
        required_components=["headline", "category_tag", "footer"],
        tags=["cover"],
    ),
    TemplateDefinition(
        id="DATA-01",
        name="Big Number",
        family="DATA",
        module="templates.data_01",
        description="Large statistic with supporting copy.",
        required_components=["headline", "body", "footer"],
        tags=["data"],
    ),
    TemplateDefinition(
        id="COMP-01",
        name="Comparison",
        family="COMP",
        module="templates.comp_01",
        description="Side-by-side comparison.",
        required_components=["headline", "body", "footer"],
        tags=["comparison"],
    ),
]

for template in DEFAULT_TEMPLATES:
    registry.register(template)


def get_registry() -> TemplateRegistry:
    return registry


def find(template_id: str) -> Optional[TemplateDefinition]:
    try:
        return registry.get(template_id)
    except KeyError:
        return None
