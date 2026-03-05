## 目录用途

- 存放 `ugc_file_tools` 的**程序内置资源（seed）**：运行时/导出中心/写回管线会直接依赖这些文件作为“空存档基底/模板原型/最小 UI 夹具”等。
- 与 `save/` 区分：`save/` 是人工维护的“输入样本库”（可能含未授权/真源样本）；`builtin_resources/` 仅包含**对外仓库可版本化**且**可作为默认依赖**的最小 seed。

## 当前状态

- `empty_base_samples/empty_base_with_infra.gil`：导出中心“使用内置空存档（默认布局）”的 base（带基础设施）。
- `empty_base_samples/empty_base_vacuum.gil`：极空基底（用于 bootstrapping/回归）。
- `seeds/infrastructure_bootstrap.gil`：基础设施 bootstrap 模板（补齐 root4/11、root4/35、root4/6、root4/22 等缺口）。
- `seeds/template_instance_exemplars.gil`：模板/实例导入的克隆原型（优先包含 `type_code=10005018` 的“空模型元件”样本）。
- `template_library/`：节点图写回模板库（server/client），供默认路径与递归扫描使用。
- `bootstrap_min_sections/min_ui_node9.json`：极简 base 缺失 UI 段时的最小 UI 夹具。
- `dtype/dtype.json`：默认 dtype（字段/类型描述），供 `.gil/.gia` 解析与导出链路读取。
- `空的界面控件组/进度条样式.gil`：UI bootstrap 的兜底 seed（当夹具不足或需补齐更多 root4 段时使用）。
- `seeds/struct_def_exemplars.gil`、`seeds/ingame_save_structs_bootstrap.gil`、`seeds/signal_node_def_templates.gil`：结构体/局内存档结构体/信号写回的默认模板候选。
- `gia_templates/`：内置 `.gia` 模板资源（信号/结构体/布局资产等导出链路默认依赖的结构模板）。

## 注意事项

- 该目录内容应随仓库分发：代码引用缺失应 fail-fast 抛错，避免静默降级。
- 保持最小化：只收纳“默认链路必需/稳定可公开”的 seed；其余真源样本请放在 `save/` 并默认忽略。
- `seeds/*.gil` 已裁剪为最小顶层字段集合（用于结构模板/夹具），如需重建请使用 `tools/minimize_ugc_file_tools_seed_gils.py`。

