from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class CenterDialogBase:
    """中心对话框的基础对象集合（dialog + root layout + 可用区域上限）。"""

    dialog: Any
    root_layout: Any
    cap_w: int
    cap_h: int


def raise_existing_center_dialog(*, QtWidgets: Any, main_window: object, dialog_attr: str) -> bool:
    """若已存在对话框实例则唤起并返回 True。"""
    existing_dialog = getattr(main_window, str(dialog_attr), None)
    if isinstance(existing_dialog, QtWidgets.QDialog):
        existing_dialog.show()
        existing_dialog.raise_()
        existing_dialog.activateWindow()
        return True
    return False


def create_center_dialog_base(
    *,
    QtCore: Any,
    QtWidgets: Any,
    Colors: Any,
    Sizes: Any,
    main_window: object,
    dialog_attr: str,
    object_name: str,
    window_title: str,
    min_w: int,
    min_h: int,
    fallback_w: int,
    fallback_h: int,
    scale_w: float,
    scale_h: float,
) -> CenterDialogBase:
    """创建中心对话框并返回基础布局对象。"""
    dialog = QtWidgets.QDialog(main_window)
    dialog.setObjectName(str(object_name))
    dialog.setWindowTitle(str(window_title))
    dialog.setSizeGripEnabled(True)
    fixed_size_hint = getattr(QtCore.Qt.WindowType, "MSWindowsFixedSizeDialogHint", None)
    if fixed_size_hint is not None:
        dialog.setWindowFlag(fixed_size_hint, False)
    dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.setWindowModality(QtCore.Qt.WindowModality.NonModal)
    dialog.setModal(False)

    screen = dialog.screen() or QtWidgets.QApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        cap_w = min(int(avail.width()), int(getattr(main_window, "width", lambda: 0)()))
        cap_h = min(int(avail.height()), int(getattr(main_window, "height", lambda: 0)()))
        if cap_w <= 0:
            cap_w = int(avail.width())
        if cap_h <= 0:
            cap_h = int(avail.height())
        target_w = max(int(min_w), int(cap_w * float(scale_w)))
        target_h = max(int(min_h), int(cap_h * float(scale_h)))
        dialog.resize(min(int(target_w), int(cap_w)), min(int(target_h), int(cap_h)))
    else:
        cap_w = int(getattr(main_window, "width", lambda: 0)())
        cap_h = int(getattr(main_window, "height", lambda: 0)())
        if cap_w > 0 and cap_h > 0:
            dialog.resize(min(int(fallback_w), int(cap_w)), min(int(fallback_h), int(cap_h)))
        else:
            dialog.resize(int(fallback_w), int(fallback_h))

    setattr(main_window, str(dialog_attr), dialog)
    dialog.destroyed.connect(lambda *_: setattr(main_window, str(dialog_attr), None))

    dialog.setStyleSheet(
        f"""
        QDialog {{
            background-color: {Colors.BG_MAIN};
        }}
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
        }}
        """
    )

    root_layout = QtWidgets.QVBoxLayout(dialog)
    root_layout.setContentsMargins(Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE)
    root_layout.setSpacing(Sizes.SPACING_LARGE)

    return CenterDialogBase(dialog=dialog, root_layout=root_layout, cap_w=int(cap_w), cap_h=int(cap_h))


def add_center_title_row(
    *,
    QtWidgets: Any,
    ThemeManager: Any,
    base: CenterDialogBase,
    title_text: str,
    right_widgets: Iterable[Any] | None = None,
) -> Any:
    """向中心对话框根布局添加标题行并返回标题 QLabel。"""
    title_row = QtWidgets.QHBoxLayout()
    title_label = QtWidgets.QLabel(str(title_text), base.dialog)
    title_label.setStyleSheet(ThemeManager.heading(level=3))
    title_row.addWidget(title_label)
    title_row.addStretch(1)
    for w in list(right_widgets or []):
        if w is not None:
            title_row.addWidget(w)
    base.root_layout.addLayout(title_row)
    return title_label


def add_center_tabs(
    *,
    QtWidgets: Any,
    base: CenterDialogBase,
    min_height: int | None = None,
    document_mode: bool = True,
) -> Any:
    """向中心对话框根布局添加 TabWidget 并返回该 tabs 实例。"""
    tabs = QtWidgets.QTabWidget(base.dialog)
    if document_mode:
        tabs.setDocumentMode(True)
    if min_height is not None:
        tabs.setMinimumHeight(int(min_height))
    base.root_layout.addWidget(tabs, 1)
    return tabs

