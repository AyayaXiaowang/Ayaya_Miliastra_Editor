from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional


@dataclass(frozen=True, slots=True)
class StructTypeIdRegistry:
    """
    结构体字段类型（param_type）到 `.gil` 内部 type_id 的映射表（集中维护）。

    说明：
    - `param_type` 来自 Graph_Generater 的代码级结构体定义（STRUCT_PAYLOAD.fields[*].param_type），目前以中文命名为主。
    - `type_id` 是 `.gil` 结构体字段 entry 中的整数编码（常见落在 field_502.int）。
    - 该映射表用于“从代码级 STRUCT_PAYLOAD 克隆模板字段 entry”时，决定选择哪类字段原型。

    注意：
    - `.gil` 的 type_id 体系属于 ugc/真源口径，不应散落在多个脚本里硬编码。
    - 若某个 param_type 尚未明确对应 type_id，应返回 None 并在调用侧 fail-fast 或走模板推断/兜底构造。
    """

    param_type_to_type_id: Mapping[str, int]

    def resolve_type_id(self, param_type: str) -> int | None:
        text = str(param_type or "").strip()
        if not text:
            return None
        value = self.param_type_to_type_id.get(text)
        return int(value) if isinstance(value, int) else None


# 单一真源：结构体字段 param_type → `.gil` type_id
#
# 来源（交叉验证）：
# - `private_extensions/third_party/genshin-ts/.../protobuf/gia.proto` 中的 `enum VarType`
#   给出了 server 侧 VarType 的完整枚举值；目前结构体字段的 `field_502.int` 与该枚举口径一致。
# - 结合 Graph_Generater 的代码级结构体定义（STRUCT_PAYLOAD.fields[*].param_type），在此处收敛为中文键。
#
# 注意：
# - 该表用于“从模板结构体中按 type_id 选择字段原型”，因此必须稳定且可复用。
# - 若发现真源 `.gil` 在结构体字段上采用不同口径（例如某些版本存在额外类型），应以样本为准扩展本表。
STRUCT_PARAM_TYPE_TO_TYPE_ID: Dict[str, int] = {
    # 标量（VarType）
    "实体": 1,
    "GUID": 2,
    "整数": 3,
    "布尔值": 4,
    "浮点数": 5,
    "字符串": 6,
    "三维向量": 12,
    "阵营": 17,
    "配置ID": 20,
    "元件ID": 21,
    "结构体": 25,
    "字典": 27,
    # 目前 Graph_Generater 的结构体定义中未直接暴露该类型名，但保留映射便于扩展/对齐
    "变量快照": 28,

    # 列表（VarType）
    "GUID列表": 7,
    "整数列表": 8,
    "布尔值列表": 9,
    "浮点数列表": 10,
    "字符串列表": 11,
    "实体列表": 13,
    "三维向量列表": 15,
    "阵营列表": 24,
    "配置ID列表": 22,
    "元件ID列表": 23,
    "结构体列表": 26,
}


DEFAULT_STRUCT_TYPE_ID_REGISTRY = StructTypeIdRegistry(param_type_to_type_id=STRUCT_PARAM_TYPE_TO_TYPE_ID)


def validate_struct_type_id_registry_against_genshin_ts_or_raise(report_path: Path | None = None) -> None:
    """
    工程化护栏：用 genshin-ts 导出的 VarType 真源表校验本地映射表是否漂移。

    - 若报告文件不存在：不报错（允许在未生成报告的环境运行）。
    - 若存在：对 `STRUCT_PARAM_TYPE_TO_TYPE_ID` 中的 key 做逐项一致性校验；不一致直接抛错。
    """
    default_path = (
        Path(__file__).resolve().parent / "refs" / "genshin_ts" / "genshin_ts__struct_field_type_ids.report.json"
    )
    rp = Path(report_path).resolve() if report_path is not None else default_path.resolve()
    if not rp.is_file():
        return
    obj = json.loads(rp.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError(f"VarType report 顶层必须是 dict：{str(rp)}")
    mapping = obj.get("mapping_param_type_to_type_id")
    if not isinstance(mapping, dict):
        raise TypeError(f"VarType report 缺少 mapping_param_type_to_type_id(dict)：{str(rp)}")

    mismatches: Dict[str, Dict[str, int]] = {}
    for k, v in STRUCT_PARAM_TYPE_TO_TYPE_ID.items():
        expected = int(v)
        actual_raw = mapping.get(str(k))
        if not isinstance(actual_raw, int):
            continue
        actual = int(actual_raw)
        if actual != expected:
            mismatches[str(k)] = {"local": int(expected), "genshin_ts": int(actual)}
    if mismatches:
        raise ValueError(f"struct_type_id_registry 与 genshin-ts VarType 不一致：{mismatches} (report={str(rp)})")


def resolve_struct_field_type_id(param_type: str) -> int:
    type_id = DEFAULT_STRUCT_TYPE_ID_REGISTRY.resolve_type_id(param_type)
    if type_id is None:
        raise ValueError(f"未知/未登记的结构体字段类型 param_type：{str(param_type or '').strip()!r}")
    return int(type_id)


def try_resolve_struct_field_type_id(param_type: str) -> Optional[int]:
    return DEFAULT_STRUCT_TYPE_ID_REGISTRY.resolve_type_id(param_type)

