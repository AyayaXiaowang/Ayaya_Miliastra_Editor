"""
custom_variables

说明：
- 该包用于收敛“自定义变量”相关的纯逻辑规则（解析/归一化/类型/spec/value message 构造）。
- 不做 I/O，不依赖 UI（不得导入 ui_patchers/*）。
"""

# 注意：此处不做 re-export，避免仅导入 `custom_variables.constants` 时触发额外模块导入链路与潜在循环依赖。
# 请按需显式导入子模块：
# - `ugc_file_tools.custom_variables.constants`
# - `ugc_file_tools.custom_variables.refs`
# - `ugc_file_tools.custom_variables.defaults`

