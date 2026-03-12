from __future__ import annotations

from pathlib import Path
from typing import Any

from .index_v1 import (
    GraphScanFailure,
    build_usage_index_v1_from_graph_payloads,
    compute_current_node_defs_fp,
    ensure_graph_cache_data,
    infer_graph_id_from_graph_code_text,
)


PROGRESS_COMPLETE_EXTRA_STEP: int = 1


def _safe_exception_text(exc: BaseException) -> str:
    """将异常格式化为可复制的文本。"""
    import traceback

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return tb.strip() if tb.strip() else f"{type(exc).__name__}: {exc}"


class UsageIndexBuildWorker:
    """在后台线程构建 usage index v1 并上报进度与结果。"""

    def __init__(
        self,
        *,
        QtCore: Any,
        workspace_root: Path,
        graph_code_files: list[Path],
        cache_path: Path | None = None,
        cache_meta: dict[str, object] | None = None,
    ) -> None:
        """初始化索引构建 worker。"""
        self._workspace_root = Path(workspace_root).resolve()
        self._graph_code_files = [Path(p).resolve() for p in (graph_code_files or [])]
        self._cache_path = Path(cache_path).resolve() if cache_path is not None else None
        self._cache_meta = dict(cache_meta) if isinstance(cache_meta, dict) else None

        class _Worker(QtCore.QThread):
            progress_changed = QtCore.pyqtSignal(int, int, str)
            succeeded = QtCore.pyqtSignal(object, object)
            failed = QtCore.pyqtSignal(str, object)

            def __init__(self, outer: "UsageIndexBuildWorker") -> None:
                """保存外部上下文以便在 run 中调用。"""
                super().__init__()
                self._outer = outer

            def run(self) -> None:
                """执行索引构建并捕获异常用于 UI 展示。"""
                try:
                    payload, failures = self._outer._build(self)
                    self.succeeded.emit(payload, failures)
                except BaseException as exc:
                    self.failed.emit(_safe_exception_text(exc), [])

        self.thread = _Worker(self)

    def _build(self, thread: Any) -> tuple[dict, list[dict]]:
        """构建索引并返回 (payload, failures)。"""
        from engine.utils.source_text import read_source_text

        node_defs_fp = compute_current_node_defs_fp(workspace_root=self._workspace_root)

        graph_files = [p for p in list(self._graph_code_files) if isinstance(p, Path) and Path(p).is_file()]
        # 去重（防御：软链接/重复扫描导致重复）
        dedup_cf: set[str] = set()
        deduped: list[Path] = []
        for p in graph_files:
            k = str(Path(p).resolve()).casefold()
            if k in dedup_cf:
                continue
            dedup_cf.add(k)
            deduped.append(Path(p).resolve())
        graph_files = deduped
        graph_files.sort(key=lambda p: str(p).casefold())

        total = len(graph_files)
        failures: list[dict] = []
        payload_items: list[tuple[str, Path, dict]] = []

        for idx, graph_file in enumerate(graph_files, start=1):
            if bool(thread.isInterruptionRequested()):
                raise RuntimeError("用户取消了索引构建。")
            thread.progress_changed.emit(
                int(idx),
                int(total + PROGRESS_COMPLETE_EXTRA_STEP),
                f"扫描：{graph_file.name}",
            )

            src = read_source_text(Path(graph_file))
            graph_id = infer_graph_id_from_graph_code_text(text=src.text)
            if str(graph_id or "").strip() == "":
                failures.append(
                    GraphScanFailure(
                        graph_file=str(Path(graph_file).resolve()),
                        graph_id="",
                        reason="节点图源码 docstring 未声明 graph_id。",
                    ).__dict__
                )
                continue

            graph_data, err = ensure_graph_cache_data(
                workspace_root=self._workspace_root,
                graph_id=str(graph_id),
                graph_code_file=Path(graph_file),
                current_node_defs_fp=node_defs_fp,
            )
            if err is not None or not isinstance(graph_data, dict):
                failures.append(
                    GraphScanFailure(
                        graph_file=str(Path(graph_file).resolve()),
                        graph_id=str(graph_id),
                        reason=str(err or "未能得到可用的 graph_cache data。"),
                    ).__dict__
                )
                continue

            payload_items.append((str(graph_id), Path(graph_file), graph_data))

        thread.progress_changed.emit(
            int(total + PROGRESS_COMPLETE_EXTRA_STEP),
            int(total + PROGRESS_COMPLETE_EXTRA_STEP),
            "生成索引…",
        )
        payload = build_usage_index_v1_from_graph_payloads(
            workspace_root=self._workspace_root,
            items=payload_items,
        )
        payload["_cache"] = dict(self._cache_meta) if self._cache_meta is not None else {"node_defs_fp": str(node_defs_fp)}
        if self._cache_path is not None:
            from .cache_v1 import write_cached_index_payload

            write_cached_index_payload(cache_path=Path(self._cache_path), payload=dict(payload))
        return payload, failures

