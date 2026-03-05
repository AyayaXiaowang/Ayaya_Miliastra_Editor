from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import ast

from .types import ExtractedSpec
from .node_spec_ast_utils import is_node_spec_decorator


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
            return {_to_literal(k): _to_literal(v) for k, v in zip(node.keys, node.values)}
        return None

    extracted: List[ExtractedSpec] = []

    for file_path in file_paths:
        if not file_path.exists():
            continue
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
            has_node_spec = False
            spec_kwargs: Dict[str, Any] = {}
            for dec in fn.decorator_list:
                # 仅提取 @node_spec(...) 装饰的函数参数（支持 @engine.node_spec(...) 形态）
                if not is_node_spec_decorator(dec):
                    continue
                has_node_spec = True
                if isinstance(dec, ast.Call):
                    for kw in dec.keywords:
                        if not kw.arg:
                            continue
                        spec_kwargs[kw.arg] = _to_literal(kw.value)
                break
            # 没有 @node_spec(...) 则跳过；有装饰器但缺字段由后续 normalizer/validator 阻断式报错
            if not has_node_spec:
                continue

            spec = ExtractedSpec(
                file_path=file_path,
                function_name=str(fn.name or ""),
                name=spec_kwargs.get("name"),
                category=spec_kwargs.get("category"),
                semantic_id=str(spec_kwargs.get("semantic_id") or ""),
                inputs=spec_kwargs.get("inputs") or [],
                outputs=spec_kwargs.get("outputs") or [],
                input_port_aliases=dict(spec_kwargs.get("input_port_aliases") or {}),
                output_port_aliases=dict(spec_kwargs.get("output_port_aliases") or {}),
                description=spec_kwargs.get("description") or "",
                mount_restrictions=list(spec_kwargs.get("mount_restrictions") or []),
                doc_reference=spec_kwargs.get("doc_reference") or "",
                dynamic_port_type=spec_kwargs.get("dynamic_port_type") or "",
                scopes=list(spec_kwargs.get("scopes") or []),
                aliases=list(spec_kwargs.get("aliases") or []),
                input_generic_constraints=dict(spec_kwargs.get("input_generic_constraints") or {}),
                output_generic_constraints=dict(spec_kwargs.get("output_generic_constraints") or {}),
                input_enum_options=dict(spec_kwargs.get("input_enum_options") or {}),
                output_enum_options=dict(spec_kwargs.get("output_enum_options") or {}),
                input_defaults=dict(spec_kwargs.get("input_defaults") or {}),
            )
            extracted.append(spec)

    return extracted


