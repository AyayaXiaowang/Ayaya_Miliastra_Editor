## 目录用途
- 存放“通用 UI 写回补丁”：在不改变 UI 树结构的前提下，对指定 GUID 的控件做定向修改（名称/显隐/RectTransform/样式等），用于批量修复或验证写回能力。

## 当前状态
- `control_variants.py`：通用控件属性写回（按 GUID 改名/显隐/RectTransform 位置大小/层级）。
- `textboxes.py`：文本框控件写回补丁（GUID 分配/层级/RectTransform 等）。
- `item_display_variants.py`：道具展示控件的差异化配置写回。
- `progressbar_variants.py` / `progressbar_recolor_full.py`：进度条样式/颜色/绑定相关写回。
- `add_progress_bars.py`：在指定父组下新增进度条控件（复制模板 record 并写回）。

## 注意事项
- 不使用 try/except；失败直接抛错，避免写坏存档。
- 跨模块复用必须走公开 API（无下划线），禁止导入 `layout_templates_parts/shared.py` 的 `_private_name`；应使用其公开函数（例如 `dump_gil_to_raw_json_object`、`find_record_by_guid`、`write_back_modified_gil_by_reencoding_payload` 等）。
- 产物统一写入 `ugc_file_tools/out/`（由上层入口负责路径收口），避免覆盖原始样本。