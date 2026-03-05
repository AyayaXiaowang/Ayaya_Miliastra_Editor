from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.models import TodoItem
from app.models.todo_detail_info_accessors import get_graph_id
from app.runtime.services.graph_data_service import get_shared_graph_data_service
from engine.graph.models.graph_model import GraphModel


class TodoTreeSourceTooltipProvider:
    """为图相关步骤提供“源码定位”提示（tooltip）。

    提示内容依赖资源管理器加载节点图源码，并结合 GraphModel 中节点的 source_lineno
    元信息推导更精确的行号。该类负责缓存，避免频繁 IO。
    """

    def __init__(
        self,
        graph_expand_dependency_getter,
    ) -> None:
        self._graph_expand_dependency_getter = graph_expand_dependency_getter
        self._graph_source_lines_cache: Dict[str, List[str]] = {}
        self._source_tooltip_cache: Dict[str, str] = {}
        # graph_id -> GraphModel（避免对每个 todo 反复 deserialize 导致卡顿）
        self._graph_model_cache: Dict[str, GraphModel] = {}
        # graph_id -> (graph_data, graph_file_path_display)
        self._graph_payload_cache: Dict[str, Tuple[Dict[str, Any], str]] = {}

    def _resolve_dependency_context(self) -> Tuple[Optional[Any], Optional[Any]]:
        if self._graph_expand_dependency_getter is None:
            return (None, None)
        dependencies = self._graph_expand_dependency_getter()
        if not isinstance(dependencies, tuple) or len(dependencies) < 2:
            return (None, None)
        _package = dependencies[0]
        resource_manager = dependencies[1]
        package_index_manager = dependencies[2] if len(dependencies) >= 3 else None
        return (resource_manager, package_index_manager)

    def get_tooltip_for_todo(self, todo: TodoItem) -> str:
        """为图相关步骤构建源码定位提示（悬停时显示）。"""
        cached = self._source_tooltip_cache.get(todo.todo_id)
        if isinstance(cached, str):
            return cached

        graph_id = get_graph_id(todo)
        if not graph_id:
            self._source_tooltip_cache[todo.todo_id] = ""
            return ""

        resource_manager, package_index_manager = self._resolve_dependency_context()
        if resource_manager is None:
            self._source_tooltip_cache[todo.todo_id] = ""
            return ""

        graph_data: Dict[str, Any]
        file_display: str
        cached_payload = self._graph_payload_cache.get(graph_id)
        if cached_payload is not None:
            graph_data, file_display = cached_payload
        else:
            graph_data_service = get_shared_graph_data_service(
                resource_manager, package_index_manager
            )
            graph_config = graph_data_service.get_graph_config(graph_id)
            if graph_config is None:
                self._source_tooltip_cache[todo.todo_id] = ""
                return ""
            graph_data = graph_config.data
            graph_file_path = resource_manager.get_graph_file_path(graph_id)
            file_display = str(graph_file_path) if graph_file_path is not None else ""
            self._graph_payload_cache[graph_id] = (graph_data, file_display)

        model = self._graph_model_cache.get(graph_id)
        if model is None:
            model = GraphModel.deserialize(graph_data)
            self._graph_model_cache[graph_id] = model

        graph_file_path = resource_manager.get_graph_file_path(graph_id)

        detail_info = todo.detail_info or {}
        related_node_ids = self._collect_related_node_ids(detail_info)
        if not related_node_ids:
            if not file_display:
                self._source_tooltip_cache[todo.todo_id] = ""
                return ""
            lines: List[str] = []
            if graph_id in self._graph_source_lines_cache:
                lines = self._graph_source_lines_cache[graph_id]
            else:
                if graph_file_path is not None and graph_file_path.exists():
                    text = graph_file_path.read_text(encoding="utf-8")
                    lines = text.splitlines()
                    self._graph_source_lines_cache[graph_id] = lines
            header_lines = [f"节点图文件：{file_display}"]
            if lines:
                header_lines.append("（该步骤未直接关联具体节点，可在文件中按节点名搜索）")
            tooltip_value = "\n".join(header_lines)
            self._source_tooltip_cache[todo.todo_id] = tooltip_value
            return tooltip_value

        lines_for_graph: List[str] = []
        if graph_id in self._graph_source_lines_cache:
            lines_for_graph = self._graph_source_lines_cache[graph_id]
        else:
            if graph_file_path is not None and graph_file_path.exists():
                text = graph_file_path.read_text(encoding="utf-8")
                lines_for_graph = text.splitlines()
                self._graph_source_lines_cache[graph_id] = lines_for_graph

        tooltip_lines: List[str] = []
        if file_display:
            tooltip_lines.append(f"节点图文件：{file_display}")
        tooltip_lines.append("关联节点：")

        for node_identifier in related_node_ids:
            node_object = model.nodes.get(str(node_identifier))
            if node_object is None:
                tooltip_lines.append(f"- 节点 id={node_identifier}（未在当前图中找到）")
                continue

            title_text = str(getattr(node_object, "title", "") or "")
            category_text = str(getattr(node_object, "category", "") or "")
            source_start = int(getattr(node_object, "source_lineno", 0) or 0)
            source_end = int(getattr(node_object, "source_end_lineno", 0) or 0)

            header_parts: List[str] = []
            if title_text:
                header_parts.append(title_text)
            if category_text:
                header_parts.append(f"（{category_text}）")
            header_parts.append(f" id={node_object.id}")
            header_text = "".join(header_parts)

            best_line = source_start if source_start > 0 else 0
            if lines_for_graph:
                search_start = source_start if source_start > 0 else 1
                if search_start < 1:
                    search_start = 1
                search_end = source_end if source_end >= search_start else search_start
                if search_end > len(lines_for_graph):
                    search_end = len(lines_for_graph)
                if search_end < search_start:
                    search_end = search_start
                found_line = 0
                if title_text:
                    for line_number in range(search_start, search_end + 1):
                        line_text = lines_for_graph[line_number - 1]
                        if title_text in line_text:
                            found_line = line_number
                            break
                if found_line > 0:
                    best_line = found_line

            line_desc = f"第 {best_line} 行" if best_line > 0 else "行号未知（节点未携带可用的源代码行信息）"

            tooltip_lines.append(f"- {header_text}")
            tooltip_lines.append(f"  源码行号：{line_desc}")

        tooltip_text = "\n".join(tooltip_lines)
        self._source_tooltip_cache[todo.todo_id] = tooltip_text
        return tooltip_text

    @staticmethod
    def _collect_related_node_ids(detail_info: Dict[str, Any]) -> List[str]:
        candidate_keys = [
            "node_id",
            "src_node",
            "dst_node",
            "target_node_id",
            "data_node_id",
            "prev_node_id",
            "node1_id",
            "node2_id",
            "branch_node_id",
        ]
        result: List[str] = []
        for key in candidate_keys:
            if key not in detail_info:
                continue
            raw_value = detail_info.get(key)
            if raw_value is None:
                continue
            value_text = str(raw_value)
            if not value_text:
                continue
            if value_text in result:
                continue
            result.append(value_text)
        return result


__all__ = ["TodoTreeSourceTooltipProvider"]


