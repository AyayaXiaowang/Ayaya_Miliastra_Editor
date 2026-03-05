from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ImportResult:
    layout_id: str
    layout_name: str
    template_id: str
    template_name: str
    template_count: int
    widget_count: int


@dataclass(slots=True)
class ImportBundleResult:
    layout_id: str
    layout_name: str
    template_count: int
    widget_count: int


__all__ = [
    "ImportBundleResult",
    "ImportResult",
]

