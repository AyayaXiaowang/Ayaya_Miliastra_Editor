from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore

from engine.resources.resource_manager import ResourceManager


class ResourceFingerprintThread(QtCore.QThread):
    """后台线程：计算资源库指纹，避免主线程扫描文件系统导致 UI 卡顿。

    说明：
    - 使用 QThread 子类，避免 `QObject.moveToThread` 的 worker 在退出阶段被 Python GC
      于错误线程析构，引发 Windows `access violation`。
    """

    fingerprint_computed = QtCore.pyqtSignal(str)

    def __init__(
        self,
        resource_manager: ResourceManager,
        *,
        trigger_directory: Path | None,
        baseline_fingerprint: str,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._resource_manager = resource_manager
        self._trigger_directory = trigger_directory
        self._baseline_fingerprint = str(baseline_fingerprint or "")
        self.setObjectName("ResourceFingerprintThread")

    def run(self) -> None:
        if self.isInterruptionRequested():
            self.fingerprint_computed.emit(str(self._baseline_fingerprint or ""))
            return

        def should_abort() -> bool:
            return bool(self.isInterruptionRequested())

        fingerprint_value = self._resource_manager.compute_resource_library_fingerprint_for_auto_refresh(
            trigger_directory=self._trigger_directory,
            baseline_fingerprint=str(self._baseline_fingerprint or ""),
            should_abort=should_abort,
        )
        self.fingerprint_computed.emit(str(fingerprint_value or ""))


