from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from engine.graph.models.graph_model import GraphModel
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_NAME_PORT_NAME,
)


class SignalBindingService:
    """负责 GraphModel 上的信号绑定与使用情况统计的领域服务。

    设计目标：
    - 为所有依赖 GraphModel.metadata["signal_bindings"] 的模块提供统一入口；
    - 集中实现“图内信号使用概览”“包级信号使用统计”等逻辑，避免在 UI/Todo/管理页面中重复拼装。
    """

    def get_node_signal_id(self, model: GraphModel, node_id: str) -> Optional[str]:
        """获取指定节点绑定的信号 ID（若未绑定则返回 None）。"""
        bindings_raw = model.metadata.get("signal_bindings")
        if not isinstance(bindings_raw, dict):
            return None
        info = bindings_raw.get(str(node_id))
        if not isinstance(info, dict):
            return None
        signal_id = info.get("signal_id")
        if signal_id is None:
            return None
        return str(signal_id)

    def set_node_signal_id(self, model: GraphModel, node_id: str, signal_id: str) -> None:
        """为指定节点写入信号绑定（覆盖旧值）。"""
        bindings_raw = model.metadata.get("signal_bindings")
        if not isinstance(bindings_raw, dict):
            bindings_raw = {}
            model.metadata["signal_bindings"] = bindings_raw
        bindings_raw[str(node_id)] = {"signal_id": str(signal_id)}

    def collect_graph_usage(
        self,
        model: GraphModel,
        signal_param_types_by_id: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        """收集当前图中已绑定信号的节点使用情况，供“信号概览”等视图使用。

        返回结构示例::

            [
                {
                    "signal_id": "signal_xxx",
                    "signal_name": "显示名称",
                    "defined_in_package": True,  # 若提供了 signal_param_types_by_id
                    "nodes": [
                        {"node_id": "node_1", "node_title": "发送信号"},
                        ...
                    ],
                    "node_count": 3,
                },
                ...
            ]
        """
        if not model.nodes:
            return []

        bindings_raw = model.metadata.get("signal_bindings")
        if not isinstance(bindings_raw, dict):
            bindings_raw = {}

        usage_by_signal: Dict[str, Dict[str, Any]] = {}

        for node_id, node in model.nodes.items():
            title = getattr(node, "title", "") or ""
            if title not in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
                continue

            binding = bindings_raw.get(node_id) or {}
            if not isinstance(binding, dict):
                continue

            signal_id_raw = binding.get("signal_id")
            if not signal_id_raw:
                continue
            signal_id = str(signal_id_raw)

            input_constants = getattr(node, "input_constants", {}) or {}
            signal_name_const = ""
            if isinstance(input_constants, dict) and SIGNAL_NAME_PORT_NAME in input_constants:
                signal_name_const = str(input_constants.get(SIGNAL_NAME_PORT_NAME) or "")

            entry = usage_by_signal.get(signal_id)
            if entry is None:
                entry = {
                    "signal_id": signal_id,
                    "signal_name": signal_name_const,
                    "nodes": [],
                }
                if signal_param_types_by_id:
                    entry["defined_in_package"] = signal_id in signal_param_types_by_id
                usage_by_signal[signal_id] = entry

            if signal_name_const and not entry.get("signal_name"):
                entry["signal_name"] = signal_name_const

            nodes_list = entry.setdefault("nodes", [])
            nodes_list.append(
                {
                    "node_id": node_id,
                    "node_title": title,
                }
            )

        if not usage_by_signal:
            return []

        result: List[Dict[str, Any]] = []
        for entry in usage_by_signal.values():
            nodes_list = entry.get("nodes") or []
            entry["node_count"] = len(nodes_list)
            result.append(entry)

        result.sort(
            key=lambda item: (
                str(item.get("signal_name") or ""),
                str(item.get("signal_id") or ""),
            )
        )
        return result

    def build_package_usage_stats(self, package) -> Dict[str, Dict[str, int]]:
        """基于包视图构建 {signal_id: {'graph_count': N, 'node_count': M}} 统计信息。

        该方法用于管理面板与存档库中展示“每个信号在哪些图中被使用”。
        """
        from engine.validate.comprehensive_rules.helpers import iter_all_package_graphs

        resource_manager = getattr(package, "resource_manager", None)
        templates = getattr(package, "templates", None)
        instances = getattr(package, "instances", None)
        level_entity = getattr(package, "level_entity", None)
        if resource_manager is None or templates is None or instances is None:
            return {}

        raw_usage: Dict[str, Dict[str, Any]] = {}
        for attachment in iter_all_package_graphs(
            resource_manager,
            templates,
            instances,
            level_entity,
        ):
            graph_config = attachment.graph_config
            if getattr(graph_config, "graph_type", "") != "server":
                continue
            graph_data = graph_config.data or {}
            metadata = graph_data.get("metadata") or {}
            bindings = metadata.get("signal_bindings") or {}
            if not isinstance(bindings, dict):
                continue
            graph_id = attachment.graph_id
            for _node_id, binding in bindings.items():
                if not isinstance(binding, dict):
                    continue
                signal_id_raw = binding.get("signal_id")
                if not signal_id_raw:
                    continue
                signal_id = str(signal_id_raw)
                entry = raw_usage.setdefault(
                    signal_id,
                    {"node_count": 0, "graph_ids": set()},
                )
                entry["node_count"] = int(entry.get("node_count", 0)) + 1
                graph_ids = entry.get("graph_ids")
                if isinstance(graph_ids, set):
                    graph_ids.add(graph_id)
                else:
                    entry["graph_ids"] = {graph_id}

        if not raw_usage:
            return {}

        result: Dict[str, Dict[str, int]] = {}
        for signal_id, data in raw_usage.items():
            graph_ids_any = data.get("graph_ids")
            if isinstance(graph_ids_any, set):
                graph_count = len(graph_ids_any)
            else:
                graph_count = 0
            node_count = int(data.get("node_count", 0))
            result[signal_id] = {
                "graph_count": graph_count,
                "node_count": node_count,
            }
        return result


_default_binding_service: SignalBindingService | None = None


def get_default_signal_binding_service() -> SignalBindingService:
    """获取进程级默认的信号绑定服务实例。"""
    global _default_binding_service
    if _default_binding_service is None:
        _default_binding_service = SignalBindingService()
    return _default_binding_service


