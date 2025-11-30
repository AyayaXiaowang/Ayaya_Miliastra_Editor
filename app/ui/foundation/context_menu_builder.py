from __future__ import annotations

from typing import Callable, Optional, List
from dataclasses import dataclass
from enum import Enum, auto

from PyQt6 import QtWidgets, QtGui, QtCore
from ui.foundation.theme_manager import ThemeManager


class StandardAction(Enum):
    """标准动作枚举（统一文案）"""
    RENAME = auto()            # 重命名
    DELETE = auto()            # 删除
    LOCATE = auto()            # 定位/定位到资源
    EDIT = auto()              # 编辑/打开编辑器
    OPEN_VARIABLES = auto()    # 打开变量
    OPEN_REFERENCES = auto()   # 查看引用/跳转引用


@dataclass
class MenuActionSpec:
    """菜单项规格"""
    text: str
    callback: Callable[[], None]
    enabled: bool = True
    checkable: bool = False
    checked: bool = False
    shortcut: Optional[str] = None
    icon: Optional[QtGui.QIcon] = None


class ContextMenuBuilder:
    """右键菜单构建器：统一样式与标准动作文案"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, apply_theme: bool = True):
        self.parent = parent
        self.apply_theme = apply_theme
        self._items: List[MenuActionSpec | str] = []  # str == "separator"

    # ========== 添加项 ==========
    def add_action(
        self,
        text: str,
        callback: Callable[[], None],
        *,
        enabled: bool = True,
        checkable: bool = False,
        checked: bool = False,
        shortcut: Optional[str] = None,
        icon: Optional[QtGui.QIcon] = None,
    ) -> "ContextMenuBuilder":
        self._items.append(MenuActionSpec(text, callback, enabled, checkable, checked, shortcut, icon))
        return self

    def add_separator(self) -> "ContextMenuBuilder":
        self._items.append("separator")
        return self

    def add_standard_action(self, action: StandardAction, callback: Callable[[], None], *, enabled: bool = True) -> "ContextMenuBuilder":
        text = self._standard_text_for(action)
        return self.add_action(text, callback, enabled=enabled)

    # ========== 构建与显示 ==========
    def build(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self.parent) if self.parent is not None else QtWidgets.QMenu()
        if self.apply_theme:
            menu.setStyleSheet(ThemeManager.context_menu_style())
        for spec in self._items:
            if spec == "separator":
                menu.addSeparator()
                continue
            assert isinstance(spec, MenuActionSpec)
            if spec.icon is not None:
                action = menu.addAction(spec.icon, spec.text)
            else:
                action = menu.addAction(spec.text)
            action.setEnabled(spec.enabled)
            if spec.checkable:
                action.setCheckable(True)
                action.setChecked(spec.checked)
            if spec.shortcut:
                action.setShortcut(QtGui.QKeySequence(spec.shortcut))
            # 将回调绑定到触发
            action.triggered.connect(lambda _checked=False, cb=spec.callback: cb())  # type: ignore[arg-type]
        return menu

    def exec_global(self, global_pos: QtCore.QPoint) -> Optional[QtGui.QAction]:
        menu = self.build()
        return menu.exec(global_pos)

    def exec_for(self, widget: QtWidgets.QWidget, pos: QtCore.QPoint) -> Optional[QtGui.QAction]:
        # 适配局部坐标：与widget组合
        menu = self.build()
        return menu.exec(widget.mapToGlobal(pos))

    # ========== 文案 ==========
    def _standard_text_for(self, action: StandardAction) -> str:
        if action == StandardAction.RENAME:
            return "重命名"
        if action == StandardAction.DELETE:
            return "删除"
        if action == StandardAction.LOCATE:
            return "定位"
        if action == StandardAction.EDIT:
            return "编辑"
        if action == StandardAction.OPEN_VARIABLES:
            return "打开变量"
        if action == StandardAction.OPEN_REFERENCES:
            return "查看引用"
        return "操作"


