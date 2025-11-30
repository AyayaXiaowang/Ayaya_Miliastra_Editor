from __future__ import annotations

import ast
from typing import Iterator, Sequence, Set, Tuple


def iter_composite_instance_pairs(class_def: ast.ClassDef) -> Iterator[Tuple[str, str]]:
    """Yield (attribute_name, class_name) pairs from `self.xxx = ClassName(...)` assignments."""
    for item in class_def.body:
        if not isinstance(item, ast.FunctionDef) or item.name != "__init__":
            continue
        for stmt in item.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if _is_self_attribute(target) and isinstance(stmt.value, ast.Call):
                    rhs = stmt.value.func
                    if isinstance(rhs, ast.Name):
                        yield target.attr, rhs.id
        break


def collect_composite_instance_aliases(tree: ast.AST) -> Set[str]:
    """Collect attribute names used for composite instances within the module."""
    aliases: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for alias, _ in iter_composite_instance_pairs(node):
                aliases.add(alias)
    return aliases


def _is_self_attribute(target: ast.AST) -> bool:
    if not isinstance(target, ast.Attribute):
        return False
    owner = target.value
    return isinstance(owner, ast.Name) and owner.id == "self"


__all__: Sequence[str] = [
    "collect_composite_instance_aliases",
    "iter_composite_instance_pairs",
]

