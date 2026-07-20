"""
manifest.py
JenniWren Carousel Production Pipeline

Data structures for the per-run production manifest. Split out of
build_carousel.py so the orchestrator's CLI/pipeline module doesn't
also own manifest schema details -- see CHANGELOG.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SlideResult:
    slide_id: str
    template: str
    status: str                      # "exported" | "skipped_qa" | "failed"
    output_file: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slide_id": self.slide_id,
            "template": self.template,
            "status": self.status,
            "output_file": self.output_file,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class ProductionManifest:
    story: str
    generated_at: str
    templates_used: List[str]
    renderer_contract_version: str
    slides: List[SlideResult] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "story": self.story,
            "generated_at": self.generated_at,
            "renderer_contract_version": self.renderer_contract_version,
            "templates_used": self.templates_used,
            "slides": [s.to_dict() for s in self.slides],
            "validation_warnings": self.validation_warnings,
            "validation_errors": self.validation_errors,
            "summary": {
                "total_slides": len(self.slides),
                "exported": sum(1 for s in self.slides if s.status == "exported"),
                "skipped_qa": sum(1 for s in self.slides if s.status == "skipped_qa"),
                "failed": sum(1 for s in self.slides if s.status == "failed"),
            },
        }

    def write(self, output_dir: Path) -> Path:
        path = output_dir / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path
