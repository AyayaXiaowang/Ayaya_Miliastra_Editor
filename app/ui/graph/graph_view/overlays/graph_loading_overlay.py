from __future__ import annotations

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager


class GraphLoadingOverlay(QtWidgets.QWidget):
    """GraphView 的加载遮罩（不依赖 scene/model）。

    设计目标：
    - 覆盖整个 GraphView（作为 view 的直接子控件，而非 viewport 子控件），避免跟随画布像素滚动。
    - 中央展示一个信息卡片：标题、状态文本、进度条与可选取消按钮。
    - 由外部（控制器/任务）更新文案与进度；不在内部启动任何后台任务。
    """

    def __init__(self, view: QtWidgets.QWidget):
        super().__init__(view)
        self._view = view
        self._cancel_handler: callable | None = None

        self.setObjectName("graphLoadingOverlay")
        self.setVisible(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 半透明遮罩背景
        self._backdrop = QtWidgets.QFrame(self)
        self._backdrop.setObjectName("graphLoadingBackdrop")
        backdrop_layout = QtWidgets.QVBoxLayout(self._backdrop)
        backdrop_layout.setContentsMargins(0, 0, 0, 0)
        backdrop_layout.setSpacing(0)
        layout.addWidget(self._backdrop, 1)

        # 中央卡片
        self._card = QtWidgets.QFrame(self._backdrop)
        self._card.setObjectName("graphLoadingCard")
        self._card.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._card.setMinimumWidth(420)
        self._card.setMaximumWidth(640)
        self._card.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        card_layout = QtWidgets.QVBoxLayout(self._card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        self._title_label = QtWidgets.QLabel("正在处理…", self._card)
        title_font = self._title_label.font()
        title_font.setPointSize(max(Sizes.FONT_NORMAL, title_font.pointSize()))
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._title_label.setTextFormat(Qt.TextFormat.PlainText)
        self._title_label.setWordWrap(True)
        card_layout.addWidget(self._title_label)

        self._detail_label = QtWidgets.QLabel("", self._card)
        detail_font = self._detail_label.font()
        detail_font.setPointSize(max(Sizes.FONT_SMALL, detail_font.pointSize()))
        self._detail_label.setFont(detail_font)
        self._detail_label.setTextFormat(Qt.TextFormat.PlainText)
        self._detail_label.setWordWrap(True)
        self._detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self._detail_label)

        self._progress_bar = QtWidgets.QProgressBar(self._card)
        self._progress_bar.setObjectName("graphLoadingProgress")
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setRange(0, 0)  # 默认不确定进度：忙碌条
        self._progress_bar.setValue(0)
        self._progress_bar.setMinimumHeight(max(18, int(Sizes.INPUT_HEIGHT * 0.55)))
        card_layout.addWidget(self._progress_bar)

        self._button_row = QtWidgets.QWidget(self._card)
        button_layout = QtWidgets.QHBoxLayout(self._button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        button_layout.addStretch(1)

        self._cancel_button = QtWidgets.QPushButton("取消", self._button_row)
        self._cancel_button.setVisible(False)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        button_layout.addWidget(self._cancel_button)
        card_layout.addWidget(self._button_row)

        backdrop_layout.addStretch(1)
        backdrop_layout.addWidget(self._card, 0, Qt.AlignmentFlag.AlignHCenter)
        backdrop_layout.addStretch(1)

        self._apply_styles()
        self.reposition()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            ThemeManager.button_style()
            + ThemeManager.input_style()
            + ThemeManager.scrollbar_style()
            + "\n".join(
                [
                    "QWidget#graphLoadingOverlay { background: transparent; }",
                    # 半透明遮罩：保持不完全遮挡背景，便于用户感知“仍在当前画布上处理”
                    f"QFrame#graphLoadingBackdrop {{ background-color: rgba(0, 0, 0, 110); }}",
                    f"QFrame#graphLoadingCard {{ background-color: {Colors.BG_CARD}; border: 1px solid {Colors.BORDER}; border-radius: 10px; }}",
                    f"QLabel {{ color: {Colors.TEXT_PRIMARY}; }}",
                    f"QProgressBar#graphLoadingProgress {{ border: 1px solid {Colors.BORDER}; border-radius: 6px; background-color: {Colors.BG_MAIN}; color: {Colors.TEXT_PRIMARY}; }}",
                    "QProgressBar#graphLoadingProgress::chunk { border-radius: 6px; }",
                ]
            )
        )

    # --- public api ---

    def show_loading(
        self,
        *,
        title: str,
        detail: str = "",
        progress_value: int | None = None,
        progress_max: int | None = None,
        cancelable: bool = False,
        on_cancel: callable | None = None,
    ) -> None:
        self._title_label.setText(str(title or "正在处理…"))
        self._detail_label.setText(str(detail or ""))
        self.set_progress(progress_value=progress_value, progress_max=progress_max)
        self.set_cancelable(cancelable=cancelable, on_cancel=on_cancel)

        self.reposition()
        self.show()
        self.raise_()

    def set_progress(self, *, progress_value: int | None, progress_max: int | None) -> None:
        if progress_max is None or progress_max <= 0:
            # 忙碌条
            self._progress_bar.setRange(0, 0)
            self._progress_bar.setValue(0)
            self._progress_bar.setFormat("处理中…")
            return

        value = int(progress_value or 0)
        max_value = int(progress_max)
        if value < 0:
            value = 0
        if value > max_value:
            value = max_value
        self._progress_bar.setRange(0, max_value)
        self._progress_bar.setValue(value)
        self._progress_bar.setFormat(f"{value}/{max_value}")

    def set_cancelable(self, *, cancelable: bool, on_cancel: callable | None) -> None:
        self._cancel_button.setVisible(bool(cancelable))
        self._cancel_handler = on_cancel if bool(cancelable) else None

    def _on_cancel_clicked(self) -> None:
        handler = getattr(self, "_cancel_handler", None)
        if handler is None:
            return
        handler()

    def hide_loading(self) -> None:
        self.hide()

    def set_detail_text(self, detail: str) -> None:
        self._detail_label.setText(str(detail or ""))

    def reposition(self) -> None:
        view = self._view
        if view is None:
            return
        self.setGeometry(view.rect())
        self._card.adjustSize()

    def showEvent(self, event) -> None:  # noqa: N802, ANN001
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self.reposition)

