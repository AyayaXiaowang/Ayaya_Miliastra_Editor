from __future__ import annotations

"""
GraphModel(JSON) 文件枚举工具（报告/批处理共用）。
"""

from pathlib import Path
from typing import List, Sequence, Set


def iter_graph_model_json_files_from_paths(paths: Sequence[str]) -> List[Path]:
    results: List[Path] = []
    patterns = (
        "*.graph_model.typed.json",
        "*.graph_model.typed.filtered.json",
        "*.graph_model.json",
    )

    for raw in paths:
        p = Path(raw).resolve()
        if p.is_file():
            if p.suffix.lower() != ".json":
                raise ValueError(f"仅支持 JSON 文件：{str(p)!r}")
            results.append(p)
            continue
        if p.is_dir():
            matched: List[Path] = []
            for pat in patterns:
                matched.extend(sorted(p.rglob(pat)))
            matched = [m.resolve() for m in matched if m.is_file()]
            if not matched:
                raise ValueError(f"目录内未找到 GraphModel JSON（匹配 {patterns}）：{str(p)!r}")
            results.extend(matched)
            continue
        raise FileNotFoundError(str(p))

    # 去重保持稳定顺序
    seen: Set[str] = set()
    unique: List[Path] = []
    for p in results:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


