from __future__ import annotations

from pathlib import Path

from .export_center.state import (
    _load_last_resource_picker_expanded_node_ids,
    _save_last_resource_picker_expanded_node_ids,
)
from .export_center_dialog_types import ExportCenterLeftPane


def build_export_center_left_pane(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    ThemeManager: object,
    dialog: object,
    workspace_root: Path,
    project_root: Path,
    shared_root: Path,
) -> ExportCenterLeftPane:
    from .resource_picker import build_resource_selection_items, make_resource_picker_widget_cls

    catalog = build_resource_selection_items(project_root=project_root, shared_root=shared_root, include_shared=True)

    left_pane = QtWidgets.QWidget()
    left_layout = QtWidgets.QVBoxLayout(left_pane)
    left_layout.setContentsMargins(0, 0, Sizes.PADDING_SMALL, 0)
    left_layout.setSpacing(Sizes.SPACING_MEDIUM)

    left_header = QtWidgets.QLabel("1. 选择资源", left_pane)
    left_header.setStyleSheet(ThemeManager.heading(level=4))
    left_layout.addWidget(left_header)

    PickerWidgetCls = make_resource_picker_widget_cls(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
    )
    picker = PickerWidgetCls(
        left_pane,
        catalog=dict(catalog),
        allowed_categories={"graphs", "templates", "player_templates", "mgmt_cfg"},
        preselected_keys=None,
        # 导出中心：避免“已选列表”遮挡树；改为左侧面板底部固定区
        show_selected_panel=False,
        show_remove_button=False,
        show_relative_path_column=False,
    )
    # UX：导出中心不希望出现横向滚动条；文本过长时用省略号即可。
    picker.tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    picker.tree.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
    header = picker.tree.header()
    # 注意：导出中心隐藏“相对路径”列后，资源树通常只有两列：["资源", "来源"]。
    # 若对 last section 启用 stretch，会把“来源”这一列拉得很宽（但它通常只需要显示“项目/共享”两字）。
    header.setStretchLastSection(False)
    if int(picker.tree.columnCount()) >= 1:
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
    if int(picker.tree.columnCount()) >= 2:
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.resizeSection(1, 70)

    expanded_ids = set(_load_last_resource_picker_expanded_node_ids(workspace_root=Path(workspace_root)))

    def _persist_picker_expanded_state() -> None:
        _save_last_resource_picker_expanded_node_ids(
            workspace_root=Path(workspace_root),
            node_ids=sorted(picker.get_expanded_node_ids(), key=lambda t: t.casefold()),
        )

    picker.tree.itemExpanded.connect(lambda _it: _persist_picker_expanded_state())
    picker.tree.itemCollapsed.connect(lambda _it: _persist_picker_expanded_state())
    dialog.finished.connect(lambda _code: _persist_picker_expanded_state())

    QtCore.QTimer.singleShot(0, lambda: picker.set_expanded_node_ids(expanded_ids))

    selected_box = QtWidgets.QGroupBox("已选资源", left_pane)
    selected_box.setStyleSheet(ThemeManager.group_box_style())
    selected_box_layout = QtWidgets.QVBoxLayout(selected_box)
    selected_box_layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    selected_box_layout.setSpacing(Sizes.SPACING_SMALL)

    selected_summary_label = QtWidgets.QLabel("未选择任何资源。", selected_box)
    selected_summary_label.setWordWrap(True)
    selected_summary_label.setStyleSheet(ThemeManager.subtle_info_style())
    selected_box_layout.addWidget(selected_summary_label)

    selected_list = QtWidgets.QListWidget(selected_box)
    selected_list.setToolTip("显示当前已选资源（可多选后移除）")
    selected_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    selected_list.setTextElideMode(QtCore.Qt.TextElideMode.ElideMiddle)
    # 允许用户根据屏幕高度/已选数量自由调整：不使用固定最大高度。
    # UX：已选列表是“核对清单”，默认应能看到更多行；仍可通过分割条拖拽进一步调整。
    selected_list.setMinimumHeight(220)
    selected_box_layout.addWidget(selected_list, 1)

    selected_btn_row = QtWidgets.QHBoxLayout()
    selected_btn_row.addStretch(1)
    selected_remove_btn = QtWidgets.QPushButton("移除所选", selected_box)
    selected_remove_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    selected_clear_btn = QtWidgets.QPushButton("清空已选", selected_box)
    selected_clear_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    selected_btn_row.addWidget(selected_remove_btn)
    selected_btn_row.addWidget(selected_clear_btn)
    selected_box_layout.addLayout(selected_btn_row)

    # 导出中心左侧：资源树（勾选区）+ 已选清单（核对区）更适合左右并排：
    # - 两边都能拉满高度，减少“列表太短”的感知；
    # - 勾选时可同时核对已选集合，符合常见“选择器 + 购物车”心智模型。
    left_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, left_pane)
    left_splitter.setHandleWidth(6)
    left_splitter.setStyleSheet(ThemeManager.splitter_style())
    left_splitter.setChildrenCollapsible(False)
    left_splitter.addWidget(picker)
    left_splitter.addWidget(selected_box)
    # 宽度分配：资源树需要展示层级与名称，默认更宽；已选清单仍保留足够空间展示路径。
    left_splitter.setStretchFactor(0, 6)
    left_splitter.setStretchFactor(1, 4)
    left_splitter.setSizes([380, 260])
    left_splitter.handle(1).setToolTip("提示：可拖拽调整“资源树 / 已选资源列表”的宽度")
    left_layout.addWidget(left_splitter, 1)

    return ExportCenterLeftPane(
        pane=left_pane,
        picker=picker,
        selected_summary_label=selected_summary_label,
        selected_list=selected_list,
        selected_remove_btn=selected_remove_btn,
        selected_clear_btn=selected_clear_btn,
        persist_expanded_state=_persist_picker_expanded_state,
    )

