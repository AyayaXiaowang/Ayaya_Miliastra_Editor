from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_numeric_message
from ugc_file_tools.gil_dump_codec.gil_container import (
    build_gil_file_bytes_from_payload,
    read_gil_container_spec,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message


_CANONICAL_SECTION35_DEFAULT_GROUPS: list[Dict[str, Any]] = [
    # 说明：这是已观测的“校验成功”样本中的最小默认分组集合（共 16 项）。
    # 该列表用于在空壳/极简 base 缺失 section35 默认分组时补齐口径，避免引入额外噪音分组导致官方校验更严格分支触发。
    {"1": "默认成就", "4": 1, "501": "<binary_data> 0A"},
    {"1": "默认极致成就", "4": 1, "501": "<binary_data> 0A"},
    {"1": "默认排行榜", "4": 1, "501": "<binary_data> 0C"},
    {"1": "你好！", "4": 1, "501": "<binary_data> 0F"},
    {"1": "全局", "4": 1, "501": "<binary_data> 0F"},
    {"1": "初始物件阵营", "4": 1, "501": "<binary_data> 11"},
    {"1": "初始玩家阵营", "4": 1, "501": "<binary_data> 11"},
    {"1": "初始造物阵营", "4": 1, "501": "<binary_data> 11"},
    {"1": "A", "501": "<binary_data> 01"},
    {"1": "B", "501": "<binary_data> 01"},
    {"1": "m", "501": "<binary_data> 01"},
    {"1": "n", "501": "<binary_data> 01"},
    {"1": "o", "501": "<binary_data> 01"},
    {"1": "v_实体", "501": "<binary_data> 01"},
    {"1": "x", "501": "<binary_data> 01"},
    {"1": "y", "501": "<binary_data> 01"},
]

# section6（4/6/1）在“校验成功”样本中的关键缺口：item[17]['3']['5'] 必须存在。
# 该字段在部分空存档 base 中缺失，会导致导出产物在官方侧更严格校验下失败（已由多份成功/失败对照确认）。
_CANONICAL_SECTION6_ITEM17_SUB3_FIELD5: Dict[str, Any] = {
    "1": 800,
    "2": 1073741825,
}


@dataclass(frozen=True, slots=True)
class GilInfrastructureGaps:
    """
    base `.gil` 缺失的“基础设施段”摘要（用于决定是否需要 bootstrap）。
    """

    # 注意：这里的路径以 payload_root（numeric_message）的顶层字段为准；
    # dump-json/report 中常见的 `4/11`、`4/35` 里的 “4” 是 dump 包装层，不属于 payload_root 字段。
    missing_section11: bool
    missing_section11_faction_entries: bool
    missing_section11_faction_field13: bool

    missing_section35: bool
    missing_section35_default_groups: bool

    missing_section6: bool
    missing_section22: bool
    missing_section2: bool

    @property
    def needs_bootstrap(self) -> bool:
        return bool(
            self.missing_section11
            or self.missing_section11_faction_entries
            or self.missing_section11_faction_field13
            or self.missing_section35
            or self.missing_section35_default_groups
            or self.missing_section6
            or self.missing_section22
            or self.missing_section2
        )


@dataclass(frozen=True, slots=True)
class GilInfrastructureBootstrapReport:
    changed: bool
    gaps: GilInfrastructureGaps

    bootstrap_gil_file: str
    infra_seed_gil_file: str

    patched_root4_11_copied_from_bootstrap: bool
    patched_root4_11_faction_field13_count: int

    patched_root4_35_copied_from_bootstrap: bool
    patched_root4_35_default_groups_copied: bool
    patched_root4_35_default_groups_len: int | None

    patched_root4_6_copied_from_bootstrap: bool
    patched_root4_22_copied_from_bootstrap: bool
    patched_root4_2_copied_from_bootstrap: bool


def _as_dict(value: Any, *, path: str) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise TypeError(f"{path} expected dict, got {type(value).__name__}")


def _as_dict_allow_binary_message(value: Any, *, path: str, max_depth: int) -> Dict[str, Any]:
    """
    兼容 dump 解码深度/策略差异：当某些段被表示为 `<binary_data> ...` 时，
    先按 message 解码回 numeric_message dict，再返回可写视图。
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.startswith("<binary_data>"):
        from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import binary_data_text_to_numeric_message

        decoded = binary_data_text_to_numeric_message(str(value), max_depth=int(max_depth))
        if isinstance(decoded, Mapping):
            return dict(decoded)
    raise TypeError(f"{path} expected dict or <binary_data>, got {type(value).__name__}")


def _as_list_of_dicts(value: Any, *, path: str) -> list[Dict[str, Any]]:
    if isinstance(value, list):
        out: list[Dict[str, Any]] = []
        for i, item in enumerate(value):
            if not isinstance(item, dict):
                raise TypeError(f"{path}[{i}] expected dict, got {type(item).__name__}")
            out.append(item)
        return out
    if isinstance(value, dict):
        return [value]
    raise TypeError(f"{path} expected list[dict] or dict, got {type(value).__name__}")


def _try_as_list_of_dicts(value: Any) -> list[Dict[str, Any]] | None:
    """
    宽松版 list[dict] 归一化：
    - list[dict]：原样返回（若存在非 dict 元素则返回 None）
    - dict：视为单元素 repeated，返回 [dict]
    - None/其他：返回 None
    """
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        out: list[Dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                return None
            out.append(item)
        return out
    return None


def detect_gil_infrastructure_gaps_in_payload_root(*, payload_root: Mapping[str, Any]) -> GilInfrastructureGaps:
    sec11 = payload_root.get("11")
    missing_section11 = not isinstance(sec11, Mapping)

    missing_section11_faction_entries = True
    missing_section11_faction_field13 = True
    if isinstance(sec11, Mapping):
        sec11_2 = sec11.get("2")
        if isinstance(sec11_2, Mapping):
            entries = _try_as_list_of_dicts(sec11_2.get("1"))
            if entries is not None:
                missing_section11_faction_entries = False
                # 若存在任意 entry 缺失 key=13，则视为缺失（样本差异：校验成功版均带该字段）
                missing_section11_faction_field13 = any(("13" not in e) for e in entries)

    sec35 = payload_root.get("35")
    missing_section35 = not isinstance(sec35, Mapping)

    missing_section35_default_groups = True
    if isinstance(sec35, Mapping):
        g1 = sec35.get("1")
        if isinstance(g1, Mapping):
            g11 = g1.get("1")
            if isinstance(g11, Mapping):
                groups = _try_as_list_of_dicts(g11.get("1"))
                if groups is not None:
                    missing_section35_default_groups = False

    # section6（dump-json path: 4/6/1）：
    # 校验成功样本中该列表固定至少 32 项，且 index=17 的 item['3'] 必须包含 key=5（见 diff 证据）。
    sec6 = payload_root.get("6")
    missing_section6 = True
    if isinstance(sec6, Mapping):
        items = _try_as_list_of_dicts(sec6.get("1"))
        if items is not None and len(items) >= 32:
            item17 = items[17] if len(items) > 17 else None
            if isinstance(item17, dict):
                sub3 = item17.get("3")
                missing_section6 = not (isinstance(sub3, Mapping) and ("5" in sub3))

    # section22（dump-json path: 4/22）：
    # 校验成功样本稳定为 message(dict) 形态，且包含 key=1/2（见多份样本一致）。
    sec22 = payload_root.get("22")
    missing_section22 = True
    if isinstance(sec22, Mapping):
        missing_section22 = not (("1" in sec22) and ("2" in sec22))

    sec2 = payload_root.get("2")
    missing_section2 = not (isinstance(sec2, str) and str(sec2).strip() != "")

    return GilInfrastructureGaps(
        missing_section11=bool(missing_section11),
        missing_section11_faction_entries=bool(missing_section11_faction_entries),
        missing_section11_faction_field13=bool(missing_section11_faction_field13),
        missing_section35=bool(missing_section35),
        missing_section35_default_groups=bool(missing_section35_default_groups),
        missing_section6=bool(missing_section6),
        missing_section22=bool(missing_section22),
        missing_section2=bool(missing_section2),
    )


def apply_gil_infrastructure_bootstrap_inplace(
    *,
    base_payload_root: Dict[str, Any],
    bootstrap_payload_root: Mapping[str, Any],
    infra_seed_payload_root: Mapping[str, Any],
) -> GilInfrastructureBootstrapReport:
    gaps = detect_gil_infrastructure_gaps_in_payload_root(payload_root=base_payload_root)

    # 不需要 bootstrap：直接返回空报告（由上层决定是否写盘）
    if not gaps.needs_bootstrap:
        return GilInfrastructureBootstrapReport(
            changed=False,
            gaps=gaps,
            bootstrap_gil_file="",
            infra_seed_gil_file="",
            patched_root4_11_copied_from_bootstrap=False,
            patched_root4_11_faction_field13_count=0,
            patched_root4_35_copied_from_bootstrap=False,
            patched_root4_35_default_groups_copied=False,
            patched_root4_35_default_groups_len=None,
            patched_root4_6_copied_from_bootstrap=False,
            patched_root4_22_copied_from_bootstrap=False,
            patched_root4_2_copied_from_bootstrap=False,
        )

    changed = False

    # 作为 bootstrap 的样本必须包含目标段（否则无法补齐）
    bootstrap_sec11 = _as_dict(bootstrap_payload_root.get("11"), path="bootstrap_payload_root['11']")
    bootstrap_sec35 = _as_dict(bootstrap_payload_root.get("35"), path="bootstrap_payload_root['35']")
    bootstrap_sec2_value = bootstrap_payload_root.get("2")
    if not (isinstance(bootstrap_sec2_value, str) and str(bootstrap_sec2_value).strip() != ""):
        raise TypeError("bootstrap_payload_root['2'] expected non-empty str")

    # 注意：`ugc_file_tools/save/test.gil`（样本库） 的 section6/section22 口径与“校验成功”样本不一致：
    # - 4/6/1 长度可能 >32（包含业务噪音 tabs）
    # - 4/22 可能为纯文本（property list）而非 message(dict)
    #
    # 这里改为从“内置空存档 base”（带基础设施的空存档）提取 canonical section6/section22，
    # 仅用于补齐缺失字段/缺口（不会覆盖 base 的业务段）。
    seed_sec6 = _as_dict(infra_seed_payload_root.get("6"), path="infra_seed_payload_root['6']")
    seed_sec22 = _as_dict(infra_seed_payload_root.get("22"), path="infra_seed_payload_root['22']")
    seed_sec6_items = _try_as_list_of_dicts(seed_sec6.get("1"))
    if seed_sec6_items is None or len(seed_sec6_items) < 32:
        raise ValueError("infra_seed_payload_root['6']['1'] is not a valid list[dict] (expected len>=32)")

    # section11: faction entries（用于补齐 key=13）
    bootstrap_sec11_2 = _as_dict(bootstrap_sec11.get("2"), path="bootstrap_payload_root['11']['2']")
    bootstrap_faction_entries = _as_list_of_dicts(
        bootstrap_sec11_2.get("1"),
        path="bootstrap_payload_root['11']['2']['1']",
    )

    # section35: default groups list
    bootstrap_35_g1 = _as_dict(bootstrap_sec35.get("1"), path="bootstrap_payload_root['35']['1']")
    bootstrap_35_g11 = _as_dict(bootstrap_35_g1.get("1"), path="bootstrap_payload_root['35']['1']['1']")
    _bootstrap_default_groups = _as_list_of_dicts(
        bootstrap_35_g11.get("1"),
        path="bootstrap_payload_root['35']['1']['1']['1']",
    )
    # 重要：bootstrap 文件里的默认分组可能包含大量业务噪音（例如道具/关卡变量分组等），
    # 对“空存档导出”而言我们只补齐“最小可用口径”，避免把 bootstrap 的业务分组一并带入。
    canonical_default_groups = list(_CANONICAL_SECTION35_DEFAULT_GROUPS)

    # ===== section11（dump-json path: 4/11）：初始阵营互斥表 =====
    patched_root4_11_copied_from_bootstrap = False
    patched_root4_11_faction_field13_count = 0

    base_sec11 = base_payload_root.get("11")
    if not isinstance(base_sec11, dict):
        base_payload_root["11"] = copy.deepcopy(bootstrap_sec11)
        changed = True
        patched_root4_11_copied_from_bootstrap = True
    else:
        base_sec11_2 = base_sec11.get("2")
        if not isinstance(base_sec11_2, dict):
            base_sec11["2"] = copy.deepcopy(bootstrap_sec11_2)
            base_sec11_2 = base_sec11["2"]
            changed = True

        base_entries_value = base_sec11_2.get("1")
        base_entries = _try_as_list_of_dicts(base_entries_value)
        if base_entries is None:
            base_sec11_2["1"] = copy.deepcopy(list(bootstrap_faction_entries))
            changed = True
        else:
            bootstrap_by_key3: dict[str, Dict[str, Any]] = {}
            for e in bootstrap_faction_entries:
                k = str(e.get("3") or "").strip()
                if k != "" and k not in bootstrap_by_key3:
                    bootstrap_by_key3[k] = e

            for base_e in base_entries:
                k = str(base_e.get("3") or "").strip()
                if k == "":
                    continue
                boot_e = bootstrap_by_key3.get(k)
                if not isinstance(boot_e, dict):
                    continue
                if "13" in base_e:
                    continue
                if "13" not in boot_e:
                    continue
                base_e["13"] = copy.deepcopy(boot_e["13"])
                patched_root4_11_faction_field13_count += 1
                changed = True

            # fallback：部分 base `.gil` 的 section11 entries 的 key=3（匹配键）可能漂移/缺失，
            # 导致无法按 key=3 从 bootstrap 样本补齐 key=13。
            #
            # 已观测：缺失 key=13 会导致官方侧更严格校验失败；因此这里提供保守兜底：
            # - 优先：当 entries 数量与 bootstrap 样本一致时，按 index 对齐补齐 key=13（避免改动其它字段）。
            # - 最后：若仍存在缺失项，则使用 bootstrap 中第一个可用的 key=13 值做统一补齐（尽量只补缺失，不覆盖其它字段）。
            missing_indices = [i for i, e in enumerate(base_entries) if isinstance(e, dict) and ("13" not in e)]
            if missing_indices:
                if len(base_entries) == len(bootstrap_faction_entries):
                    for i in missing_indices:
                        base_e2 = base_entries[i]
                        boot_e2 = bootstrap_faction_entries[i]
                        if not isinstance(base_e2, dict):
                            continue
                        if "13" in base_e2:
                            continue
                        if isinstance(boot_e2, dict) and ("13" in boot_e2):
                            base_e2["13"] = copy.deepcopy(boot_e2["13"])
                            patched_root4_11_faction_field13_count += 1
                            changed = True

                # 重新检查是否仍有缺口；若有则用 default_13 统一补齐
                if any((isinstance(e, dict) and ("13" not in e)) for e in base_entries):
                    default_13: Any | None = None
                    for e in bootstrap_faction_entries:
                        if isinstance(e, dict) and ("13" in e):
                            default_13 = e.get("13")
                            break
                    if default_13 is not None:
                        for base_e3 in base_entries:
                            if not isinstance(base_e3, dict):
                                continue
                            if "13" in base_e3:
                                continue
                            base_e3["13"] = copy.deepcopy(default_13)
                            patched_root4_11_faction_field13_count += 1
                            changed = True

    # ===== section35（dump-json path: 4/35）：默认分组列表 =====
    patched_root4_35_copied_from_bootstrap = False
    patched_root4_35_default_groups_copied = False
    patched_root4_35_default_groups_len: int | None = None

    base_sec35 = base_payload_root.get("35")
    if not isinstance(base_sec35, dict):
        base_payload_root["35"] = copy.deepcopy(bootstrap_sec35)
        changed = True
        patched_root4_35_copied_from_bootstrap = True
    else:
        base_g1 = base_sec35.get("1")
        if not isinstance(base_g1, dict):
            base_sec35["1"] = {}
            base_g1 = base_sec35["1"]
            changed = True

        base_g11 = base_g1.get("1")
        if not isinstance(base_g11, dict):
            base_g1["1"] = {}
            base_g11 = base_g1["1"]
            changed = True

        base_groups = _try_as_list_of_dicts(base_g11.get("1"))
        if base_groups is None:
            base_g11["1"] = copy.deepcopy(list(canonical_default_groups))
            patched_root4_35_default_groups_copied = True
            patched_root4_35_default_groups_len = int(len(canonical_default_groups))
            changed = True

    # ===== section6（dump-json path: 4/6）：基础设施段（列表）=====
    patched_root4_6_copied_from_bootstrap = False
    base_sec6 = base_payload_root.get("6")
    if not isinstance(base_sec6, dict):
        base_payload_root["6"] = copy.deepcopy(seed_sec6)
        changed = True
        patched_root4_6_copied_from_bootstrap = True
    else:
        base_list_value = base_sec6.get("1")
        base_items: list[Dict[str, Any]] | None = None
        if isinstance(base_list_value, list):
            if any(not isinstance(x, dict) for x in list(base_list_value)):
                raise TypeError("payload_root['6']['1'] expected list[dict]")
            base_items = base_list_value
        elif isinstance(base_list_value, dict):
            base_items = [base_list_value]
            base_sec6["1"] = base_items
            changed = True
        elif base_list_value is None:
            base_sec6["1"] = copy.deepcopy(list(seed_sec6_items))
            changed = True
            patched_root4_6_copied_from_bootstrap = True
            base_items = base_sec6["1"]
        else:
            raise TypeError(f"payload_root['6']['1'] expected list/dict/None, got {type(base_list_value).__name__}")

        # 补齐长度（对齐校验成功样本：至少 32 项）
        if base_items is not None and len(base_items) < len(seed_sec6_items):
            for item in list(seed_sec6_items[len(base_items) :]):
                base_items.append(copy.deepcopy(item))
            changed = True
            patched_root4_6_copied_from_bootstrap = True

        # 补齐 item17['3']['5']（对齐校验成功样本）
        if base_items is not None and len(base_items) > 17 and len(seed_sec6_items) > 17:
            base_item17 = base_items[17]
            seed_item17 = seed_sec6_items[17]
            if isinstance(base_item17, dict) and isinstance(seed_item17, dict):
                base_sub3 = base_item17.get("3")
                seed_sub3 = seed_item17.get("3")
                if not isinstance(base_sub3, dict):
                    base_item17["3"] = {}
                    base_sub3 = base_item17["3"]
                    changed = True
                if "5" not in base_sub3:
                    if isinstance(seed_sub3, dict) and ("5" in seed_sub3):
                        base_sub3["5"] = copy.deepcopy(seed_sub3["5"])
                    else:
                        base_sub3["5"] = copy.deepcopy(_CANONICAL_SECTION6_ITEM17_SUB3_FIELD5)
                    changed = True
                    patched_root4_6_copied_from_bootstrap = True

    # ===== section22（dump-json path: 4/22）：基础设施段（dict）=====
    patched_root4_22_copied_from_bootstrap = False
    base_sec22 = base_payload_root.get("22")
    if not isinstance(base_sec22, dict) or ("1" not in base_sec22) or ("2" not in base_sec22):
        base_payload_root["22"] = copy.deepcopy(seed_sec22)
        changed = True
        patched_root4_22_copied_from_bootstrap = True

    # ===== section2（dump-json path: 4/2）：存档显示名/标识（str）=====
    patched_root4_2_copied_from_bootstrap = False
    base_sec2 = base_payload_root.get("2")
    if not (isinstance(base_sec2, str) and str(base_sec2).strip() != ""):
        base_payload_root["2"] = str(bootstrap_sec2_value)
        changed = True
        patched_root4_2_copied_from_bootstrap = True

    return GilInfrastructureBootstrapReport(
        changed=bool(changed),
        gaps=gaps,
        bootstrap_gil_file="",
        infra_seed_gil_file="",
        patched_root4_11_copied_from_bootstrap=bool(patched_root4_11_copied_from_bootstrap),
        patched_root4_11_faction_field13_count=int(patched_root4_11_faction_field13_count),
        patched_root4_35_copied_from_bootstrap=bool(patched_root4_35_copied_from_bootstrap),
        patched_root4_35_default_groups_copied=bool(patched_root4_35_default_groups_copied),
        patched_root4_35_default_groups_len=patched_root4_35_default_groups_len,
        patched_root4_6_copied_from_bootstrap=bool(patched_root4_6_copied_from_bootstrap),
        patched_root4_22_copied_from_bootstrap=bool(patched_root4_22_copied_from_bootstrap),
        patched_root4_2_copied_from_bootstrap=bool(patched_root4_2_copied_from_bootstrap),
    )


def bootstrap_gil_infrastructure_sections(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    bootstrap_gil_file_path: Path,
) -> GilInfrastructureBootstrapReport:
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    bootstrap_path = Path(bootstrap_gil_file_path).resolve()
    if not bootstrap_path.is_file():
        raise FileNotFoundError(str(bootstrap_path))

    output_path = Path(output_gil_file_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base_payload_root = load_gil_payload_as_numeric_message(input_path, max_depth=64, prefer_raw_hex_for_utf8=True)
    bootstrap_payload_root = load_gil_payload_as_numeric_message(bootstrap_path, max_depth=64, prefer_raw_hex_for_utf8=True)
    # infra seed（内置空存档 base）：用于补齐 section6/section22 的 canonical 口径
    from ugc_file_tools.gil.builtin_empty_base import get_builtin_empty_base_gil_path

    infra_seed_path = get_builtin_empty_base_gil_path()
    infra_seed_payload_root = load_gil_payload_as_numeric_message(infra_seed_path, max_depth=64, prefer_raw_hex_for_utf8=True)

    report = apply_gil_infrastructure_bootstrap_inplace(
        base_payload_root=base_payload_root,
        bootstrap_payload_root=bootstrap_payload_root,
        infra_seed_payload_root=infra_seed_payload_root,
    )
    if not bool(report.changed):
        # 不写盘，直接返回（上层可选择跳过 bootstrap 步骤）
        return GilInfrastructureBootstrapReport(
            changed=False,
            gaps=report.gaps,
            bootstrap_gil_file=str(bootstrap_path),
            infra_seed_gil_file=str(infra_seed_path),
            patched_root4_11_copied_from_bootstrap=False,
            patched_root4_11_faction_field13_count=0,
            patched_root4_35_copied_from_bootstrap=False,
            patched_root4_35_default_groups_copied=False,
            patched_root4_35_default_groups_len=None,
            patched_root4_6_copied_from_bootstrap=False,
            patched_root4_22_copied_from_bootstrap=False,
            patched_root4_2_copied_from_bootstrap=False,
        )

    container_spec = read_gil_container_spec(input_path)
    output_path.write_bytes(
        build_gil_file_bytes_from_payload(
            payload_bytes=encode_message(base_payload_root),
            container_spec=container_spec,
        )
    )

    return GilInfrastructureBootstrapReport(
        changed=True,
        gaps=report.gaps,
        bootstrap_gil_file=str(bootstrap_path),
        infra_seed_gil_file=str(infra_seed_path),
        patched_root4_11_copied_from_bootstrap=bool(report.patched_root4_11_copied_from_bootstrap),
        patched_root4_11_faction_field13_count=int(report.patched_root4_11_faction_field13_count),
        patched_root4_35_copied_from_bootstrap=bool(report.patched_root4_35_copied_from_bootstrap),
        patched_root4_35_default_groups_copied=bool(report.patched_root4_35_default_groups_copied),
        patched_root4_35_default_groups_len=report.patched_root4_35_default_groups_len,
        patched_root4_6_copied_from_bootstrap=bool(report.patched_root4_6_copied_from_bootstrap),
        patched_root4_22_copied_from_bootstrap=bool(report.patched_root4_22_copied_from_bootstrap),
        patched_root4_2_copied_from_bootstrap=bool(report.patched_root4_2_copied_from_bootstrap),
    )


__all__ = [
    "GilInfrastructureBootstrapReport",
    "GilInfrastructureGaps",
    "apply_gil_infrastructure_bootstrap_inplace",
    "bootstrap_gil_infrastructure_sections",
    "detect_gil_infrastructure_gaps_in_payload_root",
]

