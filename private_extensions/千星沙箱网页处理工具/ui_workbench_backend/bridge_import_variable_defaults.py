from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.resources.level_variable_schema_view import (
    invalidate_default_level_variable_cache,
)

from app.runtime.services.ui_workbench.variable_defaults import apply_variable_defaults_to_registry

class _UiWorkbenchBridgeImportVariableDefaultsMixin:
    def import_variable_defaults_to_current_project(self, *, source_rel_path: str, variable_defaults: dict) -> dict:
        """
        将前端解析出的 `variable_defaults` 写回当前项目的 `自定义变量注册表.py`：
        - lv.* -> owner="level" 的声明 default_value
        - ps.* -> owner="player" 的声明 default_value

        注意：
        - 仅处理 lv/ps 前缀；其它（如 关卡./玩家自身.）不在此处导入（它们属于 .gil 的实体自定义变量范畴）。
        - 不再生成 UI_*_网页默认值.py；registry 作为单文件真源。
        """
        main_window = getattr(self, "_main_window", None)
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入变量默认值。")
        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入变量默认值。")
        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        report = apply_variable_defaults_to_registry(
            workspace_root=Path(getattr(self, "_workspace_root")).resolve(),
            package_id=current_package_id,
            source_rel_path=str(source_rel_path or ""),
            variable_defaults=variable_defaults,
        )
        invalidate_default_level_variable_cache()
        return report

