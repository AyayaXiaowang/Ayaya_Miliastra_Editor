from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ExtractedSpec:
    file_path: Path
    name: Optional[str] = None
    category: Optional[str] = None
    inputs: List[List[Any]] = field(default_factory=list)
    outputs: List[List[Any]] = field(default_factory=list)
    description: str = ""
    mount_restrictions: List[str] = field(default_factory=list)
    doc_reference: str = ""
    dynamic_port_type: str = ""
    scopes: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    input_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    output_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["file_path"] = self.file_path
        return data

    @staticmethod
    def from_dict(item: Dict[str, Any]) -> "ExtractedSpec":
        return ExtractedSpec(
            file_path=item.get("file_path"),
            name=item.get("name"),
            category=item.get("category"),
            inputs=list(item.get("inputs") or []),
            outputs=list(item.get("outputs") or []),
            description=str(item.get("description") or ""),
            mount_restrictions=list(item.get("mount_restrictions") or []),
            doc_reference=str(item.get("doc_reference") or ""),
            dynamic_port_type=str(item.get("dynamic_port_type") or ""),
            scopes=list(item.get("scopes") or []),
            aliases=list(item.get("aliases") or []),
            input_generic_constraints=dict(item.get("input_generic_constraints") or {}),
            output_generic_constraints=dict(item.get("output_generic_constraints") or {}),
        )


@dataclass
class NormalizedSpec:
    file_path: Path
    standard_key: str
    category_standard: str
    name: str
    input_types: Dict[str, str] = field(default_factory=dict)
    output_types: Dict[str, str] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    scopes: List[str] = field(default_factory=list)
    description: str = ""
    mount_restrictions: List[str] = field(default_factory=list)
    doc_reference: str = ""
    dynamic_port_type: str = ""
    inputs: List[List[Any]] = field(default_factory=list)
    outputs: List[List[Any]] = field(default_factory=list)
    input_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    output_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["file_path"] = self.file_path
        return data

    @staticmethod
    def from_dict(item: Dict[str, Any]) -> "NormalizedSpec":
        return NormalizedSpec(
            file_path=item.get("file_path"),
            standard_key=str(item.get("standard_key") or ""),
            category_standard=str(item.get("category_standard") or ""),
            name=str(item.get("name") or ""),
            input_types=dict(item.get("input_types") or {}),
            output_types=dict(item.get("output_types") or {}),
            aliases=list(item.get("aliases") or []),
            scopes=list(item.get("scopes") or []),
            description=str(item.get("description") or ""),
            mount_restrictions=list(item.get("mount_restrictions") or []),
            doc_reference=str(item.get("doc_reference") or ""),
            dynamic_port_type=str(item.get("dynamic_port_type") or ""),
            inputs=list(item.get("inputs") or []),
            outputs=list(item.get("outputs") or []),
            input_generic_constraints=dict(item.get("input_generic_constraints") or {}),
            output_generic_constraints=dict(item.get("output_generic_constraints") or {}),
        )


