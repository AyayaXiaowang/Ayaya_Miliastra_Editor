from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from .apply import (
    collect_player_template_custom_variable_targets_from_payload_root,
    extract_instance_entry_name_from_root4_5_1_entry,
    ensure_config_id_custom_variable_in_asset_entry,
    ensure_float_custom_variable_in_asset_entry,
    ensure_int_custom_variable_in_asset_entry,
    find_root4_5_1_entry_by_name,
)
from .coerce import coerce_default_float, coerce_default_int, is_blank_or_dot_text
from .constants import DEFAULT_VARIABLE_GROUP_NAME
from .refs import require_scalar_variable_name
from .web_ui_constants import (
    DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_DEFAULT,
    DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_VARIABLE_FULL_NAME,
    DEFAULT_PROGRESSBAR_INT_DEFAULTS,
    DEFAULT_SHARED_PROGRESSBAR_VARIABLE_NAMES,
)

__all__ = [
    "normalize_progressbar_binding_text",
    "ensure_progressbar_referenced_custom_variables",
    "ensure_item_display_referenced_custom_variables",
]


def normalize_progressbar_binding_text(
    *,
    role: str,
    text: str,
) -> str:
    """
    进度条绑定文本规范化：
    - 空 / "."：补齐为默认共享变量（关卡.<变量名>）
    - 其它：原样保留（可能是 组名.变量名 / lv.xxx / {1:lv.xxx} / 数字常量）
    """
    raw = str(text or "").strip()

    def _is_number_like_for_workbench(v: str) -> bool:
        # Workbench/HTML 导出可能会把“未绑定变量”的 current/min/max 写成 "0" 这类占位值。
        # 这里仅用作“是否为纯数字/浮点文本”的快速判定。
        if v == "":
            return False
        s = v.strip()
        if s.startswith(("+", "-")):
            s = s[1:]
        if s == "":
            return False
        # 允许 0 / 100 / 0.0 / 100.5
        if s.count(".") > 1:
            return False
        return all(ch.isdigit() or ch == "." for ch in s) and any(ch.isdigit() for ch in s)

    # 对齐项目约定：current 应该是变量引用；当 Workbench 给出数字占位（常见 "0"）时，
    # 视为“未绑定”，走默认共享变量自动补齐逻辑。
    if str(role) == "current" and _is_number_like_for_workbench(raw):
        raw = "."

    if not is_blank_or_dot_text(raw):
        return raw
    var_name = DEFAULT_SHARED_PROGRESSBAR_VARIABLE_NAMES.get(str(role))
    if not var_name:
        raise ValueError(f"unknown progressbar binding role: {role!r}")
    return f"{DEFAULT_VARIABLE_GROUP_NAME}.{var_name}"


def ensure_progressbar_referenced_custom_variables(
    raw_dump_object: Dict[str, Any],
    *,
    progressbar_variable_roles: Dict[Tuple[str, str], Set[str]],
    variable_defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    将进度条引用到的变量“自动创建”为实体自定义变量：
    - 关卡.<var> -> 写入 关卡实体（root4/5/1 中 name=关卡实体 的条目）
    - 玩家自身.<var> -> 写入 玩家实体（若存在）与 玩家模板(战斗预设)条目（若存在）；否则回退到 默认模版(角色编辑)
    """
    if not progressbar_variable_roles:
        return {"created_total": 0, "existed_total": 0, "targets": {}, "variables": []}

    root4 = raw_dump_object.get("4")
    if not isinstance(root4, dict):
        raise ValueError("DLL dump JSON 缺少根字段 '4'（期望为 dict）。")
    section5 = root4.get("5")
    if not isinstance(section5, dict):
        raise ValueError("DLL dump JSON 缺少字段 '4/5'（期望为 dict）。")
    entry_list = section5.get("1")
    if not isinstance(entry_list, list):
        raise ValueError("DLL dump JSON 缺少字段 '4/5/1'（期望为 list）。")

    level_entry = find_root4_5_1_entry_by_name(entry_list, "关卡实体")
    if level_entry is None:
        raise RuntimeError("未在 root4/5/1 中找到 name=关卡实体 的条目，无法写入关卡变量。")

    player_entity_entry = find_root4_5_1_entry_by_name(entry_list, "玩家实体")
    role_editor_entry = find_root4_5_1_entry_by_name(entry_list, "默认模版(角色编辑)")
    player_template_targets = collect_player_template_custom_variable_targets_from_payload_root(root4)

    created_total = 0
    existed_total = 0
    variables_report: List[Dict[str, Any]] = []

    def _iter_target_entries(group_name: str) -> list[tuple[Dict[str, Any], str, str]]:
        g = str(group_name or "").strip()
        if g == "关卡":
            return [(level_entry, "7", "关卡实体")]
        if g == "玩家自身":
            out: list[tuple[Dict[str, Any], str, str]] = []
            if player_entity_entry is not None:
                out.append((player_entity_entry, "7", "玩家实体"))
            for t in list(player_template_targets or []):
                wrappers = t.get("root5_wrappers")
                if isinstance(wrappers, list):
                    for w in wrappers:
                        if isinstance(w, dict):
                            name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                            out.append((w, "7", f"玩家模板:{name}"))
                e4 = t.get("root4_entry")
                if isinstance(e4, dict):
                    names = t.get("template_names")
                    label_name = ""
                    if isinstance(names, list) and names:
                        label_name = str(names[0])
                    label = f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)"
                    out.append((e4, "8", label))
            if out:
                return out
            if role_editor_entry is not None:
                return [(role_editor_entry, "7", "默认模版(角色编辑)")]
            raise RuntimeError(
                "进度条引用了 玩家自身.<变量>，但存档中未找到 玩家实体 / 玩家模板(wrapper) / 默认模版(角色编辑) 条目。"
            )
        raise ValueError(f"未知变量组名：{g!r}（仅支持：关卡 / 玩家自身）")

    def _build_player_targets_labels_no_raise() -> list[str]:
        labels: list[str] = []
        if player_entity_entry is not None:
            labels.append("玩家实体")
        for t in list(player_template_targets or []):
            wrappers = t.get("root5_wrappers")
            if isinstance(wrappers, list):
                for w in wrappers:
                    if not isinstance(w, dict):
                        continue
                    name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                    labels.append(f"玩家模板:{name}")
            e4 = t.get("root4_entry")
            if isinstance(e4, dict):
                names = t.get("template_names")
                label_name = ""
                if isinstance(names, list) and names:
                    label_name = str(names[0])
                labels.append(f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)")
        if not labels and role_editor_entry is not None:
            labels.append("默认模版(角色编辑)")
        seen: set[str] = set()
        deduped: list[str] = []
        for x in labels:
            k = str(x)
            if k in seen:
                continue
            seen.add(k)
            deduped.append(k)
        return deduped

    for (group_name, var_name), roles in sorted(progressbar_variable_roles.items()):
        g = str(group_name or "").strip()
        n = str(var_name or "").strip()
        if g == "" or n == "":
            continue

        full_name = f"{g}.{n}"
        n = require_scalar_variable_name(full_name=full_name, var_name=n)

        targets = _iter_target_entries(g)

        roles_s = set(str(r) for r in (roles or set()))
        default_value = int(DEFAULT_PROGRESSBAR_INT_DEFAULTS.get("current", 100))
        if "min" in roles_s:
            default_value = int(DEFAULT_PROGRESSBAR_INT_DEFAULTS.get("min", 0))
        elif "max" in roles_s:
            default_value = int(DEFAULT_PROGRESSBAR_INT_DEFAULTS.get("max", 100))
        elif "current" in roles_s:
            default_value = int(DEFAULT_PROGRESSBAR_INT_DEFAULTS.get("current", 100))

        default_source = "builtin"
        if variable_defaults and full_name in variable_defaults:
            default_value = int(coerce_default_int(variable_defaults[full_name], key=full_name))
            default_source = "user"

        created_in: list[str] = []
        existed_in: list[str] = []
        for target_entry, group_list_key, target_label in targets:
            created = ensure_int_custom_variable_in_asset_entry(
                target_entry,
                variable_name=n,
                default_value=int(default_value),
                group_list_key=str(group_list_key),
            )
            if created:
                created_total += 1
                created_in.append(str(target_label))
            else:
                existed_total += 1
                existed_in.append(str(target_label))
        variables_report.append(
            {
                "group": g,
                "variable_name": n,
                "roles": sorted(roles_s),
                "default_value": int(default_value),
                "default_value_source": default_source,
                "created": bool(created_in),
                "target_entity_name": (created_in[0] if created_in else (existed_in[0] if existed_in else "")),
                "created_in": created_in,
                "existed_in": existed_in,
            }
        )

    return {
        "created_total": int(created_total),
        "existed_total": int(existed_total),
        "targets": {"关卡": ["关卡实体"], "玩家自身": _build_player_targets_labels_no_raise()},
        "variables": variables_report,
    }


def ensure_item_display_referenced_custom_variables(
    raw_dump_object: Dict[str, Any],
    *,
    config_id_variable_refs: set[Tuple[str, str]],
    int_variable_refs: set[Tuple[str, str]],
    float_variable_refs: set[Tuple[str, str]],
    variable_defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    将道具展示（按钮锚点）引用到的变量“自动创建”为实体自定义变量：
    - 玩家自身.<var> -> 写入 玩家实体（若存在）与 玩家模板(战斗预设)条目（若存在）；否则回退到 默认模版(角色编辑)
    - 关卡.<var> -> 写入 关卡实体
    """
    if not config_id_variable_refs and not int_variable_refs and not float_variable_refs:
        return {"created_total": 0, "existed_total": 0, "targets": {}, "variables": []}

    root4 = raw_dump_object.get("4")
    if not isinstance(root4, dict):
        raise ValueError("DLL dump JSON 缺少根字段 '4'（期望为 dict）。")
    section5 = root4.get("5")
    if not isinstance(section5, dict):
        raise ValueError("DLL dump JSON 缺少字段 '4/5'（期望为 dict）。")
    entry_list = section5.get("1")
    if not isinstance(entry_list, list):
        raise ValueError("DLL dump JSON 缺少字段 '4/5/1'（期望为 list）。")

    level_entry = find_root4_5_1_entry_by_name(entry_list, "关卡实体")
    if level_entry is None:
        raise RuntimeError("未在 root4/5/1 中找到 name=关卡实体 的条目，无法写入关卡变量。")

    player_entity_entry = find_root4_5_1_entry_by_name(entry_list, "玩家实体")
    role_editor_entry = find_root4_5_1_entry_by_name(entry_list, "默认模版(角色编辑)")
    player_template_targets = collect_player_template_custom_variable_targets_from_payload_root(root4)

    created_total = 0
    existed_total = 0
    variables_report: List[Dict[str, Any]] = []

    def _iter_target_entries(group_name: str) -> list[tuple[Dict[str, Any], str, str]]:
        g = str(group_name or "").strip()
        if g == "关卡":
            return [(level_entry, "7", "关卡实体")]
        if g == "玩家自身":
            out: list[tuple[Dict[str, Any], str, str]] = []
            if player_entity_entry is not None:
                out.append((player_entity_entry, "7", "玩家实体"))
            for t in list(player_template_targets or []):
                wrappers = t.get("root5_wrappers")
                if isinstance(wrappers, list):
                    for w in wrappers:
                        if isinstance(w, dict):
                            name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                            out.append((w, "7", f"玩家模板:{name}"))
                e4 = t.get("root4_entry")
                if isinstance(e4, dict):
                    names = t.get("template_names")
                    label_name = ""
                    if isinstance(names, list) and names:
                        label_name = str(names[0])
                    label = f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)"
                    out.append((e4, "8", label))
            if out:
                return out
            if role_editor_entry is not None:
                return [(role_editor_entry, "7", "默认模版(角色编辑)")]
            raise RuntimeError(
                "道具展示引用了 玩家自身.<变量>，但存档中未找到 玩家实体 / 玩家模板(wrapper) / 默认模版(角色编辑) 条目。"
            )
        raise ValueError(f"未知变量组名：{g!r}（仅支持：关卡 / 玩家自身）")

    def _build_player_targets_labels_no_raise() -> list[str]:
        labels: list[str] = []
        if player_entity_entry is not None:
            labels.append("玩家实体")
        for t in list(player_template_targets or []):
            wrappers = t.get("root5_wrappers")
            if isinstance(wrappers, list):
                for w in wrappers:
                    if not isinstance(w, dict):
                        continue
                    name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                    labels.append(f"玩家模板:{name}")
            e4 = t.get("root4_entry")
            if isinstance(e4, dict):
                names = t.get("template_names")
                label_name = ""
                if isinstance(names, list) and names:
                    label_name = str(names[0])
                labels.append(f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)")
        if not labels and role_editor_entry is not None:
            labels.append("默认模版(角色编辑)")
        seen: set[str] = set()
        deduped: list[str] = []
        for x in labels:
            k = str(x)
            if k in seen:
                continue
            seen.add(k)
            deduped.append(k)
        return deduped

    # 1) 配置ID变量（type_code=20）
    for (group_name, var_name) in sorted(config_id_variable_refs):
        g = str(group_name or "").strip()
        n = str(var_name or "").strip()
        if g == "" or n == "":
            continue
        targets = _iter_target_entries(g)
        full_name = f"{g}.{n}"
        n = require_scalar_variable_name(full_name=full_name, var_name=n)
        default_value = 0
        default_source = "builtin"
        if variable_defaults and full_name in variable_defaults:
            default_value = int(coerce_default_int(variable_defaults[full_name], key=full_name))
            default_source = "user"
        created_in: list[str] = []
        existed_in: list[str] = []
        for target_entry, group_list_key, target_label in targets:
            created = ensure_config_id_custom_variable_in_asset_entry(
                target_entry,
                variable_name=n,
                default_value=int(default_value),
                group_list_key=str(group_list_key),
            )
            if created:
                created_total += 1
                created_in.append(str(target_label))
            else:
                existed_total += 1
                existed_in.append(str(target_label))
        variables_report.append(
            {
                "group": g,
                "variable_name": n,
                "roles": ["config_id"],
                "type_code": 20,
                "default_value": int(default_value),
                "default_value_source": default_source,
                "created": bool(created_in),
                "target_entity_name": (created_in[0] if created_in else (existed_in[0] if existed_in else "")),
                "created_in": created_in,
                "existed_in": existed_in,
            }
        )

    # 2) 整数变量（type_code=3）：次数/数量等
    for (group_name, var_name) in sorted(int_variable_refs):
        g = str(group_name or "").strip()
        n = str(var_name or "").strip()
        if g == "" or n == "":
            continue
        targets = _iter_target_entries(g)
        full_name = f"{g}.{n}"
        n = require_scalar_variable_name(full_name=full_name, var_name=n)
        default_value = 0
        if full_name == str(DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_VARIABLE_FULL_NAME):
            default_value = int(DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_DEFAULT)
        default_source = "builtin"
        if variable_defaults and full_name in variable_defaults:
            default_value = int(coerce_default_int(variable_defaults[full_name], key=full_name))
            default_source = "user"
        created_in2: list[str] = []
        existed_in2: list[str] = []
        for target_entry, group_list_key, target_label in targets:
            created = ensure_int_custom_variable_in_asset_entry(
                target_entry,
                variable_name=n,
                default_value=int(default_value),
                group_list_key=str(group_list_key),
            )
            if created:
                created_total += 1
                created_in2.append(str(target_label))
            else:
                existed_total += 1
                existed_in2.append(str(target_label))
        variables_report.append(
            {
                "group": g,
                "variable_name": n,
                "roles": ["int"],
                "type_code": 3,
                "default_value": int(default_value),
                "default_value_source": default_source,
                "created": bool(created_in2),
                "target_entity_name": (created_in2[0] if created_in2 else (existed_in2[0] if existed_in2 else "")),
                "created_in": created_in2,
                "existed_in": existed_in2,
            }
        )

    # 3) 浮点变量（type_code=5）：冷却时间等
    for (group_name, var_name) in sorted(float_variable_refs):
        g = str(group_name or "").strip()
        n = str(var_name or "").strip()
        if g == "" or n == "":
            continue
        targets = _iter_target_entries(g)
        full_name = f"{g}.{n}"
        n = require_scalar_variable_name(full_name=full_name, var_name=n)
        default_value = 0.0
        default_source = "builtin"
        if variable_defaults and full_name in variable_defaults:
            default_value = float(coerce_default_float(variable_defaults[full_name], key=full_name))
            default_source = "user"
        created_in3: list[str] = []
        existed_in3: list[str] = []
        for target_entry, group_list_key, target_label in targets:
            created = ensure_float_custom_variable_in_asset_entry(
                target_entry,
                variable_name=n,
                default_value=float(default_value),
                group_list_key=str(group_list_key),
            )
            if created:
                created_total += 1
                created_in3.append(str(target_label))
            else:
                existed_total += 1
                existed_in3.append(str(target_label))
        variables_report.append(
            {
                "group": g,
                "variable_name": n,
                "roles": ["float"],
                "type_code": 5,
                "default_value": float(default_value),
                "default_value_source": default_source,
                "created": bool(created_in3),
                "target_entity_name": (created_in3[0] if created_in3 else (existed_in3[0] if existed_in3 else "")),
                "created_in": created_in3,
                "existed_in": existed_in3,
            }
        )

    return {
        "created_total": int(created_total),
        "existed_total": int(existed_total),
        "targets": {"关卡": ["关卡实体"], "玩家自身": _build_player_targets_labels_no_raise()},
        "variables": variables_report,
    }

