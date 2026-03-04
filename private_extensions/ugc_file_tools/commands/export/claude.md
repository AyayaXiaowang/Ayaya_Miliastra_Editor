## 目录用途
`ugc_file_tools` 的导出类命令集合：将资源库中的节点图/模板/信号/结构体等导出为中间产物（如 GraphModel(JSON)、Graph IR、`.gia` 等），用于写回、对比与诊断。

## 当前状态
- 节点图导出入口以 `export_graph_model_json_from_graph_code.py` 为核心：负责把 Graph Code 解析为 GraphModel，并补充端口类型推断信息，输出到 `ugc_file_tools/out/`。
- 校准图集批量导出由 `export_calibration_graph_models.py` 提供：用于批量生成 GraphModel(JSON) 供后续写回/差异分析。
- 默认采用 **严格解析（fail-closed）** 对齐资源加载链路；在需要“尽力产出中间产物用于诊断”的场景，可切换为 **非严格解析**（允许图结构问题存在，但仍输出 GraphModel 供后续工具分析）。
- 节点图 `.gia` 导出支持 `--id-ref-gil` 与 `--id-ref-overrides-json`：用于回填 `entity_key/component_key` 占位符（找不到同名时可用 overrides 手动覆盖）。
- 元件相关导出：
  - `export_project_templates_instances_bundle_gia.py`：项目存档 → 导出“元件模板+实体摆放(装饰物实例)” bundle.gia（wire-level 保真切片；依赖模板 JSON 的 `metadata.ugc.source_gia_file`）。

## 注意事项
- 工具默认不吞错；严格模式下失败会直接抛出，便于定位问题源头。
- 输出文件强制落到 `ugc_file_tools/out/`（由 `output_paths` 统一管理），避免污染仓库其它目录。

