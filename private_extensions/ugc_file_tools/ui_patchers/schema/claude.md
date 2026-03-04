## 目录用途
- 存放“基于 UI Schema Library 的写回能力”：将已沉淀的 schema record 克隆/实例化到 `.gil` 的 UI 段，用于快速复用已验证结构（避免手工拼 record）。

## 当前状态
- `schema_clone.py`：从 `ugc_file_tools/ui_schema_library` 克隆 UI record（可选改名/改坐标/改层级/注册到布局表）。
- `custom_variable_defaults_fixer.py`：基于 HTML 的 `data-ui-variable-defaults` 校正并补齐实体自定义变量默认值（写回 `.gil`）。
- `custom_variable_specs.py`：自定义变量 spec 的门面/兼容入口（单一真源在 `ugc_file_tools/custom_variables/*`）。

## 注意事项
- 不使用 try/except；遇到结构不一致直接抛错。
- 跨模块复用必须走公开 API（无下划线）；与 UI record 低层操作相关的通用能力应从 `ui_patchers/layout/layout_templates_parts/shared.py` 的公开函数导入。