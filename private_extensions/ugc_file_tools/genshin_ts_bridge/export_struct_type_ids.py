from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from private_extensions.ugc_file_tools.genshin_ts_bridge.parse_gia_proto import parse_enum_from_proto
from private_extensions.ugc_file_tools.genshin_ts_bridge.paths import resolve_paths


@dataclass(frozen=True, slots=True)
class StructTypeIdExportResult:
    enum_name: str
    mapping_param_type_to_type_id: Dict[str, int]
    unmapped_param_types: List[str]


def _default_param_type_to_vartype_name() -> Dict[str, str]:
    # Graph_Generater（用户侧）结构体定义使用的中文 param_type -> 真源 VarType 名称
    return {
        "实体": "Entity",
        "GUID": "GUID",
        "整数": "Integer",
        "布尔值": "Boolean",
        "浮点数": "Float",
        "字符串": "String",
        "GUID列表": "GUIDList",
        "整数列表": "IntegerList",
        "布尔值列表": "BooleanList",
        "浮点数列表": "FloatList",
        "字符串列表": "StringList",
        "三维向量": "Vector",
        "实体列表": "EntityList",
        "三维向量列表": "VectorList",
        "阵营": "Faction",
        "阵营列表": "FactionList",
        "配置ID": "Configuration",
        "元件ID": "Prefab",
        "配置ID列表": "ConfigurationList",
        "元件ID列表": "PrefabList",
        "结构体": "Struct",
        "结构体列表": "StructList",
        "字典": "Dictionary",
        # 目前 Graph_Generater 的结构体定义较少显式使用该类型名，但保留映射便于对齐
        "变量快照": "VariableSnapshot",
    }


def build_struct_param_type_to_type_id() -> StructTypeIdExportResult:
    p = resolve_paths()
    var_type = parse_enum_from_proto(proto_path=p.gia_proto_path, enum_name="VarType")
    param_to_vartype = _default_param_type_to_vartype_name()

    mapping: Dict[str, int] = {}
    unmapped: List[str] = []
    for param_type, vartype_name in sorted(param_to_vartype.items(), key=lambda kv: kv[0]):
        type_id = var_type.members_by_name.get(str(vartype_name))
        if type_id is None:
            unmapped.append(str(param_type))
            continue
        mapping[str(param_type)] = int(type_id)

    if unmapped:
        # fail-fast：避免生成半套映射后继续写回导致隐式漂移
        raise ValueError(f"以下 param_type 无法从 VarType 解析到 type_id：{unmapped}")

    return StructTypeIdExportResult(
        enum_name="VarType",
        mapping_param_type_to_type_id=mapping,
        unmapped_param_types=[],
    )


def _write_report_json(result: StructTypeIdExportResult) -> Path:
    p = resolve_paths()
    refs_dir = p.graph_generater_root / "private_extensions" / "ugc_file_tools" / "refs" / "genshin_ts"
    refs_dir.mkdir(parents=True, exist_ok=True)
    out_path = refs_dir / "genshin_ts__struct_field_type_ids.report.json"
    out_path.write_text(
        json.dumps(
            {
                "enum": result.enum_name,
                "mapping_param_type_to_type_id": result.mapping_param_type_to_type_id,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    result = build_struct_param_type_to_type_id()
    report_path = _write_report_json(result)
    print(str(report_path))


if __name__ == "__main__":
    main()

