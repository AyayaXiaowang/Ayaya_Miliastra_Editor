from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ExtractedSpec:
    file_path: Path
    # 节点实现函数名（Python 标识符），用于在运行时从模块中定位具体实现
    function_name: str = ""
    name: Optional[str] = None
    category: Optional[str] = None
    semantic_id: str = ""
    inputs: List[List[Any]] = field(default_factory=list)
    outputs: List[List[Any]] = field(default_factory=list)
    description: str = ""
    mount_restrictions: List[str] = field(default_factory=list)
    doc_reference: str = ""
    dynamic_port_type: str = ""
    scopes: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    # 端口别名：{当前端口名: [历史端口名1, ...]}，用于兼容端口改名
    input_port_aliases: Dict[str, List[str]] = field(default_factory=dict)
    output_port_aliases: Dict[str, List[str]] = field(default_factory=dict)
    input_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    output_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    # 直接从 @node_spec 抽取的输入/输出端口枚举候选项
    input_enum_options: Dict[str, List[str]] = field(default_factory=dict)
    output_enum_options: Dict[str, List[str]] = field(default_factory=dict)
    # 输入端口默认值：{端口名: 默认值}
    input_defaults: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["file_path"] = self.file_path
        return data

    @staticmethod
    def from_dict(item: Dict[str, Any]) -> "ExtractedSpec":
        return ExtractedSpec(
            file_path=item.get("file_path"),
            function_name=str(item.get("function_name") or ""),
            name=item.get("name"),
            category=item.get("category"),
            semantic_id=str(item.get("semantic_id") or ""),
            inputs=list(item.get("inputs") or []),
            outputs=list(item.get("outputs") or []),
            description=str(item.get("description") or ""),
            mount_restrictions=list(item.get("mount_restrictions") or []),
            doc_reference=str(item.get("doc_reference") or ""),
            dynamic_port_type=str(item.get("dynamic_port_type") or ""),
            scopes=list(item.get("scopes") or []),
            aliases=list(item.get("aliases") or []),
            input_port_aliases=dict(item.get("input_port_aliases") or {}),
            output_port_aliases=dict(item.get("output_port_aliases") or {}),
            input_generic_constraints=dict(item.get("input_generic_constraints") or {}),
            output_generic_constraints=dict(item.get("output_generic_constraints") or {}),
            input_enum_options=dict(item.get("input_enum_options") or {}),
            output_enum_options=dict(item.get("output_enum_options") or {}),
            input_defaults=dict(item.get("input_defaults") or {}),
        )


@dataclass
class NormalizedSpec:
    file_path: Path
    # 节点实现函数名（Python 标识符），用于在运行时从模块中定位具体实现
    function_name: str
    standard_key: str
    category_standard: str
    name: str
    semantic_id: str = ""
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
    # 端口别名：{当前端口名: [历史端口名1, ...]}，用于兼容端口改名
    input_port_aliases: Dict[str, List[str]] = field(default_factory=dict)
    output_port_aliases: Dict[str, List[str]] = field(default_factory=dict)
    input_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    output_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    # 规范化后透传的枚举候选项（键仍为端口名）
    input_enum_options: Dict[str, List[str]] = field(default_factory=dict)
    output_enum_options: Dict[str, List[str]] = field(default_factory=dict)
    # 输入端口默认值：{端口名: 默认值}
    input_defaults: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["file_path"] = self.file_path
        return data

    @staticmethod
    def from_dict(item: Dict[str, Any]) -> "NormalizedSpec":
        return NormalizedSpec(
            file_path=item.get("file_path"),
            function_name=str(item.get("function_name") or ""),
            standard_key=str(item.get("standard_key") or ""),
            category_standard=str(item.get("category_standard") or ""),
            name=str(item.get("name") or ""),
            semantic_id=str(item.get("semantic_id") or ""),
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
            input_port_aliases=dict(item.get("input_port_aliases") or {}),
            output_port_aliases=dict(item.get("output_port_aliases") or {}),
            input_generic_constraints=dict(item.get("input_generic_constraints") or {}),
            output_generic_constraints=dict(item.get("output_generic_constraints") or {}),
            input_enum_options=dict(item.get("input_enum_options") or {}),
            output_enum_options=dict(item.get("output_enum_options") or {}),
            input_defaults=dict(item.get("input_defaults") or {}),
        )


