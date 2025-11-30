from __future__ import annotations

from pathlib import Path
from typing import List, Any
import ast

from .types import ExtractedSpec


def extract_specs(file_paths: List[Path]) -> List[ExtractedSpec]:
    """
    基于 AST 的节点规范提取。
    
    约定：
    - 输入为待分析的实现文件路径
    - 输出为规范化前的“原始提取项”列表（后续由 normalizer/validator 处理）
    - 不导入模块本身，避免导入副作用
    """
    for p in file_paths:
        if not isinstance(p, Path):
            raise TypeError("file_paths 列表元素必须是 pathlib.Path 实例")

    def _to_literal(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.List):
            return [_to_literal(e) for e in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(_to_literal(e) for e in node.elts)
        if isinstance(node, ast.Dict):
            return { _to_literal(k): _to_literal(v) for k, v in zip(node.keys, node.values) }
        return None

    extracted: List[ExtractedSpec] = []

    for file_path in file_paths:
        if not file_path.exists():
            continue
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
            spec_kwargs: Dict[str, Any] = {}
            for dec in fn.decorator_list:
                # 仅提取 @node_spec(...) 装饰的函数参数
                if isinstance(dec, ast.Call):
                    callee = dec.func
                    if isinstance(callee, ast.Name) and callee.id == "node_spec":
                        for kw in dec.keywords:
                            spec_kwargs[kw.arg] = _to_literal(kw.value)
                        break
            if not spec_kwargs:
                continue

            spec = ExtractedSpec(
                file_path=file_path,
                name=spec_kwargs.get("name"),
                category=spec_kwargs.get("category"),
                inputs=spec_kwargs.get("inputs") or [],
                outputs=spec_kwargs.get("outputs") or [],
                description=spec_kwargs.get("description") or "",
                mount_restrictions=list(spec_kwargs.get("mount_restrictions") or []),
                doc_reference=spec_kwargs.get("doc_reference") or "",
                dynamic_port_type=spec_kwargs.get("dynamic_port_type") or "",
                scopes=list(spec_kwargs.get("scopes") or []),
                aliases=list(spec_kwargs.get("aliases") or []),
                input_generic_constraints=dict(spec_kwargs.get("input_generic_constraints") or {}),
                output_generic_constraints=dict(spec_kwargs.get("output_generic_constraints") or {}),
            )
            extracted.append(spec)

    return extracted


