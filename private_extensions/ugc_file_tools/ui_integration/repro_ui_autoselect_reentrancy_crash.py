from __future__ import annotations

"""
最小复现：在 `selection_changed` 回调栈内同步修改 selection（add_keys/remove_keys）可能触发 Qt re-entrancy 崩溃。

运行方式（仓库根目录）：
python -X utf8 private_extensions/ugc_file_tools/ui_integration/repro_ui_autoselect_reentrancy_crash.py
"""

import sys
from pathlib import Path


_PARENTS_TO_REPO_ROOT = 3


def main() -> int:
    from PyQt6 import QtCore, QtWidgets
    
    # 允许直接从仓库根运行本脚本（无需走 -m）；显式注入 repo_root 到 sys.path。
    repo_root = Path(__file__).resolve().parents[_PARENTS_TO_REPO_ROOT]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # 本脚本不需要真实文件 IO；用一个最小的 catalog 即可。
    from app.ui.foundation.theme_manager import Colors, Sizes
    from private_extensions.ugc_file_tools.ui_integration.resource_picker import ResourceSelectionItem, make_resource_picker_widget_cls

    dummy_path = Path(__file__).resolve()
    ui_item = ResourceSelectionItem(source_root="project", category="ui_src", relative_path="管理配置/UI源码/dummy.html", absolute_path=dummy_path)
    var_item = ResourceSelectionItem(
        source_root="project",
        category="custom_vars",
        relative_path="关卡实体/某变量 (vid)",
        absolute_path=dummy_path,
        meta={"owner_ref": "level", "variable_id": "vid", "variable_name": "某变量", "variable_type": "int"},
    )
    catalog = {
        "ui_src": [ui_item],
        "custom_vars": [var_item],
        "graphs": [],
        "templates": [],
        "instances": [],
        "player_templates": [],
        "mgmt_cfg": [],
        "resource_repo": [],
    }

    app = QtWidgets.QApplication([])
    WidgetCls = make_resource_picker_widget_cls(QtCore=QtCore, QtWidgets=QtWidgets, Colors=Colors, Sizes=Sizes)
    picker = WidgetCls(
        None,
        catalog=catalog,
        allowed_categories={"ui_src", "custom_vars"},
        preselected_keys=None,
        show_remove_button=False,
        show_selected_panel=False,
        show_relative_path_column=False,
    )

    # 关键：在 selection_changed 回调栈内去 add_keys 会导致 re-entrancy。
    # 我们用 singleShot(0) 模拟修复后的行为，确保脚本能稳定退出。
    def on_selection_changed() -> None:
        keys = picker.get_selected_keys()
        if ui_item.key in keys and var_item.key not in keys:
            QtCore.QTimer.singleShot(0, lambda: picker.add_keys([var_item.key]))

    picker.selection_changed.connect(on_selection_changed)

    # 触发一次 selection_changed：模拟“用户勾选 UI”
    picker.add_keys([ui_item.key])

    # 跑一个短暂事件循环，让 singleShot 执行完毕
    QtCore.QTimer.singleShot(50, app.quit)
    app.exec()

    keys2 = picker.get_selected_keys()
    assert ui_item.key in keys2
    assert var_item.key in keys2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

