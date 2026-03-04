from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Dict, Tuple

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.resources.management_naming_rules import get_id_field_for_type


class ResourcePreviewScanService:
    """资源预览扫描服务（无 PyQt6 依赖）。

    用途：
    - UI 侧在“预览其它项目存档”时，不依赖当前 ResourceManager 作用域；
    - 直接从磁盘扫描指定 resource root（共享根或某个项目存档根）下的资源 ID 列表；
    - 内建轻量缓存：按 (root_key, resource_type) 记忆扫描结果，避免频繁触盘。
    """

    def __init__(self) -> None:
        self._ids_cache: Dict[Tuple[str, ResourceType], list[str]] = {}
        # 结构体定义分类扫描缓存：按 root_key 记忆 (basic_ids, ingame_save_ids)
        self._struct_definition_ids_by_kind_cache: Dict[str, tuple[list[str], list[str]]] = {}

    def invalidate(self) -> None:
        """清空全部扫描缓存。"""
        self._ids_cache.clear()
        self._struct_definition_ids_by_kind_cache.clear()

    def get_resource_ids(
        self,
        *,
        root_key: str,
        root_dir: Path,
        resource_type: ResourceType,
    ) -> list[str]:
        cache_key = (str(root_key), resource_type)
        cached = self._ids_cache.get(cache_key)
        if isinstance(cached, list):
            return list(cached)

        ids = scan_resource_ids_under_root(root_dir=root_dir, resource_type=resource_type)
        self._ids_cache[cache_key] = list(ids)
        return list(ids)

    def get_struct_definition_ids_by_kind(
        self,
        *,
        root_key: str,
        root_dir: Path,
    ) -> tuple[list[str], list[str]]:
        """扫描结构体定义并按类型（basic / ingame_save）分类返回。

        设计目的：
        - UI 的“项目存档预览”不依赖当前 ResourceManager 的索引作用域；
        - 直接从磁盘结构体定义文件中提取 STRUCT_ID 与（可选）STRUCT_TYPE/STRUCT_PAYLOAD，
          并按目录约定/声明字段归类。
        """
        cache_key = str(root_key or "")
        cached = self._struct_definition_ids_by_kind_cache.get(cache_key)
        if isinstance(cached, tuple) and len(cached) == 2:
            basic_ids, ingame_ids = cached
            return list(basic_ids), list(ingame_ids)

        basic_ids, ingame_ids = scan_struct_definition_ids_by_kind_under_root(root_dir=root_dir)
        self._struct_definition_ids_by_kind_cache[cache_key] = (list(basic_ids), list(ingame_ids))
        return list(basic_ids), list(ingame_ids)


def extract_python_module_level_string_constant(file_path: Path, *, constant_name: str) -> str:
    """从 Python 文件中提取模块级字符串常量（SIGNAL_ID / STRUCT_ID 等）。"""
    code_text = file_path.read_text(encoding="utf-8-sig")
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


def extract_struct_definition_type_from_file(file_path: Path) -> str:
    """从结构体定义文件中提取结构体类型（basic / ingame_save）。

    兼容口径：
    - 优先使用模块级 `STRUCT_TYPE = "basic"/"ingame_save"`；
    - 其次尝试从 `STRUCT_PAYLOAD` 的字典常量中读取 `struct_ype/struct_type`（仅限字面量 dict）。
    """
    struct_type = extract_python_module_level_string_constant(file_path, constant_name="STRUCT_TYPE")
    if struct_type:
        return struct_type.strip()

    code_text = file_path.read_text(encoding="utf-8-sig")
    parsed_tree = ast.parse(code_text, filename=str(file_path))
    for node in parsed_tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id != "STRUCT_PAYLOAD":
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            for key_node, value_node in zip(node.value.keys, node.value.values):
                if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                    continue
                if key_node.value not in {"struct_ype", "struct_type"}:
                    continue
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    return value_node.value.strip()
    return ""


def scan_struct_definition_ids_by_kind_under_root(*, root_dir: Path) -> tuple[list[str], list[str]]:
    """扫描结构体定义并按类型（basic / ingame_save）分类返回 ID 列表（不依赖 ResourceManager）。"""
    struct_root_dir = root_dir / Path(str(ResourceType.STRUCT_DEFINITION.value))
    if not struct_root_dir.exists() or not struct_root_dir.is_dir():
        return [], []

    id_to_kind: dict[str, str] = {}
    py_files = sorted(
        list(struct_root_dir.rglob("*.py")),
        key=lambda path: path.as_posix().casefold(),
    )
    for py_file in py_files:
        if not py_file.is_file():
            continue
        if py_file.name.startswith("_"):
            continue
        if "校验" in py_file.stem:
            continue
        if py_file.parent.name == "__pycache__":
            continue

        struct_id = extract_python_module_level_string_constant(py_file, constant_name="STRUCT_ID").strip()
        if not struct_id:
            continue

        parts = getattr(py_file, "parts", ())
        kind = ""
        if "局内存档结构体" in parts:
            kind = "ingame_save"
        elif "基础结构体" in parts:
            kind = "basic"
        else:
            kind = extract_struct_definition_type_from_file(py_file)

        normalized = str(kind or "").strip().lower()
        if normalized != "ingame_save":
            normalized = "basic"

        # 若同一 struct_id 出现多个来源：ingame_save 优先（更严格）。
        if id_to_kind.get(struct_id) == "ingame_save":
            continue
        if normalized == "ingame_save":
            id_to_kind[struct_id] = "ingame_save"
        else:
            id_to_kind.setdefault(struct_id, "basic")

    basic_ids = [sid for sid, kind in id_to_kind.items() if kind == "basic"]
    ingame_ids = [sid for sid, kind in id_to_kind.items() if kind == "ingame_save"]
    basic_ids.sort(key=lambda text: text.casefold())
    ingame_ids.sort(key=lambda text: text.casefold())
    return basic_ids, ingame_ids


def scan_resource_ids_under_root(*, root_dir: Path, resource_type: ResourceType) -> list[str]:
    """在给定资源根目录下扫描某一资源类型的 ID 列表（不依赖 ResourceManager 当前作用域）。"""
    resource_dir = root_dir / Path(str(resource_type.value))
    if not resource_dir.exists() or not resource_dir.is_dir():
        return []

    # Python 代码资源：递归扫描
    if resource_type in {ResourceType.GRAPH, ResourceType.SIGNAL, ResourceType.STRUCT_DEFINITION}:
        ids: list[str] = []
        py_files = sorted(
            list(resource_dir.rglob("*.py")),
            key=lambda path: path.as_posix().casefold(),
        )
        for py_file in py_files:
            if not py_file.is_file():
                continue
            if py_file.name.startswith("_"):
                continue
            if "校验" in py_file.stem:
                continue
            if py_file.parent.name == "__pycache__":
                continue

            resource_id = ""
            if resource_type == ResourceType.GRAPH:
                meta = load_graph_metadata_from_file(py_file)
                resource_id = str(meta.graph_id or "").strip() or py_file.stem
            elif resource_type == ResourceType.SIGNAL:
                resource_id = extract_python_module_level_string_constant(
                    py_file,
                    constant_name="SIGNAL_ID",
                )
            else:
                resource_id = extract_python_module_level_string_constant(
                    py_file,
                    constant_name="STRUCT_ID",
                )

            if isinstance(resource_id, str) and resource_id.strip():
                ids.append(resource_id.strip())
        ids.sort(key=lambda text: text.casefold())
        return ids

    # JSON 资源：只扫描直接子文件
    id_field = get_id_field_for_type(resource_type) or "id"
    ids: list[str] = []
    json_files = sorted(
        list(resource_dir.glob("*.json")),
        key=lambda path: path.as_posix().casefold(),
    )
    for json_file in json_files:
        if not json_file.is_file():
            continue
        payload = json.loads(json_file.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            continue
        value = payload.get(id_field)
        if not isinstance(value, str) or not value.strip():
            continue
        ids.append(value.strip())
    ids.sort(key=lambda text: text.casefold())
    return ids

