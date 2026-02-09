from __future__ import annotations

"""UI HTML Workbench 产物的调试标签规范化。

背景：
- Web 侧预览/检查器通常会用 `data-debug-label` 定位元素；
- 但扁平化输出中，某些文本元素会被兜底标注为 `data-debug-label="text-"`（或类似），从而产生大量重复；
- 当定位逻辑假设 label 唯一时，会出现“左下角列表可点，但点击无反应/定位不到”的问题。

本模块提供一个“后处理”步骤：对生成的 `*.flattened__*.flattened.html` 做 label 去重，
保证同一文件内 `data-debug-label` 唯一，从而让 Web 侧无需改动也能稳定定位。
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DebugLabelNormalizeResult:
    html_path: Path
    changed: bool
    duplicate_label_count: int


_DEBUG_LABEL_ATTR_RE = re.compile(r'data-debug-label="([^"]*)"')


def normalize_ui_html_bundle_cli_flattened_outputs(
    *,
    workspace_root: Path,
    package_id: str,
    source_html_file: Path,
) -> list[DebugLabelNormalizeResult]:
    """规范化 `app/runtime/cache/ui_html_bundle_cli/<package_id>/` 下的扁平化 HTML 产物。

    约定：
    - 目标文件名形如：`<source_stem>.flattened__<hash>.flattened.html`
    - 本函数只处理“扁平化预览 HTML”，不触碰原始 UI 源码 HTML。
    """
    ws = Path(workspace_root).resolve()
    pkg = str(package_id or "").strip()
    if not pkg or pkg in {"global_view", "unclassified_view"}:
        return []

    cache_dir = (ws / "app" / "runtime" / "cache" / "ui_html_bundle_cli" / pkg).resolve()
    if not cache_dir.is_dir():
        return []

    stem = Path(source_html_file).stem
    if not stem:
        return []

    targets = sorted(
        cache_dir.glob(f"{stem}.flattened__*.flattened.html"),
        key=lambda p: p.as_posix().casefold(),
    )
    if not targets:
        return []

    results: list[DebugLabelNormalizeResult] = []
    for html_path in targets:
        text = html_path.read_text(encoding="utf-8")
        new_text, duplicate_count = _dedupe_debug_labels_in_html_text(text)
        changed = new_text != text
        if changed:
            html_path.write_text(new_text, encoding="utf-8")
        results.append(
            DebugLabelNormalizeResult(
                html_path=html_path,
                changed=changed,
                duplicate_label_count=int(duplicate_count),
            )
        )
    return results


def _dedupe_debug_labels_in_html_text(html_text: str) -> tuple[str, int]:
    counts: dict[str, int] = {}
    duplicate_count = 0

    def _repl(match: re.Match[str]) -> str:
        nonlocal duplicate_count
        label = match.group(1)
        current = counts.get(label, 0) + 1
        counts[label] = current
        if current == 1:
            return match.group(0)
        duplicate_count += 1
        # 约定：仅对重复项追加后缀，首个保持原 label，最大限度保留可读性。
        return f'data-debug-label="{label}__{current}"'

    return _DEBUG_LABEL_ATTR_RE.sub(_repl, str(html_text or "")), int(duplicate_count)

