## 目录用途
- 存放 UI 布局相关的写回/导出工具（围绕 `.gil` 的 UI 段）：布局模板写回、布局资产 `.gia` 导出、以及少量布局修复补丁入口。
- 本目录偏“门面层/入口层”：可复用的低层 record/children/registry 操作统一下沉到 `layout_templates_parts/`。

## 当前状态
- `layout_templates.py`：布局/控件组写回入口（对外兼容）；内部实现拆分在 `layout_templates_parts/`。
- `fix_pc_canvas_center_anchor_controls.py`：校正 PC 画布尺寸切换导致贴边控件漂移的问题（anchor 修正 + anchored_position 重算）。
- `layout_asset_gia.py`：从 `.gil` 提取“布局 root + children”并导出为布局资产 `.gia`（非 NodeGraph）。

## 注意事项
- 不使用 try/except；结构不符合预期直接抛错（fail-fast）。
- 跨模块复用必须走公开 API（无下划线），禁止 `from ... import _private_name`；低层能力统一从 `layout_templates_parts/shared.py` 的公开函数导入。