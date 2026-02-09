from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tests._helpers.project_paths import get_repo_root


def test_app_ui_is_not_importable_as_top_level_ui_package() -> None:
    # `tests/ui/` 会在 pytest 下形成命名空间包 `ui`（用于测试分组），这是允许的。
    # 但 `<repo>/app/ui` 绝不能被当成顶层 `ui.*` 导入，否则会导致 `ui.*` 与 `app.ui.*` 双导入。
    # 备注：在部分 Python 版本/实现里，`find_spec("ui.todo")` 在 parent 不存在时会抛 `ModuleNotFoundError`，
    # 因此这里用顶层 spec 作为“不可导入”的稳定判定。
    assert importlib.util.find_spec("ui") is None


def test_repo_app_dir_not_on_sys_path() -> None:
    project_root = get_repo_root()
    app_dir = (project_root / "app").resolve()
    normalized_sys_path = {Path(entry).resolve() for entry in sys.path if entry}
    assert app_dir not in normalized_sys_path


def test_no_ui_modules_loaded() -> None:
    forbidden_prefixes = (
        "ui.todo",
        "ui.graph",
        "ui.main_window",
    )
    assert all(not any(module_name.startswith(prefix) for prefix in forbidden_prefixes) for module_name in sys.modules)


