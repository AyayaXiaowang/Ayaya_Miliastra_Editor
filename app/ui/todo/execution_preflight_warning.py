from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from app.models import TodoItem
from app.models.todo_detail_info_accessors import get_detail_type, get_graph_id


@dataclass(frozen=True)
class GraphExecutionRequiredSignal:
    signal_id: str
    signal_name: str
    defined_in_package: Optional[bool] = None
    node_count: Optional[int] = None

    def build_display_label(self) -> str:
        name_text = str(self.signal_name or "").strip()
        signal_id_text = str(self.signal_id or "").strip()
        parts: list[str] = []
        if name_text:
            parts.append(name_text)
        if signal_id_text:
            parts.append(f"({signal_id_text})")
        label = " ".join(parts) if parts else "(未命名信号)"

        if self.defined_in_package is True:
            return f"{label}（已定义）"
        if self.defined_in_package is False:
            return f"{label}（当前存档未定义）"
        return label


@dataclass(frozen=True)
class GraphExecutionPreflightSummary:
    """执行前扫描结果：用于决定是否需要弹窗提醒用户提前定义资源。"""

    graph_id: str
    includes_signal: bool
    includes_struct: bool
    includes_composite: bool
    required_signals: List[GraphExecutionRequiredSignal]

    @property
    def should_warn(self) -> bool:
        return bool(self.includes_signal or self.includes_struct or self.includes_composite)

    @property
    def suggested_signal_id_for_navigation(self) -> str:
        """用于 UI 的“跳转定位”辅助：优先选择未定义的信号，否则选择第一个可用信号。"""
        for entry in self.required_signals:
            if entry.defined_in_package is False and str(entry.signal_id or "").strip():
                return str(entry.signal_id or "").strip()
        for entry in self.required_signals:
            if str(entry.signal_id or "").strip():
                return str(entry.signal_id or "").strip()
        return ""

    def build_dialog_message(self) -> str:
        """构建给消息弹窗的中文提示文案（不依赖 Qt）。"""
        required_items: list[str] = []
        if self.includes_signal:
            required_items.append("信号")
        if self.includes_struct:
            required_items.append("结构体")
        if self.includes_composite:
            required_items.append("复合节点")

        required_caption = "、".join(required_items) if required_items else ""
        if not required_caption:
            return ""

        bullet_lines: list[str] = []
        if self.includes_signal:
            if self.required_signals:
                bullet_lines.append(
                    "- 信号：请先在【管理配置 → 信号管理】中创建或确认以下信号定义（名称与参数需一致），再开始执行："
                )
                for entry in self.required_signals[:12]:
                    bullet_lines.append(f"  - {entry.build_display_label()}")
                if len(self.required_signals) > 12:
                    bullet_lines.append(f"  - …以及另外 {len(self.required_signals) - 12} 个信号")
                if self.suggested_signal_id_for_navigation:
                    bullet_lines.append("  提示：可在弹窗中点击“前往信号管理”跳转并定位到相关信号。")
            else:
                bullet_lines.append(
                    "- 信号：请先在【管理配置 → 信号管理】中创建或确认信号定义，再开始执行"
                )
        if self.includes_struct:
            bullet_lines.append("- 结构体：请先在【结构体定义】中创建或确认结构体与字段，再开始执行")
        if self.includes_composite:
            bullet_lines.append("- 复合节点：请先在【复合节点库】中新建并保存（必要时刷新节点库），再开始执行")

        details = "\n".join(bullet_lines)
        return (
            f"当前节点图包含：{required_caption}。\n"
            "这些内容需要提前手动定义好，否则后续自动执行可能失败或结果不一致。\n\n"
            f"{details}"
        )


def inspect_graph_execution_preflight(
    todo_map: Dict[str, TodoItem],
    graph_id: str,
) -> GraphExecutionPreflightSummary:
    """扫描 todo_map，判断指定 graph_id 是否包含需要提前手动定义的内容。"""
    normalized_graph_id = str(graph_id or "")
    if not normalized_graph_id:
        return GraphExecutionPreflightSummary(
            graph_id="",
            includes_signal=False,
            includes_struct=False,
            includes_composite=False,
            required_signals=[],
        )

    includes_signal = False
    includes_struct = False
    includes_composite = False

    required_signals_map: dict[str, GraphExecutionRequiredSignal] = {}

    def _add_required_signal(
        *,
        signal_id: object,
        signal_name: object,
        defined_in_package: object,
        node_count: object,
    ) -> None:
        signal_id_text = str(signal_id or "").strip()
        signal_name_text = str(signal_name or "").strip()

        # 去重 key：优先 signal_id，否则退化到 name（尽量保持稳定）
        key = signal_id_text if signal_id_text else f"name:{signal_name_text}"
        if not key:
            return

        defined_value: Optional[bool] = None
        if isinstance(defined_in_package, bool):
            defined_value = defined_in_package

        node_count_value: Optional[int] = None
        if isinstance(node_count, int):
            node_count_value = int(node_count)
        elif isinstance(node_count, str):
            node_count_text = node_count.strip()
            if node_count_text.isdigit():
                node_count_value = int(node_count_text)

        existing = required_signals_map.get(key)
        if existing is None:
            required_signals_map[key] = GraphExecutionRequiredSignal(
                signal_id=signal_id_text,
                signal_name=signal_name_text,
                defined_in_package=defined_value,
                node_count=node_count_value,
            )
            return

        # 合并：尽量补齐缺失信息；defined_in_package 优先使用“明确 False”
        merged_signal_id = existing.signal_id or signal_id_text
        merged_signal_name = existing.signal_name or signal_name_text
        merged_defined: Optional[bool]
        if existing.defined_in_package is False or defined_value is False:
            merged_defined = False
        else:
            merged_defined = existing.defined_in_package if existing.defined_in_package is not None else defined_value
        merged_node_count = existing.node_count if existing.node_count is not None else node_count_value

        required_signals_map[key] = GraphExecutionRequiredSignal(
            signal_id=merged_signal_id,
            signal_name=merged_signal_name,
            defined_in_package=merged_defined,
            node_count=merged_node_count,
        )

    for todo in todo_map.values():
        detail_info = todo.detail_info or {}
        if get_graph_id(detail_info) != normalized_graph_id:
            continue
        detail_type = get_detail_type(detail_info)
        if detail_type in ("graph_signals_overview", "graph_bind_signal"):
            includes_signal = True
            if detail_type == "graph_signals_overview":
                signals = detail_info.get("signals", []) or []
                if isinstance(signals, list):
                    for entry in signals:
                        if not isinstance(entry, dict):
                            continue
                        _add_required_signal(
                            signal_id=entry.get("signal_id"),
                            signal_name=entry.get("signal_name"),
                            defined_in_package=entry.get("defined_in_package"),
                            node_count=entry.get("node_count"),
                        )
            if detail_type == "graph_bind_signal":
                _add_required_signal(
                    signal_id=detail_info.get("signal_id"),
                    signal_name=detail_info.get("signal_name"),
                    defined_in_package=None,
                    node_count=None,
                )
        elif detail_type == "graph_bind_struct":
            includes_struct = True
        elif detail_type == "composite_root":
            includes_composite = True

        if includes_signal and includes_struct and includes_composite:
            break

    return GraphExecutionPreflightSummary(
        graph_id=normalized_graph_id,
        includes_signal=includes_signal,
        includes_struct=includes_struct,
        includes_composite=includes_composite,
        required_signals=sorted(
            list(required_signals_map.values()),
            key=lambda entry: (
                0 if entry.defined_in_package is False else (1 if entry.defined_in_package is None else 2),
                str(entry.signal_name or "").strip().lower(),
                str(entry.signal_id or "").strip().lower(),
            ),
        ),
    )


__all__ = [
    "GraphExecutionRequiredSignal",
    "GraphExecutionPreflightSummary",
    "inspect_graph_execution_preflight",
]


