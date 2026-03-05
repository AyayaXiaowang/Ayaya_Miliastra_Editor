from __future__ import annotations

from pathlib import Path
from typing import List

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module


_checked_workspaces: set[str] = set()


class SharedSignalsForbiddenRule(ValidationRule):
    """禁止在共享根目录中提供信号定义（*.py）。

    约定：
    - 信号定义必须放在各自项目存档的 `管理配置/信号/`；
    - 共享根 `assets/资源库/共享/` 不再承载任何信号定义，避免作用域与 ID 解析不稳定导致导出结果漂移。
    """

    rule_id = "engine_code_shared_signals_forbidden"
    category = "信号系统"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.workspace_path is None or ctx.file_path is None:
            return []

        ws_key = str(Path(ctx.workspace_path).resolve())
        if ws_key in _checked_workspaces:
            return []
        _checked_workspaces.add(ws_key)

        shared_signals_dir = (
            Path(ctx.workspace_path)
            / "assets"
            / "资源库"
            / "共享"
            / "管理配置"
            / "信号"
        )
        if not shared_signals_dir.is_dir():
            return []

        py_files = sorted(
            [p for p in shared_signals_dir.glob("*.py") if p.is_file()],
            key=lambda p: p.as_posix().casefold(),
        )
        if not py_files:
            return []

        tree = get_cached_module(ctx)
        rels = [str(p.relative_to(Path(ctx.workspace_path))).replace("\\", "/") for p in py_files]
        msg = (
            "共享根目录中检测到信号定义文件（已禁止）。\n"
            "请将信号定义迁移到各自项目存档的 `管理配置/信号/`，并删除共享目录下的信号文件：\n"
            + "\n".join([f"- {r}" for r in rels])
        )
        return [
            create_rule_issue(
                self,
                Path(ctx.file_path),
                tree,
                "CODE_SHARED_SIGNALS_FORBIDDEN",
                msg,
            )
        ]


__all__ = ["SharedSignalsForbiddenRule"]

