from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .discovery import discover_implementation_files
from .extractor_ast import extract_specs
from .normalizer import normalize_specs
from .validator import validate_specs
from .merger import merge_specs
from .indexer import build_index


def run_pipeline(workspace_path: Path) -> Dict[str, Any]:
    """
    运行 V2 节点解析管线，返回索引结构：
    {
      "by_key": { standard_key: item_dict, ... },
      "alias_to_key": { f"{category}/{alias}": standard_key, ... }
    }
    """
    if not isinstance(workspace_path, Path):
        raise TypeError("workspace_path 必须是 pathlib.Path 实例")

    # 1) 发现实现文件
    files = discover_implementation_files(workspace_path)
    # 2) AST 提取（不导入模块）
    extracted = extract_specs(files)
    # 3) 标准化
    normalized = normalize_specs(extracted)
    # 4) 校验（阻断式）
    validated = validate_specs(normalized)
    # 5) 合并（server 优先，端口不兼容→作用域变体）
    library_by_key = merge_specs(validated)
    # 6) 索引
    index = build_index(library_by_key)
    return index



