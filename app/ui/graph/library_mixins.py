from typing import Any, Callable, Optional

from PyQt6 import QtCore, QtWidgets

from app.common.selection_restore_policy import compute_selection_restore_decision
from app.ui.foundation.toolbar_utils import apply_standard_toolbar
from app.ui.foundation import dialog_utils


class SearchFilterMixin:
    """提供标准化的搜索输入框绑定与文本归一化。"""

    def connect_search(
        self,
        search_line_edit: QtWidgets.QLineEdit,
        on_text_changed: Callable[[str], None],
        placeholder: str = "搜索...",
    ) -> None:
        search_line_edit.setPlaceholderText(placeholder)
        search_line_edit.textChanged.connect(on_text_changed)

    def normalize_query(self, text: str) -> str:
        return text.strip().lower()

    # === 通用过滤助手 ===
    def filter_list_items(
        self,
        list_widget: QtWidgets.QListWidget,
        query: str,
        text_getter: Optional[Callable[[QtWidgets.QListWidgetItem], str]] = None,
    ) -> None:
        """按文本匹配隐藏/显示列表项。"""
        q = self.normalize_query(query)
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            value = text_getter(item) if text_getter else item.text()
            item.setHidden(q not in value.lower())

    def ensure_current_item_visible_or_select_first(
        self,
        list_widget: QtWidgets.QListWidget,
        *,
        on_selected: Optional[Callable[[QtWidgets.QListWidgetItem], None]] = None,
    ) -> None:
        """若当前选中项被隐藏，则选中第一条可见记录。

        适用场景：
        - 搜索过滤后，当前选中项可能被隐藏；此时需要切换到第一条可见记录，
          保持“有可见内容就有焦点”的体验，并避免右侧详情仍显示已被过滤掉的上下文。
        """
        current_item = list_widget.currentItem()
        if current_item is not None and not current_item.isHidden():
            return
        for row_index in range(list_widget.count()):
            item = list_widget.item(row_index)
            if item is not None and not item.isHidden():
                list_widget.setCurrentItem(item)
                if on_selected is not None:
                    on_selected(item)
                return

    def filter_table_rows_by_columns(
        self,
        table_widget: QtWidgets.QTableWidget,
        query: str,
        columns: list[int],
    ) -> None:
        """按指定列文本匹配隐藏/显示表格行。"""
        q = self.normalize_query(query)
        for row in range(table_widget.rowCount()):
            matched = False
            for col in columns:
                item = table_widget.item(row, col)
                if item and q in item.text().lower():
                    matched = True
                    break
            table_widget.setRowHidden(row, not matched)

    def filter_card_map(
        self,
        card_map: dict[str, QtWidgets.QWidget],
        query: str,
        match_fn: Callable[[QtWidgets.QWidget, str], bool],
    ) -> None:
        """按自定义匹配逻辑过滤卡片（值为 QWidget 的映射）。"""
        q = self.normalize_query(query)
        for _, card in card_map.items():
            card.setVisible(match_fn(card, q))


class SelectionAndScrollMixin:
    """统一选中与滚动到可见区域的辅助方法。"""

    def scroll_to_widget(
        self,
        scroll_area: QtWidgets.QScrollArea,
        target_widget: QtWidgets.QWidget,
        center: bool = True,
    ) -> None:
        container_widget = scroll_area.widget()
        if container_widget is None:
            raise ValueError("scroll_area 未设置内部容器 widget")

        target_center_pos = target_widget.mapTo(container_widget, target_widget.rect().center())
        viewport_height = scroll_area.viewport().height()
        vertical_bar = scroll_area.verticalScrollBar()

        if center:
            target_value = max(0, int(target_center_pos.y() - viewport_height / 2))
        else:
            target_value = max(0, int(target_center_pos.y()))

        vertical_bar.setValue(target_value)

    def select_and_center_list_item(
        self,
        list_widget: QtWidgets.QListWidget,
        target_item: QtWidgets.QListWidgetItem,
    ) -> None:
        list_widget.setCurrentItem(target_item)
        list_widget.scrollToItem(target_item, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)

    def select_and_center_tree_item(
        self,
        tree_widget: QtWidgets.QTreeWidget,
        target_item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        tree_widget.setCurrentItem(target_item)
        tree_widget.scrollToItem(target_item, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)

    def select_and_center_table_row(
        self,
        table_widget: QtWidgets.QTableWidget,
        row_index: int,
    ) -> None:
        if row_index < 0 or row_index >= table_widget.rowCount():
            raise ValueError("row_index 超出表格范围")
        table_widget.selectRow(row_index)
        model_index = table_widget.model().index(row_index, 0)
        table_widget.scrollTo(model_index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)


class ToolbarMixin:
    """与 apply_standard_toolbar 配套的工具栏构建辅助。"""

    def init_toolbar(self, toolbar_layout: QtWidgets.QHBoxLayout) -> None:
        apply_standard_toolbar(toolbar_layout)

    def setup_toolbar_with_search(
        self,
        toolbar_layout: QtWidgets.QHBoxLayout,
        buttons: list[QtWidgets.QAbstractButton],
        search_line_edit: Optional[QtWidgets.QLineEdit] = None,
    ) -> None:
        for button in buttons:
            toolbar_layout.addWidget(button)
        toolbar_layout.addStretch()
        if search_line_edit is not None:
            toolbar_layout.addWidget(search_line_edit)


class ConfirmDialogMixin:
    """统一的确认/提示对话框。"""

    def confirm(self, title: str, message: str) -> bool:
        return dialog_utils.ask_yes_no_dialog(self, title, message)

    def show_warning(self, title: str, message: str) -> None:
        dialog_utils.show_warning_dialog(self, title, message)

    def show_info(self, title: str, message: str) -> None:
        dialog_utils.show_info_dialog(self, title, message)

    def show_error(self, title: str, message: str) -> None:
        dialog_utils.show_error_dialog(self, title, message)


def rebuild_list_with_preserved_selection(
    list_widget: QtWidgets.QListWidget,
    *,
    previous_key: Optional[Any],
    had_selection_before_refresh: bool,
    build_items: Callable[[], None],
    key_getter: Callable[[QtWidgets.QListWidgetItem], Optional[Any]],
    on_restored_selection: Optional[Callable[[Any], None]] = None,
    on_first_selection: Optional[Callable[[Any], None]] = None,
    on_cleared_selection: Optional[Callable[[], None]] = None,
) -> None:
    """统一的“列表刷新 + 选中策略”助手。

    适用场景：
    - 元件库 / 实体摆放 / 管理配置库等“左树 + 右列表”页面；
    - 需要在重建列表时尽量恢复原选中项，
      无法恢复时在列表非空状态下选中第一条记录；
    - 当列表从“有选中项”变为空时，向上层发出一次“空选中”通知，
      由主窗口或右侧面板负责收起属性页。

    参数说明：
    - previous_key: 刷新前选中项对应的业务 key（如 template_id / instance_id / (section_key, item_id)）。
    - had_selection_before_refresh: 刷新前是否存在选中项（即便无法解析出有效 key）。
    - build_items: 负责向 list_widget 重新插入条目；函数内部不应调用 clear()。
    - key_getter: 从列表项中提取业务 key，用于匹配 previous_key 与首条记录。
    - on_restored_selection: 成功恢复原选中项时的回调（可为空）。
    - on_first_selection: 无法恢复但列表非空、默认选中第一条记录时的回调（可为空）。
    - on_cleared_selection: 列表从“有选中项”变为空时的回调（可为空）。
    """
    previous_updates_enabled = bool(list_widget.updatesEnabled())
    list_widget.setUpdatesEnabled(False)

    # 列表重建期间禁止发射信号，避免：
    # - clear() 触发一次“空选中”回调；
    # - build_items() 逐项 addItem 导致的 UI 反复刷新与级联更新（右侧面板/状态徽章等）。
    signal_blocker = QtCore.QSignalBlocker(list_widget)
    try:
        list_widget.clear()
        build_items()
    finally:
        # 必恢复语义：即使 build_items() 抛错，也不能把列表永久留在“禁用更新/阻塞信号”的状态，
        # 否则 UI 表现为假死（无法重绘/无法触发选中联动）。
        del signal_blocker
        list_widget.setUpdatesEnabled(previous_updates_enabled)

    item_count = list_widget.count()
    keys_by_row: list[Any | None] = []
    for row_index in range(item_count):
        list_item = list_widget.item(row_index)
        keys_by_row.append(key_getter(list_item))

    decision = compute_selection_restore_decision(
        keys_by_row=keys_by_row,
        previous_key=previous_key,
        had_selection_before_refresh=had_selection_before_refresh,
    )

    if decision.action == "restored":
        row_index = int(decision.row_index) if decision.row_index is not None else -1
        if row_index < 0 or row_index >= item_count:
            return
        list_item = list_widget.item(row_index)
        if list_item is None:
            return
        list_widget.setCurrentItem(list_item)
        if on_restored_selection is not None:
            on_restored_selection(decision.key)
        return

    if decision.action == "cleared":
        if on_cleared_selection is not None:
            on_cleared_selection()
        return

    if decision.action == "none":
        return

    # previous_key 为空或无法恢复，但当前列表非空：默认选中第一条。
    list_widget.setCurrentRow(0)
    if on_first_selection is not None:
        first_key = decision.key
        if first_key is not None:
            on_first_selection(first_key)

