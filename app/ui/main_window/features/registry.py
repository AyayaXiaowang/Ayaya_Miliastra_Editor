from __future__ import annotations

from typing import Any, List

from app.ui.main_window.features.feature_protocol import MainWindowFeature
from app.ui.main_window.features.central_pages_assembly_feature import CentralPagesAssemblyFeature
from app.ui.main_window.features.right_panel_assembly_feature import RightPanelAssemblyFeature


def install_default_main_window_features(*, main_window: Any) -> List[MainWindowFeature]:
    """安装默认主窗口 Feature 集合（渐进迁移的统一入口）。"""
    features: List[MainWindowFeature] = [
        CentralPagesAssemblyFeature(),
        RightPanelAssemblyFeature(),
    ]
    for feature in features:
        feature.install(main_window=main_window)
    return features


