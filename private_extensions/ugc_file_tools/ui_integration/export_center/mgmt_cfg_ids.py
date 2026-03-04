from __future__ import annotations

from pathlib import Path


def _extract_module_level_string_constant(*, file_path: Path, constant_name: str) -> str:
    import ast

    code_text = Path(file_path).read_text(encoding="utf-8-sig")
    parsed_tree = ast.parse(code_text, filename=str(file_path))
    for node in parsed_tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id != constant_name:
                    continue
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value.strip()
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name):
                continue
            if node.target.id != constant_name:
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value.strip()
    return ""


def _collect_writeback_ids_from_mgmt_cfg_items(items: list[object]) -> tuple[list[str], list[str], list[str]]:
    selected_signal_ids: list[str] = []
    selected_basic_struct_ids: list[str] = []
    selected_ingame_struct_ids: list[str] = []
    for it in list(items):
        if getattr(it, "category", None) != "mgmt_cfg":
            continue
        rel = str(getattr(it, "relative_path", None) or "").replace("\\", "/")
        abs_path = Path(getattr(it, "absolute_path")).resolve()
        if abs_path.suffix.lower() != ".py":
            continue
        marker = f"/{rel}"
        if "/管理配置/信号/" in marker:
            sid = _extract_module_level_string_constant(file_path=abs_path, constant_name="SIGNAL_ID")
            if not sid:
                raise ValueError(f"信号定义缺少 SIGNAL_ID：{str(abs_path)}")
            selected_signal_ids.append(str(sid))
        if "/管理配置/结构体定义/基础结构体/" in marker:
            sid = _extract_module_level_string_constant(file_path=abs_path, constant_name="STRUCT_ID")
            if not sid:
                raise ValueError(f"结构体定义缺少 STRUCT_ID：{str(abs_path)}")
            selected_basic_struct_ids.append(str(sid))
        if "/管理配置/结构体定义/局内存档结构体/" in marker:
            sid = _extract_module_level_string_constant(file_path=abs_path, constant_name="STRUCT_ID")
            if not sid:
                raise ValueError(f"局内存档结构体定义缺少 STRUCT_ID：{str(abs_path)}")
            selected_ingame_struct_ids.append(str(sid))

    selected_signal_ids = sorted(set(selected_signal_ids), key=lambda t: t.casefold())
    selected_basic_struct_ids = sorted(set(selected_basic_struct_ids), key=lambda t: t.casefold())
    selected_ingame_struct_ids = sorted(set(selected_ingame_struct_ids), key=lambda t: t.casefold())
    return (selected_signal_ids, selected_basic_struct_ids, selected_ingame_struct_ids)

