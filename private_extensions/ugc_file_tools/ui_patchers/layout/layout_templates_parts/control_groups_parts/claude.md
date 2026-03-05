## 目录用途
- `layout_templates_parts/control_groups.py` 的拆分实现区：承载“控件组打组/保存模板/模板落布局/层级与 RectTransform 修正”等实现细节。
- 对外稳定入口仍为 `ugc_file_tools.ui_patchers.layout.layout_templates_parts.control_groups`（薄门面 + re-export）。

## 当前状态
- parts 目录仅用于内部实现拆分；外部模块不应直接依赖 `control_groups_parts/*` 的具体路径。

## 注意事项
- 不使用 try/except；结构不一致/字段缺失直接抛错（fail-fast）。
- 跨模块复用必须通过公开 API（无下划线）从门面层导出；避免外部直接导入 parts 子模块或 `_private_name`。

