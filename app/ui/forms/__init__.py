"""表单与对话框辅助模块入口。

当前主要导出：
- `FormDialogBuilder`：基于 `FormDialog` 的轻量表单构建器，集中封装常见输入控件。

更高层的表单 schema 或领域专用表单应在各自模块中定义，本包仅提供 UI 层的构建工具。
"""

from .schema_dialog import FormDialogBuilder

__all__ = ["FormDialogBuilder"]


