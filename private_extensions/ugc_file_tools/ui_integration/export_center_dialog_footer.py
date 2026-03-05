from __future__ import annotations

from typing import Any

from .export_center_dialog_types import ExportCenterFooter


def build_export_center_footer(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    dialog: object,
    open_task_history_dialog: object,
    main_window: object,
) -> tuple[Any, ExportCenterFooter]:
    btn_row = QtWidgets.QHBoxLayout()

    history_btn = QtWidgets.QPushButton("最近任务", dialog)
    history_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    history_btn.clicked.connect(lambda: open_task_history_dialog(main_window=main_window))

    btn_row.addWidget(history_btn)
    btn_row.addStretch(1)

    back_btn = QtWidgets.QPushButton("上一步", dialog)
    back_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    back_btn.setEnabled(False)

    next_btn = QtWidgets.QPushButton("下一步", dialog)
    next_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    close_btn = QtWidgets.QPushButton("关闭", dialog)
    close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    close_btn.clicked.connect(dialog.reject)

    btn_row.addWidget(back_btn)
    btn_row.addWidget(next_btn)
    btn_row.addWidget(close_btn)

    footer = ExportCenterFooter(
        history_btn=history_btn,
        back_btn=back_btn,
        next_btn=next_btn,
        close_btn=close_btn,
    )
    return btn_row, footer

