from __future__ import annotations

import inspect
from typing import Callable, Dict, Tuple


class _ExecutableCodegenRuntimeExportsMixin:
    def _ensure_graph_scope(self) -> str:
        scope = str(getattr(self, "_current_graph_type", "") or "").strip().lower()
        return scope if scope in {"server", "client"} else "server"

    def _get_runtime_exports_for_scope(self) -> Dict[str, Callable[..., object]]:
        """加载并缓存当前作用域下的运行时节点函数导出表。"""
        scope = self._ensure_graph_scope()
        cached = self._runtime_exports_by_scope.get(scope)
        if cached is not None:
            return cached
        from app.runtime.engine.node_impl_loader import load_node_exports_for_scope

        exports = load_node_exports_for_scope(scope)
        self._runtime_exports_by_scope[scope] = exports
        return exports

    def _call_requires_game(self, func_name: str) -> bool:
        """判断节点函数调用是否需要传入 `self.game`。"""
        scope = self._ensure_graph_scope()
        key: Tuple[str, str] = (scope, str(func_name or ""))
        if key in self._requires_game_cache:
            return self._requires_game_cache[key]

        exports = self._get_runtime_exports_for_scope()
        target = exports.get(func_name)
        if target is None:
            raise ValueError(
                f"无法生成可执行代码：运行时未找到节点函数 '{func_name}'（scope={scope}）。"
                "请确认节点实现可被 V2 清单发现，且 prelude 已正确导出。"
            )

        sig = inspect.signature(target)
        params = list(sig.parameters.values())
        requires = bool(params) and (params[0].name == "game")
        self._requires_game_cache[key] = requires
        return requires


__all__ = ["_ExecutableCodegenRuntimeExportsMixin"]

