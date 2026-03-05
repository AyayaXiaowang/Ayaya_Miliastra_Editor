from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets

from app.ui.foundation import dialog_utils, prompt_text

__all__ = ["prompt_entity_name", "confirm_entity_delete", "validate_unique_entity_name"]


def prompt_entity_name(
    parent: QtWidgets.QWidget,
    *,
    title: str,
    label: str,
    placeholder: str = "",
    text: str = "",
) -> Optional[str]:
    """统一的命名输入入口，保持布局/模板面板的交互一致。"""
    return prompt_text(
        parent,
        title,
        label,
        placeholder=placeholder,
        text=text,
    )


def confirm_entity_delete(
    parent: QtWidgets.QWidget,
    name: str,
    *,
    extra_message: str = "",
) -> bool:
    """统一的删除确认提示。"""
    message = f"确定要删除 '{name}' 吗？"
    if extra_message:
        message = f"{message}\n{extra_message}"
    return dialog_utils.ask_yes_no_dialog(parent, "确认删除", message)


def validate_unique_entity_name(
    parent: QtWidgets.QWidget,
    name: str,
    *,
    entity_label: str,
    existing_names,
    exclude_name: str | None = None,
    case_sensitive: bool = False,
) -> str | None:
    """对实体名称进行空值与唯一性校验，返回合法名称或 None。"""
    normalized = (name or "").strip()
    if not normalized:
        dialog_utils.show_warning_dialog(
            parent,
            "名称无效",
            f"{entity_label}名称不能为空。",
        )
        return None

    if case_sensitive:
        key = normalized
        exclude_key = exclude_name or ""
        candidates = [value for value in existing_names]
    else:
        key = normalized.casefold()
        exclude_key = (exclude_name or "").casefold()
        candidates = [value.casefold() for value in existing_names]

    for candidate in candidates:
        if exclude_name and candidate == exclude_key:
            continue
        if candidate == key:
            dialog_utils.show_warning_dialog(
                parent,
                "名称重复",
                f"已存在同名{entity_label}，请使用其他名称。",
            )
            return None

    return normalized

