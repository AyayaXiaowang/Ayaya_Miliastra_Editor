from __future__ import annotations

"""
gil_id_listing.py

目标：
- 直接读取 `.gil`，列出其中包含的：
  - 元件：template_id（元件ID）与 instance_guid（实例 GUID），并尽量提取实例名（便于人工核对）
  - 实体：instance_id_int（实体实例ID），并尽量提取实例名

说明：
- `.gil` 本体是一个简单的 container（header + payload + footer），payload 为 protobuf-like bytes。
- 这里不依赖任何外部 DLL，复用仓库现有的 protobuf-like decoder，将 payload 解码为 dump-json 兼容的 numeric_message。

约束：
- 不使用 try/except：结构不符合预期直接抛错，避免静默漏报/错报。
- 输出做稳定排序/稳定去重，便于 diff 与复现。
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_numeric_message


JsonDict = Dict[str, Any]


def _to_list_of_dicts(value: Any) -> List[JsonDict]:
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _first_dict(value: Any) -> Optional[JsonDict]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def _ensure_list_allow_scalar(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return [value]


# -------------------- component instances (template_id + instance_guid) --------------------


def _try_extract_component_name_from_record(record: JsonDict) -> str:
    """
    从 dump-json record 中抽取“元件实例名称”。

    经验结构（从样本对照抽取）：
    - record['2'] 为元件ID（template_id，1000xxxx）
    - record['6'] 为 repeated message 列表
      - 某个条目包含 record['11']['1'] 的字符串（名称）
    """
    v6 = record.get("6")
    for it in _to_list_of_dicts(v6):
        # 兼容两种常见形态：
        # - {"1": 1, "11": {"1": "名字"}}
        # - {"1": 1, "11": "名字"}
        v11 = it.get("11")
        if isinstance(v11, str):
            name = str(v11).strip()
            if name != "":
                return name

        inner11 = _first_dict(v11)
        if not isinstance(inner11, dict):
            continue
        name_val = inner11.get("1")
        if isinstance(name_val, str):
            name = str(name_val).strip()
            if name != "":
                return name
    return ""


def extract_component_instances_from_payload_root(payload_root: JsonDict) -> List[JsonDict]:
    """
    从 payload_root 深度扫描并抽取“元件实例”候选记录：
    - instance_guid: int
    - template_id: int
    - name: str（可能为空）
    """
    collected: List[JsonDict] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return

        cid = value.get("2")
        guid = value.get("1")
        if isinstance(cid, int) and isinstance(guid, int):
            # heuristic：guid 为大整数；template_id 为 1000xxxx 一类的正整数
            if int(guid) > 1_000_000_000 and 1 <= int(cid) <= 999_999_999:
                collected.append(
                    {
                        "instance_guid": int(guid),
                        "template_id": int(cid),
                        "name": _try_extract_component_name_from_record(value),
                    }
                )

        for _k, v in value.items():
            visit(v)

    visit(payload_root)

    # 稳定去重：以 (instance_guid, template_id) 为主键；若同键多条，优先保留 name 非空者。
    dedup: Dict[Tuple[int, int], JsonDict] = {}
    for item in collected:
        guid = int(item.get("instance_guid") or 0)
        tid = int(item.get("template_id") or 0)
        key = (guid, tid)
        prev = dedup.get(key)
        if prev is None:
            dedup[key] = item
            continue
        prev_name = str(prev.get("name") or "")
        new_name = str(item.get("name") or "")
        if prev_name == "" and new_name != "":
            dedup[key] = item

    return list(dedup.values())


def build_component_name_to_template_id(*, component_instances: List[JsonDict]) -> Dict[str, int]:
    """
    将元件实例列表归并为 `name -> template_id`（first-wins，稳定：按扫描顺序）。

    注意：同名映射到不同 template_id 的情况不会抛错（诊断工具倾向“尽量列出”）。
    """
    out: Dict[str, int] = {}
    for it in component_instances:
        name = str(it.get("name") or "").strip()
        if name == "":
            continue
        tid = it.get("template_id")
        if not isinstance(tid, int) or int(tid) <= 0:
            continue
        if name not in out:
            out[name] = int(tid)
    return out


# -------------------- entity instances (instance_id_int) --------------------


def _extract_entity_instance_id_int(entry: JsonDict) -> int | None:
    value = entry.get("1")
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    if isinstance(value, int):
        return int(value)
    return None


def _extract_entity_instance_name(entry: JsonDict) -> str:
    # 经验：entry['5'] 为 meta repeated；item['1']==1 的 item['11']['1'] 为名称
    meta_list = _ensure_list_allow_scalar(entry.get("5"))
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        container = item.get("11")
        if not isinstance(container, dict):
            continue
        name_val = container.get("1")
        if isinstance(name_val, str):
            return str(name_val).strip()
    return ""


def extract_entity_instances_from_payload_root(payload_root: JsonDict) -> List[JsonDict]:
    """
    从 payload_root['5']['1']（实体摆放 entries）抽取实体实例：
    - instance_id_int: int
    - name: str（可能为空）
    """
    section5 = payload_root.get("5")
    if not isinstance(section5, dict):
        return []

    entries = _ensure_list_allow_scalar(section5.get("1"))

    items: List[JsonDict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        instance_id_int = _extract_entity_instance_id_int(entry)
        if not isinstance(instance_id_int, int) or int(instance_id_int) <= 0:
            continue
        items.append(
            {
                "instance_id_int": int(instance_id_int),
                "name": _extract_entity_instance_name(entry),
            }
        )

    # 稳定去重：以 instance_id_int 为主键；若多条，优先保留 name 非空者。
    dedup: Dict[int, JsonDict] = {}
    for it in items:
        iid = int(it.get("instance_id_int") or 0)
        prev = dedup.get(iid)
        if prev is None:
            dedup[iid] = it
            continue
        prev_name = str(prev.get("name") or "")
        new_name = str(it.get("name") or "")
        if prev_name == "" and new_name != "":
            dedup[iid] = it
    return list(dedup.values())


def build_entity_name_to_instance_id_int(*, entity_instances: List[JsonDict]) -> Dict[str, int]:
    """
    将实体实例列表归并为 `name -> instance_id_int`（first-wins，稳定：按出现顺序）。
    """
    out: Dict[str, int] = {}
    for it in entity_instances:
        name = str(it.get("name") or "").strip()
        if name == "":
            continue
        iid = it.get("instance_id_int")
        if not isinstance(iid, int) or int(iid) <= 0:
            continue
        if name not in out:
            out[name] = int(iid)
    return out


# -------------------- top-level API --------------------


def list_component_and_entity_ids_from_gil_file(
    *,
    gil_file_path: Path,
    max_depth: int = 16,
    include_instances: bool = False,
) -> JsonDict:
    """
    直接读取 `.gil`，导出其中的“元件/实体 ID 清单”。

    返回 dict（可直接 json.dumps）：
    - schema_version: int
    - source_gil_file: str
    - component_template_ids: list[int]
    - entity_instance_id_ints: list[int]
    - component_name_to_template_id: dict[str, int]
    - entity_name_to_instance_id_int: dict[str, int]
    - （可选）component_instances / entity_instances
    """
    p = Path(gil_file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    payload_root = load_gil_payload_as_numeric_message(p, max_depth=int(max_depth), prefer_raw_hex_for_utf8=False)

    component_instances = extract_component_instances_from_payload_root(payload_root)
    entity_instances = extract_entity_instances_from_payload_root(payload_root)

    component_template_ids = sorted({int(it["template_id"]) for it in component_instances if isinstance(it.get("template_id"), int)})
    entity_instance_id_ints = sorted(
        {int(it["instance_id_int"]) for it in entity_instances if isinstance(it.get("instance_id_int"), int)}
    )

    out: JsonDict = {
        "schema_version": 1,
        "source_gil_file": str(p),
        "decode_max_depth": int(max_depth),
        "component_template_ids": component_template_ids,
        "component_template_ids_count": int(len(component_template_ids)),
        "entity_instance_id_ints": entity_instance_id_ints,
        "entity_instance_id_ints_count": int(len(entity_instance_id_ints)),
        "component_name_to_template_id": build_component_name_to_template_id(component_instances=component_instances),
        "entity_name_to_instance_id_int": build_entity_name_to_instance_id_int(entity_instances=entity_instances),
    }

    if bool(include_instances):
        # 稳定输出：按 id 升序排序（再按 name）
        out["component_instances"] = sorted(
            component_instances,
            key=lambda x: (int(x.get("template_id") or 0), int(x.get("instance_guid") or 0), str(x.get("name") or "")),
        )
        out["entity_instances"] = sorted(
            entity_instances,
            key=lambda x: (int(x.get("instance_id_int") or 0), str(x.get("name") or "")),
        )

    return out


__all__ = [
    "extract_component_instances_from_payload_root",
    "extract_entity_instances_from_payload_root",
    "build_component_name_to_template_id",
    "build_entity_name_to_instance_id_int",
    "list_component_and_entity_ids_from_gil_file",
]


