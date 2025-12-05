from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class NodeSpec:
    name: str
    category: str  # "事件节点" | "执行节点" | "查询节点" | "运算节点" | "流程控制节点" | "复合节点"
    scopes: List[str] = field(default_factory=list)  # ["server"], ["client"], 或两者
    inputs: List[Tuple[str, str]] = field(default_factory=list)  # [(端口名, 类型)]，类型示例："流程"、"布尔"、"泛型"、"整数"...
    outputs: List[Tuple[str, str]] = field(default_factory=list)  # [(端口名, 类型)]
    description: str = ""
    mount_restrictions: List[str] = field(default_factory=list)
    doc_reference: str = ""
    dynamic_port_type: str = ""  # 用于动态端口（如多分支）：默认端口类型，如"流程"
    aliases: List[str] = field(default_factory=list)  # 名称同义词（可选）
    input_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    output_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    # 输入/输出端口的枚举候选项配置：{端口名: [选项1, 选项2, ...]}
    input_enum_options: Dict[str, List[str]] = field(default_factory=dict)
    output_enum_options: Dict[str, List[str]] = field(default_factory=dict)


def node_spec(
    *,
    name: str,
    category: str,
    scopes: List[str] | None = None,
    inputs: List[Tuple[str, str]] | None = None,
    outputs: List[Tuple[str, str]] | None = None,
    description: str = "",
    mount_restrictions: List[str] | None = None,
    doc_reference: str = "",
    dynamic_port_type: str = "",
    aliases: List[str] | None = None,
    input_generic_constraints: Dict[str, List[str]] | None = None,
    output_generic_constraints: Dict[str, List[str]] | None = None,
    input_enum_options: Dict[str, List[str]] | None = None,
    output_enum_options: Dict[str, List[str]] | None = None,
):
    """为真实实现函数声明节点定义元数据（唯一权威）。

    参数全部为显式命名参数，避免位置参数歧义。
    """

    spec = NodeSpec(
        name=name,
        category=category,
        scopes=list(scopes) if scopes else [],
        inputs=list(inputs) if inputs else [],
        outputs=list(outputs) if outputs else [],
        description=description,
        mount_restrictions=list(mount_restrictions) if mount_restrictions else [],
        doc_reference=doc_reference,
        dynamic_port_type=dynamic_port_type,
        aliases=list(aliases) if aliases else [],
        input_generic_constraints=dict(input_generic_constraints or {}),
        output_generic_constraints=dict(output_generic_constraints or {}),
        input_enum_options=dict(input_enum_options or {}),
        output_enum_options=dict(output_enum_options or {}),
    )

    def decorator(func):
        func.__node_spec__ = spec
        return func

    return decorator
