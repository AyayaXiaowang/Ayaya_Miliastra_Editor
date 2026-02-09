from __future__ import annotations

from pathlib import Path

from tests._helpers.project_paths import get_repo_root


def test_repo_has_no_core_directories() -> None:
    """
    命名约束：仓库内不允许再出现名为 core/Core/... 的子目录。

    原因：历史上存在 `core.*` 导入入口，新成员/AI 容易把“目录名 core”
    误解为旧入口，造成长期协作噪音。
    """

    repo_root = get_repo_root()

    skip_dir_names = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        # 发布产物/第三方依赖目录（例如 PyInstaller onedir 内置的 numpy/core）
        "release",
    }

    core_dirs: list[Path] = []
    for directory_path in repo_root.rglob("*"):
        if not directory_path.is_dir():
            continue

        if any(part in skip_dir_names for part in directory_path.parts):
            continue

        if directory_path.name.lower() == "core":
            core_dirs.append(directory_path)

    assert core_dirs == [], "仓库内发现名为 core 的目录：\n" + "\n".join(
        str(path.relative_to(repo_root)) for path in core_dirs
    )


