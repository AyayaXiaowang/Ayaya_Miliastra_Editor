from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .file_io import _sanitize_filename


def _find_graph_like_objects(python_object: Any) -> List[Dict[str, Any]]:
    graph_objects: List[Dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            has_name = any(
                isinstance(key, str) and key.endswith("name@string") for key in value.keys()
            )
            if has_name and "3 nodes" in value:
                nodes_value = value.get("3 nodes")
                if isinstance(nodes_value, list) and any(
                    isinstance(node_item, dict) and "4 connects" in node_item for node_item in nodes_value
                ):
                    graph_objects.append(value)
                elif isinstance(nodes_value, dict) and "4 connects" in nodes_value:
                    graph_objects.append(value)
            for child_value in value.values():
                walk(child_value)
            return
        if isinstance(value, list):
            for child_value in value:
                walk(child_value)
            return

    walk(python_object)
    return graph_objects


def _extract_resource_entries(python_object: Any) -> List[Dict[str, Any]]:
    """
    尽量抽取“带 info + name”结构的资源条目，方便后续按名称/类型归档。
    """
    resource_entries: List[Dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            info_object = value.get("1 info")
            name_value = value.get("3 name@string") or value.get("2 name@string")
            if isinstance(info_object, dict) and isinstance(name_value, str) and name_value.strip() != "":
                resource_entries.append(value)
            for child_value in value.values():
                walk(child_value)
            return
        if isinstance(value, list):
            for child_value in value:
                walk(child_value)
            return

    walk(python_object)
    return resource_entries


def _pick_resource_output_subdir(resource_object: Dict[str, Any]) -> Path:
    name_value = resource_object.get("3 name@string") or resource_object.get("2 name@string") or ""
    if not isinstance(name_value, str):
        return Path("原始解析") / "资源条目" / "未命名"

    if "关卡实体" in name_value or name_value.endswith("_关卡实体"):
        return Path("实体摆放")
    if "节点图" in name_value:
        return Path("节点图") / "原始解析"
    if "玩家模板" in name_value:
        return Path("战斗预设") / "玩家模板"
    if "职业" in name_value:
        return Path("战斗预设") / "职业"
    if "投射物" in name_value:
        return Path("战斗预设") / "投射物"
    if "单位状态" in name_value:
        return Path("战斗预设") / "单位状态"
    if "道具" in name_value:
        return Path("战斗预设") / "道具"
    if "技能资源" in name_value:
        return Path("管理配置") / "技能资源"
    if "技能" in name_value:
        return Path("战斗预设") / "技能"
    if "结构体" in name_value:
        return Path("管理配置") / "结构体定义"
    if "变量" in name_value:
        return Path("管理配置") / "关卡变量"
    if "信号" in name_value:
        return Path("管理配置") / "信号"
    if "UI" in name_value or "布局" in name_value:
        return Path("管理配置") / "UI布局"
    if "控件" in name_value or "按钮" in name_value:
        return Path("管理配置") / "UI控件模板"
    if "元件" in name_value:
        return Path("元件库")

    return Path("原始解析") / "资源条目" / "未分类"


def _build_resource_file_name(resource_object: Dict[str, Any]) -> str:
    info_object = resource_object.get("1 info")
    name_value = resource_object.get("3 name@string") or resource_object.get("2 name@string") or "unnamed"

    type_value: Optional[int] = None
    id_value: Optional[int] = None
    if isinstance(info_object, dict):
        possible_type = info_object.get("2 type@int")
        possible_id = info_object.get("4 id@int") or info_object.get("5 id@int")
        if isinstance(possible_type, int):
            type_value = possible_type
        if isinstance(possible_id, int):
            id_value = possible_id

    name_text = str(name_value)
    name_part = _sanitize_filename(name_text, max_length=80)

    if type_value is not None and id_value is not None:
        return f"type{type_value}_id{id_value}_{name_part}.json"
    if id_value is not None:
        return f"id{id_value}_{name_part}.json"
    return f"{name_part}.json"


