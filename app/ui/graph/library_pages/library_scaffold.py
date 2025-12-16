"""库/列表页通用基建：协议与左右分栏骨架。"""

from dataclasses import dataclass
from typing import Any, Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.panels.panel_scaffold import PanelScaffold, SectionCard


@dataclass(frozen=True)
class LibrarySelection:
    """统一描述库页当前选中项。

    - kind   : 资源类别或子页面标识，例如 "template" / "instance" / "graph"
               / "combat:player_template" / "management:timer" 等；
    - id     : 主业务 ID；当语义上仅存在“当前 section”而无具体记录时，可使用空字符串；
    - context: 额外上下文字段（例如 section_key、视图范围 scope 等），供上层按需使用。
    """

    kind: str
    id: str
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class LibraryChangeEvent:
    """库页数据变更事件（用于触发持久化与其它视图联动）。

    约定：
    - kind      : 资源类别，例如 "template" / "instance" / "graph" / "management" / "combat"；
    - id        : 主业务 ID；对管理/战斗等 section+id 场景，推荐在 context 中携带 section_key；
    - operation : "create" / "update" / "delete" / "refresh" / 其它自定义动词；
    - context   : 附加上下文，例如 {"section_key": "timer", "scope": "package"}。
    """

    kind: str
    id: str
    operation: str
    context: dict[str, Any] | None = None


class LibraryPageMixin:
    """库/列表页通用协议的轻量 Mixin。

    仅约定接口签名，不直接绑定具体 UI 结构；
    各库页可选择性继承并实现下列方法，主窗口与控制器仅依赖这些统一入口：

    - set_context(view) : 绑定 PackageView / GlobalResourceView / UnclassifiedResourceView 等资源视图；
    - reload()          : 在当前上下文下全量刷新列表/树，并负责选中恢复；
    - get_selection()   : 返回当前选中的 LibrarySelection；无选中时返回 None；
    - set_selection(sel): 根据 LibrarySelection 恢复选中；不匹配的 kind 应被安全忽略。
    """

    def set_context(self, view: Any) -> None:  # pragma: no cover - 协议默认实现
        raise NotImplementedError

    def reload(self) -> None:  # pragma: no cover - 协议默认实现
        raise NotImplementedError

    def get_selection(self) -> Optional[LibrarySelection]:
        return None

    def set_selection(self, selection: Optional[LibrarySelection]) -> None:
        _ = selection

    def notify_selection_state(
        self,
        has_selection: bool,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        """向主窗口报告当前库页是否存在有效选中项。

        设计用途：
        - 库页在刷新或清空选中时可调用本方法，主窗口统一依据当前视图模式
          收起右侧属性/详情容器并更新可见性，而无需各页面分别调用
          `_update_right_panel_visibility()`。
        - `context` 可在需要时附带额外信息（例如 section_key），供主窗口针对
          特定模式执行更精细的收起逻辑。
        """
        window = self.window()
        handler = getattr(window, "_on_library_selection_state_changed", None) if window else None
        if callable(handler):
            handler(has_selection, context or {})
            return
        if not has_selection:
            updater = getattr(window, "_update_right_panel_visibility", None) if window else None
            if callable(updater):
                updater()


class DualPaneLibraryScaffold(PanelScaffold):
    """提供带左右分区的通用 PanelScaffold 模板。"""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        title: str,
        description: str,
    ) -> None:
        super().__init__(parent, title=title, description=description)
        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self._splitter_added = False

    def build_dual_pane(
        self,
        left_widget: QtWidgets.QWidget,
        right_widget: QtWidgets.QWidget,
        *,
        left_title: str,
        left_description: str,
        right_title: str,
        right_description: str,
        left_stretch: int = 0,
        right_stretch: int = 1,
    ) -> tuple[SectionCard, SectionCard]:
        """在骨架中添加左右 SectionCard，并返回两个卡片以便继续配置。"""
        if not self._splitter_added:
            self.body_layout.addWidget(self._splitter, 1)
            self._splitter_added = True

        left_section = SectionCard(left_title, left_description)
        left_section.add_content_widget(left_widget, stretch=left_stretch)
        self._splitter.addWidget(left_section)

        right_section = SectionCard(right_title, right_description)
        right_section.add_content_widget(right_widget, stretch=right_stretch)
        self._splitter.addWidget(right_section)

        self._splitter.setStretchFactor(0, left_stretch if left_stretch else 0)
        self._splitter.setStretchFactor(1, right_stretch if right_stretch else 1)
        return left_section, right_section

