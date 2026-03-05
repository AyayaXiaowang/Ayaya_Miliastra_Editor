from __future__ import annotations

from pathlib import Path

from engine.utils.workspace import looks_like_workspace_root, resolve_workspace_root


def get_repo_root() -> Path:
    """
    返回仓库根目录（repo root）。

    设计目标：
    - 不依赖调用方文件深度，避免测试分目录后 `Path(__file__).parents[...]` 失效；
    - 不依赖当前工作目录；
    - 不使用 try/except 吞错：定位失败应直接抛出断言错误。
    """
    repo_root = resolve_workspace_root(start_paths=[Path(__file__).resolve()])
    assert looks_like_workspace_root(repo_root), f"failed to locate repo root from: {Path(__file__).resolve()}"
    return repo_root



