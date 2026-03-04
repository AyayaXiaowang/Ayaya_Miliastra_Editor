from __future__ import annotations

"""
layout_templates_parts

将 `layout_templates.py` 的实现按职责拆分到多个小模块中：
- `shared.py`：常量、dataclass 与通用工具函数（varint/children/record 操作、DLL dump、写回等）
- `layout_create.py`：新增布局 root
- `progressbar_templates.py`：创建进度条模板并放置实例
- `control_groups.py`：控件打组/保存模板/层级写回

上层入口仍保留在 `ugc_file_tools.ui_patchers.layout_templates`，以确保对外导入兼容。
"""



