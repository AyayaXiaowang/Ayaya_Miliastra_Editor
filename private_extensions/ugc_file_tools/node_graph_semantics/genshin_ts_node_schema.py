from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .graph_model import _normalize_graph_model_payload, _normalize_nodes_list


@dataclass(frozen=True, slots=True)
class GenshinTsNodeRecord:
    """
    genshin-ts / NodeEditorPack 的节点画像（最小必要字段）：
    - `inputs` / `outputs`：仅描述 **数据端口**（不含流程端口）的类型表达式。
    - `id`：NodeEditorPack 视角下的节点 ID（通常是 generic id；reflectMap 可映射到 concrete id）。
    """

    id: int
    name: str
    inputs: List[str]
    outputs: List[str]


@dataclass(frozen=True, slots=True)
class GenshinTsNodeSchemaIndex:
    report_path: Path
    record_by_node_id_int: Dict[int, GenshinTsNodeRecord]
    concrete_maps: List[List[int]]
    concrete_pins: Dict[str, int]


_CACHED_SCHEMA_INDEX: Optional[GenshinTsNodeSchemaIndex] = None
_CACHED_SCHEMA_LOADED: bool = False


def _default_report_path() -> Path:
    # private_extensions/ugc_file_tools/node_graph_writeback/*.py -> parents[1] == private_extensions/ugc_file_tools
    ugc_tools_root = Path(__file__).resolve().parents[1]
    return (ugc_tools_root / "refs" / "genshin_ts" / "genshin_ts__node_schema.report.json").resolve()


def load_genshin_ts_node_schema_index(*, report_path: Optional[Path] = None) -> Optional[GenshinTsNodeSchemaIndex]:
    """
    读取 `genshin_ts__node_schema.report.json` 并构建索引：
    - key：node_type_id_int（concrete/generic 的数字 ID）
    - value：inputs/outputs 类型表达式

    返回 None：表示 report 不存在（不启用该校验）。
    """
    rp = (Path(report_path).resolve() if report_path is not None else _default_report_path())
    if not rp.is_file():
        return None
    obj = json.loads(rp.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError(f"genshin-ts node schema report 顶层必须是 dict：{str(rp)}")

    records = obj.get("node_pin_records")
    if not isinstance(records, list):
        raise TypeError(f"genshin-ts node schema report 缺少 node_pin_records(list)：{str(rp)}")

    record_by_id: Dict[int, GenshinTsNodeRecord] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        raw_id = rec.get("id")
        if not isinstance(raw_id, int):
            continue
        inputs = rec.get("inputs")
        outputs = rec.get("outputs")
        if not isinstance(inputs, list) or not isinstance(outputs, list):
            continue
        name = str(rec.get("name") or "").strip()
        record = GenshinTsNodeRecord(
            id=int(raw_id),
            name=str(name),
            inputs=[str(x) for x in inputs if str(x or "").strip() != ""],
            outputs=[str(x) for x in outputs if str(x or "").strip() != ""],
        )
        record_by_id[int(record.id)] = record

        # reflectMap: [[concrete_id, reflect], ...]，将 concrete id 同样映射到该 record
        reflect_map = rec.get("reflectMap")
        if isinstance(reflect_map, list):
            for item in reflect_map:
                if isinstance(item, (list, tuple)) and len(item) >= 1 and isinstance(item[0], int):
                    record_by_id[int(item[0])] = record

    if not record_by_id:
        raise ValueError(f"genshin-ts node schema report 解析结果为空：{str(rp)}")

    # concrete_map（可选）：用于计算 indexOfConcrete（泛型/反射端口）
    concrete_maps: List[List[int]] = []
    concrete_pins: Dict[str, int] = {}
    cm = obj.get("concrete_map")
    if isinstance(cm, dict):
        maps_obj = cm.get("maps")
        pins_obj = cm.get("pins")
        if isinstance(maps_obj, list):
            for row in maps_obj:
                if not isinstance(row, list):
                    continue
                ints = [int(v) for v in row if isinstance(v, int)]
                if ints:
                    concrete_maps.append(ints)
        if isinstance(pins_obj, dict):
            for k, v in pins_obj.items():
                key = str(k or "").strip()
                if key == "":
                    continue
                if isinstance(v, int):
                    concrete_pins[key] = int(v)

    return GenshinTsNodeSchemaIndex(
        report_path=rp,
        record_by_node_id_int=record_by_id,
        concrete_maps=concrete_maps,
        concrete_pins=concrete_pins,
    )


def _get_cached_schema_index() -> Optional[GenshinTsNodeSchemaIndex]:
    global _CACHED_SCHEMA_INDEX, _CACHED_SCHEMA_LOADED
    if _CACHED_SCHEMA_LOADED:
        return _CACHED_SCHEMA_INDEX
    _CACHED_SCHEMA_LOADED = True
    _CACHED_SCHEMA_INDEX = load_genshin_ts_node_schema_index()
    return _CACHED_SCHEMA_INDEX


def try_resolve_index_of_concrete_from_genshin_ts(
    *,
    node_type_id_int: int,
    is_input: bool,
    pin_index: int,
    var_type_int: int,
) -> Optional[int]:
    """
    使用 genshin-ts/NodeEditorPack 的 ConcreteMap 解析 indexOfConcrete（若可用）。

    返回 None：表示该节点/端口未在 ConcreteMap.pins 中登记或 report 缺失。
    """
    schema = _get_cached_schema_index()
    if schema is None:
        return None
    if not schema.concrete_maps or not schema.concrete_pins:
        return None
    record = schema.record_by_node_id_int.get(int(node_type_id_int))
    if record is None:
        return None
    generic_id = int(record.id)
    pin_type = 3 if bool(is_input) else 4
    key = f"{int(generic_id)}:{int(pin_type)}:{int(pin_index)}"
    map_index = schema.concrete_pins.get(key)
    if not isinstance(map_index, int):
        return None
    if int(map_index) < 0 or int(map_index) >= len(schema.concrete_maps):
        raise ValueError(
            f"ConcreteMap.pins 指向越界 maps 索引：{key} -> {map_index} (maps_len={len(schema.concrete_maps)})"
        )
    allowed = schema.concrete_maps[int(map_index)]
    # 允许 index=0（不写入 field_110.field_1），由上游 wrapper 按样本口径处理
    if int(var_type_int) in allowed:
        return int(allowed.index(int(var_type_int)))
    return None


def _map_node_record_type_token_to_var_type_int(type_token: str) -> Optional[int]:
    """
    将 NodeEditorPack 的类型表达式 token 映射到 server VarType(int)（仅覆盖常用可判定子集）。

    例：
    - "Int" -> 3
    - "Bol" -> 4
    - "Flt" -> 5
    - "Str" -> 6
    - "Vec" -> 12
    - "Gid" -> 2
    - "Ety" -> 1
    - "Fct" -> 17
    - "Cfg" -> 20
    - "Pfb" -> 21
    - "E<123>" -> 14
    - "L<Int>" -> 8

    无法判定（例如 "R<T>" / "S<...>"）：返回 None（跳过该项类型对齐校验）。
    """
    t = str(type_token or "").strip()
    if t == "":
        return None
    basic: Dict[str, int] = {
        "Int": 3,
        "Bol": 4,
        "Flt": 5,
        "Str": 6,
        "Vec": 12,
        "Gid": 2,
        "Ety": 1,
        "Fct": 17,
        "Cfg": 20,
        "Pfb": 21,
    }
    if t in basic:
        return int(basic[t])
    if t.startswith("E<") and t.endswith(">"):
        # 特例：NodeEditorPack/genshin-ts 会用枚举 token 表达“局部变量引用”端口类型。
        # 在 Graph_Generater/写回侧，该端口类型使用 VarType=16(局部变量) 表达。
        # 目前已观测到 `获取局部变量(Get Local Variable, type_id=18)` 的端口 token 为 E<1016>。
        inner = t[len("E<") : -1].strip()
        if inner.isdigit() and int(inner) == 1016:
            return 16
        return 14
    if t.startswith("L<") and t.endswith(">"):
        inner = t[len("L<") : -1].strip()
        inner_vt = _map_node_record_type_token_to_var_type_int(inner)
        if inner_vt is None:
            return None
        list_map: Dict[int, int] = {
            2: 7,   # GUID -> GUIDList
            3: 8,   # Int -> IntegerList
            4: 9,   # Bool -> BooleanList
            5: 10,  # Float -> FloatList
            6: 11,  # String -> StringList
            1: 13,  # Entity -> EntityList
            12: 15, # Vector -> VectorList
            20: 22, # Config -> ConfigurationList
            21: 23, # Prefab -> PrefabList
            17: 24, # Faction -> FactionList
        }
        return int(list_map.get(int(inner_vt))) if int(inner_vt) in list_map else None
    return None


@dataclass(frozen=True, slots=True)
class GenshinTsNodeSchemaCheckIssue:
    node_title: str
    node_type_id_int: int
    kind: str  # "missing_schema" | "port_count_mismatch" | "port_type_mismatch"
    details: Dict[str, Any]


def check_graph_model_against_genshin_ts_node_schema(
    *,
    graph_model_json_object: Dict[str, Any],
    node_type_id_by_graph_node_id: Dict[str, int],
    node_defs_by_name: Dict[str, Any],
    scope: str,
    strict_missing_schema: bool,
    output_report_name: str = "precheck.genshin_ts_node_schema.report.json",
) -> Tuple[Optional[Path], List[GenshinTsNodeSchemaCheckIssue]]:
    """
    对写回输入的 GraphModel(JSON) 做“真源节点画像”一致性校验。

    校验策略（保守）：
    - 仅对 genshin-ts schema 中“可命中 record”的节点做校验；
    - 对 schema 缺失节点默认 **不阻断**（strict_missing_schema=False），只输出报告；
    - port_count / 可判定的 port_type 不一致：直接视为错误（写回会更容易导入失败或端口错位）。

    返回：(report_path_or_none, issues)
    - report_path_or_none：若 report 不存在则为 None；若存在则总会生成 out/*.report.json
    """
    schema = load_genshin_ts_node_schema_index()
    if schema is None:
        return None, []

    # 延迟导入，避免 prechecks 触发重依赖初始化
    from .graph_generater import _is_flow_port_by_node_def
    from .var_base import _map_server_port_type_to_var_type_id

    gm = _normalize_graph_model_payload(graph_model_json_object)
    nodes = _normalize_nodes_list(gm)
    issues: List[GenshinTsNodeSchemaCheckIssue] = []

    # 动态端口节点：不做“数量/类型强校验”，避免误报（它们的 pins 数量/顺序随 GraphModel 而变）。
    #
    # 说明：
    # - `拼装列表/拼装字典`：GraphModel 通常不包含内部 pin0(len) 等隐藏 pins，按 index 对齐会错位。
    # - `发送信号/监听信号/向服务器发送信号`：参数端口是动态展开的，port_count 固定校验会误报。
    dynamic_titles: set[str] = {"拼装列表", "拼装字典", "发送信号", "监听信号", "向服务器发送信号"}

    for node_payload in nodes:
        title = str(node_payload.get("title") or node_payload.get("name") or "").strip()
        node_id = str(node_payload.get("id") or "").strip()
        if node_id == "":
            continue
        type_id_int = node_type_id_by_graph_node_id.get(node_id)
        if not isinstance(type_id_int, int):
            continue

        record = schema.record_by_node_id_int.get(int(type_id_int))
        if record is None:
            issues.append(
                GenshinTsNodeSchemaCheckIssue(
                    node_title=title,
                    node_type_id_int=int(type_id_int),
                    kind="missing_schema",
                    details={"scope": str(scope), "node_id": str(node_id)},
                )
            )
            continue

        node_def = node_defs_by_name.get(str(title))
        if node_def is None:
            # 这属于更上游的问题（写回本来也会 KeyError）；这里不重复报
            continue

        inputs_value = node_payload.get("inputs")
        outputs_value = node_payload.get("outputs")
        if not isinstance(inputs_value, list) or not isinstance(outputs_value, list):
            continue

        data_inputs = [str(p) for p in inputs_value if not _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=True)]
        data_outputs = [str(p) for p in outputs_value if not _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=False)]

        # 端口数量校验（跳过动态端口节点）
        if title not in dynamic_titles and (len(data_inputs) != len(record.inputs) or len(data_outputs) != len(record.outputs)):
            issues.append(
                GenshinTsNodeSchemaCheckIssue(
                    node_title=title,
                    node_type_id_int=int(type_id_int),
                    kind="port_count_mismatch",
                    details={
                        "record_name": record.name,
                        "data_inputs_count": len(data_inputs),
                        "data_outputs_count": len(data_outputs),
                        "expected_inputs_count": len(record.inputs),
                        "expected_outputs_count": len(record.outputs),
                        "data_inputs": data_inputs,
                        "data_outputs": data_outputs,
                        "expected_inputs": record.inputs,
                        "expected_outputs": record.outputs,
                    },
                )
            )
            continue

        # 动态端口节点：跳过类型校验（index 对齐不稳定）
        if title in dynamic_titles:
            continue

        # 端口类型对齐（仅对可判定 token 做校验）：
        # - 优先使用工具链 enrich 后的 typed JSON（*_port_types）
        # - 缺失时回退 GraphModel 快照字段（effective_*_types），以支持“接地单图/未 enrich”场景
        input_port_types = node_payload.get("input_port_types")
        if not isinstance(input_port_types, dict):
            input_port_types = node_payload.get("effective_input_types")
        output_port_types = node_payload.get("output_port_types")
        if not isinstance(output_port_types, dict):
            output_port_types = node_payload.get("effective_output_types")
        if not isinstance(input_port_types, dict) or not isinstance(output_port_types, dict):
            continue

        # inputs：按 index 对齐（record.inputs 是“数据端口”顺序）
        for idx, port_name in enumerate(data_inputs):
            if idx >= len(record.inputs):
                break
            expected_token = str(record.inputs[idx] or "").strip()
            expected_vt = _map_node_record_type_token_to_var_type_int(expected_token)
            if expected_vt is None:
                continue
            actual_type_text = input_port_types.get(str(port_name))
            if not isinstance(actual_type_text, str):
                continue
            actual_text = actual_type_text.strip()
            if actual_text == "" or actual_text == "流程" or ("泛型" in actual_text):
                continue
            actual_vt = _map_server_port_type_to_var_type_id(actual_text)
            if int(actual_vt) != int(expected_vt):
                issues.append(
                    GenshinTsNodeSchemaCheckIssue(
                        node_title=title,
                        node_type_id_int=int(type_id_int),
                        kind="port_type_mismatch",
                        details={
                            "direction": "input",
                            "index": int(idx),
                            "port_name": str(port_name),
                            "expected_token": expected_token,
                            "expected_var_type_int": int(expected_vt),
                            "actual_port_type_text": actual_text,
                            "actual_var_type_int": int(actual_vt),
                        },
                    )
                )

        # outputs：同理
        for idx, port_name in enumerate(data_outputs):
            if idx >= len(record.outputs):
                break
            expected_token = str(record.outputs[idx] or "").strip()
            expected_vt = _map_node_record_type_token_to_var_type_int(expected_token)
            if expected_vt is None:
                continue
            actual_type_text = output_port_types.get(str(port_name))
            if not isinstance(actual_type_text, str):
                continue
            actual_text = actual_type_text.strip()
            if actual_text == "" or actual_text == "流程" or ("泛型" in actual_text):
                continue
            actual_vt = _map_server_port_type_to_var_type_id(actual_text)
            if int(actual_vt) != int(expected_vt):
                issues.append(
                    GenshinTsNodeSchemaCheckIssue(
                        node_title=title,
                        node_type_id_int=int(type_id_int),
                        kind="port_type_mismatch",
                        details={
                            "direction": "output",
                            "index": int(idx),
                            "port_name": str(port_name),
                            "expected_token": expected_token,
                            "expected_var_type_int": int(expected_vt),
                            "actual_port_type_text": actual_text,
                            "actual_var_type_int": int(actual_vt),
                        },
                    )
                )

    # 输出报告（即使 issues 为空也输出，便于追溯“使用了哪个 report”）
    from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

    report_name = str(output_report_name or "").strip() or "precheck.genshin_ts_node_schema.report.json"
    out_path = resolve_output_file_path_in_out_dir(Path(report_name))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "source_report": str(schema.report_path),
                "scope": str(scope),
                "strict_missing_schema": bool(strict_missing_schema),
                "issues": [
                    {
                        "node_title": i.node_title,
                        "node_type_id_int": int(i.node_type_id_int),
                        "kind": i.kind,
                        "details": i.details,
                    }
                    for i in issues
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return out_path, issues

