"""信号管理对话框 - 管理存档的全局信号"""

from PyQt6 import QtCore

from app.ui.widgets.signal_table_widget import SignalTableWidget
from app.ui.dialogs.management_dialog_base import ManagementDialogBase


class SignalManagerDialog(ManagementDialogBase):
    """信号管理对话框"""

    # 信号：信号配置已更新
    signals_updated = QtCore.pyqtSignal()

    def __init__(self, signals: dict, parent=None):
        super().__init__(
            title_text="📡 信号管理器",
            info_text="",
            width=800,
            height=600,
            parent=parent,
        )
        self.signals_dict = signals  # Dict[str, SignalConfig]

        self.signal_table_widget = SignalTableWidget(self)
        self.signal_table_widget.set_signal_dict(self.signals_dict)
        self.signal_table_widget.signals_modified.connect(self._on_signals_modified)
        self.add_body_widget(self.signal_table_widget)

    def _on_signals_modified(self) -> None:
        """信号数据更新"""
        self.signals_updated.emit()
