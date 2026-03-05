from __future__ import annotations

import re
from pathlib import Path

from tests._helpers.project_paths import get_repo_root
from engine.utils.path_utils import normalize_slash


def test_no_ui_direct_in_memory_graph_payload_cache_import() -> None:
    """
    防止缓存与数据源分叉：
    - `app.common.in_memory_graph_payload_cache` 只允许被运行时服务层（GraphDataService）集中桥接，
      UI 层不得直接 import/调用该模块的失效函数，否则会出现“某入口清了缓存，另一个入口仍拿到旧数据”。
    """
    repo_root = get_repo_root()
    ui_root = repo_root / "app" / "ui"
    assert ui_root.exists() and ui_root.is_dir()

    forbidden_module = "app.common.in_memory_graph_payload_cache"
    allowed_app_importers = {
        "app/runtime/services/graph_data_service.py",
    }

    forbidden_import_patterns = [
        re.compile(r"^\s*import\s+app\.common\.in_memory_graph_payload_cache\b", re.MULTILINE),
        re.compile(r"^\s*from\s+app\.common\.in_memory_graph_payload_cache\s+import\b", re.MULTILINE),
        re.compile(r"^\s*from\s+app\.common\s+import\s+.*\bin_memory_graph_payload_cache\b", re.MULTILINE),
    ]

    def _imports_forbidden_module(py_file: Path) -> bool:
        text = py_file.read_text(encoding="utf-8")
        return any(pattern.search(text) for pattern in forbidden_import_patterns)

    ui_offenders: list[str] = []
    for py_file in ui_root.rglob("*.py"):
        if _imports_forbidden_module(py_file):
            ui_offenders.append(normalize_slash(str(py_file.relative_to(repo_root))))

    assert ui_offenders == [], (
        f"UI 层禁止直接 import `{forbidden_module}`（含 `from app.common import in_memory_graph_payload_cache`），"
        f"请改走 GraphDataService：{ui_offenders}"
    )

    # 进一步收敛入口：在 app 内部仅允许 GraphDataService 桥接该模块，避免未来新增“绕过门面”的数据源与失效入口。
    app_root = repo_root / "app"
    app_offenders: list[str] = []
    for py_file in app_root.rglob("*.py"):
        rel = normalize_slash(str(py_file.relative_to(repo_root)))
        if rel in allowed_app_importers:
            continue
        if _imports_forbidden_module(py_file):
            app_offenders.append(rel)

    assert app_offenders == [], (
        f"app 层除 `{sorted(allowed_app_importers)}` 外禁止 import `{forbidden_module}`，"
        f"请统一通过 GraphDataService 桥接：{app_offenders}"
    )


