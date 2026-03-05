from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from engine.graph.models.graph_model import GraphModel


@dataclass(frozen=True, slots=True)
class GraphSearchResultItem:
    """单条搜索命中结果（用于 UI 列表展示与跳转）。

    设计目标：
    - 信息对“调试时快速定位”友好：标题/类别/ID/坐标/源码行/变量名/常量摘要/命中类型。
    - 结构化字段，UI 可自由组合展示/Tooltip 展示；本模块不依赖 PyQt。
    """

    node_id: str
    title: str
    category: str
    export_index: int
    pos: Tuple[float, float]
    source_lineno: int
    source_end_lineno: int
    port_names: Tuple[str, ...]
    code_var_names: Tuple[str, ...]
    var_pairs: Tuple[Tuple[str, str], ...]
    constant_previews: Tuple[str, ...]
    comment_preview: str
    matched_tags: Tuple[str, ...]
    var_relation_hints: Tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphSearchMatch:
    """搜索结果：命中的节点与应保持高亮的连线集合。"""

    query: str
    tokens_cf: Tuple[str, ...]
    source_spans: Tuple[Tuple[int, int], ...]
    node_ids: List[str]
    edge_ids_to_keep: List[str]
    var_relation_hints_by_node_id: Dict[str, Tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _NodeFieldIndex:
    node_id_cf: str
    title_cf: str
    category_cf: str
    code_vars_cf: str
    ports_cf: str
    constants_cf: str
    var_names_cf: str
    comments_cf: str
    source_cf: str


@dataclass(frozen=True, slots=True)
class GraphSearchIndex:
    """节点图搜索索引（纯逻辑，不依赖 PyQt）。"""

    graph_id: str
    graph_name: str
    source_file: str
    # 节点“导出到 GIA 的稳定序号”（与写回侧 `_sort_graph_nodes_for_stable_ids` 同口径：按 (y,x,title,node_id) 排序后从 1 开始）
    node_export_index_by_id: Dict[str, int]
    node_text_by_id: Dict[str, str]
    node_pos_by_id: Dict[str, Tuple[float, float]]
    node_title_by_id: Dict[str, str]
    node_category_by_id: Dict[str, str]
    node_source_range_by_id: Dict[str, Tuple[int, int]]
    node_port_names_by_id: Dict[str, Tuple[str, ...]]
    node_code_var_names_by_id: Dict[str, Tuple[str, ...]]
    node_var_pairs_by_id: Dict[str, Tuple[Tuple[str, str], ...]]
    node_constant_previews_by_id: Dict[str, Tuple[str, ...]]
    node_comment_preview_by_id: Dict[str, str]
    node_fields_by_id: Dict[str, _NodeFieldIndex]
    edge_endpoints_by_id: Dict[str, Tuple[str, str]]
    edge_ids_by_node_id: Dict[str, Tuple[str, ...]]
    var_definitions_by_name: Dict[str, List[Tuple[str, str]]]
    var_display_name_by_cf: Dict[str, str]
    var_related_nodes_by_name: Dict[str, set[str]]

    @staticmethod
    def build(model: GraphModel, *, source_code: str | None = None) -> "GraphSearchIndex":
        graph_id = str(getattr(model, "graph_id", "") or "")
        graph_name = str(getattr(model, "graph_name", "") or "")
        metadata = getattr(model, "metadata", {}) or {}
        source_file = str(metadata.get("source_file", "") or "")

        source_lines: list[str] = source_code.splitlines() if isinstance(source_code, str) and source_code else []

        node_text_by_id: Dict[str, str] = {}
        node_pos_by_id: Dict[str, Tuple[float, float]] = {}
        node_title_by_id: Dict[str, str] = {}
        node_category_by_id: Dict[str, str] = {}
        node_source_range_by_id: Dict[str, Tuple[int, int]] = {}
        node_port_names_by_id: Dict[str, Tuple[str, ...]] = {}
        node_code_var_names_by_id: Dict[str, Tuple[str, ...]] = {}
        node_var_pairs_by_id: Dict[str, Tuple[Tuple[str, str], ...]] = {}
        node_constant_previews_by_id: Dict[str, Tuple[str, ...]] = {}
        node_comment_preview_by_id: Dict[str, str] = {}
        node_fields_by_id: Dict[str, _NodeFieldIndex] = {}

        # (src_node, src_port) -> [dst_node, ...]
        outgoing_nodes_by_endpoint: Dict[Tuple[str, str], List[str]] = {}
        edge_endpoints_by_id: Dict[str, Tuple[str, str]] = {}
        edge_ids_by_node_id: Dict[str, List[str]] = {}
        for edge_id, edge_obj in (getattr(model, "edges", {}) or {}).items():
            edge_identifier = str(edge_id or "")
            src_node_id = str(getattr(edge_obj, "src_node", "") or "")
            src_port_name = str(getattr(edge_obj, "src_port", "") or "")
            dst_node_id = str(getattr(edge_obj, "dst_node", "") or "")

            edge_endpoints_by_id[edge_identifier] = (src_node_id, dst_node_id)
            if src_node_id:
                edge_ids_by_node_id.setdefault(src_node_id, []).append(edge_identifier)
            if dst_node_id:
                edge_ids_by_node_id.setdefault(dst_node_id, []).append(edge_identifier)
            key = (src_node_id, src_port_name)
            outgoing_nodes_by_endpoint.setdefault(key, []).append(dst_node_id)

        # 变量名（casefold）-> [(定义节点ID, 输出端口名), ...]
        var_definitions_by_name: Dict[str, List[Tuple[str, str]]] = {}
        var_display_name_by_cf: Dict[str, str] = {}

        for node_id, node_obj in (getattr(model, "nodes", {}) or {}).items():
            node_identifier = str(node_id or "")
            title_text = str(getattr(node_obj, "title", "") or "")
            category_text = str(getattr(node_obj, "category", "") or "")
            pos_value = getattr(node_obj, "pos", (0.0, 0.0))
            pos_x = float(pos_value[0]) if isinstance(pos_value, (list, tuple)) and len(pos_value) >= 2 else 0.0
            pos_y = float(pos_value[1]) if isinstance(pos_value, (list, tuple)) and len(pos_value) >= 2 else 0.0
            node_pos_by_id[node_identifier] = (pos_x, pos_y)
            node_title_by_id[node_identifier] = title_text
            node_category_by_id[node_identifier] = category_text

            # 分字段索引（用于 UI 展示“命中类型”）
            code_var_fragments: List[str] = []
            port_fragments: List[str] = []
            constant_fragments: List[str] = []
            var_fragments: List[str] = []
            comment_fragments: List[str] = []
            source_fragments: List[str] = []

            # 端口名：输入/输出
            port_names: List[str] = []
            port_name_set: set[str] = set()
            for port_obj in getattr(node_obj, "inputs", []) or []:
                port_name = str(getattr(port_obj, "name", "") or "")
                if port_name:
                    port_fragments.append(port_name)
                    if port_name not in port_name_set:
                        port_name_set.add(port_name)
                        port_names.append(port_name)
            for port_obj in getattr(node_obj, "outputs", []) or []:
                port_name = str(getattr(port_obj, "name", "") or "")
                if port_name:
                    port_fragments.append(port_name)
                    if port_name not in port_name_set:
                        port_name_set.add(port_name)
                        port_names.append(port_name)
            node_port_names_by_id[node_identifier] = tuple(port_names)

            # 输入常量（输入框内容）
            input_constants = getattr(node_obj, "input_constants", {}) or {}
            constant_previews: List[str] = []
            if isinstance(input_constants, dict):
                for key_obj, value_obj in input_constants.items():
                    key_text = str(key_obj) if key_obj is not None else ""
                    if key_text:
                        constant_fragments.append(key_text)
                    _collect_text_fragments(value_obj, constant_fragments, max_depth=4, max_items=80)

                    # 预览（用于 UI 列表），避免把超大常量直接塞进一行文本
                    if len(constant_previews) < 6 and key_text:
                        preview_value = _preview_value(value_obj, max_depth=2, max_items=6, max_len=60)
                        if preview_value:
                            constant_previews.append(f"{key_text}={preview_value}")

            # 代码变量名：NodeModel.custom_var_names（输出口名 -> 变量名）
            custom_var_names = getattr(node_obj, "custom_var_names", {}) or {}
            var_pairs: List[Tuple[str, str]] = []
            if isinstance(custom_var_names, dict):
                for out_port_name_obj, var_name_obj in custom_var_names.items():
                    out_port_name = str(out_port_name_obj) if out_port_name_obj is not None else ""
                    var_name = str(var_name_obj) if var_name_obj is not None else ""
                    if out_port_name:
                        var_fragments.append(out_port_name)
                    if var_name:
                        var_fragments.append(var_name)
                        if len(var_pairs) < 10:
                            var_pairs.append((out_port_name, var_name))
                        var_name_cf = var_name.strip().casefold()
                        if var_name_cf:
                            var_definitions_by_name.setdefault(var_name_cf, []).append(
                                (node_identifier, out_port_name)
                            )
                            if var_name_cf not in var_display_name_by_cf:
                                var_display_name_by_cf[var_name_cf] = var_name.strip()

            # 注释
            custom_comment = str(getattr(node_obj, "custom_comment", "") or "")
            inline_comment = str(getattr(node_obj, "inline_comment", "") or "")
            if custom_comment:
                comment_fragments.append(custom_comment)
            if inline_comment:
                comment_fragments.append(inline_comment)

            # 源码信息（可用于定位/搜索）
            source_lineno = int(getattr(node_obj, "source_lineno", 0) or 0)
            source_end_lineno = int(getattr(node_obj, "source_end_lineno", 0) or 0)
            if source_lineno > 0:
                source_fragments.append(str(source_lineno))
            if source_end_lineno > 0 and source_end_lineno != source_lineno:
                source_fragments.append(str(source_end_lineno))
            node_source_range_by_id[node_identifier] = (source_lineno, source_end_lineno)

            # 代码变量名：从源码中提取“赋值左值变量名”（例如：目标踏板GUID列表 = 获取节点图变量(...)）。
            # 说明：解析器不会把该左值写入 NodeModel.custom_var_names，因此搜索索引在 UI 层补齐。
            code_var_names: Tuple[str, ...] = tuple()
            if source_lines and 1 <= source_lineno <= len(source_lines):
                code_var_names = _extract_assigned_variable_names_from_line(source_lines[source_lineno - 1])
            node_code_var_names_by_id[node_identifier] = code_var_names
            code_var_fragments.extend(list(code_var_names))

            # 图级信息：graph_id / graph_name / source_file（为了支持 @xxx.py 这类查询）
            graph_fragments: List[str] = []
            if graph_id:
                graph_fragments.append(graph_id)
            if graph_name:
                graph_fragments.append(graph_name)
            if source_file:
                _append_unique(graph_fragments, source_file)
                file_name = Path(source_file).name
                if file_name:
                    _append_unique(graph_fragments, file_name)
                    _append_unique(graph_fragments, f"@{file_name}")
                _append_unique(graph_fragments, f"@{source_file}")

            # 合并成“全字段文本索引”
            all_fragments: List[str] = [node_identifier]
            if title_text:
                all_fragments.append(title_text)
            if category_text:
                all_fragments.append(category_text)
            all_fragments.extend(code_var_fragments)
            all_fragments.extend(port_fragments)
            all_fragments.extend(constant_fragments)
            all_fragments.extend(var_fragments)
            all_fragments.extend(comment_fragments)
            all_fragments.extend(source_fragments)
            all_fragments.extend(graph_fragments)

            node_text_by_id[node_identifier] = "\n".join([t for t in all_fragments if t]).casefold()

            # UI 展示用缓存
            node_var_pairs_by_id[node_identifier] = tuple([(p, v) for p, v in var_pairs if v])
            node_constant_previews_by_id[node_identifier] = tuple([s for s in constant_previews if s])
            comment_preview = ""
            if inline_comment.strip():
                comment_preview = inline_comment.strip()
            elif custom_comment.strip():
                comment_preview = custom_comment.strip()
            node_comment_preview_by_id[node_identifier] = _truncate_text(comment_preview, 120)

            node_fields_by_id[node_identifier] = _NodeFieldIndex(
                node_id_cf=node_identifier.casefold(),
                title_cf=title_text.casefold(),
                category_cf=category_text.casefold(),
                code_vars_cf="\n".join(code_var_fragments).casefold(),
                ports_cf="\n".join(port_fragments).casefold(),
                constants_cf="\n".join(constant_fragments).casefold(),
                var_names_cf="\n".join(var_fragments).casefold(),
                comments_cf="\n".join(comment_fragments).casefold(),
                source_cf=(str(source_file or "") + "\n" + "\n".join(source_fragments)).casefold(),
            )

        # === 节点导出序号（GIA 写回口径） ===
        # 说明：
        # - 该序号与 `ugc_file_tools.node_graph_writeback.layout._sort_graph_nodes_for_stable_ids(...)` 同口径；
        # - 用途：在 UI（布局Y调试 tooltip / 搜索）中展示与匹配 “导出时的从 1 开始 node_index”。
        node_export_index_by_id: Dict[str, int] = {}
        all_node_ids = list(node_pos_by_id.keys())

        def _export_sort_key(node_id: str) -> Tuple[float, float, str, str]:
            pos = node_pos_by_id.get(node_id, (0.0, 0.0))
            title = str(node_title_by_id.get(node_id, "") or "").strip()
            # 与写回侧一致：按 (y,x,title,node_id) 排序
            return (float(pos[1]), float(pos[0]), str(title), str(node_id))

        for export_index, node_id in enumerate(sorted(all_node_ids, key=_export_sort_key), start=1):
            node_export_index_by_id[str(node_id)] = int(export_index)
            # 加入全文索引：允许直接用数字搜索导出序号
            if node_id in node_text_by_id:
                node_text_by_id[node_id] = str(node_text_by_id[node_id]) + "\n" + str(export_index)

        # 变量名（casefold）-> 相关节点集合（定义节点 + 直接使用节点）
        var_related_nodes_by_name: Dict[str, set[str]] = {}
        for var_name_cf, definitions in var_definitions_by_name.items():
            related_nodes: set[str] = set()
            for def_node_id, def_out_port in definitions:
                if def_node_id:
                    related_nodes.add(def_node_id)
                if not def_node_id or not def_out_port:
                    continue
                for dst_node_id in outgoing_nodes_by_endpoint.get((def_node_id, def_out_port), []) or []:
                    if dst_node_id:
                        related_nodes.add(str(dst_node_id))
            if related_nodes:
                var_related_nodes_by_name[var_name_cf] = related_nodes

        return GraphSearchIndex(
            graph_id=graph_id,
            graph_name=graph_name,
            source_file=source_file,
            node_export_index_by_id=node_export_index_by_id,
            node_text_by_id=node_text_by_id,
            node_pos_by_id=node_pos_by_id,
            node_title_by_id=node_title_by_id,
            node_category_by_id=node_category_by_id,
            node_source_range_by_id=node_source_range_by_id,
            node_port_names_by_id=node_port_names_by_id,
            node_code_var_names_by_id=node_code_var_names_by_id,
            node_var_pairs_by_id=node_var_pairs_by_id,
            node_constant_previews_by_id=node_constant_previews_by_id,
            node_comment_preview_by_id=node_comment_preview_by_id,
            node_fields_by_id=node_fields_by_id,
            edge_endpoints_by_id=edge_endpoints_by_id,
            edge_ids_by_node_id={k: tuple(v) for k, v in edge_ids_by_node_id.items() if k},
            var_definitions_by_name=var_definitions_by_name,
            var_display_name_by_cf=var_display_name_by_cf,
            var_related_nodes_by_name=var_related_nodes_by_name,
        )

    def build_result_item(
        self,
        node_id: str,
        *,
        tokens_cf: Tuple[str, ...],
        var_relation_hints: Tuple[str, ...] = tuple(),
    ) -> GraphSearchResultItem:
        """按需构建单条搜索结果项（用于 UI 列表分页展示）。

        设计目标：
        - `match()` 只返回 node_ids/edge_ids 等“导航必需”数据，避免在命中很多节点时一次性构造大量对象。
        - UI 在分页渲染时按需构建当前页的少量结果项。
        """
        node_identifier = str(node_id or "")
        if not node_identifier:
            raise ValueError("node_id 不能为空")
        fields = self.node_fields_by_id.get(node_identifier)
        if fields is None:
            raise KeyError(f"node_id 不存在于搜索索引中: {node_identifier}")

        title_text = str(self.node_title_by_id.get(node_identifier, "") or "")
        category_text = str(self.node_category_by_id.get(node_identifier, "") or "")
        export_index_int = int(self.node_export_index_by_id.get(node_identifier, 0) or 0)
        pos = self.node_pos_by_id.get(node_identifier, (0.0, 0.0))
        src_line, src_end = self.node_source_range_by_id.get(node_identifier, (0, 0))
        port_names = self.node_port_names_by_id.get(node_identifier, tuple())
        code_var_names = self.node_code_var_names_by_id.get(node_identifier, tuple())
        var_pairs = self.node_var_pairs_by_id.get(node_identifier, tuple())
        constant_previews = self.node_constant_previews_by_id.get(node_identifier, tuple())
        comment_preview = str(self.node_comment_preview_by_id.get(node_identifier, "") or "")

        matched_tags = self._compute_matched_tags_for_node(
            node_identifier,
            fields,
            tokens_cf=tokens_cf,
            export_index_int=export_index_int,
            var_relation_hints=var_relation_hints,
        )

        return GraphSearchResultItem(
            node_id=node_identifier,
            title=title_text,
            category=category_text,
            export_index=export_index_int,
            pos=pos,
            source_lineno=int(src_line or 0),
            source_end_lineno=int(src_end or 0),
            port_names=tuple(port_names or tuple()),
            code_var_names=tuple(code_var_names or tuple()),
            var_pairs=tuple(var_pairs or tuple()),
            constant_previews=tuple(constant_previews or tuple()),
            comment_preview=comment_preview,
            matched_tags=matched_tags,
            var_relation_hints=tuple(var_relation_hints or tuple()),
        )

    def _compute_matched_tags_for_node(
        self,
        node_id: str,
        fields: _NodeFieldIndex,
        *,
        tokens_cf: Tuple[str, ...],
        export_index_int: int,
        var_relation_hints: Tuple[str, ...],
    ) -> Tuple[str, ...]:
        tag_set: set[str] = set()
        export_index_cf = str(export_index_int).casefold() if int(export_index_int) > 0 else ""
        source_file_cf = str(self.source_file or "").casefold()
        graph_id_cf = str(self.graph_id or "").casefold()
        graph_name_cf = str(self.graph_name or "").casefold()

        for token_cf in list(tokens_cf or tuple()):
            if token_cf and token_cf in fields.node_id_cf:
                tag_set.add("ID")
            if token_cf and export_index_cf and token_cf in export_index_cf:
                tag_set.add("GIA序号")
            if token_cf and token_cf in fields.title_cf:
                tag_set.add("标题")
            if token_cf and token_cf in fields.category_cf:
                tag_set.add("类别")
            if token_cf and token_cf in fields.code_vars_cf:
                tag_set.add("代码变量")
            if token_cf and token_cf in fields.ports_cf:
                tag_set.add("端口")
            if token_cf and token_cf in fields.constants_cf:
                tag_set.add("常量")
            if token_cf and token_cf in fields.var_names_cf:
                tag_set.add("变量名")
            if token_cf and token_cf in fields.comments_cf:
                tag_set.add("注释")
            if token_cf and (token_cf in fields.source_cf or (source_file_cf and token_cf in source_file_cf)):
                tag_set.add("源文件/行号")
            if token_cf and (token_cf in graph_id_cf or token_cf in graph_name_cf):
                tag_set.add("图信息")

        if bool(var_relation_hints):
            tag_set.add("变量关联")

        ordered_tag_names = [
            "标题",
            "类别",
            "ID",
            "GIA序号",
            "代码变量",
            "变量名",
            "变量关联",
            "常量",
            "端口",
            "注释",
            "源文件/行号",
            "图信息",
        ]
        matched_tags: List[str] = []
        for tag in ordered_tag_names:
            if tag in tag_set:
                matched_tags.append(tag)
        return tuple(matched_tags)

    def match(self, query: str) -> GraphSearchMatch:
        tokens_cf_list, source_spans_list = _tokenize_query_with_source_spans(query)
        if (not tokens_cf_list) and (not source_spans_list):
            return GraphSearchMatch(
                query=str(query or ""),
                tokens_cf=tuple(),
                source_spans=tuple(),
                node_ids=[],
                edge_ids_to_keep=[],
                var_relation_hints_by_node_id={},
            )
        tokens_cf = tuple([str(t) for t in (tokens_cf_list or []) if str(t)])
        source_spans = tuple(
            [(int(a), int(b)) for a, b in (source_spans_list or []) if int(a) > 0 and int(b) > 0]
        )
        tokens_cf_list_for_contains = list(tokens_cf)

        preferred_export_index: int | None = None
        # 约定：当用户输入“纯数字”时，优先把 GIA序号（导出序号）精确匹配的结果排到最前。
        if len(tokens_cf) == 1 and str(tokens_cf[0]).isdigit():
            preferred_export_index = int(tokens_cf[0])

        matched_node_ids: set[str] = set()
        var_relation_hints_by_node: Dict[str, set[str]] = {}

        # 1) 普通文本匹配：节点标题/端口名/输入常量/注释等
        if tokens_cf:
            for node_id, indexed_text in self.node_text_by_id.items():
                if _contains_all_tokens(indexed_text, tokens_cf_list_for_contains):
                    matched_node_ids.add(str(node_id))
        else:
            # 仅按源码行范围过滤：先选中全量节点，再做范围裁剪。
            matched_node_ids = set(str(node_id) for node_id in self.node_text_by_id.keys())

        # 2) 代码变量名扩展：若查询词匹配某个变量名，则额外包含“定义节点 + 直接使用节点”
        if tokens_cf:
            for var_name_cf, related_nodes in self.var_related_nodes_by_name.items():
                if _contains_all_tokens(var_name_cf, tokens_cf_list_for_contains):
                    matched_node_ids.update(related_nodes)
                    display_var = self.var_display_name_by_cf.get(var_name_cf, var_name_cf)
                    def_nodes = {nid for nid, _ in (self.var_definitions_by_name.get(var_name_cf, []) or []) if nid}
                    for related_node_id in related_nodes:
                        normalized_id = str(related_node_id or "")
                        if not normalized_id:
                            continue
                        role = "定义" if normalized_id in def_nodes else "使用"
                        var_relation_hints_by_node.setdefault(normalized_id, set()).add(f"{role}:{display_var}")

        # 3) 源码行范围过滤：支持 `@xxx.py (75-80)` 这类写法
        if source_spans:
            filtered_ids: set[str] = set()
            for node_id in matched_node_ids:
                src_line, src_end = self.node_source_range_by_id.get(node_id, (0, 0))
                start_line = int(src_line or 0)
                end_line = int(src_end or 0) if int(src_end or 0) > 0 else start_line
                if start_line <= 0:
                    continue

                overlaps_all = True
                for span_start, span_end in source_spans:
                    if end_line < int(span_start) or start_line > int(span_end):
                        overlaps_all = False
                        break
                if overlaps_all:
                    filtered_ids.add(node_id)
            matched_node_ids = filtered_ids

        if not matched_node_ids:
            return GraphSearchMatch(
                query=str(query or ""),
                tokens_cf=tokens_cf,
                source_spans=source_spans,
                node_ids=[],
                edge_ids_to_keep=[],
                var_relation_hints_by_node_id={},
            )

        def sort_key(node_id: str) -> Tuple[int, float, float, str]:
            pos = self.node_pos_by_id.get(node_id, (0.0, 0.0))
            export_rank = 1
            if isinstance(preferred_export_index, int) and preferred_export_index > 0:
                export_rank = 0 if int(self.node_export_index_by_id.get(node_id, 0) or 0) == int(preferred_export_index) else 1
            # 按视觉阅读顺序：Y → X → node_id（稳定）
            return (int(export_rank), float(pos[1]), float(pos[0]), str(node_id))

        ordered_node_ids = sorted(matched_node_ids, key=sort_key)

        edge_ids_to_keep_set: set[str] = set()
        for node_id in list(matched_node_ids):
            for edge_id in self.edge_ids_by_node_id.get(str(node_id), tuple()) or tuple():
                if edge_id in edge_ids_to_keep_set:
                    continue
                src_node_id, dst_node_id = self.edge_endpoints_by_id.get(str(edge_id), ("", ""))
                if src_node_id in matched_node_ids and dst_node_id in matched_node_ids:
                    edge_ids_to_keep_set.add(str(edge_id))
        edge_ids_to_keep: List[str] = sorted(edge_ids_to_keep_set)

        var_relation_hints_by_node_id: Dict[str, Tuple[str, ...]] = {}
        for node_id, hint_set in (var_relation_hints_by_node or {}).items():
            node_identifier = str(node_id or "")
            if not node_identifier:
                continue
            if not hint_set:
                continue
            var_relation_hints_by_node_id[node_identifier] = tuple(sorted(hint_set))

        return GraphSearchMatch(
            query=str(query or ""),
            tokens_cf=tokens_cf,
            source_spans=source_spans,
            node_ids=ordered_node_ids,
            edge_ids_to_keep=edge_ids_to_keep,
            var_relation_hints_by_node_id=var_relation_hints_by_node_id,
        )


def _tokenize_query(query: str) -> List[str]:
    text = str(query or "").strip()
    if not text:
        return []
    return [part.casefold() for part in text.split() if part.strip()]


def _tokenize_query_with_source_spans(query: str) -> tuple[List[str], List[Tuple[int, int]]]:
    """将查询拆分为 tokens + 源码行范围过滤。

    支持：
    - `@xxx.py (75-80)`
    - `@xxx.py 75-80`
    - `行：75-80`
    - `(75)` / `75`

    说明：
    - tokens 仍遵循“全字段包含所有 tokens”的默认语义；
    - 行范围用于在 tokens 匹配后进一步裁剪（按节点 source_lineno/source_end_lineno 交集判定）。
    """
    raw_text = str(query or "").strip()
    if not raw_text:
        return ([], [])

    raw_parts = [part for part in raw_text.split() if part.strip()]
    tokens_cf: List[str] = []
    spans: List[Tuple[int, int]] = []
    for part in raw_parts:
        span = _try_parse_source_span_token(part)
        if span is not None:
            spans.append(span)
            continue
        tokens_cf.append(str(part).casefold())
    return (tokens_cf, spans)


def _try_parse_source_span_token(token: str) -> Tuple[int, int] | None:
    text = str(token or "").strip()
    if not text:
        return None

    # 约定：为避免“数字搜索”与“行号过滤”冲突，只有在显式格式下才解析为行号过滤。
    # - 显式前缀：行: / 行：
    # - 显式括号：(...) / [...] / {...}
    # - 兼容：范围 token（75-80）允许无括号（通常用于 @file.py 之后的行号范围）
    raw_text = text
    has_wrapper = len(raw_text) >= 2 and raw_text[0] in "([{" and raw_text[-1] in ")]}"
    has_line_prefix = raw_text.startswith("行：") or raw_text.startswith("行:")
    is_range_token = "-" in raw_text

    # 常见前缀：行：75-80 / 行:75-80
    if has_line_prefix:
        text = text.split("：", 1)[-1] if "：" in text else text.split(":", 1)[-1]
        text = text.strip()

    # 去掉外围括号/分隔符
    text = text.strip().strip("()[]{}").strip()
    text = text.rstrip(",，.;；").strip()
    if not text:
        return None

    # 75-80
    if "-" in text:
        if not (has_line_prefix or has_wrapper or is_range_token):
            return None
        left, right = text.split("-", 1)
        left_text = left.strip()
        right_text = right.strip()
        if left_text.isdigit() and right_text.isdigit():
            start_line = int(left_text)
            end_line = int(right_text)
            if start_line <= 0 or end_line <= 0:
                return None
            if start_line > end_line:
                start_line, end_line = end_line, start_line
            return (start_line, end_line)
        return None

    # 单行：75
    if text.isdigit():
        if not (has_line_prefix or has_wrapper):
            return None
        line_no = int(text)
        return (line_no, line_no) if line_no > 0 else None

    return None


def _contains_all_tokens(haystack: str, tokens_cf: List[str]) -> bool:
    if not tokens_cf:
        return True
    if not haystack:
        return False
    for token in tokens_cf:
        if token not in haystack:
            return False
    return True


def _collect_text_fragments(
    value: Any,
    out_fragments: List[str],
    *,
    max_depth: int,
    max_items: int,
) -> None:
    """从常量值中递归提取可搜索文本片段。

    约束：
    - 不做 try/except；类型不支持时直接走 str(value) 回退。
    - 通过 max_depth/max_items 限制复杂度，避免超大常量导致搜索索引膨胀。
    """
    if value is None:
        return
    if len(out_fragments) >= int(max_items):
        return

    if isinstance(value, str):
        if value:
            out_fragments.append(value)
        return

    if isinstance(value, (int, float, bool)):
        out_fragments.append(str(value))
        return

    if max_depth <= 0:
        out_fragments.append(str(value))
        return

    if isinstance(value, dict):
        for key_obj, inner_obj in value.items():
            if len(out_fragments) >= int(max_items):
                return
            _collect_text_fragments(key_obj, out_fragments, max_depth=max_depth - 1, max_items=max_items)
            if len(out_fragments) >= int(max_items):
                return
            _collect_text_fragments(inner_obj, out_fragments, max_depth=max_depth - 1, max_items=max_items)
        return

    if isinstance(value, (list, tuple, set)):
        for item in value:
            if len(out_fragments) >= int(max_items):
                return
            _collect_text_fragments(item, out_fragments, max_depth=max_depth - 1, max_items=max_items)
        return

    out_fragments.append(str(value))


def _truncate_text(text: str, max_len: int) -> str:
    t = str(text or "")
    limit = int(max_len)
    if limit <= 0:
        return ""
    if len(t) <= limit:
        return t
    return t[: max(0, limit - 1)] + "…"


def _preview_value(value: Any, *, max_depth: int, max_items: int, max_len: int) -> str:
    """构建用于 UI 列表展示的“常量值短预览”。

    约束：
    - 不使用 try/except；类型不支持时回退到 str(value) 并截断。
    - 通过 max_depth/max_items/max_len 控制复杂度与长度，避免大对象拖慢 UI。
    """
    if value is None:
        return ""
    limit = int(max_len)
    if limit <= 0:
        return ""

    if isinstance(value, str):
        return _truncate_text(value, limit)

    if isinstance(value, (int, float, bool)):
        return _truncate_text(str(value), limit)

    if max_depth <= 0:
        return _truncate_text(str(value), limit)

    item_limit = max(1, int(max_items))

    if isinstance(value, dict):
        parts: List[str] = []
        for idx, (k, v) in enumerate(value.items()):
            if idx >= item_limit:
                parts.append("...")
                break
            key_text = _truncate_text(str(k), 16)
            val_text = _preview_value(v, max_depth=max_depth - 1, max_items=item_limit, max_len=32)
            if val_text:
                parts.append(f"{key_text}:{val_text}")
            else:
                parts.append(key_text)
        return _truncate_text("{" + ", ".join(parts) + "}", limit)

    if isinstance(value, (list, tuple, set)):
        parts = []
        for idx, item in enumerate(value):
            if idx >= item_limit:
                parts.append("...")
                break
            parts.append(_preview_value(item, max_depth=max_depth - 1, max_items=item_limit, max_len=32))
        open_bracket, close_bracket = ("[", "]") if isinstance(value, list) else ("(", ")")
        if isinstance(value, set):
            open_bracket, close_bracket = ("{", "}")
        return _truncate_text(open_bracket + ", ".join([p for p in parts if p]) + close_bracket, limit)

    return _truncate_text(str(value), limit)


def _append_unique(fragments: List[str], text: str) -> None:
    value = str(text or "").strip()
    if not value:
        return
    if value in fragments:
        return
    fragments.append(value)


def _extract_assigned_variable_names_from_line(line: str) -> Tuple[str, ...]:
    """从“赋值语句行”中提取左值变量名。

    支持：
    - `目标踏板GUID列表: "GUID列表" = 获取节点图变量(...)`
    - `原始位置, 原始旋转 = 获取实体位置与旋转(...)`

    不支持/不处理：
    - 属性赋值（如 `self.xxx = ...`）
    - 下标赋值（如 `arr[0] = ...`）
    """
    text = str(line or "")
    if not text:
        return tuple()
    # 去掉行内注释
    if "#" in text:
        text = text.split("#", 1)[0]
    if "=" not in text:
        return tuple()
    left = text.split("=", 1)[0].strip()
    if not left:
        return tuple()

    names: list[str] = []
    for part in left.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        if ":" in candidate:
            candidate = candidate.split(":", 1)[0].strip()
        if not candidate:
            continue
        # 过滤属性/下标等复杂左值，仅保留纯变量名
        if candidate.isidentifier():
            names.append(candidate)

    # 去重但保序
    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return tuple(deduped)


