"""“背包”通用组件表单。"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6 import QtWidgets

from app.ui.forms.schema_bound_form import FormFieldSpec, SchemaBoundForm


def create_backpack_form(
    settings: Dict[str, object],
    parent: QtWidgets.QWidget,
    *,
    on_settings_changed: Optional[Callable[[], None]] = None,
) -> QtWidgets.QWidget:
    """为“背包”组件创建简单表单，只暴露背包容量字段。

    说明：
    - 使用 settings["背包容量"] 作为单一配置项，默认值为 20。
    - 该设置与引擎侧 BackpackComponentConfig.to_dict() 的字段名称保持一致。
    """
    container = QtWidgets.QWidget(parent)
    layout = QtWidgets.QFormLayout(container)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(4)

    schema_form = SchemaBoundForm(
        container,
        [
            FormFieldSpec(
                key="背包容量",
                label="背包容量:",
                kind="int_spin",
                default=20,
                minimum_int=0,
                maximum_int=9999,
                on_changed=(
                    (lambda _value: on_settings_changed())
                    if on_settings_changed is not None
                    else None
                ),
            )
        ],
        settings,  # type: ignore[arg-type]
    )
    schema_form.build_into(layout)
    # 绑定器需要保活：信号回调引用实例方法，避免局部变量被提前回收
    container._schema_form = schema_form  # type: ignore[attr-defined]
    return container


__all__ = ["create_backpack_form"]


