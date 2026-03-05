"""节点图加载器（解析 + 增强布局）。

职责：
- 解析 `.py` 节点图为 GraphModel + metadata
- 执行与编辑器一致的增强布局流程（克隆就地布局 + 差分合并）
- 组装 `load_graph()` 对外返回结构，并与 GraphCacheFacade 协作做缓存命中/回退
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from engine.configs.resource_types import ResourceType
from engine.graph.models.graph_model import GraphModel
from engine.graph.semantic import GraphSemanticPass
from engine.layout import LayoutService
from engine.layout.utils.augmented_layout_merge import apply_augmented_layout_merge
from engine.nodes.node_registry import get_node_registry
from engine.utils.logging.logger import log_error, log_info

from .graph_cache_facade import GraphCacheFacade
from .graph_result_data_builder import GraphResultDataBuilder
from .resource_file_ops import ResourceFileOps
from .resource_state import ResourceIndexState

if TYPE_CHECKING:
    from engine.graph import GraphCodeParser


class GraphLoader:
    """负责节点图加载（解析 + 增强布局）与缓存协商。"""

    def __init__(
        self,
        workspace_path: Path,
        *,
        file_ops: ResourceFileOps,
        index_state: ResourceIndexState,
        cache_facade: GraphCacheFacade,
        result_data_builder: GraphResultDataBuilder,
    ) -> None:
        self._workspace_path = workspace_path
        self._file_ops = file_ops
        self._index_state = index_state
        self._cache_facade = cache_facade
        self._result_data_builder = result_data_builder

        self._graph_parser: Optional["GraphCodeParser"] = None
        # GraphCodeParser 依赖 NodeRegistry 的节点库；复合节点集合随 active_package_id 变化。
        # 若切换项目存档后继续复用旧 parser，会导致缺少当前存档复合节点并在 strict 模式下解析失败。
        self._graph_parser_active_package_id: str | None = None

    def load_graph(self, graph_id: str) -> Optional[dict]:
        """加载节点图，带持久化与内存缓存。"""
        resource_file = self._resolve_graph_file_path(graph_id)
        if not resource_file or not resource_file.exists():
            return None

        if resource_file.suffix != ".py":
            log_error(
                "  [ERROR] 节点图必须是类结构 Python 文件(.py)，当前文件: {}",
                resource_file,
            )
            return None

        current_mtime = resource_file.stat().st_mtime

        cached = self._cache_facade.get_graph_from_memory_cache(graph_id, current_mtime)
        if cached is not None:
            if self._result_data_builder.ensure_folder_path_from_file(cached, resource_file=resource_file):
                self._cache_facade.store_graph_in_memory_cache(graph_id, cached, current_mtime)
            return cached

        persisted = self._cache_facade.load_persistent_graph_cache_if_compatible(graph_id, resource_file)
        if persisted:
            log_info("[缓存][图] 命中持久化缓存：{}", graph_id)
            # 为内存缓存补齐 node_defs_fp，便于后续命中时做实现变更失效判定
            meta = persisted.get("metadata")
            if not isinstance(meta, dict):
                meta = {}
                persisted["metadata"] = meta
            existing_fp = str(meta.get("node_defs_fp") or "").strip()
            if not existing_fp:
                meta["node_defs_fp"] = self._cache_facade.get_current_node_defs_fingerprint()
            self._result_data_builder.ensure_folder_path_from_file(persisted, resource_file=resource_file)

            # 重要：语义元数据（signal_bindings/struct_bindings 等）属于派生字段，且依赖
            # 结构体/信号/变量等“代码级 Schema”（随 active_package_id 作用域变化）。
            #
            # 持久化缓存仅按“图文件 mtime + 节点库指纹 + 布局设置快照”做兼容性判断，
            # 但无法覆盖 Schema 变化；因此命中持久化缓存时仍需对 GraphModel 运行一次
            # GraphSemanticPass，以刷新派生语义元数据，避免 validate_package/编辑器
            # 看到过期的 struct_bindings（常见：结构体从 ingame_save 迁移为 basic 后仍显示未绑定）。
            cached_graph_data = persisted.get("data")
            if isinstance(cached_graph_data, dict):
                needs_port_type_upgrade = False
                cached_nodes = cached_graph_data.get("nodes")
                if isinstance(cached_nodes, list) and cached_nodes:
                    for node_dict in cached_nodes:
                        if not isinstance(node_dict, dict):
                            continue
                        if ("input_types" not in node_dict) or ("output_types" not in node_dict):
                            needs_port_type_upgrade = True
                            break

                model = GraphModel.deserialize(cached_graph_data)
                GraphSemanticPass.apply(model=model)
                # 结构体节点字段端口补齐（仅新增缺失端口）：
                # - 解析 `.py` 时，结构体节点往往只在 metadata.struct_bindings 中记录 struct_id，
                #   而字段端口未显式出现在源码中；UI 会在加载结构体定义后动态补全端口。
                # - 若 graph_cache 在“端口未补齐”的模型上完成增强布局并写盘，则首次打开时会按“短节点”
                #   排版；随后 UI 补齐字段端口导致节点高度突增，出现重叠。
                # - 因此资源层在写 graph_cache 前必须把字段端口补齐，确保布局基于最终端口集合计算。
                self._ensure_struct_node_ports(model)
                # 端口类型快照属于“展示/工具链辅助数据”，可在命中持久化缓存时惰性补齐并写回，
                # 避免旧缓存长期缺少字段影响下游读取。
                registry = get_node_registry(self._workspace_path, include_composite=True)
                node_library = registry.get_library()
                self._apply_port_type_snapshots(model, node_library=node_library)
                persisted["data"] = model.serialize()
                if needs_port_type_upgrade:
                    self._cache_facade.save_persistent_graph_cache(graph_id, resource_file, persisted)

            self._cache_facade.store_graph_in_memory_cache(graph_id, persisted, current_mtime)
            return persisted

        log_info("[缓存][图] 未命中持久化缓存，开始解析与自动布局：{}", graph_id)
        parser = self._get_graph_parser()
        graph_model, metadata = parser.parse_file(resource_file)

        if (not getattr(graph_model, "graph_variables", None)) and metadata.get("graph_variables"):
            graph_model.graph_variables = metadata["graph_variables"]

        self._index_state.set_file_path(ResourceType.GRAPH, graph_id, resource_file)

        # 结构体节点字段端口补齐：确保增强布局在“最终端口集合”下计算，避免 UI 后续补齐端口后发生重叠。
        self._ensure_struct_node_ports(graph_model)

        # 首次加载或缓存失效时：执行与编辑器“自动排版”完全等价的增强布局流程
        self._apply_enhanced_layout_to_model(graph_model)

        result_data = self._result_data_builder.build_result_data(
            graph_id=graph_id,
            graph_model=graph_model,
            parsed_metadata=metadata,
            resource_file=resource_file,
        )

        self._cache_facade.save_persistent_graph_cache(graph_id, resource_file, result_data)
        self._cache_facade.store_graph_in_memory_cache(graph_id, result_data, current_mtime)
        return result_data

    # ===== 内部：文件路径解析 =====

    def _resolve_graph_file_path(self, graph_id: str) -> Optional[Path]:
        resource_file = self._index_state.get_file_path(ResourceType.GRAPH, graph_id)
        if resource_file is None:
            resource_file = self._file_ops.get_resource_file_path(
                ResourceType.GRAPH, graph_id, self._index_state.filename_cache
            )
        return resource_file

    # ===== 内部：解析器惰性初始化 =====

    def _get_graph_parser(self) -> "GraphCodeParser":
        from engine.utils.runtime_scope import get_active_package_id

        current_active_package_id = get_active_package_id()
        if (
            self._graph_parser is None
            or current_active_package_id != self._graph_parser_active_package_id
        ):
            from engine.graph import GraphCodeParser

            registry = get_node_registry(self._workspace_path, include_composite=True)
            node_library = registry.get_library()
            self._graph_parser = GraphCodeParser(
                self._workspace_path,
                node_library=node_library,
            )
            self._graph_parser_active_package_id = current_active_package_id
        return self._graph_parser

    # ===== 内部：增强布局差分合并 =====

    def _apply_enhanced_layout_to_model(self, model: GraphModel) -> None:
        """
        使用 LayoutService 的增强布局结果更新传入模型（仅模型层，不涉及场景）。

        设计目标：
        - 与 UI 层 AutoLayoutController 使用的“克隆就地布局 + 差分合并”流程保持语义一致；
        - 在不修改 .py 源文件的前提下，为 GraphModel 注入数据副本节点、更新连线并回填坐标；
        - 仅删除在增强结果中已被清理、且标记为数据副本的节点，避免误删用户节点。
        """
        registry = get_node_registry(self._workspace_path, include_composite=True)
        node_library = registry.get_library()

        result = LayoutService.compute_layout(
            model,
            node_library=node_library,
            include_augmented_model=True,
            workspace_path=self._workspace_path,
        )
        apply_augmented_layout_merge(
            model,
            result,
            allow_fallback_without_augmented=True,
        )
        self._apply_port_type_snapshots(model, node_library=node_library)

    @staticmethod
    def _extract_struct_field_names(struct_payload: dict) -> list[str]:
        """从结构体定义 payload 中提取字段名列表（保持出现顺序）。"""
        names: list[str] = []

        value_entries = struct_payload.get("value")
        if isinstance(value_entries, list):
            for entry in value_entries:
                if not isinstance(entry, dict):
                    continue
                raw_name = entry.get("key")
                name = str(raw_name).strip() if isinstance(raw_name, str) else ""
                if name:
                    names.append(name)
            return names

        fields_entries = struct_payload.get("fields")
        if isinstance(fields_entries, list):
            for entry in fields_entries:
                if not isinstance(entry, dict):
                    continue
                raw_name = entry.get("field_name")
                name = str(raw_name).strip() if isinstance(raw_name, str) else ""
                if name:
                    names.append(name)
        return names

    @classmethod
    def _ensure_struct_node_ports(cls, model: GraphModel) -> None:
        """为结构体节点补齐字段端口（仅新增缺失端口，不主动删除）。

        说明：
        - UI 在打开图时会基于 `metadata["struct_bindings"]` 与结构体定义补全字段端口；
        - 资源层在生成 graph_cache（尤其是首次解析+自动布局）时也必须执行同样的补齐，
          否则布局会按“短节点”计算并写盘，UI 后续补齐端口导致节点高度突增而重叠。
        """
        struct_bindings = model.get_struct_bindings()
        if not struct_bindings:
            return

        from engine.graph.common import (
            STRUCT_BUILD_NODE_TITLE,
            STRUCT_BUILD_STATIC_INPUTS,
            STRUCT_MODIFY_NODE_TITLE,
            STRUCT_MODIFY_STATIC_INPUTS,
            STRUCT_NODE_TITLES,
            STRUCT_SPLIT_NODE_TITLE,
            STRUCT_SPLIT_STATIC_OUTPUTS,
        )
        from engine.resources.definition_schema_view import get_default_definition_schema_view

        schema_view = get_default_definition_schema_view()
        struct_definitions = schema_view.get_all_struct_definitions() or {}
        if not isinstance(struct_definitions, dict) or not struct_definitions:
            return

        for node in (getattr(model, "nodes", None) or {}).values():
            node_id = str(getattr(node, "id", "") or "")
            node_title = str(getattr(node, "title", "") or "")
            if not node_id or node_title not in STRUCT_NODE_TITLES:
                continue

            binding = struct_bindings.get(node_id)
            if not isinstance(binding, dict):
                continue

            struct_id_value = binding.get("struct_id")
            struct_id = str(struct_id_value).strip() if struct_id_value is not None else ""
            if not struct_id:
                continue

            struct_payload = struct_definitions.get(struct_id)
            if not isinstance(struct_payload, dict):
                continue

            all_field_names = cls._extract_struct_field_names(struct_payload)
            if not all_field_names:
                continue

            selected_raw = binding.get("field_names")
            selected_names: list[str] = []
            if isinstance(selected_raw, list):
                for entry in selected_raw:
                    if isinstance(entry, str) and entry.strip():
                        selected_names.append(entry.strip())

            # 与 UI 行为一致：field_names 为空时，视为“选择全部字段”。
            if not selected_names:
                fields_in_order = all_field_names
            else:
                selected_set = set(selected_names)
                fields_in_order = [name for name in all_field_names if name in selected_set]
                if not fields_in_order:
                    continue

            if node_title == STRUCT_SPLIT_NODE_TITLE:
                static_outputs = set(STRUCT_SPLIT_STATIC_OUTPUTS)
                for field_name in fields_in_order:
                    if field_name in static_outputs:
                        continue
                    node.add_output_port(field_name)
                continue

            # 拼装结构体 / 修改结构体：字段端口为输入端口
            if node_title == STRUCT_BUILD_NODE_TITLE:
                static_inputs = set(STRUCT_BUILD_STATIC_INPUTS)
            elif node_title == STRUCT_MODIFY_NODE_TITLE:
                static_inputs = set(STRUCT_MODIFY_STATIC_INPUTS)
            else:
                static_inputs = set()

            for field_name in fields_in_order:
                if field_name in static_inputs:
                    continue
                node.add_input_port(field_name)

    @staticmethod
    def _apply_port_type_snapshots(model: GraphModel, *, node_library: dict) -> None:
        """为 GraphModel 的每个端口补齐“类型快照”（用于 graph_cache / 工具链）。

        约定：
        - 不作为连线判定的单一真源（连线判定仍应优先走上下文感知 is_flow_port_with_context 等入口）；
        - 未能推导时直接抛错，强制要求节点库/复合节点定义提供完整的端口类型信息。

        重要：本快照是“展示级有效类型缓存”。
        - 优先使用 metadata.port_type_overrides 与节点已有的非泛型快照；
        - 当声明为泛型家族时，结合输入常量与连线做尽力推断；
        - 无法推断时回退到节点定义的声明/动态类型（通常为“泛型/泛型字典/泛型列表”等）。
        """
        from engine.graph.common import node_name_index_from_library
        from engine.nodes.node_definition_loader import find_composite_node_def
        from engine.graph.port_type_effective_resolver import (
            apply_effective_port_type_snapshots,
            build_port_type_overrides,
            resolve_override_type_for_node_port,
        )

        # 重要：NodeDef 定位唯一真源为 `NodeModel.node_def_ref`（builtin: canonical key；composite: composite_id）。
        # 运行时禁止基于 title/category/scope 做 NodeDef fallback；缺失 node_def_ref 视为不兼容数据，应触发缓存重建。
        from engine.nodes.port_name_rules import get_dynamic_port_type
        from engine.utils.graph.graph_utils import is_flow_port_name

        port_type_overrides = build_port_type_overrides(model)

        def _can_resolve_port_type(node_def, port_name: str, *, is_input: bool) -> bool:
            port_text = str(port_name or "").strip()
            if port_text == "":
                return False
            if is_flow_port_name(port_text):
                return True
            type_dict = node_def.input_types if is_input else node_def.output_types
            if port_text in type_dict:
                return True
            inferred = get_dynamic_port_type(port_text, type_dict, str(getattr(node_def, "dynamic_port_type", "") or ""))
            return bool(inferred)

        def _is_node_def_compatible_for_node(node_def, node_obj) -> bool:
            for port in getattr(node_obj, "inputs", None) or []:
                port_name = str(getattr(port, "name", "") or "")
                if not _can_resolve_port_type(node_def, port_name, is_input=True):
                    return False
            for port in getattr(node_obj, "outputs", None) or []:
                port_name = str(getattr(port, "name", "") or "")
                if resolve_override_type_for_node_port(port_type_overrides, getattr(node_obj, "id", ""), port_name):
                    continue
                if not _can_resolve_port_type(node_def, port_name, is_input=False):
                    return False
            return True

        # 1) 为所有节点选择兼容的 NodeDef（需兼容 scope 变体与端口集合差异）
        node_def_by_id: dict[str, object] = {}
        for node in (getattr(model, "nodes", None) or {}).values():
            node_id = str(getattr(node, "id", "") or "")
            node_def_ref = getattr(node, "node_def_ref", None)
            if node_def_ref is None:
                raise ValueError(
                    f"节点缺少 node_def_ref（node_id={node_id}，title={getattr(node, 'title', '')}）。"
                    "该数据视为旧缓存/旧模型，不允许运行时 title fallback；请触发重建 graph_cache。"
                )

            kind = str(getattr(node_def_ref, "kind", "") or "").strip()
            key = str(getattr(node_def_ref, "key", "") or "").strip()
            if kind == "builtin":
                node_def = node_library.get(key)
                if node_def is None:
                    raise KeyError(f"node_library 中未找到 builtin NodeDef：{key}（node_id={node_id}）")
            elif kind == "composite":
                node_def = None
                for _, candidate in node_library.items():
                    if not getattr(candidate, "is_composite", False):
                        continue
                    if str(getattr(candidate, "composite_id", "") or "") == key:
                        node_def = candidate
                        break
                if node_def is None:
                    raise KeyError(f"node_library 中未找到 composite NodeDef（composite_id={key}，node_id={node_id}）")
            elif kind == "event":
                # 自定义事件入口：无 NodeDef；有效类型推断将回退到快照/overrides
                node_def = None
            else:
                raise ValueError(f"非法 node_def_ref.kind：{kind!r}（node_id={node_id}）")

            if node_def is not None and (not _is_node_def_compatible_for_node(node_def, node)):
                raise ValueError(
                    f"节点端口集合与 NodeDef 不兼容：node_id={node_id}，node_def_ref={kind}:{key}"
                )

            node_def_by_id[node_id] = node_def

        # 2) 计算并写回“有效类型快照”（可复用的 graph_cache 缓存口径）
        apply_effective_port_type_snapshots(
            model,
            node_def_resolver=lambda node: node_def_by_id.get(str(getattr(node, "id", "") or "")),
            port_type_overrides=port_type_overrides,
        )


