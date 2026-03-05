from __future__ import annotations

"""
create_graph_variable_all_types_in_gil.py

目标：
- 生成一个用于“节点图变量写回能力自测”的 .gil：
  - 在目标节点图 GraphEntry['6'] 写入覆盖 **Graph_Generater/engine/type_registry.py 的 VARIABLE_TYPES（允许集合）**
    的节点图变量定义；
  - 每种类型写入“长度不同”的默认值（列表/字典用不同元素数量，字符串用不同文本长度等）。

说明：
- 该脚本仅写回节点图变量定义表，不修改节点/连线。
- 注意：`枚举(VarType=14)` / `局部变量(VarType=16)` 属于端口/运行期机制范畴，**不作为“节点图变量类型”写回**；
  若真源样本中出现该写法，通常意味着样本为实验/污染数据，应通过合约/差异报告定位并剔除。
- 不使用 try/except；失败直接抛错，便于定位。
"""

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from ugc_file_tools.node_graph_writeback.graph_variables import (
    build_graph_variable_def_item_from_metadata as _build_graph_variable_def_item_from_metadata,
    extract_struct_defs_from_payload_root as _extract_struct_defs_from_payload_root,
)
from ugc_file_tools.commands.create_type_id_matrix_in_gil import (
    find_graph_entry as _find_graph_entry,
    get_payload_root as _get_payload_root,
)


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    temp_out = resolve_output_file_path_in_out_dir(Path("_tmp_graph_vars_all_types.dump.json"))
    dump_gil_to_json(str(input_path), str(temp_out))
    raw_dump_object = json.loads(temp_out.read_text(encoding="utf-8"))
    if not isinstance(raw_dump_object, dict):
        raise ValueError("DLL dump-json 顶层不是 dict")
    return raw_dump_object


def _get_first_graph_id_int(payload_root: Dict[str, Any]) -> Optional[int]:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        return None
    groups = section.get("1")
    groups_list = groups if isinstance(groups, list) else [groups] if isinstance(groups, dict) else []
    for group in groups_list:
        if not isinstance(group, dict):
            continue
        entries = group.get("1")
        entries_list = entries if isinstance(entries, list) else [entries] if isinstance(entries, dict) else []
        for entry in entries_list:
            if not isinstance(entry, dict):
                continue
            header = entry.get("1")
            header_obj = header[0] if isinstance(header, list) and header and isinstance(header[0], dict) else header
            if not isinstance(header_obj, dict):
                continue
            gid = header_obj.get("5")
            if isinstance(gid, int):
                return int(gid)
    return None


def _choose_demo_struct_def(struct_defs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从 base/template 的结构体定义里挑一个“字段数较多且类型可写回”的结构体做演示。"""
    supported_field_types = {1, 2, 3, 4, 5, 6, 12, 17, 20, 21}
    candidates: List[Dict[str, Any]] = []
    for sd in struct_defs:
        fields = sd.get("fields")
        if not isinstance(fields, list) or not fields:
            continue
        field_types = [f.get("var_type_int") for f in fields if isinstance(f, dict)]
        if not field_types or not all(isinstance(v, int) and int(v) in supported_field_types for v in field_types):
            continue
        candidates.append(sd)

    if not candidates:
        raise ValueError("未找到可用于节点图变量默认值写回的结构体定义（base/template 可能缺少 struct_defs 或字段类型不在支持集合内）。")

    def score(sd: Dict[str, Any]) -> Tuple[int, int, int, str]:
        fields = sd.get("fields") if isinstance(sd.get("fields"), list) else []
        types = [int(f.get("var_type_int")) for f in fields if isinstance(f, dict) and isinstance(f.get("var_type_int"), int)]
        has_string = 1 if 6 in types else 0
        unique_types = len(set(types))
        return (has_string, len(types), unique_types, str(sd.get("name") or ""))

    # 优先：含字符串字段 > 字段数更多 > 类型更丰富 > 名字稳定
    return sorted(candidates, key=score, reverse=True)[0]


def _build_demo_struct_values_by_def(struct_def: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """根据结构体定义生成 2 份结构体默认值（不同长度/内容），但字段类型/数量严格一致。"""
    fields = struct_def.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError(f"struct_def 缺少 fields：{struct_def!r}")

    # values 顺序：按 struct_def.fields（已按 index 排序）
    values_a: List[Any] = []
    values_b: List[Any] = []

    long_text = "结构体字段_长字符串_用于测试节点图变量写回_12345_ABCDE_中文"
    short_text = "短"

    for i, f in enumerate(fields):
        if not isinstance(f, dict):
            raise ValueError(f"struct_def.fields 元素不是 dict：{f!r}")
        vt = f.get("var_type_int")
        if not isinstance(vt, int):
            raise ValueError(f"struct_def.fields 缺少 var_type_int：{f!r}")
        vt_int = int(vt)

        if vt_int == 6:
            # 字符串字段：A 用长文本，B 用短文本（并按位置做一点差异）
            values_a.append(f"{long_text}_{i}")
            values_b.append(f"{short_text}{i}")
        elif vt_int == 5:
            values_a.append(3.1415926)
            values_b.append(-2.5)
        elif vt_int == 4:
            values_a.append(True)
            values_b.append(False)
        elif vt_int == 3:
            values_a.append(123456 + i)
            values_b.append(i)
        elif vt_int == 12:
            values_a.append((1.0 + i, 2.0 + i, 3.0 + i))
            values_b.append((0.0, 0.0, 0.0))
        elif vt_int in (1, 2, 17, 20, 21):
            # id-like：尽量用“保守值”，避免引用校验风险
            values_a.append(0)
            values_b.append(0)
        else:
            raise ValueError(f"暂不支持该结构体字段类型写回：var_type_int={vt_int} struct={struct_def.get('name')!r}")

    struct_value_a = {"values": values_a}
    struct_value_b = {"values": values_b}
    return struct_value_a, struct_value_b


def _build_all_types_graph_variables(*, struct_def: Dict[str, Any]) -> List[Dict[str, Any]]:
    long_text = (
        "这是一个用于测试『节点图变量写回』的长字符串默认值。"
        "包含：中文、ASCII、数字12345，以及一些符号_-+=*/()[]{}."
        "长度应明显大于短字符串。"
    )

    struct_value_a, struct_value_b = _build_demo_struct_values_by_def(struct_def)
    struct_id_int = int(struct_def.get("struct_id"))

    variables: List[Dict[str, Any]] = [
        {"name": "var_实体", "variable_type": "实体", "default_value": 0, "description": "VarType=1", "is_exposed": False},
        {"name": "var_GUID", "variable_type": "GUID", "default_value": "1073742153", "description": "VarType=2", "is_exposed": False},
        {"name": "var_整数", "variable_type": "整数", "default_value": 123456789, "description": "VarType=3", "is_exposed": False},
        {"name": "var_布尔值", "variable_type": "布尔值", "default_value": True, "description": "VarType=4", "is_exposed": False},
        {"name": "var_浮点数", "variable_type": "浮点数", "default_value": 3.1415926, "description": "VarType=5", "is_exposed": False},
        {"name": "var_字符串", "variable_type": "字符串", "default_value": long_text, "description": "VarType=6", "is_exposed": False},
        {"name": "var_GUID列表_len5", "variable_type": "GUID列表", "default_value": ["1073742154", "1073742155", "1073742156", "1073742157", "1073742158"], "description": "VarType=7", "is_exposed": False},
        {"name": "var_整数列表_len7", "variable_type": "整数列表", "default_value": [1, 2, 3, 4, 5, 6, 7], "description": "VarType=8", "is_exposed": False},
        {"name": "var_布尔值列表_len4", "variable_type": "布尔值列表", "default_value": [True, False, True, False], "description": "VarType=9", "is_exposed": False},
        {"name": "var_浮点数列表_len6", "variable_type": "浮点数列表", "default_value": [0.1, 1.2, -2.5, 3.75, 4.0, 6.28], "description": "VarType=10", "is_exposed": False},
        {"name": "var_字符串列表_len3", "variable_type": "字符串列表", "default_value": ["条目A", "条目B_更长一点", "条目C"], "description": "VarType=11", "is_exposed": False},
        {"name": "var_三维向量", "variable_type": "三维向量", "default_value": (1.0, 2.0, 3.0), "description": "VarType=12", "is_exposed": False},
        {"name": "var_实体列表_len2", "variable_type": "实体列表", "default_value": [0, 0], "description": "VarType=13", "is_exposed": False},
        {"name": "var_三维向量列表_len4", "variable_type": "三维向量列表", "default_value": [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0), (9.0, 8.0, 7.0), (-1.0, -2.0, -3.0)], "description": "VarType=15", "is_exposed": False},
        {"name": "var_阵营", "variable_type": "阵营", "default_value": 1, "description": "VarType=17", "is_exposed": False},
        {"name": "var_配置ID", "variable_type": "配置ID", "default_value": 0, "description": "VarType=20(保守用0避免引用校验)", "is_exposed": False},
        {"name": "var_元件ID", "variable_type": "元件ID", "default_value": 0, "description": "VarType=21(保守用0避免引用校验)", "is_exposed": False},
        {"name": "var_配置ID列表_len3", "variable_type": "配置ID列表", "default_value": [0, 0, 0], "description": "VarType=22", "is_exposed": False},
        {"name": "var_元件ID列表_len4", "variable_type": "元件ID列表", "default_value": [0, 0, 0, 0], "description": "VarType=23", "is_exposed": False},
        {"name": "var_阵营列表_len2", "variable_type": "阵营列表", "default_value": [1, 2], "description": "VarType=24", "is_exposed": False},
        {
            "name": f"var_结构体_{str(struct_def.get('name') or 'unknown')}",
            "variable_type": "结构体",
            "struct_id": struct_id_int,
            "default_value": struct_value_a,
            "description": f"VarType=25(struct_id={struct_id_int})",
            "is_exposed": False,
        },
        {
            "name": f"var_结构体列表_{str(struct_def.get('name') or 'unknown')}_len2",
            "variable_type": "结构体列表",
            "struct_id": struct_id_int,
            "default_value": [struct_value_b, struct_value_a],
            "description": f"VarType=26(struct_id={struct_id_int})",
            "is_exposed": False,
        },
        {
            "name": "var_字典_字符串到整数_len5",
            "variable_type": "字典",
            "dict_key_type": "字符串",
            "dict_value_type": "整数",
            "default_value": {
                "金币": 0,
                "钻石": 123,
                "提示_短": 1,
                "提示_长一点的键名": 2,
                "计数器": 999,
            },
            "description": "VarType=27",
            "is_exposed": False,
        },
    ]
    return variables


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="生成一个包含全 VarType 节点图变量表(entry['6']) 的测试 .gil。")
    parser.add_argument("--template-gil", required=True, help="模板 .gil（提供节点图段结构与一个 graph entry 用于克隆）")
    parser.add_argument("--base-gil", default=None, help="可选：输出容器 .gil（为空则使用 template_gil）")
    parser.add_argument("--output-gil", required=True, help="输出 .gil（强制写入 ugc_file_tools/out/）")
    parser.add_argument("--graph-id", type=int, default=None, help="目标 graph_id_int（默认使用模板的第一张图）")
    parser.add_argument(
        "--graph-name",
        default="节点图变量_VARIABLE_TYPES_写回测试",
        help="写入到 graph entry['2'] 的名称（强调：只覆盖 VARIABLE_TYPES 允许集合）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    template_gil_path = Path(args.template_gil).resolve()
    base_gil_path = Path(args.base_gil).resolve() if args.base_gil else template_gil_path

    template_raw = _dump_gil_to_raw_json_object(template_gil_path)
    template_payload = _get_payload_root(template_raw)
    template_section = template_payload.get("10")
    if not isinstance(template_section, dict):
        raise ValueError("template_gil 缺少节点图段 payload['10']")

    base_raw = _dump_gil_to_raw_json_object(base_gil_path)
    payload_root = _get_payload_root(base_raw)

    # 若 base 缺少节点图段，则从 template 自举
    section = payload_root.get("10")
    if not isinstance(section, dict):
        section = copy.deepcopy(template_section)
        payload_root["10"] = section

    # 目标 graph_id
    graph_id_int = int(args.graph_id) if isinstance(args.graph_id, int) else _get_first_graph_id_int(template_payload)
    if not isinstance(graph_id_int, int):
        raise ValueError("无法确定 graph_id（请通过 --graph-id 指定）")

    # 构造变量定义
    struct_defs = _extract_struct_defs_from_payload_root(payload_root)
    struct_def = _choose_demo_struct_def(struct_defs)
    variables = _build_all_types_graph_variables(struct_def=struct_def)
    var_defs = [_build_graph_variable_def_item_from_metadata(v, struct_defs=struct_defs) for v in variables]

    # 克隆模板 entry，写入变量表与名称
    template_entry = _find_graph_entry(template_payload, int(graph_id_int))
    new_entry = copy.deepcopy(template_entry)
    new_entry["2"] = [str(args.graph_name)]
    new_entry["6"] = list(var_defs)
    # 强制写入 graph_id（避免 template 与用户指定不一致）
    header = new_entry.get("1")
    header_obj = header[0] if isinstance(header, list) and header and isinstance(header[0], dict) else header
    if not isinstance(header_obj, dict):
        raise ValueError("模板 graph entry 缺少 header(entry['1'])")
    header_obj["5"] = int(graph_id_int)
    new_entry["1"] = [header_obj]

    # 将 base 的节点图段收口为“1 个 wrapper + 1 张图”（避免与 base 里已有图互相影响）
    sec = payload_root.get("10")
    if not isinstance(sec, dict):
        raise ValueError("payload_root 缺少节点图段 '10'")
    template_wrappers = template_section.get("1")
    template_wrappers_list = (
        template_wrappers
        if isinstance(template_wrappers, list)
        else [template_wrappers]
        if isinstance(template_wrappers, dict)
        else []
    )
    if not template_wrappers_list or not isinstance(template_wrappers_list[0], dict):
        raise ValueError("template_gil 的 payload['10']['1'] 缺少 wrapper")
    wrapper0 = copy.deepcopy(template_wrappers_list[0])
    wrapper0["1"] = [new_entry]
    sec["1"] = [wrapper0]
    sec["7"] = 1

    # 封装写回
    container_spec = read_gil_container_spec(base_gil_path)
    payload_bytes = encode_message(payload_root)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)

    out_path = resolve_output_file_path_in_out_dir(Path(args.output_gil))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(output_bytes)

    print("================================================================================")
    print("GraphEntry['6'] 节点图变量全类型测试 .gil 已生成：")
    print(f"- template_gil: {str(template_gil_path)}")
    print(f"- base_gil: {str(base_gil_path)}")
    print(f"- graph_id_int: {graph_id_int}")
    print(f"- graph_name: {args.graph_name}")
    print(f"- variables_count: {len(var_defs)}")
    print(f"- output_gil: {str(out_path)}")
    print("================================================================================")


if __name__ == "__main__":
    main()



