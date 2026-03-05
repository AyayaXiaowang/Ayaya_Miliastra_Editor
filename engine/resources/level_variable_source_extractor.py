from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import tokenize

from engine.graph.utils.ast_utils import (
    NOT_EXTRACTABLE,
    clear_module_constants_context,
    collect_module_constants,
    extract_constant_value,
    set_module_constants_context,
)

_SYNTAX_CHECK_SNIPPET = (
    "import sys;"
    "code=sys.stdin.read();"
    "compile(code, sys.argv[1], 'exec')"
)


def _find_module_assignment_value(tree: ast.Module, name: str) -> ast.expr | None:
    want = str(name or "").strip()
    if not want:
        return None

    for stmt in list(getattr(tree, "body", []) or []):
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            for target in targets:
                if isinstance(target, ast.Name) and target.id == want:
                    return stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            if isinstance(target, ast.Name) and target.id == want:
                return getattr(stmt, "value", None)
    return None


def _try_extract_level_variable_definition_from_ast(node: ast.expr) -> dict | None:
    if isinstance(node, ast.Dict):
        value = extract_constant_value(node)
        if value is NOT_EXTRACTABLE or not isinstance(value, dict):
            return None
        return dict(value)

    if not isinstance(node, ast.Call):
        return None

    func = getattr(node, "func", None)
    is_lvd_call = False
    if isinstance(func, ast.Name) and func.id == "LevelVariableDefinition":
        is_lvd_call = True
    elif isinstance(func, ast.Attribute) and func.attr == "LevelVariableDefinition":
        is_lvd_call = True
    if not is_lvd_call:
        return None

    payload: dict[str, object] = {
        "variable_id": "",
        "variable_name": "",
        "variable_type": "",
        "default_value": None,
        "is_global": True,
        "description": "",
        "metadata": {},
    }

    ordered_fields = [
        "variable_id",
        "variable_name",
        "variable_type",
        "default_value",
        "is_global",
        "description",
        "metadata",
    ]

    for idx, arg_node in enumerate(list(getattr(node, "args", []) or [])):
        if idx >= len(ordered_fields):
            return None
        extracted = extract_constant_value(arg_node)
        if extracted is NOT_EXTRACTABLE:
            return None
        payload[ordered_fields[idx]] = extracted

    allowed = set(ordered_fields)
    for kw in list(getattr(node, "keywords", []) or []):
        key = getattr(kw, "arg", None)
        if key is None:
            return None
        name = str(key).strip()
        if name not in allowed:
            return None
        extracted = extract_constant_value(getattr(kw, "value", None))
        if extracted is NOT_EXTRACTABLE:
            return None
        payload[name] = extracted

    return dict(payload)


def try_extract_variable_file_header_and_entries_from_code(
    py_path: Path,
) -> tuple[str | None, str | None, list[dict] | None]:
    """从关卡变量代码资源文件中静态提取 (VARIABLE_FILE_ID, VARIABLE_FILE_NAME, LEVEL_VARIABLES)。"""
    if not py_path.is_file():
        return None, None, None

    with tokenize.open(str(py_path)) as f:
        source_text = f.read()

    tree = ast.parse(source_text, filename=str(py_path))
    constants = collect_module_constants(tree)
    set_module_constants_context(constants)

    file_id_expr = _find_module_assignment_value(tree, "VARIABLE_FILE_ID")
    if file_id_expr is None:
        clear_module_constants_context()
        return None, None, None
    file_id_value = extract_constant_value(file_id_expr)
    if file_id_value is NOT_EXTRACTABLE or not isinstance(file_id_value, str) or not file_id_value.strip():
        clear_module_constants_context()
        return None, None, None

    file_name_value: str | None = None
    file_name_expr = _find_module_assignment_value(tree, "VARIABLE_FILE_NAME")
    if file_name_expr is not None:
        extracted_name = extract_constant_value(file_name_expr)
        if extracted_name is not NOT_EXTRACTABLE and isinstance(extracted_name, str) and extracted_name.strip():
            file_name_value = str(extracted_name).strip()

    lv_expr = _find_module_assignment_value(tree, "LEVEL_VARIABLES")
    if lv_expr is None:
        clear_module_constants_context()
        return str(file_id_value).strip(), file_name_value, None

    if not isinstance(lv_expr, (ast.List, ast.Tuple)):
        clear_module_constants_context()
        return str(file_id_value).strip(), file_name_value, None

    items: list[dict] = []
    for elt in list(getattr(lv_expr, "elts", []) or []):
        entry = _try_extract_level_variable_definition_from_ast(elt)
        if not isinstance(entry, dict):
            clear_module_constants_context()
            return str(file_id_value).strip(), file_name_value, None
        items.append(dict(entry))

    clear_module_constants_context()
    return str(file_id_value).strip(), file_name_value, list(items)


def check_python_source_syntax(py_path: Path) -> tuple[bool, str]:
    """检查 py_path 的 Python 语法是否有效（不导入模块、不执行顶层代码）。"""
    code_bytes = py_path.read_bytes()
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", _SYNTAX_CHECK_SNIPPET, str(py_path)],
        capture_output=True,
        input=code_bytes,
    )
    if completed.returncode == 0:
        return True, ""

    stderr_text = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
    stdout_text = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
    raw_message = (stderr_text or stdout_text).strip()
    if not raw_message:
        return False, "unknown syntax error"
    last_line = raw_message.splitlines()[-1].strip()
    return False, last_line


__all__ = [
    "check_python_source_syntax",
    "try_extract_variable_file_header_and_entries_from_code",
]

