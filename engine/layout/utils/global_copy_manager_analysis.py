from __future__ import annotations

from collections import deque
from typing import Dict, List, Set, Tuple

from .copy_identity_utils import is_data_node_copy, resolve_copy_block_id
from .graph_query_utils import is_data_edge
from .global_copy_manager_types import (
    BlockDataDependency,
    CopyPlan,
    FORBIDDEN_CROSS_BLOCK_COPY_NODE_TITLES,
)


class _GlobalCopyManagerAnalysisMixin:
    def analyze_dependencies(self) -> None:
        """分析所有块的数据依赖"""
        # 步骤1：构建流程节点到块的映射
        self._build_flow_to_block_mapping()

        # 步骤1.1：预计算块的横向列索引（column），供“禁止跨块复制”节点的 owner 选择使用。
        # 注意：该列索引与阶段5块间排版使用同一套 solver 逻辑，但不依赖像素坐标。
        self._block_column_index_by_block_id = self._compute_block_column_index_by_block_id()

        # 步骤2：收集每个块直接消费的数据节点
        self._collect_direct_consumers()

        # 步骤2.1：为禁止跨块复制的语义敏感节点确定 owner 块（用于闭包扩展截断）
        #
        # 重要：此处采用“两段式”确定 owner：
        # - Pass A：先在所有块中“遇到语义敏感节点即停止向上游扩展”（不依赖 owner），
        #          以收集“哪些块引用了该敏感节点”（包含间接引用）；
        # - Pass B：再按 (block_column, block_index) 选出真正的 owner 块，并仅在 owner 块内
        #          穿透敏感节点继续展开其纯数据上游闭包。
        #
        # 背景：仅用“直接被流程节点消费”的集合来选 owner 会遗漏“间接引用”（例如 结束裁剪值→比较→双分支），
        # 从而把敏感节点的初始化上游误归属到更右侧的 set 块，导致 data 线出现右→左回头线。
        self._clear_full_closures()
        self._expand_to_full_closure(
            forbidden_expansion_mode="stop_all",
            attach_unassigned_output_subgraphs=False,
        )
        self._build_forbidden_owner_block_mapping()

        # 步骤3：扩展到完整的上游闭包（按 owner 允许穿透敏感节点）
        self._clear_full_closures()
        self._expand_to_full_closure(
            forbidden_expansion_mode="respect_owner",
            attach_unassigned_output_subgraphs=True,
        )

        # 步骤4：识别跨块共享的数据节点
        self._identify_shared_nodes()

        # 步骤5：生成复制计划
        self._generate_copy_plans()

    def _clear_full_closures(self) -> None:
        """清空每个块的 full_data_closure，便于多轮闭包扩展复用同一批 BlockDataDependency。"""
        for dependency in self.block_dependencies.values():
            dependency.full_data_closure = set()

    def _build_flow_to_block_mapping(self) -> None:
        """构建流程节点到块的映射"""
        for block in self.layout_blocks:
            block_id = f"block_{block.order_index}"
            for flow_id in block.flow_nodes:
                self._flow_to_block[flow_id] = block_id

    @staticmethod
    def _parse_block_index_from_block_id(block_id: str) -> int:
        if not isinstance(block_id, str) or not block_id.startswith("block_"):
            return 0
        suffix = block_id.split("_", 1)[-1]
        return int(suffix) if suffix.isdigit() else 0

    def _compute_block_column_index_by_block_id(self) -> Dict[str, int]:
        """计算每个块的横向列索引（column_index）。

        说明：
        - 该列索引用于“禁止跨块复制”的节点归属（owner）选择，避免跨块回头线（右→左）。
        - 不依赖块的像素坐标，只依赖块间有向关系（按端口顺序）与稳定编号。
        """
        if not self.layout_blocks:
            return {}

        from ..blocks.block_relationship_analyzer import BlockRelationshipAnalyzer
        from ..blocks.block_positioning_engine import BlockPositioningEngine

        # 构建 flow_node_id → LayoutBlock 的映射（与 BlockRelationshipAnalyzer 同源）
        flow_to_block_map: Dict[str, object] = {}
        for layout_block in self.layout_blocks:
            for flow_node_id in getattr(layout_block, "flow_nodes", None) or []:
                flow_to_block_map[str(flow_node_id)] = layout_block

        analyzer = BlockRelationshipAnalyzer(self.model, self.layout_blocks)
        ordered_children = analyzer.analyze_relationships()
        parent_sets = analyzer.parent_map

        # spacing / initial 对列索引计算无影响，这里使用极简值即可。
        engine = BlockPositioningEngine(
            self.model,
            self.layout_blocks,
            flow_to_block_map,  # type: ignore[arg-type]
            initial_x=0.0,
            initial_y=0.0,
            block_x_spacing=1.0,
            block_y_spacing=1.0,
            parents_map=parent_sets,
        )
        column_map = engine.compute_column_indices(
            set(self.layout_blocks),
            ordered_children,
            parent_sets=parent_sets,
        )

        block_to_column: Dict[str, int] = {}
        for block_obj, col in (column_map or {}).items():
            order_index = int(getattr(block_obj, "order_index", 0) or 0)
            if order_index <= 0:
                continue
            block_to_column[f"block_{order_index}"] = int(col)

        # 兜底：缺失映射的块回退到其稳定编号，保证排序稳定且可复现。
        for layout_block in self.layout_blocks:
            block_id = f"block_{int(getattr(layout_block, 'order_index', 0) or 0)}"
            if block_id and block_id not in block_to_column:
                block_to_column[block_id] = int(getattr(layout_block, "order_index", 0) or 0)

        return block_to_column

    def _block_column(self, block_id: str) -> int:
        """将 block_id 映射为列索引（越小越靠左）；无映射时回退到块序号。"""
        if not block_id:
            return 0
        cached = self._block_column_index_by_block_id.get(block_id)
        if cached is not None:
            return int(cached)
        return self._parse_block_index_from_block_id(block_id)

    def _collect_direct_consumers(self) -> None:
        """收集每个块直接消费的数据节点"""
        for block in self.layout_blocks:
            block_id = f"block_{block.order_index}"
            flow_ids = set(block.flow_nodes)

            dependency = BlockDataDependency(
                block_id=block_id,
                block_index=block.order_index,
                flow_node_ids=flow_ids,
            )

            # 遍历流程节点的输入边，找到直接消费的数据节点
            for flow_id in sorted(flow_ids):
                in_edges = self._data_in_edges_by_dst.get(flow_id, [])
                for edge in in_edges:
                    src_id = getattr(edge, "src_node", None)
                    if not isinstance(src_id, str) or not src_id:
                        continue
                    if self._is_pure_data_node(src_id):
                        dependency.direct_data_consumers.add(self._resolve_canonical_original_id(src_id))

            self.block_dependencies[block_id] = dependency

    def _expand_to_full_closure(
        self,
        *,
        forbidden_expansion_mode: str,
        attach_unassigned_output_subgraphs: bool,
    ) -> None:
        """将直接消费扩展到完整的上游闭包。

        Args:
            forbidden_expansion_mode:
                - "stop_all": 遇到“禁止跨块复制”的语义敏感节点时，所有块均停止向上游扩展；
                - "respect_owner": 仅在 owner 块内穿透敏感节点继续扩展，其它块在该节点处终止。
            attach_unassigned_output_subgraphs:
                是否在闭包扩展完成后执行尾部纯数据子图挂载（仅最终一轮需要）。
        """
        for block_id, dependency in self.block_dependencies.items():
            visited: Set[str] = set()
            traversal_queue: deque[str] = deque(sorted(dependency.direct_data_consumers))

            while traversal_queue:
                current_canonical_id = traversal_queue.popleft()
                if current_canonical_id in visited:
                    continue
                visited.add(current_canonical_id)

                if not current_canonical_id:
                    continue
                dependency.full_data_closure.add(current_canonical_id)

                # 语义敏感节点（禁止跨块复制）：对其上游闭包扩展必须是“端点可控”的，否则会产生孤立副本。
                if self._is_cross_block_copy_forbidden(current_canonical_id):
                    mode = str(forbidden_expansion_mode or "").strip().lower()
                    if mode == "stop_all":
                        continue
                    if mode == "respect_owner":
                        owner_block_id = self._forbidden_owner_block_by_canonical.get(current_canonical_id, "")
                        if owner_block_id and owner_block_id != block_id:
                            continue

                upstream_candidates = self._logical_upstream_by_data_dst.get(current_canonical_id, set())
                for upstream_canonical in sorted(upstream_candidates):
                    if upstream_canonical and upstream_canonical not in visited:
                        traversal_queue.append(upstream_canonical)

        if attach_unassigned_output_subgraphs:
            # 兜底：将“仅由输出引脚消费/未被任何流程节点直接消费”的纯数据尾部子图挂载到合适的块上，
            # 避免这些节点在阶段2未被放置，从而在 UI 中显示为“不属于任何块”。
            self._attach_unassigned_output_data_subgraphs()

    def _build_forbidden_owner_block_mapping(self) -> None:
        """为禁止跨块复制的语义敏感节点推断 owner block_id（确定性）。

        说明：
        - owner 选择必须覆盖“间接引用”的场景（例如：敏感节点 -> 比较/拼装 -> flow），
          因此以 full_data_closure 为依据，而不是仅依赖 direct_data_consumers。
        - 采用 rank=(block_column, block_index) 的稳定选择，避免跨块回头线（右→左）。
        """
        owner_map: Dict[str, str] = {}
        owner_rank_map: Dict[str, Tuple[int, int]] = {}
        for block_id, dependency in self.block_dependencies.items():
            block_index = int(getattr(dependency, "block_index", 0) or 0)
            block_column = int(self._block_column(block_id))
            for canonical_id in sorted(dependency.full_data_closure):
                if not self._is_cross_block_copy_forbidden(canonical_id):
                    continue
                candidate_rank = (block_column, block_index)
                existing_rank = owner_rank_map.get(canonical_id)
                if existing_rank is None or candidate_rank < existing_rank:
                    owner_map[canonical_id] = block_id
                    owner_rank_map[canonical_id] = candidate_rank
        self._forbidden_owner_block_by_canonical = owner_map

    def _attach_unassigned_output_data_subgraphs(self) -> None:
        """
        处理一种常见布局缺口：
        - 某些纯数据节点只参与最终输出组装（例如 `拼装字典`），不作为任何流程节点的输入；
        - 全局依赖分析仅以“流程节点输入”作为种子会遗漏这段尾部纯数据链；
        - 结果是这些节点不会出现在任何块的 block_data_nodes 中，阶段2不会放置它们。

        修复策略（确定性、最小侵入）：
        - 找到当前未被任何块 full_data_closure 覆盖的“纯数据 sink”（没有任何数据输出边，但有数据输入边）；
        - 对每个 sink，沿纯数据上游追溯，收集仍未归属的尾部子图；
          - 将该尾部子图挂到“依赖它的已归属数据节点所在的最靠后块”（最大 block_index）上；
          若无法推断，则挂到图内最后一个块上。
        """
        if not self.block_dependencies:
            return

        # 已归属的数据 canonical 集合
        assigned: Set[str] = set()
        canonical_to_max_block_index: Dict[str, int] = {}
        max_block_index = 0
        for block_id, dependency in self.block_dependencies.items():
            max_block_index = max(max_block_index, int(dependency.block_index))
            for canonical_id in dependency.full_data_closure:
                if not canonical_id:
                    continue
                assigned.add(canonical_id)
                existing = canonical_to_max_block_index.get(canonical_id, 0)
                if int(dependency.block_index) > existing:
                    canonical_to_max_block_index[canonical_id] = int(dependency.block_index)

        # 扫描数据边，统计 canonical 级别的入/出度（仅纯数据节点）。
        outgoing_canonicals: Set[str] = set()
        incoming_canonicals: Set[str] = set()
        for edge in sorted(self.model.edges.values(), key=lambda item: getattr(item, "id", "")):
            if not is_data_edge(self.model, edge):
                continue
            src_id = getattr(edge, "src_node", "") or ""
            dst_id = getattr(edge, "dst_node", "") or ""
            if not src_id or not dst_id:
                continue
            if self._is_pure_data_node(src_id):
                src_canonical = self._resolve_canonical_original_id(src_id)
                if src_canonical:
                    outgoing_canonicals.add(src_canonical)
            if self._is_pure_data_node(dst_id):
                dst_canonical = self._resolve_canonical_original_id(dst_id)
                if dst_canonical:
                    incoming_canonicals.add(dst_canonical)

        # 找到“未归属 + 有入边 + 无出边”的纯数据 canonical sink
        unassigned_sinks: List[str] = []
        for node_id, node_obj in self.model.nodes.items():
            if not self._is_pure_data_node(str(node_id)):
                continue
            canonical_id = self._resolve_canonical_original_id(str(node_id))
            if not canonical_id:
                continue
            # 只处理原始节点（canonical 必须在 nodes 内）；副本由 copy_block_id 归属处理。
            if canonical_id not in self.model.nodes:
                continue
            if canonical_id in assigned:
                continue
            if canonical_id not in incoming_canonicals:
                continue
            if canonical_id in outgoing_canonicals:
                continue
            if canonical_id not in unassigned_sinks:
                unassigned_sinks.append(canonical_id)
        unassigned_sinks.sort()

        if not unassigned_sinks:
            return

        newly_assigned: Set[str] = set()
        block_to_column_index: Dict[str, int] = {}

        # 预计算“块 → 列索引”（与块间排版一致），用于判定 UI 视角下的“最右侧块”。
        # 注意：order_index 只是稳定编号，不等同于横向列位置。
        from ..blocks.block_relationship_analyzer import BlockRelationshipAnalyzer
        from ..blocks.block_positioning_engine import BlockPositioningEngine

        flow_to_block_map: Dict[str, object] = {}
        for layout_block in self.layout_blocks:
            for flow_node_id in getattr(layout_block, "flow_nodes", None) or []:
                flow_to_block_map[str(flow_node_id)] = layout_block

        analyzer = BlockRelationshipAnalyzer(self.model, self.layout_blocks)
        ordered_children = analyzer.analyze_relationships()
        parent_sets = analyzer.parent_map

        # 这里不需要真实像素 X，只需要列索引；spacing/initial 不影响列计算。
        engine = BlockPositioningEngine(
            self.model,
            self.layout_blocks,
            flow_to_block_map,  # type: ignore[arg-type]
            initial_x=0.0,
            initial_y=0.0,
            block_x_spacing=1.0,
            block_y_spacing=1.0,
            parents_map=parent_sets,
        )
        column_map = engine.compute_column_indices(set(self.layout_blocks), ordered_children, parent_sets=parent_sets)
        for block_obj, col in (column_map or {}).items():
            block_id = f"block_{int(getattr(block_obj, 'order_index', 0) or 0)}"
            block_to_column_index[block_id] = int(col)

        def _parse_block_index_from_block_id(block_id: str) -> int:
            if not isinstance(block_id, str) or not block_id.startswith("block_"):
                return 0
            suffix = block_id.split("_", 1)[-1]
            return int(suffix) if suffix.isdigit() else 0

        def _infer_connected_block_id(node_instance_id: str) -> str:
            """
            将一个“连接在边界上的节点实例”解析为其所属块ID（block_*）。
            支持流程节点 / 数据节点 / 数据副本；若无法解析，返回空字符串。
            """
            if not isinstance(node_instance_id, str) or not node_instance_id:
                return ""

            flow_block_id = self._flow_to_block.get(node_instance_id, "")
            if flow_block_id:
                return str(flow_block_id)

            node_obj = self.model.nodes.get(node_instance_id)
            if node_obj is None:
                return ""

            if is_data_node_copy(node_obj):
                copy_block = resolve_copy_block_id(node_obj)
                return str(copy_block)

            if self._is_pure_data_node(node_instance_id):
                canonical = self._resolve_canonical_original_id(node_instance_id)
                owner_index = int(canonical_to_max_block_index.get(canonical, 0))
                if owner_index > 0:
                    return f"block_{owner_index}"
                return ""

            return ""

        def _block_column(block_id: str) -> int:
            """将 block_id 映射为列索引（越大越靠右）；无映射时回退到块序号。"""
            if not block_id:
                return 0
            if block_id in block_to_column_index:
                return int(block_to_column_index[block_id])
            return _parse_block_index_from_block_id(block_id)

        def _resolve_target_block_for_tail(tail_node_ids: Set[str]) -> str:
            """
            目标块选择规则（避免回头线）：
            - 对整段尾部纯数据链（tail_node_ids），收集其与外部相连的“边界节点”（入边来源/出边去向）；
            - 取这些边界节点所在块的最大 block_index；
            - 若无法解析任何边界块，则保持“未归属”，由编排器在后续阶段将其作为独立纯数据块布局。

            这样可以覆盖用户期望的情况：
            - 某个尾部节点（如 拼装列表）被块7内节点消费 → tail 挂到块7；
            - 多个块都连接 tail → tail 挂到最右侧那个块，避免回头线；
            - 与任何流程块都不相连（例如仅由虚拟输出引脚消费）→ tail 单独成块，避免被强行塞进末尾流程块。
            """
            best_block_id = ""
            best_column = -1
            if not tail_node_ids:
                return f"block_{int(max_block_index)}"

            # 入边边界：外部 -> tail
            for tail_id in sorted(tail_node_ids):
                incoming_edges = self._data_in_edges_by_dst.get(tail_id, []) or []
                for edge in incoming_edges:
                    src_id = getattr(edge, "src_node", "") or ""
                    if not isinstance(src_id, str) or not src_id:
                        continue
                    if src_id in tail_node_ids:
                        continue
                    src_block_id = _infer_connected_block_id(src_id)
                    src_column = _block_column(src_block_id)
                    if src_column > best_column:
                        best_block_id = src_block_id
                        best_column = src_column

            # 出边边界：tail -> 外部
            for tail_id in sorted(tail_node_ids):
                outgoing_edges = self._data_out_edges_by_src.get(tail_id, []) or []
                for edge in outgoing_edges:
                    dst_id = getattr(edge, "dst_node", "") or ""
                    if not isinstance(dst_id, str) or not dst_id:
                        continue
                    if dst_id in tail_node_ids:
                        continue
                    dst_block_id = _infer_connected_block_id(dst_id)
                    dst_column = _block_column(dst_block_id)
                    if dst_column > best_column:
                        best_block_id = dst_block_id
                        best_column = dst_column

            if best_block_id:
                return str(best_block_id)
            # 无任何边界块：保持未归属，交由布局编排器在后续阶段生成“纯数据孤立块”。
            return ""

        for sink_canonical in unassigned_sinks:
            if sink_canonical in newly_assigned or sink_canonical in assigned:
                continue

            # 收集该 sink 的“尾部子图”：沿纯数据上游追溯，遇到已归属节点即停止扩展。
            # 说明：此处只挂载“尚未归属任何块”的那一段尾部纯数据链，
            # 避免把整张图的上游依赖强行纳入同一块导致复制膨胀。
            tail_queue: deque[str] = deque([sink_canonical])
            tail_visited: Set[str] = set()
            tail_to_attach: Set[str] = set()
            while tail_queue:
                current = tail_queue.popleft()
                if not current or current in tail_visited:
                    continue
                tail_visited.add(current)
                if current in assigned:
                    continue
                tail_to_attach.add(current)
                for upstream in sorted(self._logical_upstream_by_data_dst.get(current, set())):
                    if upstream and upstream not in tail_visited:
                        tail_queue.append(upstream)

            if not tail_to_attach:
                continue

            target_block_id = _resolve_target_block_for_tail(tail_to_attach)
            dependency = self.block_dependencies.get(target_block_id)
            if dependency is None:
                continue

            for canonical_id in sorted(tail_to_attach):
                dependency.full_data_closure.add(canonical_id)
                newly_assigned.add(canonical_id)
                assigned.add(canonical_id)

    def _identify_shared_nodes(self) -> None:
        """识别被多个块使用的数据节点"""
        # 收集每个数据节点被哪些块使用
        for block_id, dependency in self.block_dependencies.items():
            for data_id in dependency.full_data_closure:
                if data_id not in self.data_node_consumers:
                    self.data_node_consumers[data_id] = []
                if block_id not in self.data_node_consumers[data_id]:
                    self.data_node_consumers[data_id].append(block_id)

        # 按块序号排序（首个块保留原始节点）
        for data_id, block_ids in self.data_node_consumers.items():
            # 对“禁止跨块复制”的语义敏感节点：
            # - owner 块应尽量选择最靠左的列，避免跨块数据边出现右→左回头线；
            # - 列内再按稳定编号（order_index）排序，保证可复现。
            if self._is_cross_block_copy_forbidden(data_id):
                block_ids.sort(
                    key=lambda bid: (
                        int(self._block_column(bid)),
                        int(self.block_dependencies[bid].block_index),
                    )
                )
            else:
                block_ids.sort(key=lambda bid: self.block_dependencies[bid].block_index)

    def _generate_copy_plans(self) -> None:
        """生成复制计划"""
        for data_id, block_ids in self.data_node_consumers.items():
            if len(block_ids) <= 1:
                # 只被一个块使用，不需要复制
                continue

            # 首个块保留原始节点
            owner_block_id = block_ids[0]
            owner_index = self.block_dependencies[owner_block_id].block_index

            plan = CopyPlan(
                original_node_id=data_id,
                owner_block_id=owner_block_id,
                owner_block_index=owner_index,
            )

            # 语义敏感节点：即便跨块共享也禁止复制，避免副本破坏局部状态/作用域语义。
            # 仍然保留 CopyPlan 用于“单一 owner 块归属”，从而避免同一原始节点被多个块同时放置。
            if self._is_cross_block_copy_forbidden(data_id):
                self.copy_plans[data_id] = plan
                continue

            # 其他块需要创建/复用副本（每个块只创建一个副本）
            for block_id in block_ids[1:]:
                existing_copy_id = self._existing_copy_by_original_and_block.get((data_id, block_id))
                if existing_copy_id:
                    plan.copy_targets[block_id] = existing_copy_id
                else:
                    plan.copy_targets[block_id] = f"{data_id}_copy_{block_id}_1"

            self.copy_plans[data_id] = plan

    def _is_cross_block_copy_forbidden(self, canonical_original_id: str) -> bool:
        """判断某 canonical 数据节点是否禁止跨块复制。

        注意：这里的 canonical_original_id 必须是根原始节点 ID（非副本）。
        """
        if not isinstance(canonical_original_id, str) or not canonical_original_id:
            return False
        node_obj = self.model.nodes.get(canonical_original_id)
        if node_obj is None:
            return False
        title_value = getattr(node_obj, "title", "") or ""
        return str(title_value) in FORBIDDEN_CROSS_BLOCK_COPY_NODE_TITLES

    # ---------------------------------------------------------------------
    # 兼容旧引用：外部 doc/排查脚本可能会使用该常量名
    # ---------------------------------------------------------------------

    # keep for readability: FORBIDDEN_CROSS_BLOCK_COPY_NODE_TITLES imported above

