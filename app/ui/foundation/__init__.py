"""UI 基础设施与通用工具组件包。

包含基础控件、主题与样式管理、通用交互辅助方法以及滚动/刷新等与具体业务无关的 UI 工具。

对外暴露的核心入口包括：
- 统一风格的对话框基类：BaseDialog, FormDialog
- 标准化的消息框与输入对话框：show_*_dialog, ask_*_dialog, prompt_* 系列
- 主题与样式管理：ThemeManager 及 Colors/Sizes/Icons/Gradients/HTMLStyles
"""

from app.ui.foundation.base_widgets import BaseDialog, FormDialog
from app.ui.foundation.dialog_utils import (
    apply_standard_button_box_labels,
    ask_acknowledge_or_suppress_dialog,
    ask_yes_no_dialog,
    show_error_dialog,
    show_info_dialog,
    show_warning_dialog,
)
from app.ui.foundation.input_dialogs import (
    prompt_int,
    prompt_item,
    prompt_text as _form_prompt_text,
)
from app.ui.foundation.theme_manager import ThemeManager

prompt_text = _form_prompt_text
prompt_form_text = _form_prompt_text

__all__ = [
    "BaseDialog",
    "FormDialog",
    "ThemeManager",
    "apply_standard_button_box_labels",
    "ask_acknowledge_or_suppress_dialog",
    "ask_yes_no_dialog",
    "prompt_text",
    "prompt_form_text",
    "prompt_item",
    "prompt_int",
    "show_error_dialog",
    "show_info_dialog",
    "show_warning_dialog",
]
