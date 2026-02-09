from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from engine.resources.custom_variable_file_refs import (
    normalize_custom_variable_file_refs,
    serialize_custom_variable_file_refs,
)
from engine.resources.level_variable_schema_view import (
    CATEGORY_CUSTOM,
    LevelVariableSchemaView,
    invalidate_default_level_variable_cache,
)

from app.cli.ui_variable_validator import (
    _scope_set_default,
    crc32_hex,
    iter_ui_html_files,
    parse_variable_path,
    _iter_placeholder_matches,
    _iter_progressbar_binding_attr_matches,
    _is_number_literal,
    _normalize_progressbar_binding_expr,
)
from app.cli.ui_variable_defaults_extractor import try_extract_ui_variable_defaults_from_html


@dataclass(frozen=True, slots=True)
class UiQuickFixAction:
    file_path: Path
    summary: str


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _iter_placeholders_in_file(path: Path) -> Iterable[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    for _token, raw_expr, _offset in _iter_placeholder_matches(text):
        yield _token, raw_expr.strip()
    for _token, raw_expr, _offset in _iter_progressbar_binding_attr_matches(text):
        expr = _normalize_progressbar_binding_expr(raw_expr)
        if not expr:
            continue
        # min/max 支持数字常量；这里无需生成变量
        if _is_number_literal(expr):
            continue
        yield _token, expr


KeyPath = Tuple[str, ...]


def _collect_required_variables(
    ui_source_dir: Path,
) -> tuple[
    Dict[str, Dict[str, set[KeyPath]]],
    Dict[str, Dict[str, Dict[str, object]]],
    Dict[str, Dict[str, int]],
]:
    """返回按 scope 分组的需求：

    {
      "ps": { "变量名": {(), (k1,), (k1,k2), ...} },   # () 表示标量变量；非空 tuple 表示字典键路径
      "lv": { "变量名": {(), (k1,), ...} },
      "p1": ...
    }

    同时返回从 HTML `data-ui-variable-defaults` 抽取到的“字典键默认值”（仅一层字典）：

    {
      "lv": { "变量名": {"k1": 0, "k2": "x", ...} },
      "ps": { "变量名": {...} },
      ...
    }

    以及返回“进度条绑定引用到的标量整数变量”的默认值建议（按 scope 分组）：

    {
      "lv": { "UI结算_整数__完整度_当前": 20, ... },
      "ps": { ... },
      ...
    }

    目的：修复“状态切换用键不在 data-ui-text 占位符中出现”导致 validate-ui --fix 漏掉键的问题。
    """
    allowed_scopes = _scope_set_default()
    required: Dict[str, Dict[str, set[KeyPath]]] = {scope: {} for scope in allowed_scopes}
    defaults_by_scope: Dict[str, Dict[str, Dict[str, object]]] = {scope: {} for scope in allowed_scopes}
    progressbar_int_defaults_by_scope: Dict[str, Dict[str, int]] = {scope: {} for scope in allowed_scopes}

    def _coerce_default_int(value: object) -> int:
        if isinstance(value, bool):
            return int(1 if value else 0)
        if isinstance(value, int):
            return int(value)
        if isinstance(value, float):
            return int(value)
        text = str(value if value is not None else "").strip()
        if text and _is_number_literal(text):
            return int(float(text))
        return 0

    for html_path in iter_ui_html_files(ui_source_dir):
        # 1) data-ui-variable-defaults：显式声明的字典键（含默认值）
        extracted = try_extract_ui_variable_defaults_from_html(html_path)
        if extracted is not None:
            raw_defaults = extracted.raw_defaults
            if isinstance(raw_defaults, dict):
                for full_key, payload in raw_defaults.items():
                    full_key_text = str(full_key or "").strip()
                    if "." not in full_key_text:
                        continue
                    scope_part, _, var_name = full_key_text.partition(".")
                    scope = str(scope_part or "").strip().lower()
                    if scope not in allowed_scopes:
                        continue
                    name = str(var_name or "").strip()
                    if not name:
                        continue
                    if not isinstance(payload, dict):
                        # extractor 已校验顶层 value 必须是 dict；这里再防御一次
                        continue

                    key_set = required[scope].setdefault(name, set())
                    bucket = defaults_by_scope[scope].setdefault(name, {})
                    for k, v in payload.items():
                        key_text = str(k or "").strip()
                        if not key_text:
                            continue
                        # data-ui-variable-defaults 约定：字典变量是一层 key/value 表（key 不再拆分为多段路径）
                        key_set.add((key_text,))
                        # 保留 JSON 解码后的值类型（int/str/...），供 quickfix 写入 default_value
                        if key_text not in bucket:
                            bucket[key_text] = v

        # 2) data-ui-text / progressbar bindings：占位符引用（仅能得到键路径，不一定有默认值）
        # 注：progressbar bindings 的语义是“整数标量变量”，与文本占位符（默认字符串/字典）不同，因此这里需要区分 token 来源。
        for token, raw_expr in _iter_placeholders_in_file(html_path):
            scope, segments = parse_variable_path(raw_expr)
            if scope == "ls":
                raise ValueError(f"不支持 UI 占位符使用 ls 前缀，请改用 lv：{raw_expr!r}（{html_path}）")
            if scope not in allowed_scopes:
                continue
            if not segments:
                continue

            token_lower = str(token or "").lower()
            is_progressbar_binding = "data-progress-" in token_lower
            if is_progressbar_binding:
                # 进度条 binding 只允许标量变量（单段）；字典键路径由 validate-ui 报错，这里不做自动迁移
                if len(segments) != 1:
                    continue
                var_name = str(segments[0])
                required[scope].setdefault(var_name, set()).add(())

                # 默认值建议：
                # - 优先：镜像命名 "<dict>__<key_path>" 可从 data-ui-variable-defaults 的字典默认值推导
                # - fallback：按 role（min=0/max=100/current=100）给保守缺省值
                inferred: int | None = None
                if "__" in var_name:
                    base, _sep, rest = var_name.partition("__")
                    key_path_text = str(rest or "").replace("__", ".").strip()
                    if base and key_path_text:
                        base_defaults = defaults_by_scope.get(scope, {}).get(str(base), {})
                        if isinstance(base_defaults, dict) and key_path_text in base_defaults:
                            inferred = _coerce_default_int(base_defaults.get(key_path_text))

                if inferred is None:
                    role = "current"
                    if "data-progress-min-var" in token_lower:
                        role = "min"
                    elif "data-progress-max-var" in token_lower:
                        role = "max"
                    inferred = 0 if role == "min" else 100

                bucket = progressbar_int_defaults_by_scope[scope]
                if var_name not in bucket:
                    bucket[var_name] = int(inferred)
                continue

            root_name = segments[0]
            key_set = required[scope].setdefault(root_name, set())
            if len(segments) == 1:
                key_set.add(())
                continue

            # 2+ 段：字典键路径（支持多层，写入 default_value 嵌套 dict）
            key_path = tuple(seg for seg in segments[1:] if seg)
            if key_path:
                key_set.add(key_path)

    return required, defaults_by_scope, progressbar_int_defaults_by_scope


def _variable_id_for(package_id: str, *, scope: str, variable_name: str) -> str:
    digest = crc32_hex(f"{package_id}:{scope}:{variable_name}")
    return f"ui_{digest}__{package_id}"


def _ensure_generated_variable_file_dir(package_root: Path) -> Path:
    return package_root / "管理配置" / "关卡变量" / "自定义变量"


def _ensure_player_template_dir(package_root: Path) -> Path:
    return package_root / "战斗预设" / "玩家模板"


def _discover_player_templates(package_root: Path) -> list[Path]:
    template_dir = _ensure_player_template_dir(package_root)
    if not template_dir.is_dir():
        return []
    return sorted([p for p in template_dir.glob("*.json") if p.is_file()], key=lambda p: p.as_posix())


def _get_player_custom_variable_file_ids_from_template(template_json: dict) -> list[str]:
    metadata = template_json.get("metadata")
    if not isinstance(metadata, dict):
        return []
    return normalize_custom_variable_file_refs(metadata.get("custom_variable_file"))


def _set_player_custom_variable_file_ids(template_json: dict, file_ids: Sequence[str]) -> None:
    metadata = template_json.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        template_json["metadata"] = metadata
    metadata["custom_variable_file"] = serialize_custom_variable_file_refs(file_ids)


def _load_schema_view_for_package(package_id: str) -> LevelVariableSchemaView:
    schema_view = LevelVariableSchemaView()
    schema_view.set_active_package_id(package_id)
    return schema_view


def _pick_existing_player_variable_file_id(package_id: str, schema_view: LevelVariableSchemaView, templates: Sequence[Path]) -> str:
    # 优先：从任一玩家模板 metadata.custom_variable_file 指向的文件中挑一个存在的普通自定义变量文件
    candidate_ids: list[str] = []
    for path in templates:
        payload = _read_json(path)
        candidate_ids.extend(_get_player_custom_variable_file_ids_from_template(payload))

    # 去重保持顺序
    seen = set()
    ordered = []
    for file_id in candidate_ids:
        if file_id in seen:
            continue
        seen.add(file_id)
        ordered.append(file_id)

    custom_files = schema_view.get_custom_variable_files()
    for file_id in ordered:
        info = custom_files.get(file_id)
        if info is not None:
            return file_id

    # fallback：若模板没有或不存在，尝试从当前包里任意普通自定义变量文件里挑一个
    for file_id, info in custom_files.items():
        # 仅取当前 package_root 下的文件（避免误用共享）
        if f"项目存档/{package_id}/" in info.absolute_path.as_posix().replace("\\", "/"):
            return file_id

    return ""


def _merge_existing_variables_from_file(schema_view: LevelVariableSchemaView, file_id: str) -> list[dict]:
    existing = schema_view.get_variables_by_file_id(file_id)
    return [dict(item) for item in existing]


def _merge_existing_variables_from_files(schema_view: LevelVariableSchemaView, file_ids: Sequence[str]) -> list[dict]:
    merged_by_name: Dict[str, dict] = {}
    for file_id in file_ids:
        file_id_text = str(file_id or "").strip()
        if not file_id_text:
            continue
        for item in schema_view.get_variables_by_file_id(file_id_text) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("variable_name") or "").strip()
            if not name:
                continue
            if name not in merged_by_name:
                merged_by_name[name] = dict(item)
    return list(merged_by_name.values())


def _build_generated_variables(
    package_id: str,
    *,
    scope: str,
    required: Dict[str, set[KeyPath]],
    existing: Sequence[dict],
    dict_default_values_by_name: Dict[str, Dict[str, object]] | None = None,
    scalar_int_default_values_by_name: Dict[str, int] | None = None,
) -> list[dict]:
    # 先按 variable_name 建索引（保留原 variable_id/type/default）
    by_name: Dict[str, dict] = {}
    for item in existing:
        name = str(item.get("variable_name") or "").strip()
        if not name:
            continue
        if name in by_name:
            continue
        by_name[name] = dict(item)

    def _ensure_nested_dict(default_value: dict, path: KeyPath, *, leaf_default: object | None) -> None:
        current = default_value
        # path 至少 1 段
        for key in path[:-1]:
            next_value = current.get(key)
            if not isinstance(next_value, dict):
                next_value = {}
                current[key] = next_value
            current = next_value
        leaf = path[-1]
        if leaf not in current:
            current[leaf] = "" if leaf_default is None else leaf_default

    scalar_int_defaults = scalar_int_default_values_by_name or {}

    for variable_name, key_paths in required.items():
        dict_defaults = (dict_default_values_by_name or {}).get(variable_name, {})
        if variable_name not in by_name:
            dict_paths = [p for p in key_paths if p]
            if dict_paths:
                by_name[variable_name] = {
                    "variable_id": _variable_id_for(package_id, scope=scope, variable_name=variable_name),
                    "variable_name": variable_name,
                    "variable_type": "字典",
                    "default_value": {},
                    "is_global": True,
                    "description": "UI 文本占位符引用（由 validate-ui --fix 自动生成）",
                    "metadata": {
                        "category": "UI自动生成",
                        # 若来自 data-ui-variable-defaults，则把这些键标为 managed（便于后续 apply-ui-defaults --prune-managed-keys）
                        "ui_defaults_managed_keys": sorted([str(k) for k in dict_defaults.keys()]) if dict_defaults else [],
                    },
                }
                default_value = by_name[variable_name].get("default_value")
                if not isinstance(default_value, dict):
                    default_value = {}
                    by_name[variable_name]["default_value"] = default_value
                for path in sorted(dict_paths):
                    leaf_default = None
                    if len(path) == 1:
                        leaf_default = dict_defaults.get(path[0])
                    _ensure_nested_dict(default_value, path, leaf_default=leaf_default)
            else:
                if variable_name in scalar_int_defaults:
                    by_name[variable_name] = {
                        "variable_id": _variable_id_for(package_id, scope=scope, variable_name=variable_name),
                        "variable_name": variable_name,
                        "variable_type": "整数",
                        "default_value": int(scalar_int_defaults.get(variable_name, 0)),
                        "is_global": True,
                        "description": "UI 进度条绑定引用（由 validate-ui --fix 自动生成）",
                        "metadata": {"category": "UI自动生成"},
                    }
                    continue
                by_name[variable_name] = {
                    "variable_id": _variable_id_for(package_id, scope=scope, variable_name=variable_name),
                    "variable_name": variable_name,
                    "variable_type": "字符串",
                    "default_value": "",
                    "is_global": True,
                    "description": "UI 文本占位符引用（由 validate-ui --fix 自动生成）",
                    "metadata": {"category": "UI自动生成"},
                }
            continue

        # 已存在：若需要字典键，尽力补齐（仅支持一层字典）
        dict_paths = [p for p in key_paths if p]
        if not dict_paths:
            # 标量：若被进度条绑定引用，则应为整数；仅对 UI 自动生成变量做自愈升级，避免误改手写文件。
            if variable_name in scalar_int_defaults:
                current = by_name[variable_name]
                meta = current.get("metadata")
                category = meta.get("category") if isinstance(meta, dict) else None
                vtype = str(current.get("variable_type") or "").strip()
                if category == "UI自动生成" and vtype != "整数":
                    current["variable_type"] = "整数"
                    current["default_value"] = int(scalar_int_defaults.get(variable_name, 0))
                    current["description"] = "UI 进度条绑定引用（由 validate-ui --fix 自动生成）"
            continue
        current = by_name[variable_name]
        vtype = str(current.get("variable_type") or "").strip()
        if vtype != "字典":
            # 不做自动升级；让校验报错提示人工处理
            continue
        default_value = current.get("default_value")
        if not isinstance(default_value, dict):
            default_value = {}
            current["default_value"] = default_value
        for path in sorted(dict_paths):
            leaf_default = None
            if len(path) == 1:
                leaf_default = dict_defaults.get(path[0])
            _ensure_nested_dict(default_value, path, leaf_default=leaf_default)

    # 清理：移除不再被 UI 引用的“UI自动生成”变量（避免长期堆积）
    required_names = set(required.keys())
    for name, item in list(by_name.items()):
        meta = item.get("metadata")
        category = meta.get("category") if isinstance(meta, dict) else None
        if category == "UI自动生成" and name not in required_names:
            del by_name[name]

    # 稳定排序：先其它（保持 existing 原序），再 UI 自动生成（按名称排序）
    generated = []
    others = []
    for item in by_name.values():
        meta = item.get("metadata")
        category = meta.get("category") if isinstance(meta, dict) else None
        if category == "UI自动生成":
            generated.append(item)
        else:
            others.append(item)
    generated_sorted = sorted(generated, key=lambda x: str(x.get("variable_name") or ""))
    return others + generated_sorted


def _write_generated_variable_file(
    path: Path,
    *,
    file_id: str,
    file_name: str,
    variables: Sequence[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from engine.graph.models.package_model import LevelVariableDefinition")
    lines.append("")
    lines.append(f'VARIABLE_FILE_ID = "{file_id}"')
    lines.append(f'VARIABLE_FILE_NAME = "{file_name}"')
    lines.append("")
    lines.append("LEVEL_VARIABLES: list[LevelVariableDefinition] = [")
    for item in variables:
        # 仅保留 loader 识别字段，避免把运行期附加的 source_* 写回
        payload = {
            "variable_id": item.get("variable_id"),
            "variable_name": item.get("variable_name"),
            "variable_type": item.get("variable_type"),
            "default_value": item.get("default_value"),
            "is_global": item.get("is_global", True),
            "description": item.get("description", ""),
            "metadata": item.get("metadata", {}),
        }
        lines.append("    LevelVariableDefinition(")
        lines.append(f"        variable_id={repr(payload['variable_id'])},")
        lines.append(f"        variable_name={repr(payload['variable_name'])},")
        lines.append(f"        variable_type={repr(payload['variable_type'])},")
        lines.append(f"        default_value={repr(payload['default_value'])},")
        lines.append(f"        is_global={repr(payload['is_global'])},")
        lines.append(f"        description={repr(payload['description'])},")
        lines.append(f"        metadata={repr(payload['metadata'])},")
        lines.append("    ),")
    lines.append("]")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_ui_variable_quickfixes(
    *,
    workspace_root: Path,
    package_id: str,
    dry_run: bool,
) -> list[UiQuickFixAction]:
    """根据 UI源码 中的 ps/p1~p8/lv 引用，自动补齐变量定义与玩家模板引用。"""
    package_root = (
        workspace_root
        / "assets"
        / "资源库"
        / "项目存档"
        / package_id
    )
    ui_source_dir = package_root / "管理配置" / "UI源码"
    required_by_scope, defaults_by_scope, progressbar_int_defaults_by_scope = _collect_required_variables(ui_source_dir)

    player_required_ps = required_by_scope.get("ps", {})
    player_required_by_slot: Dict[str, Dict[str, set[KeyPath]]] = {}
    for scope in ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]:
        bucket = required_by_scope.get(scope, {})
        if bucket:
            player_required_by_slot[scope] = bucket

    level_required = required_by_scope.get("lv", {})

    schema_view = _load_schema_view_for_package(package_id)

    actions: list[UiQuickFixAction] = []

    # ===== 玩家变量：生成文件 + 修改玩家模板 custom_variable_file =====
    player_templates = _discover_player_templates(package_root)
    player_var_dir = _ensure_generated_variable_file_dir(package_root)

    # 1) ps：共享玩家变量（不区分玩家槽位）——写入一份文件，并追加到所有玩家模板
    generated_player_file_id_ps = f"ui_player_custom_variables__{package_id}"
    generated_player_file_name_ps = f"UI_玩家变量_自动生成__{package_id}"
    player_var_path_ps = player_var_dir / "UI_玩家变量_自动生成.py"
    if player_required_ps:
        existing_player_file_id = _pick_existing_player_variable_file_id(
            package_id, schema_view, player_templates
        )
        existing_player_vars: list[dict] = []
        if existing_player_file_id:
            existing_player_vars = _merge_existing_variables_from_file(schema_view, existing_player_file_id)
        player_vars_payload_ps = _build_generated_variables(
            package_id,
            scope="ps",
            required=player_required_ps,
            existing=existing_player_vars,
            dict_default_values_by_name=defaults_by_scope.get("ps", {}),
            scalar_int_default_values_by_name=progressbar_int_defaults_by_scope.get("ps", {}),
        )
        if dry_run:
            actions.append(
                UiQuickFixAction(
                    file_path=player_var_path_ps,
                    summary=f"[DRY-RUN] 将写入玩家变量文件(ps)：{generated_player_file_id_ps}（{len(player_vars_payload_ps)} 条）",
                )
            )
        else:
            _write_generated_variable_file(
                player_var_path_ps,
                file_id=generated_player_file_id_ps,
                file_name=generated_player_file_name_ps,
                variables=player_vars_payload_ps,
            )
            actions.append(
                UiQuickFixAction(
                    file_path=player_var_path_ps,
                    summary=f"写入玩家变量文件(ps)：{generated_player_file_id_ps}（{len(player_vars_payload_ps)} 条）",
                )
            )

    # 2) p1~p8：按槽位生成变量文件，并仅追加到对应槽位的玩家模板
    # 说明：槽位顺序按 玩家模板目录（*.json）排序，便于离线工作流稳定复现。
    for index, template_path in enumerate(player_templates):
        scope = f"p{index + 1}"
        required_slot = player_required_by_slot.get(scope, {})
        if not required_slot:
            continue

        template_payload = _read_json(template_path)
        old_refs = _get_player_custom_variable_file_ids_from_template(template_payload)
        existing_vars_merged = _merge_existing_variables_from_files(schema_view, old_refs)

        file_id = f"ui_player_custom_variables__{package_id}__{scope}"
        file_name = f"UI_玩家变量_{scope}_自动生成__{package_id}"
        file_path = player_var_dir / f"UI_玩家变量_{scope}_自动生成.py"

        payloads = _build_generated_variables(
            package_id,
            scope=scope,
            required=required_slot,
            existing=existing_vars_merged,
            dict_default_values_by_name=defaults_by_scope.get(scope, {}),
            scalar_int_default_values_by_name=progressbar_int_defaults_by_scope.get(scope, {}),
        )

        if dry_run:
            actions.append(
                UiQuickFixAction(
                    file_path=file_path,
                    summary=f"[DRY-RUN] 将写入玩家变量文件({scope})：{file_id}（{len(payloads)} 条）",
                )
            )
        else:
            _write_generated_variable_file(
                file_path,
                file_id=file_id,
                file_name=file_name,
                variables=payloads,
            )
            actions.append(
                UiQuickFixAction(
                    file_path=file_path,
                    summary=f"写入玩家变量文件({scope})：{file_id}（{len(payloads)} 条）",
                )
            )

        new_refs = list(old_refs)
        # 先追加 ps 文件（如果有需求）
        if player_required_ps and generated_player_file_id_ps not in new_refs:
            new_refs.append(generated_player_file_id_ps)
        # 再追加槽位文件
        if file_id not in new_refs:
            new_refs.append(file_id)

        if new_refs == list(old_refs):
            continue
        _set_player_custom_variable_file_ids(template_payload, new_refs)
        if dry_run:
            actions.append(
                UiQuickFixAction(
                    file_path=template_path,
                    summary=(
                        f"[DRY-RUN] 将更新玩家模板({scope}) custom_variable_file: "
                        f"{' / '.join(old_refs) if old_refs else '<empty>'} -> {' / '.join(new_refs)}"
                    ),
                )
            )
        else:
            _write_json(template_path, template_payload)
            actions.append(
                UiQuickFixAction(
                    file_path=template_path,
                    summary=(
                        f"更新玩家模板({scope}) custom_variable_file: "
                        f"{' / '.join(old_refs) if old_refs else '<empty>'} -> {' / '.join(new_refs)}"
                    ),
                )
            )

    # 如果存在 ps 需求，则确保所有玩家模板都引用 ps 文件
    if player_required_ps:
        for template_path in player_templates:
            template_payload = _read_json(template_path)
            old_refs = _get_player_custom_variable_file_ids_from_template(template_payload)
            if generated_player_file_id_ps in old_refs:
                continue
            new_refs = list(old_refs) + [generated_player_file_id_ps]
            _set_player_custom_variable_file_ids(template_payload, new_refs)
            if dry_run:
                actions.append(
                    UiQuickFixAction(
                        file_path=template_path,
                        summary=(
                            "[DRY-RUN] 将更新玩家模板 custom_variable_file: "
                            f"{' / '.join(old_refs) if old_refs else '<empty>'} -> {' / '.join(new_refs)}"
                        ),
                    )
                )
                continue
            _write_json(template_path, template_payload)
            actions.append(
                UiQuickFixAction(
                    file_path=template_path,
                    summary=(
                        "更新玩家模板 custom_variable_file: "
                        f"{' / '.join(old_refs) if old_refs else '<empty>'} -> {' / '.join(new_refs)}"
                    ),
                )
            )

    # ===== 关卡变量（lv）：生成文件（不需要改模板引用）=====
    # 只在有需求时生成
    if level_required:
        existing_level_vars: list[dict] = []
        # 若已有同名生成文件，合并之（避免覆盖用户已改的 default_value）
        generated_level_file_id = f"ui_level_variables__{package_id}"
        current_custom_files = schema_view.get_custom_variable_files()
        if generated_level_file_id in current_custom_files:
            existing_level_vars = _merge_existing_variables_from_file(schema_view, generated_level_file_id)

        generated_level_file_name = f"UI_关卡变量_自动生成__{package_id}"
        level_vars_payload = _build_generated_variables(
            package_id,
            scope="lv",
            required=level_required,
            existing=existing_level_vars,
            dict_default_values_by_name=defaults_by_scope.get("lv", {}),
            scalar_int_default_values_by_name=progressbar_int_defaults_by_scope.get("lv", {}),
        )

        level_var_dir = _ensure_generated_variable_file_dir(package_root)
        level_var_path = level_var_dir / "UI_关卡变量_自动生成.py"

        if dry_run:
            actions.append(
                UiQuickFixAction(
                    file_path=level_var_path,
                    summary=f"[DRY-RUN] 将写入关卡变量文件：{generated_level_file_id}（{len(level_vars_payload)} 条）",
                )
            )
        else:
            _write_generated_variable_file(
                level_var_path,
                file_id=generated_level_file_id,
                file_name=generated_level_file_name,
                variables=level_vars_payload,
            )
            actions.append(
                UiQuickFixAction(
                    file_path=level_var_path,
                    summary=f"写入关卡变量文件：{generated_level_file_id}（{len(level_vars_payload)} 条）",
                )
            )

    if not dry_run:
        invalidate_default_level_variable_cache()

    return actions

