"""
JenniWren Production Engine
qa.py

Quality assurance framework for validating rendered slides before export.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List

from .renderer import RenderContext


class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class QAIssue:
    severity: Severity
    rule: str
    message: str


@dataclass
class QAReport:
    passed: bool = True
    issues: List[QAIssue] = field(default_factory=list)

    def add(self, severity: Severity, rule: str, message: str):
        self.issues.append(QAIssue(severity, rule, message))
        if severity == Severity.ERROR:
            self.passed = False


class QARule:
    """Base QA rule."""

    name = "rule"

    def validate(self, context: RenderContext, report: QAReport):
        raise NotImplementedError


class HeadlineExistsRule(QARule):
    name = "headline_exists"

    def validate(self, context, report):
        if not context.metadata.get("headline"):
            report.add(
                Severity.ERROR,
                self.name,
                "Headline is missing."
            )


class BodyExistsRule(QARule):
    name = "body_exists"

    def validate(self, context, report):
        if not context.metadata.get("body"):
            report.add(
                Severity.WARNING,
                self.name,
                "Body copy is empty."
            )


class FooterExistsRule(QARule):
    name = "footer_exists"

    def validate(self, context, report):
        if not context.metadata.get("footer"):
            report.add(
                Severity.WARNING,
                self.name,
                "Footer is missing."
            )


class TemplateExistsRule(QARule):
    name = "template_exists"

    def validate(self, context, report):
        if not context.template_id:
            report.add(
                Severity.ERROR,
                self.name,
                "No template specified."
            )


class QAEngine:
    """
    Executes all quality assurance rules.
    """

    def __init__(self):
        self.rules: List[QARule] = []
        self.before: List[Callable] = []
        self.after: List[Callable] = []

    def register(self, rule: QARule):
        self.rules.append(rule)

    def run(self, context: RenderContext) -> QAReport:

        report = QAReport()

        for hook in self.before:
            hook(context, report)

        for rule in self.rules:
            rule.validate(context, report)

        for hook in self.after:
            hook(context, report)

        return report


def create_default_qa() -> QAEngine:

    qa = QAEngine()

    qa.register(TemplateExistsRule())
    qa.register(HeadlineExistsRule())
    qa.register(BodyExistsRule())
    qa.register(FooterExistsRule())

    return qa
