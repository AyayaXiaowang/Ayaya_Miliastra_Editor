"""节点图保存器（代码生成 + 往返校验 + 写盘）。

职责：
- 将 GraphModel + metadata 通过应用层 code_generator 生成 `.py` 源码
- 使用 RoundtripValidator 做“往返校验”，失败则取消保存
- 处理重命名/移动导致的旧文件删除与索引状态更新
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Protocol, TYPE_CHECKING

from engine.configs.resource_types import ResourceType
from engine.graph.models.graph_model import GraphModel
from engine.nodes.node_registry import get_node_registry
from engine.utils.logging.logger import log_error, log_info

from .resource_cache_service import ResourceCacheService
from .resource_file_ops import ResourceFileOps
from .resource_state import ResourceIndexState

if TYPE_CHECKING:
    from engine.validate import RoundtripValidator


class GraphCodeGenerator(Protocol):
    def generate_code(self, graph_model: GraphModel, metadata: Optional[Dict[str, Any]] = None) -> str: ...


class GraphSaver:
    """节点图保存器：负责写盘与往返校验。"""

    def __init__(
        self,
        workspace_path: Path,
        *,
        file_ops: ResourceFileOps,
        cache_service: ResourceCacheService,
        index_state: ResourceIndexState,
        graph_code_generator: Optional[GraphCodeGenerator],
    ) -> None:
        self._workspace_path = workspace_path
        self._file_ops = file_ops
        self._cache_service = cache_service
        self._index_state = index_state
        self._graph_code_generator = graph_code_generator

        self._roundtrip_validator: Optional["RoundtripValidator"] = None

    def save_graph(self, graph_id: str, data: dict) -> tuple[bool, Optional[Path]]:
        """保存节点图资源，返回 (是否成功, 最终文件路径)。"""
        if self._graph_code_generator is None:
            raise ValueError(
                "GraphResourceService.save_graph 需要注入 graph_code_generator（应用层生成器），"
                "请从 app 层构造 ResourceManager 时传入。"
            )

        graph_data = data.get("data", data)
        graph_model = GraphModel.deserialize(graph_data)

        metadata = {
            "graph_id": data.get("graph_id", graph_model.graph_id) or graph_id,
            "graph_name": data.get("name", graph_model.graph_name) or graph_id,
            "graph_type": data.get("graph_type", graph_model.metadata.get("graph_type", "server")),
            "folder_path": data.get("folder_path", ""),
            "description": data.get("description", graph_model.description) or "",
        }

        validator = self._get_roundtrip_validator()
        validation_result = validator.validate(graph_model, metadata)
        if not validation_result.success:
            log_error("[保存失败] 节点图 '{}' 无法通过往返验证", metadata["graph_name"])
            log_error("   错误类型: {}", validation_result.error_type)
            log_error("   错误信息: {}", validation_result.error_message)
            if validation_result.error_details:
                log_error("   详细信息: {}", validation_result.error_details)
            if validation_result.line_number:
                log_error("   错误行号: {}", validation_result.line_number)
            log_info("   提示: 保存已取消，原文件未被修改")
            return False, None

        generated_code = self._graph_code_generator.generate_code(graph_model, metadata)

        resource_name = metadata["graph_name"]
        resource_file = self._file_ops.get_resource_file_path(
            ResourceType.GRAPH,
            graph_id,
            self._index_state.filename_cache,
            extension=".py",
            graph_metadata=metadata,
            resource_name=resource_name,
        )

        resource_file.parent.mkdir(parents=True, exist_ok=True)

        old_file = self._index_state.get_file_path(ResourceType.GRAPH, graph_id)
        if old_file and old_file.exists() and old_file != resource_file:
            old_file.unlink()
            log_info("  [移动/重命名] 已删除旧位置文件: {}", old_file)

        with open(resource_file, "w", encoding="utf-8") as file_obj:
            file_obj.write(generated_code)

        log_info(
            "  [OK] 已保存节点图代码: {}",
            resource_file.relative_to(self._file_ops.resource_library_dir),
        )

        json_file = resource_file.with_suffix(".json")
        if json_file.exists():
            json_file.unlink()
            log_info("  [清理] 已删除旧的JSON文件: {}", json_file.name)

        self._index_state.set_filename(ResourceType.GRAPH, graph_id, resource_file.stem)
        self._index_state.set_file_path(ResourceType.GRAPH, graph_id, resource_file)

        current_mtime = resource_file.stat().st_mtime
        cache_key = (ResourceType.GRAPH, graph_id)

        result_data = {
            "graph_id": metadata.get("graph_id", graph_id),
            "name": metadata.get("graph_name", graph_model.graph_name),
            "graph_type": metadata.get("graph_type", "server"),
            "folder_path": metadata.get("folder_path", ""),
            "description": metadata.get("description", ""),
            "data": graph_model.serialize(),
            "metadata": {},
        }

        self._cache_service.add(cache_key, result_data, current_mtime)
        return True, resource_file

    def _get_roundtrip_validator(self) -> "RoundtripValidator":
        if self._roundtrip_validator is None:
            from engine.validate import RoundtripValidator

            if self._graph_code_generator is None:
                raise ValueError(
                    "GraphResourceService.save_graph 需要注入 graph_code_generator（应用层生成器），"
                    "以避免 engine 层绑定运行时/插件导入。"
                )

            registry = get_node_registry(self._workspace_path, include_composite=True)
            node_library = registry.get_library()
            self._roundtrip_validator = RoundtripValidator(
                self._workspace_path,
                node_library=node_library,
                code_generator=self._graph_code_generator,
            )
        return self._roundtrip_validator


