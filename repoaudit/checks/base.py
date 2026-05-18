"""Base types for all checks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckResult:
    """Result of a single check."""

    name: str
    category: str
    passed: bool
    severity: str  # "required" | "recommended" | "optional"
    message: str
    detail: str = field(default="")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "detail": self.detail,
        }


class Check(ABC):
    """Abstract base for a group of related checks."""

    @abstractmethod
    def run(self, repo_path: Path, language: dict) -> list[CheckResult]:
        """Run all checks in this group and return results."""
