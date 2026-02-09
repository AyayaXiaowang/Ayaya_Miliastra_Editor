from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.theme_manager import ThemeManager


_app = QtWidgets.QApplication.instance()
if _app is None:
    _app = QtWidgets.QApplication([])


def _build_graph_search_like_item_widget(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """构造一个与 GraphSearchOverlay 结果项相同的三行富文本 widget。

    关键点：
    - 使用 rich text QLabel（Qt 会走 QTextDocument 渲染路径）。
    - 使用与 GraphSearchOverlay 相同的 layout margins/spacing，便于复现“文本裁切”的真实场景。
    """
    widget = QtWidgets.QWidget(parent)
    widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    layout = QtWidgets.QVBoxLayout(widget)
    layout.setContentsMargins(10, 6, 10, 6)
    layout.setSpacing(2)

    label1 = QtWidgets.QLabel(widget)
    label1.setTextFormat(QtCore.Qt.TextFormat.RichText)
    label1.setText("<b>1. 发送<span style='background:#FFD54F;color:#000'>信号</span> [执行节点]</b>")

    label2 = QtWidgets.QLabel(widget)
    label2.setTextFormat(QtCore.Qt.TextFormat.RichText)
    label2.setText("命中：<b>标题</b>：发送<span style='background:#FFD54F;color:#000'>信号</span>")

    label3 = QtWidgets.QLabel(widget)
    label3.setTextFormat(QtCore.Qt.TextFormat.RichText)
    label3.setText("命中：标题 / ID  |  GIA序号：3  |  id：476a144d")

    layout.addWidget(label1)
    layout.addWidget(label2)
    layout.addWidget(label3)
    return widget


def test_graph_search_results_item_widget_geometry_not_shrunk_by_item_padding() -> None:
    """回归：GraphSearchOverlay 的结果项采用 setItemWidget，自绘三行文本。

    Qt 的实现细节：
    - QListWidget.setItemWidget 实际走 setIndexWidget；
    - QStyledItemDelegate.updateEditorGeometry 会把 editor 放到 SE_ItemViewItemText 的 rect 中；
    - 若 QSS 对 QListWidget::item 设置了 padding，会缩小 editor 的可用高度，导致三行文本被裁切。

    因此本用例断言：editor 的高度不应被 item 的 padding 明显“吃掉”。
    """
    list_widget = QtWidgets.QListWidget()
    list_widget.setObjectName("graphSearchResults")
    list_widget.setStyleSheet(ThemeManager.graph_search_overlay_style())
    list_widget.setSpacing(0)
    list_widget.resize(620, 240)
    list_widget.show()

    item = QtWidgets.QListWidgetItem()
    # 使用一个“典型的”结果项高度：当前 GraphSearchOverlay 会基于 font metrics 估算，
    # 但不同平台/字体会略有差异；这里取一个稳健的值用于几何回归。
    item.setSizeHint(QtCore.QSize(0, 74))
    list_widget.addItem(item)

    editor = _build_graph_search_like_item_widget(list_widget)
    list_widget.setItemWidget(item, editor)

    # 触发布局与 delegate 的 editor geometry 计算
    QtWidgets.QApplication.processEvents()
    QtWidgets.QApplication.processEvents()

    item_rect = list_widget.visualItemRect(item)
    editor_rect = editor.geometry()

    diff_h = int(item_rect.height() - editor_rect.height())
    assert (
        diff_h <= 4
    ), f"editor geometry was unexpectedly shrunk: itemH={item_rect.height()} editorH={editor_rect.height()} diff={diff_h}px"

