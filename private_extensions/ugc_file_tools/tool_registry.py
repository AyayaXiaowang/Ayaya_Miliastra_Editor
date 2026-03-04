from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """统一工具注册表条目（ugc_file_tools tool 子命令可转发的工具）。"""

    name: str
    summary: str
    risk: str
    section: str


TOOL_SPECS: tuple[ToolSpec, ...] = (
    # 解析导出（`.gil` → 项目存档/结构化数据）
    ToolSpec(
        name="extract_gil_to_package",
        risk="写盘",
        section="解析导出（`.gil` → 项目存档/结构化数据）",
        summary=".gil 导出为项目存档目录（核心实现：gil_package_exporter/）。",
    ),
    ToolSpec(
        name="parse_package",
        risk="只读/写盘",
        section="解析导出（`.gil` → 项目存档/结构化数据）",
        summary="解析项目存档并输出结构化摘要 JSON。",
    ),
    ToolSpec(
        name="parse_gil_to_model",
        risk="写盘",
        section="解析导出（`.gil` → 项目存档/结构化数据）",
        summary="一键入口：导出项目存档 → 输出摘要（可选 codegen）。",
    ),
    ToolSpec(
        name="parse_gil_to_full_model",
        risk="写盘",
        section="解析导出（`.gil` → 项目存档/结构化数据）",
        summary="全量入口：导出 → 摘要 → codegen → 校验（更重）。",
    ),
    ToolSpec(
        name="gil_to_readable_json",
        risk="写盘",
        section="解析导出（`.gil` → 项目存档/结构化数据）",
        summary="自研可读 JSON dump（用于分析 protobuf-like payload）。",
    ),

    # 节点图 IR（可读节点图导出/分析）
    ToolSpec(
        name="export_graph_ir_from_package",
        risk="写盘",
        section="节点图 IR（可读节点图导出/分析）",
        summary="从项目存档导出 Graph IR（JSON/Markdown）。",
    ),
    ToolSpec(
        name="parse_gil_to_graph_ir",
        risk="写盘",
        section="节点图 IR（可读节点图导出/分析）",
        summary="从 .gil（可选先导出项目存档）导出 Graph IR。",
    ),
    ToolSpec(
        name="parse_gil_payload_to_graph_ir",
        risk="写盘",
        section="节点图 IR（可读节点图导出/分析）",
        summary="直接解析 .gil payload（10.1.1 NodeGraph blob）导出 Graph IR（更贴近 .gia pins/edges）。",
    ),
    ToolSpec(
        name="parse_gia_to_graph_ir",
        risk="写盘",
        section="节点图 IR（可读节点图导出/分析）",
        summary="从 .gia 解析并导出 Graph IR（结合 node_data/index.json 补全提示）。",
    ),
    ToolSpec(
        name="inspect_parsed_node_graphs",
        risk="只读",
        section="节点图 IR（可读节点图导出/分析）",
        summary="打印内部解析后的 nodes/edges 摘要，便于 sanity check。",
    ),

    # `.gia` 辅助导出/写回
    ToolSpec(
        name="gia_to_readable_json",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="导出 .gia 为可读 JSON（protobuf-like lossless field map；用于分析/对照）。",
    ),
    ToolSpec(
        name="export_project_templates_to_gia",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="从项目存档导出元件模板为 .gia（包含自定义变量；基于 base 元件 .gia 克隆结构）。",
    ),
    ToolSpec(
        name="export_project_templates_instances_bundle_gia",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="项目存档 → 从模板 JSON 的 source_gia_file 做 wire-level 切片，导出“元件模板+实体摆放(实例)” bundle.gia（保真保装饰物）。",
    ),
    ToolSpec(
        name="export_project_player_templates_to_gia",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="从项目存档导出玩家模板为 .gia（包含自定义变量；基于 base 玩家模板 .gia 克隆结构）。",
    ),
    ToolSpec(
        name="import_player_template_gia_to_project_archive",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="将玩家模板 .gia 导入到项目存档（生成玩家模板 JSON + 变量文件；保留自定义变量）。",
    ),
    ToolSpec(
        name="import_gia_templates_and_instances_to_project_archive",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="将包含“元件模板 + 装饰物/实体摆放”的 .gia 包导入到项目存档（生成 元件库/实体摆放 JSON + 索引）。",
    ),
    ToolSpec(
        name="import_gia_node_graphs_to_project_archive",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="将 `.gia` NodeGraph 导入到项目存档（生成 节点图 Graph Code；可选导入后综合校验）。",
    ),
    ToolSpec(
        name="list_gia_entities",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="解析实体类/装饰物挂件类 .gia 的 accessories，导出实体清单 JSON（含 pos/yaw/scale/template_id；可按颜色归类 circle/rect）。",
    ),
    ToolSpec(
        name="create_multi_param_signal_demo_gia",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="生成一个自包含的“多参数信号”节点图 .gia（不依赖 base .gil）。",
    ),
    ToolSpec(
        name="create_node_graph_from_signal_def_gia",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="从一个信号定义样本 .gia 提取端口索引，生成调用该信号的节点图 .gia（用于真源校验对照）。",
    ),
    ToolSpec(
        name="gia_build_decorations_bundle",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="从 decorations_*.report.json 生成“装饰物挂件类” .gia（基于 base .gia 作为结构模板）。",
    ),
    ToolSpec(
        name="gia_build_asset_bundle_decorations",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="从 decorations_*.report.json 生成“资产包类” .gia（基于 base 资产包 .gia 作为结构模板）。",
    ),
    ToolSpec(
        name="gia_export_decorations_variants",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="批量导出多种 .gia 变体（实体/资产包），用于二分定位真源导入约束（可选复制到 Beyond_Local_Export）。",
    ),
    ToolSpec(
        name="gia_patch_file_path_wire",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="保真 wire-level patch：只替换 Root.filePath（用于验证重编码是否破坏真源可见性）。",
    ),
    ToolSpec(
        name="gia_build_decorations_bundle_wire",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="wire-level 保真：基于实体类 base .gia 克隆装饰物记录并批量生成 N 个装饰物（同时更新 relatedIds/filePath）。",
    ),
    ToolSpec(
        name="gia_build_entity_decorations_wire",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="wire-level：生成“带装饰物的实体类” .gia（同步写入 relatedIds + parent 内部 packed id 列表，并修正装饰物对 parent id 的绑定）。",
    ),
    ToolSpec(
        name="gia_merge_and_center_decorations",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="wire-level：装饰物合并/居中（默认 keep_world：移动 parent 并补偿 local，装饰物世界坐标不动；也支持 move_decorations）；多 parent 可合并挂到同一 parent（更新 relatedIds/parent bind/packed list）。",
    ),
    ToolSpec(
        name="gia_convert_component_entity",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="wire-level：对“元件模板+实体摆放(实例)” bundle.gia 做元件↔实体双向转换（Root.field_1 templates / Root.field_2 instances）。",
    ),
    ToolSpec(
        name="gia_process_preview_entities_in_pack",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="wire-level：对打包 .gia 内匹配的预览实体做居中/同关合并，并整体平移使控模型到原点（best-effort）。",
    ),
    ToolSpec(
        name="gia_graph_ir_to_gia",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="将 parse_gia_to_graph_ir 导出的 Graph IR JSON 写回/生成 .gia（输出强制落盘到 out/）。",
    ),
    ToolSpec(
        name="export_basic_structs_to_gia",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="导出基础结构体（共享根 + 项目存档根的 *.py）为 .gia（StructureDefinition GraphUnit）。",
    ),
    ToolSpec(
        name="export_basic_signals_to_gia",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="导出基础信号（共享根 + 项目存档根的 *.py）为 .gia（信号相关 node_defs GraphUnit）。",
    ),
    ToolSpec(
        name="create_minimal_send_signal_variants_gia",
        risk="写盘",
        section="`.gia` 辅助导出/写回",
        summary="生成最小的“实体创建时 + 发送信号”节点图 3 变体并导出为 .gia（不连线/直接填参/连线参数）。",
    ),

    # Graph Code（反编译/生成）
    ToolSpec(
        name="generate_graph_code_from_package",
        risk="写盘",
        section="Graph Code（反编译/生成）",
        summary="从项目存档批量生成 Graph Code（Python）。",
    ),
    ToolSpec(
        name="generate_graph_code_from_pyugc_graph",
        risk="写盘",
        section="Graph Code（反编译/生成）",
        summary="无参考反编译：从单图 pyugc_graph JSON 生成 Graph Code。",
    ),
    ToolSpec(
        name="generate_graph_code_from_flow_chain",
        risk="写盘",
        section="Graph Code（反编译/生成）",
        summary="从线性 flow 链生成 Graph Code（偏校准/复刻）。",
    ),
    ToolSpec(
        name="export_graph_model_json_from_graph_code",
        risk="写盘",
        section="Graph Code（反编译/生成）",
        summary="Graph Code → GraphModel(JSON)（用于后续写回/布局）。",
    ),
    ToolSpec(
        name="export_calibration_graph_models",
        risk="写盘",
        section="Graph Code（反编译/生成）",
        summary="批量导出 Graph_Generater 资源库的校准图集为 *.graph_model.typed.json（输出到 out/）。",
    ),
    ToolSpec(
        name="generate_ui_action_dispatcher_graph_code",
        risk="写盘",
        section="Graph Code（反编译/生成）",
        summary="从 管理配置/UI交互映射/*.ui_actions.json 生成“UI 交互待绑定清单”（JSON 报告；不生成节点图）。",
    ),
    ToolSpec(
        name="sync_ui_guid_registry_from_gil",
        risk="写盘",
        section="Graph Code（反编译/生成）",
        summary="以 base .gil 的 UI records 为准校准 ui_guid_registry.json（用于修复 ui_key 回填错 ID；保存带历史留档）。",
    ),
    ToolSpec(
        name="sync_component_id_registry_from_gil",
        risk="写盘",
        section="Graph Code（反编译/生成）",
        summary="以 base .gil 抽取“元件名→元件ID”并写入 component_id_registry.json（用于 component_key 回填；保存带历史留档）。",
    ),
    ToolSpec(
        name="export_ui_workbench_bundles_from_html",
        risk="写盘",
        section="UI（Workbench/HTML）",
        summary="项目存档 UI源码 HTML → 生成/更新 Workbench bundle（写入 UI源码/__workbench_out__/*.ui_bundle.json）。",
    ),
    ToolSpec(
        name="export_project_graphs_to_gia",
        risk="写盘",
        section="Graph Code（反编译/生成）",
        summary="从项目存档导出节点图为 .gia（复用 UI 导出口径；支持按 graph_code 文件子集导出）。",
    ),
    ToolSpec(
        name="inspect_ui_guid",
        risk="只读",
        section="节点图 IR（可读节点图导出/分析）",
        summary="给定一个 UI guid，反查对应的 ui_key / UI record 名称 / 父子关系（只读）。",
    ),

    # 节点类型/语义映射辅助
    ToolSpec(
        name="export_graph_generater_node_ports",
        risk="写盘",
        section="节点类型/语义映射辅助",
        summary="从 Graph_Generater 节点库导出 inputs/outputs 清单。",
    ),
    ToolSpec(
        name="build_node_type_semantic_map_from_calibration",
        risk="写盘",
        section="节点类型/语义映射辅助",
        summary="用校准图对齐语义映射，生成/补全 graph_ir/node_type_semantic_map.json。",
    ),
    ToolSpec(
        name="import_type_id_cn_mapping_csv",
        risk="写盘",
        section="节点类型/语义映射辅助",
        summary="将人工整理的 type_id→中文名 CSV 批量导入到 graph_ir/node_type_semantic_map.json。",
    ),
    ToolSpec(
        name="report_node_type_semantic_map_invalid_nodes",
        risk="只读/写盘",
        section="节点类型/语义映射辅助",
        summary="校验 node_type_semantic_map.json 中中文节点名是否都存在于实现节点库；默认输出报告到 out/；发现无效会抛错。",
    ),
    ToolSpec(
        name="report_node_type_semantic_map_coverage",
        risk="只读/写盘",
        section="节点类型/语义映射辅助",
        summary="生成映射覆盖率报告：列出实现节点库已实现但映射表缺失的节点名等（输出到 out/）。",
    ),
    ToolSpec(
        name="report_node_type_semantic_map_vs_genshin_ts",
        risk="只读/写盘",
        section="节点类型/语义映射辅助",
        summary="交叉诊断：对齐 node_type_semantic_map.json 与 genshin-ts node schema/concrete_map（输出到 out/）。",
    ),
    ToolSpec(
        name="create_type_id_matrix_in_gil",
        risk="危险写盘",
        section="节点类型/语义映射辅助",
        summary="在 .gil 中新增 type_id 矩阵图（用于截图校准/映射补全）。",
    ),
    ToolSpec(
        name="create_type_id_list_graph_in_gil",
        risk="危险写盘",
        section="节点类型/语义映射辅助",
        summary="在 .gil 中新增 type_id 列表图（用于生成全节点样本库图，或按自定义 list 批量造节点）。",
    ),

    # `.gil` 写回（结构体/节点图）
    ToolSpec(
        name="add_struct_definition_to_gil",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="向 .gil 写回结构体定义（多种 preset）。",
    ),
    ToolSpec(
        name="add_signal_definition_to_gil",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="向 .gil 写回信号定义（含参数）并生成对应节点定义（发送/监听/向服务器发送）。",
    ),
    ToolSpec(
        name="fix_gil_signal_param_field6",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="修复 .gil 信号参数定义缺失 field_6(send_to_server_port_index) 的损坏问题（wire-level 最小补丁）。",
    ),
    ToolSpec(
        name="merge_gil_signal_entries",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="wire-level：合并两条 signal entry（指定 keep/remove，可选重命名 keep），并 remap 节点图引用 + 修补 compositePinIndex + 清理冗余 node_defs。",
    ),
    ToolSpec(
        name="repair_gil_signals_from_imported_gia",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="给定 .gil 与已导入 .gia 列表，自动执行信号修复（去重复用/重绑引用/补齐参数 field_6/清理残留）。",
    ),
    ToolSpec(
        name="repair_gil_signals_from_export_report",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="给定 .gil 与 export_project_graphs_to_gia 的 report.json，自动收集 .gia 并执行信号修复（复用 repair_gil_signals_from_imported_gia）。",
    ),
    ToolSpec(
        name="create_signal_listener_graph_in_gil",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="为存档内所有信号生成“监听信号节点墙”节点图，并写回输出新 .gil。",
    ),
    ToolSpec(
        name="create_node_graph_in_gil",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="新增一张节点图并写回输出新 .gil。",
    ),
    ToolSpec(
        name="add_node_to_gil_node_graph",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="向指定节点图追加节点并写回输出新 .gil。",
    ),
    ToolSpec(
        name="graph_model_json_to_gil_node_graph",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="GraphModel(JSON) → 写回 .gil 节点图段（flow/data 连线）。",
    ),
    ToolSpec(
        name="export_gil_writeback_variants_for_bisect",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="批量导出多份 GIL 写回变体（通过 UGC_WB_DISABLE 禁用不同补丁点），用于进游戏二分定位“到底哪处补丁让真源可识别”。",
    ),
    ToolSpec(
        name="sync_graph_code_to_gil_preserve_graph_variables",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="将本地 Graph Code 写回覆盖到目标 .gil；GraphVariables 增删改以本地为准；同名变量 default_value 可选保留目标 .gil 的值（参数开关）。",
    ),
    ToolSpec(
        name="edit_template_in_gil",
        risk="危险写盘",
        section="`.gil` 写回（结构体/节点图）",
        summary="修改/克隆 .gil 的元件库模板（TemplateConfig-like），并写回输出新 .gil。",
    ),

    # 维护/诊断辅助
    ToolSpec(
        name="report_node_graph_writeback_coverage",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="统计节点图写回样本覆盖情况（输出报告）。",
    ),
    ToolSpec(
        name="report_graph_writeback_gaps",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="写回覆盖差异报告：对比 GraphModel(JSON) 需求 vs 模板样本库覆盖，输出 gap 清单到 out/。",
    ),
    ToolSpec(
        name="report_gia_vs_gil_graph_ir_diff",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="对同一份 GraphModel 同时跑 GIA 导出与 GIL 写回，解析两边 Graph IR 并输出差异报告（用于定位口径分叉：GIA 有但 GIL 没有/不一致）。",
    ),
    ToolSpec(
        name="report_gil_payload_graph_ir_diff",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="对比两份 .gil 的 payload NodeGraph Graph IR（edges/pins），输出差异报告（用于定位“游戏处理后导出 vs 工具直接处理”的结构差异）。",
    ),
    ToolSpec(
        name="report_gil_dump_json_diff",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="对比两份 .gil 的 dump-json(payload 数值键 JSON)，输出深度 diff 报告（按路径列出差异；可选落盘两侧 dump-json）。",
    ),
    ToolSpec(
        name="report_gil_payload_root_wire_sections_diff",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="wire-level 对照：按 payload_root field_number 对比两份 .gil 的 length-delimited section payload bytes 是否完全一致（用于证明是否发生 payload drift）。",
    ),
    ToolSpec(
        name="auto_wire_graph_writeback_gaps_in_gil",
        risk="危险写盘",
        section="维护/诊断辅助",
        summary="根据 report_graph_writeback_gaps 的 JSON 报告，在指定 .gil 的节点图里自动写入 data-link/OutParam record（减少人工连线）。",
    ),
    ToolSpec(
        name="report_graph_variable_truth_diff",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="扫描真源 .gil 的 GraphEntry['6']，并与 Graph_Generater VARIABLE_TYPES 做差异对比（报告写入 out/）。",
    ),
    ToolSpec(
        name="check_graph_variable_writeback_contract",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="合约校验：检查写回产物 .gil 的 GraphEntry['6'] 变量表类型集合/keyType/valueType 是否满足不变量。",
    ),
    ToolSpec(
        name="check_get_custom_variable_dict_outparam",
        risk="写盘",
        section="维护/诊断辅助",
        summary="端到端诊断：导出 GraphModel→写回临时 .gil→解析 payload NodeGraph IR，校验 Get_Custom_Variable 的字典 OUT_PARAM(MapBase K/V) 是否对齐 GraphModel 推断，避免“字典退化为整数”。",
    ),
    ToolSpec(
        name="build_minimal_graph_variables_reference_gil",
        risk="危险写盘",
        section="维护/诊断辅助",
        summary="生成“节点图变量全类型”的最简参考 .gil（清空 nodes，仅保留/重建 GraphEntry['6']；可选跑合约校验）。",
    ),
    ToolSpec(
        name="extract_graph_entry_demo_gil",
        risk="危险写盘",
        section="维护/诊断辅助",
        summary="从已有 .gil 抽取/裁剪单张节点图，用于制作最小示范存档（可清空 nodes/过滤变量）。",
    ),
    ToolSpec(
        name="report_node_template_coverage_diff",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="对齐写回脚本的节点模板库机制：对比 template 覆盖集合 vs GraphModel 所需节点，输出差异报告。",
    ),
    ToolSpec(
        name="refresh_project_archive_parse_status",
        risk="写盘",
        section="维护/诊断辅助",
        summary="批量刷新/重建 parse_status/ 下解析状态文档。",
    ),
    ToolSpec(
        name="merge_level_select_preview_components",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="项目存档维护：合并“选关预览”双元件关卡展示元件为单母体（keep_world 合并 decorations），并同步补丁 GraphVariables 与执行图逻辑（默认 dry-run；需 --dangerous 才写盘）。",
    ),
    ToolSpec(
        name="merge_project_instances_keep_world",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="项目存档维护：合并多个实体摆放实例为一个新实例（keep_world：保持装饰物世界变换不变）。输出新模板 + 新实例；默认 dry-run，需 --dangerous 才写盘并重建索引。",
    ),
    ToolSpec(
        name="list_gil_ids",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="直接解析 .gil，列出其中包含的元件(template_id)/实体(instance_id) ID 清单并导出 JSON。",
    ),
    ToolSpec(
        name="patch_gil_add_motioner",
        risk="危险写盘",
        section="维护/诊断辅助",
        summary="危险写盘：为指定实例补齐“运动器(Motioner)”组项（root4/5/1[*].7 追加 {1:4,2:1,14:{505:1}}），输出新 .gil 到 out/。",
    ),
    ToolSpec(
        name="inspect_gil_signals",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="只读分析：从 .gil 提取 signal entries(root4/10/5/3) + NodeGraph 内信号节点使用情况摘要（用于多点发送/监听信号排查与格式反推）。",
    ),
    ToolSpec(
        name="inspect_json",
        risk="只读",
        section="维护/诊断辅助",
        summary="通用 JSON 深层路径查询/探测（dict/list；支持 keys/len 预览与 trace）。",
    ),
    ToolSpec(
        name="decode_gil",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="通用字节流解析与 dump（用于二次分析嵌套 data）。",
    ),
    ToolSpec(
        name="export_center_scan_base_gil_conflicts",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="导出中心辅助：在子进程中扫描 base `.gil` 的冲突信息（UI布局/节点图/模板/实体），输出 report.json 供 overwrite/add/skip 弹窗使用。",
    ),
    ToolSpec(
        name="export_center_scan_gil_id_ref_candidates",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="导出中心辅助：在子进程中扫描指定 `.gil` 的“元件名→元件ID / 实体名→实体GUID”候选全集，输出 report.json 供 UI 手动选择缺失 ID 的兜底交互使用。",
    ),
    ToolSpec(
        name="export_center_identify_gil_backfill_comparison",
        risk="只读/写盘",
        section="维护/诊断辅助",
        summary="导出中心辅助：在子进程中执行回填识别（identify_gil_backfill_comparison），输出 report.json 供 UI 表格渲染与缺失项提示。",
    ),
)


_TOOL_NAMES: list[str] = [t.name for t in TOOL_SPECS]
if any(str(n).strip() == "" for n in _TOOL_NAMES):
    raise ValueError("tool_registry: 工具名不能为空")
if len(_TOOL_NAMES) != len(set(_TOOL_NAMES)):
    duplicated = sorted({n for n in _TOOL_NAMES if _TOOL_NAMES.count(n) > 1})
    raise ValueError(f"tool_registry: duplicated tool names: {duplicated}")

TOOL_NAME_SET: frozenset[str] = frozenset(_TOOL_NAMES)


def iter_tool_specs() -> tuple[ToolSpec, ...]:
    return TOOL_SPECS


def iter_tool_module_names() -> list[str]:
    return list(_TOOL_NAMES)


def find_tool_spec(tool_name: str) -> ToolSpec | None:
    normalized = str(tool_name or "").strip().replace("-", "_")
    if normalized == "":
        return None
    for spec in TOOL_SPECS:
        if spec.name == normalized:
            return spec
    return None


