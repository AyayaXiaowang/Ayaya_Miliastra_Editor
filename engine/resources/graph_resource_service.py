"""节点图资源服务 - 负责图的解析、生成与缓存。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from engine.configs.resource_types import ResourceType
from engine.configs.settings import settings
from engine.graph.models.graph_model import GraphModel
from engine.graph.utils.metadata_extractor import extract_metadata_from_code
from engine.layout import LayoutService
from engine.nodes.node_registry import get_node_registry
from engine.resources.graph_cache_manager import GraphCacheManager
from engine.utils.cache.fingerprint import (
    build_graph_fingerprints_for_model,
    compute_layout_signature_for_model,
)
from engine.utils.logging.logger import log_error, log_info
from .resource_cache_service import ResourceCacheService
from .resource_file_ops import ResourceFileOps
from .resource_state import ResourceIndexState

if TYPE_CHECKING:
    from engine.graph import ExecutableCodeGenerator, GraphCodeParser
    from engine.validate import RoundtripValidator


class GraphResourceService:
    """节点图专用服务：负责 .py 解析、自动布局、代码生成与往返校验及缓存。"""

    def __init__(
        self,
        workspace_path: Path,
        file_ops: ResourceFileOps,
        cache_service: ResourceCacheService,
        graph_cache_manager: GraphCacheManager,
        index_state: ResourceIndexState,
    ) -> None:
        self.workspace_path = workspace_path
        self._file_ops = file_ops
        self._cache_service = cache_service
        self._graph_cache_manager = graph_cache_manager
        self._index_state = index_state

        self._graph_parser: Optional["GraphCodeParser"] = None
        self._code_generator: Optional["ExecutableCodeGenerator"] = None
        self._roundtrip_validator: Optional["RoundtripValidator"] = None

    def _get_graph_parser(self) -> "GraphCodeParser":
        if self._graph_parser is None:
            from engine.graph import GraphCodeParser

            registry = get_node_registry(self.workspace_path, include_composite=True)
            node_library = registry.get_library()
            self._graph_parser = GraphCodeParser(
                self.workspace_path, node_library=node_library
            )
        return self._graph_parser

    def _get_code_generator(self) -> "ExecutableCodeGenerator":
        if self._code_generator is None:
            from engine.graph import ExecutableCodeGenerator

            registry = get_node_registry(self.workspace_path, include_composite=True)
            node_library = registry.get_library()
            self._code_generator = ExecutableCodeGenerator(
                self.workspace_path, node_library=node_library
            )
        return self._code_generator

    def _get_roundtrip_validator(self) -> "RoundtripValidator":
        if self._roundtrip_validator is None:
            from engine.validate import RoundtripValidator

            registry = get_node_registry(self.workspace_path, include_composite=True)
            node_library = registry.get_library()
            self._roundtrip_validator = RoundtripValidator(
                self.workspace_path, node_library=node_library
            )
        return self._roundtrip_validator

    def save_graph(self, graph_id: str, data: dict) -> tuple[bool, Optional[Path]]:
        """保存节点图资源，返回 (是否成功, 最终文件路径)。"""
        graph_data = data.get("data", data)
        graph_model = GraphModel.deserialize(graph_data)

        metadata = {
            "graph_id": data.get("graph_id", graph_model.graph_id) or graph_id,
            "graph_name": data.get("name", graph_model.graph_name) or graph_id,
            "graph_type": data.get(
                "graph_type", graph_model.metadata.get("graph_type", "server")
            ),
            "folder_path": data.get("folder_path", ""),
            "description": data.get("description", graph_model.description) or "",
        }

        validator = self._get_roundtrip_validator()
        validation_result = validator.validate(graph_model, metadata)
        if not validation_result.success:
            log_error(
                "[保存失败] 节点图 '{}' 无法通过往返验证",
                metadata["graph_name"],
            )
            log_error("   错误类型: {}", validation_result.error_type)
            log_error("   错误信息: {}", validation_result.error_message)
            if validation_result.error_details:
                log_error("   详细信息: {}", validation_result.error_details)
            if validation_result.line_number:
                log_error("   错误行号: {}", validation_result.line_number)
            log_info("   提示: 保存已取消，原文件未被修改")
            return False, None

        generator = self._get_code_generator()
        generated_code = generator.generate_code(graph_model, metadata)

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

        with open(resource_file, "w", encoding="utf-8") as file:
            file.write(generated_code)

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

    def load_graph(self, graph_id: str) -> Optional[dict]:
        """加载节点图，带持久化与内存缓存。"""
        resource_file = self._index_state.get_file_path(ResourceType.GRAPH, graph_id)
        if resource_file is None:
            resource_file = self._file_ops.get_resource_file_path(
                ResourceType.GRAPH, graph_id, self._index_state.filename_cache
            )

        if not resource_file or not resource_file.exists():
            return None

        if resource_file.suffix != ".py":
            log_error(
                "  [ERROR] 节点图必须是类结构 Python 文件(.py)，当前文件: {}",
                resource_file,
            )
            return None

        current_mtime = resource_file.stat().st_mtime
        cache_key = (ResourceType.GRAPH, graph_id)

        cached = self._cache_service.get(cache_key, current_mtime)
        if cached is not None:
            return cached

        persisted = self._graph_cache_manager.load_persistent_graph_cache(
            graph_id, resource_file
        )
        if persisted and self._is_persistent_layout_settings_compatible(persisted):
            log_info("[缓存][图] 命中持久化缓存：{}", graph_id)
            self._cache_service.add(cache_key, persisted, current_mtime)
            return persisted

        log_info("[缓存][图] 未命中持久化缓存，开始解析与自动布局：{}", graph_id)
        parser = self._get_graph_parser()
        graph_model, metadata = parser.parse_file(resource_file)
        if (not getattr(graph_model, "graph_variables", None)) and metadata.get(
            "graph_variables"
        ):
            graph_model.graph_variables = metadata["graph_variables"]

        self._index_state.set_file_path(ResourceType.GRAPH, graph_id, resource_file)

        # 首次加载或缓存失效时：执行与编辑器“自动排版”完全等价的增强布局流程，
        # 基于克隆体计算跨块复制与几何布局，再将结果通过差分合并回当前模型，保证
        # 编辑器、节点图库与任务清单等所有使用点看到的节点/副本/连线与坐标一致。
        self._apply_enhanced_layout_to_model(graph_model)

        graph_data = graph_model.serialize()
        result_data: dict = {
            "graph_id": metadata.get("graph_id", graph_id),
            "name": metadata.get("graph_name", graph_data.get("graph_name", "")),
            "graph_type": metadata.get("graph_type", "server"),
            "folder_path": metadata.get("folder_path", ""),
            "description": metadata.get("description", ""),
            "data": graph_data,
            "metadata": {},
        }

        if settings.FINGERPRINT_ENABLED:
            try_nodes_for_sig = []
            try_nodes_for_fp = []
            for n in graph_model.nodes.values():
                node_id = getattr(n, "id", "")
                title_cn = getattr(n, "title", "")
                px, py = (float(n.pos[0]), float(n.pos[1]))
                try_nodes_for_sig.append((node_id, title_cn, px, py))
                try_nodes_for_fp.append((node_id, px, py))
            layout_sig = compute_layout_signature_for_model(try_nodes_for_sig)
            fp_map = build_graph_fingerprints_for_model(
                try_nodes_for_fp,
                k_neighbors=int(settings.FINGERPRINT_K),
                round_ratio_digits=int(settings.FINGERPRINT_ROUND_DIGITS),
            )
            items = {}
            for node_id, fp in fp_map.items():
                items[node_id] = {
                    "ratios": list(fp.ratios),
                    "nearest_distance": float(fp.nearest_distance),
                    "neighbor_count": int(fp.neighbor_count),
                    "center": [float(fp.center[0]), float(fp.center[1])],
                }
            result_data["metadata"]["fingerprints"] = {
                "version": 1,
                "layout_signature": layout_sig,
                "params": {
                    "k": int(settings.FINGERPRINT_K),
                    "round": int(settings.FINGERPRINT_ROUND_DIGITS),
                },
                "items": items,
            }

        # 记录当前布局相关设置快照（用于判断持久化缓存是否与当前布局语义兼容）
        result_data["metadata"]["layout_settings"] = self._current_layout_settings_snapshot()

        self._graph_cache_manager.save_persistent_graph_cache(
            graph_id, resource_file, result_data
        )
        self._cache_service.add(cache_key, result_data, current_mtime)
        return result_data

    def _apply_enhanced_layout_to_model(self, model: GraphModel) -> None:
        """
        使用 LayoutService 的增强布局结果更新传入模型（仅模型层，不涉及场景）。

        设计目标：
        - 与 UI 层 AutoLayoutController 使用的“克隆就地布局 + 差分合并”流程保持语义一致；
        - 在不修改 .py 源文件的前提下，为 GraphModel 注入数据副本节点、更新连线并回填坐标；
        - 仅删除在增强结果中已被清理、且标记为数据副本的节点，避免误删用户节点。
        """
        registry = get_node_registry(self.workspace_path, include_composite=True)
        node_library = registry.get_library()

        result = LayoutService.compute_layout(
            model,
            node_library=node_library,
            include_augmented_model=True,
        )
        augmented = getattr(result, "augmented_model", None)

        # 纯数据图或布局服务未返回增强模型时，退化为只回填坐标/基本块/调试信息。
        if augmented is None:
            positions = result.positions or {}
            for node_id, pos in positions.items():
                node_obj = model.nodes.get(node_id)
                if not node_obj:
                    continue
                x_pos = float(pos[0]) if len(pos) > 0 else 0.0
                y_pos = float(pos[1]) if len(pos) > 1 else 0.0
                node_obj.pos = (x_pos, y_pos)
            model.basic_blocks = list(result.basic_blocks or [])
            debug_map = result.y_debug_info or {}
            if debug_map:
                setattr(model, "_layout_y_debug_info", dict(debug_map))
            return

        original = model
        model_node_ids_before = set(original.nodes.keys())
        model_edge_ids_before = set(original.edges.keys())
        augmented_node_ids = set(augmented.nodes.keys())
        augmented_edge_ids = set(augmented.edges.keys())

        # 合并增强模型中新出现的节点（例如跨块复制产生的数据副本）。
        nodes_to_add = augmented_node_ids - model_node_ids_before
        for node_id in nodes_to_add:
            original.nodes[node_id] = augmented.nodes[node_id]

        # 合并增强模型中新出现的连线。
        edges_to_add = augmented_edge_ids - model_edge_ids_before
        for edge_id in edges_to_add:
            original.edges[edge_id] = augmented.edges[edge_id]

        # 删除在增强结果中被移除的旧连线（例如被副本间连线替换的跨块旧边）。
        edges_to_remove = model_edge_ids_before - augmented_edge_ids
        if edges_to_remove:
            for edge_id in list(edges_to_remove):
                original.edges.pop(edge_id, None)

        # 删除在增强结果中被清理掉的孤立副本节点，仅针对数据副本节点生效，避免误删用户节点。
        nodes_to_remove = model_node_ids_before - augmented_node_ids
        if nodes_to_remove:
            for node_id in list(nodes_to_remove):
                node_obj = original.nodes.get(node_id)
                if not node_obj:
                    continue
                if not getattr(node_obj, "is_data_node_copy", False):
                    continue
                # 先移除与该副本节点关联的边
                related_edge_ids = [
                    edge_id
                    for edge_id, edge in original.edges.items()
                    if edge.src_node == node_id or edge.dst_node == node_id
                ]
                for edge_id in related_edge_ids:
                    original.edges.pop(edge_id, None)
                # 再移除节点本身
                original.nodes.pop(node_id, None)

        # 回填坐标：以增强模型中的坐标为准，确保节点与副本的最终位置与自动排版一致。
        for node_id, aug_node in augmented.nodes.items():
            node_obj = original.nodes.get(node_id)
            if not node_obj:
                continue
            pos = getattr(aug_node, "pos", (0.0, 0.0)) or (0.0, 0.0)
            x_pos = float(pos[0]) if len(pos) > 0 else 0.0
            y_pos = float(pos[1]) if len(pos) > 1 else 0.0
            node_obj.pos = (x_pos, y_pos)

        # 回填基本块与布局 Y 调试信息。
        basic_blocks = list(getattr(result, "basic_blocks", None) or augmented.basic_blocks or [])
        original.basic_blocks = basic_blocks

        debug_map_aug = getattr(augmented, "_layout_y_debug_info", None) or {}
        if debug_map_aug:
            setattr(original, "_layout_y_debug_info", dict(debug_map_aug))

    def load_graph_metadata(self, graph_id: str) -> Optional[dict]:
        """加载节点图的轻量级元数据（不执行节点图代码）。"""
        resource_file = self._index_state.get_file_path(ResourceType.GRAPH, graph_id)
        if not resource_file or not resource_file.exists():
            return None

        current_mtime = resource_file.stat().st_mtime
        cache_key = (ResourceType.GRAPH, f"{graph_id}_metadata")
        cached = self._cache_service.get(cache_key, current_mtime)
        if cached is not None:
            return cached

        with open(resource_file, "r", encoding="utf-8") as f:
            content = f.read()

        metadata_obj = extract_metadata_from_code(content)
        metadata = {
            "graph_id": metadata_obj.graph_id or graph_id,
            "name": metadata_obj.graph_name or "",
            "graph_type": metadata_obj.graph_type or "server",
            "folder_path": metadata_obj.folder_path or "",
            "description": metadata_obj.description or "",
            "node_count": 0,
            "edge_count": 0,
            "modified_time": current_mtime,
        }

        import re

        lines = content.split("\n")
        node_count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith('"""'):
                continue
            if stripped.startswith("from ") or stripped.startswith("import "):
                continue
            if stripped.startswith("with ") or stripped.startswith("class ") or stripped.startswith(
                "def "
            ):
                continue

            if "=" in stripped and "(" in stripped and ")" in stripped:
                if (
                    " == " in stripped
                    or " != " in stripped
                    or " <= " in stripped
                    or " >= " in stripped
                ):
                    continue
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    right_side = parts[1].strip()
                    if re.match(r"^[\w\u4e00-\u9fa5]+\s*\(", right_side):
                        node_count += 1
                        continue

            if "(" in stripped and ")" in stripped:
                if re.match(r"^[\w\u4e00-\u9fa5]+\s*\(", stripped):
                    node_count += 1

        metadata["node_count"] = max(0, node_count)

        edge_count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith('"""'):
                continue
            if "=" in stripped and "(" in stripped:
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    right_side = parts[1].strip()
                    param_refs = re.findall(r"=\s*([\w\u4e00-\u9fa5]+\d*)", right_side)
                    edge_count += len(param_refs)

        metadata["edge_count"] = max(0, edge_count)
        self._cache_service.add(cache_key, metadata, current_mtime)
        return metadata

    # ===== 内部：布局设置兼容性检查 =====

    def _current_layout_settings_snapshot(self) -> dict:
        """获取与布局结果相关的全局设置快照（跨块复制、紧凑排列、布局算法版本等）。"""
        from engine.configs.settings import settings

        return {
            "DATA_NODE_CROSS_BLOCK_COPY": bool(
                getattr(settings, "DATA_NODE_CROSS_BLOCK_COPY", True)
            ),
            "LAYOUT_TIGHT_BLOCK_PACKING": bool(
                getattr(settings, "LAYOUT_TIGHT_BLOCK_PACKING", True)
            ),
            # 布局算法版本号：用于在跨块复制/块归属等布局语义发生变更时主动失效旧缓存。
            "LAYOUT_ALGO_VERSION": int(getattr(settings, "LAYOUT_ALGO_VERSION", 1)),
        }

    def _is_persistent_layout_settings_compatible(self, persisted: dict) -> bool:
        """
        检查持久化缓存中的布局设置快照是否与当前全局设置兼容。

        若不兼容（例如跨块复制开关状态不同），则应视为缓存失效并重新解析+布局，
        避免出现“切换设置或重启后首次打开需要再点一次排版”的现象。
        """
        if not isinstance(persisted, dict):
            return False
        metadata = persisted.get("metadata")
        if not isinstance(metadata, dict):
            return False
        cached_settings = metadata.get("layout_settings")
        if not isinstance(cached_settings, dict):
            return False
        current = self._current_layout_settings_snapshot()
        for key, current_value in current.items():
            cached_value = cached_settings.get(key)
            # 对布尔开关保持向后兼容的布尔比较
            if isinstance(current_value, bool):
                if bool(cached_value) != current_value:
                    return False
                continue
            # 对于非布尔字段（例如布局算法版本号），使用精确相等判定，缺失或不相等即视为不兼容
            if cached_value != current_value:
                return False
        return True

    def update_persistent_graph_cache(
        self,
        graph_id: str,
        file_path: Path,
        result_data: dict,
        delta: Optional[dict] = None,
        layout_changed: Optional[bool] = None,
    ) -> dict:
        """更新图的持久化缓存并同步内存缓存，返回最终写入的数据。"""
        log_info(
            "[缓存][图] 更新持久化缓存：{}（delta={}, layout_changed={}）",
            graph_id,
            "是" if delta else "否",
            layout_changed,
        )
        final_result: dict = {}

        if delta:
            base = self._graph_cache_manager.read_persistent_graph_cache_result_data(
                graph_id
            )
            if base is None:
                base = result_data or {}
            final_result = dict(base)
            for k, v in (result_data or {}).items():
                final_result[k] = v
            delta_data = (delta or {}).get("data")
            if isinstance(delta_data, dict):
                final_data = dict(final_result.get("data") or {})
                if "nodes" in delta_data:
                    existing_nodes = final_data.get("nodes") or []
                    node_by_id = {
                        n.get("id"): n
                        for n in existing_nodes
                        if isinstance(n, dict) and "id" in n
                    }
                    for n_delta in (delta_data.get("nodes") or []):
                        node_id = n_delta.get("id")
                        if not node_id:
                            continue
                        existing = node_by_id.get(node_id, {})
                        merged = dict(existing)
                        for nk, nv in n_delta.items():
                            merged[nk] = nv
                        node_by_id[node_id] = merged
                    seen = set()
                    merged_list = []
                    for n in existing_nodes:
                        node_id = n.get("id")
                        if node_id in node_by_id and node_id not in seen:
                            merged_list.append(node_by_id[node_id])
                            seen.add(node_id)
                    for node_id, node_value in node_by_id.items():
                        if node_id not in seen:
                            merged_list.append(node_value)
                    final_data["nodes"] = merged_list
                for key in ("edges", "graph_variables"):
                    if key in delta_data:
                        final_data[key] = delta_data[key]
                final_result["data"] = final_data
            for field in ("name", "graph_type", "folder_path", "description"):
                if field in (delta or {}):
                    final_result[field] = delta[field]
            if "metadata" in (delta or {}):
                md = dict(final_result.get("metadata") or {})
                md.update(delta["metadata"])
                final_result["metadata"] = md
        else:
            final_result = result_data

        need_recompute_fp = bool(layout_changed if layout_changed is not None else True)
        if settings.FINGERPRINT_ENABLED and isinstance(final_result, dict):
            md0 = final_result.get("metadata") or {}
            has_old_fp = isinstance(md0.get("fingerprints"), dict)
            if not need_recompute_fp and has_old_fp:
                pass
            else:
                data_obj = final_result.get("data") or {}
                nodes_list = data_obj.get("nodes") or []
                try_nodes_for_sig = []
                try_nodes_for_fp = []
                for n in nodes_list:
                    node_id = n.get("id", "")
                    title_cn = n.get("title", "")
                    pos = n.get("pos", n.get("position", [0.0, 0.0]))
                    px = float(pos[0]) if len(pos) > 0 else 0.0
                    py = float(pos[1]) if len(pos) > 1 else 0.0
                    try_nodes_for_sig.append((node_id, title_cn, px, py))
                    try_nodes_for_fp.append((node_id, px, py))
                if try_nodes_for_fp:
                    layout_sig = compute_layout_signature_for_model(try_nodes_for_sig)
                    fp_map = build_graph_fingerprints_for_model(
                        try_nodes_for_fp,
                        k_neighbors=int(settings.FINGERPRINT_K),
                        round_ratio_digits=int(settings.FINGERPRINT_ROUND_DIGITS),
                    )
                    items = {}
                    for node_id, fp in fp_map.items():
                        items[node_id] = {
                            "ratios": list(fp.ratios),
                            "nearest_distance": float(fp.nearest_distance),
                            "neighbor_count": int(fp.neighbor_count),
                            "center": [
                                float(fp.center[0]),
                                float(fp.center[1]),
                            ],
                        }
                    md = final_result.get("metadata") or {}
                    md["fingerprints"] = {
                        "version": 1,
                        "layout_signature": layout_sig,
                        "params": {
                            "k": int(settings.FINGERPRINT_K),
                            "round": int(settings.FINGERPRINT_ROUND_DIGITS),
                        },
                        "items": items,
                    }
                    final_result["metadata"] = md

        # 更新布局设置快照，确保持久化缓存与当前布局开关状态（如跨块复制）一致
        if isinstance(final_result, dict):
            md2 = final_result.get("metadata") or {}
            md2["layout_settings"] = self._current_layout_settings_snapshot()
            final_result["metadata"] = md2

        self._graph_cache_manager.save_persistent_graph_cache(
            graph_id, file_path, final_result
        )
        current_mtime = file_path.stat().st_mtime
        cache_key = (ResourceType.GRAPH, graph_id)
        self._cache_service.add(cache_key, final_result, current_mtime)
        return final_result


