from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from engine.resources.level_variable_schema_view import LevelVariableSchemaView

import json

from app.cli.ui_variable_defaults_extractor import (
    extract_ui_variable_defaults_from_html,
    try_extract_ui_variable_defaults_from_html,
)
from app.cli.ui_variable_quickfixes import _variable_id_for, _write_generated_variable_file  # noqa: PLC2701


@dataclass(frozen=True, slots=True)
class ApplyUiDefaultsAction:
    file_path: Path
    summary: str


def _load_level_variables_by_file_id(*, package_id: str, file_id: str) -> list[dict]:
    schema_view = LevelVariableSchemaView()
    schema_view.set_active_package_id(str(package_id))
    existing = schema_view.get_variables_by_file_id(str(file_id))
    return [dict(item) for item in (existing or []) if isinstance(item, dict)]


def _merge_defaults_shallow(*, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    # incoming 优先；保留 existing 中可能存在的额外键（避免丢键）。
    merged: dict[str, Any] = dict(existing)
    merged.update(dict(incoming))
    return merged


def _normalize_one_level_value(value: Any) -> Any:
    # 约束（见 管理配置/关卡变量/claude.md）：
    # - 字典变量 default_value 只允许“一层键值表”，不允许 value 再是 dict。
    # 因此若页面 defaults 里出现 dict value，则压成 JSON 字符串，仍保留信息且满足约束。
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _normalize_one_level_dict(source: dict[str, Any]) -> dict[str, Any]:
    return {str(k): _normalize_one_level_value(v) for k, v in source.items()}


_PROGRESSBAR_BINDING_ATTR_PATTERN = re.compile(
    r"\bdata-progress-(current|min|max)-var\s*=\s*(\"|')([^\"']*?)\2",
    re.IGNORECASE,
)
_MOUSTACHE_WRAPPER = re.compile(r"^\{\{\s*([^{}]+?)\s*\}\}$")
_NUMBER_LITERAL_PATTERN = re.compile(r"^[+-]?\d+(\.\d+)?$")


def _normalize_binding_expr(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    match = _MOUSTACHE_WRAPPER.fullmatch(text)
    if match:
        return str(match.group(1) or "").strip()
    return text


def _is_number_literal(text: str) -> bool:
    return bool(_NUMBER_LITERAL_PATTERN.match(str(text or "").strip()))


def _parse_number_literal(text: str) -> int | float:
    value = str(text or "").strip()
    if "." in value:
        return float(value)
    return int(value)


def _try_parse_lv_dict_key(expr: str) -> tuple[str, str] | None:
    """解析 lv.<dict_var>.<key>（仅支持一层键）。"""
    text = str(expr or "").strip()
    if not text:
        return None
    scope, sep, rest = text.partition(".")
    if sep != ".":
        return None
    if scope.strip().lower() != "lv":
        return None
    segments = [s for s in rest.split(".") if s]
    if len(segments) != 2:
        return None
    return segments[0], segments[1]


class _ProgressbarBindingParser(HTMLParser):
    """抽取每个 progressbar 元素的三元绑定（current/min/max）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        current = ""
        minv = ""
        maxv = ""
        for k, v in attrs:
            key = str(k or "").strip().lower()
            val = "" if v is None else str(v)
            if key == "data-progress-current-var":
                current = val
            elif key == "data-progress-min-var":
                minv = val
            elif key == "data-progress-max-var":
                maxv = val
        if current or minv or maxv:
            self.entries.append({"tag": str(tag), "current": current, "min": minv, "max": maxv})


def _derive_sibling_key(current_key: str, *, suffix: str) -> str:
    ck = str(current_key or "")
    if ck.endswith("_current"):
        return ck[: -len("_current")] + suffix
    return ""


def _infer_progressbar_defaults_from_html_text(text: str) -> dict[str, dict[str, Any]]:
    """从 progressbar 绑定推导“缺省默认值”。

    设计目标：
    - 不依赖 data-ui-variable-defaults（即使没写 defaults 也能补齐）
    - 不覆盖显式 defaults（由上层调用保证）

    推导规则（保守但可用）：
    - current-var（lv.xxx.current_key）：默认 0
    - min-var（lv.xxx.min_key）：默认 0
    - max-var（lv.xxx.max_key）：默认 100
    - min/max 为数字常量（"0"/"100"）时不生成变量写入（因为它不是变量引用）
    """
    inferred: dict[str, dict[str, Any]] = {}
    parser = _ProgressbarBindingParser()
    parser.feed(str(text or ""))

    for entry in parser.entries:
        cur_expr = _normalize_binding_expr(entry.get("current", ""))
        min_expr = _normalize_binding_expr(entry.get("min", ""))
        max_expr = _normalize_binding_expr(entry.get("max", ""))

        cur_parsed = _try_parse_lv_dict_key(cur_expr)
        if cur_parsed is None:
            continue
        var_name, cur_key = cur_parsed

        bucket = inferred.setdefault(var_name, {})
        # current：缺省 0（安全）
        if cur_key not in bucket:
            bucket[cur_key] = 0

        # min：若为 lv 变量且 key 形如 *_min，则缺省 0；若为常量且 current_key 形如 *_current，则推导 *_min=常量
        if min_expr:
            if _is_number_literal(min_expr):
                inferred_min_key = _derive_sibling_key(cur_key, suffix="_min")
                if inferred_min_key:
                    if inferred_min_key not in bucket:
                        bucket[inferred_min_key] = _parse_number_literal(min_expr)
            else:
                min_parsed = _try_parse_lv_dict_key(min_expr)
                if min_parsed is not None:
                    min_var, min_key = min_parsed
                    if min_var == var_name and min_key.endswith("_min") and min_key not in bucket:
                        bucket[min_key] = 0

        # max：若为 lv 变量且 key 形如 *_max，则缺省 100；若为常量且 current_key 形如 *_current，则推导 *_max=常量
        if max_expr:
            if _is_number_literal(max_expr):
                inferred_max_key = _derive_sibling_key(cur_key, suffix="_max")
                if inferred_max_key:
                    if inferred_max_key not in bucket:
                        bucket[inferred_max_key] = _parse_number_literal(max_expr)
            else:
                max_parsed = _try_parse_lv_dict_key(max_expr)
                if max_parsed is not None:
                    max_var, max_key = max_parsed
                    if max_var == var_name and max_key.endswith("_max") and max_key not in bucket:
                        bucket[max_key] = 100

    return inferred


def _apply_inferred_defaults_into_existing_dict(
    *,
    base: dict[str, Any],
    inferred: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """仅对缺失/空字符串键写入 inferred 默认值。返回 (new_dict, applied_key_count)。"""
    merged = dict(base)
    applied = 0
    for k, v in inferred.items():
        key = str(k)
        if key not in merged:
            merged[key] = v
            applied += 1
            continue
        if merged.get(key) == "":
            merged[key] = v
            applied += 1
    return merged, applied


def apply_ui_variable_defaults_to_level_variables(
    *,
    workspace_root: Path,
    package_id: str,
    html_path: Path,
    dry_run: bool,
) -> list[ApplyUiDefaultsAction]:
    package_id = str(package_id or "").strip()
    if not package_id:
        raise ValueError("package_id 不能为空")

    html_path = Path(html_path)
    if not html_path.is_absolute():
        html_path = (Path(workspace_root) / html_path).resolve()
    else:
        html_path = html_path.resolve()

    result = extract_ui_variable_defaults_from_html(html_path)
    html_text = html_path.read_text(encoding="utf-8")
    inferred_by_var = _infer_progressbar_defaults_from_html_text(html_text)

    package_root = (
        Path(workspace_root).resolve()
        / "assets"
        / "资源库"
        / "项目存档"
        / package_id
    )
    var_dir = package_root / "管理配置" / "关卡变量" / "自定义变量"
    var_path = var_dir / "UI_关卡变量_自动生成.py"

    file_id = f"ui_level_variables__{package_id}"
    file_name = f"UI_关卡变量_自动生成__{package_id}"

    existing_vars = _load_level_variables_by_file_id(package_id=package_id, file_id=file_id)
    by_name: dict[str, dict] = {}
    for item in existing_vars:
        name = str(item.get("variable_name") or "").strip()
        if not name:
            continue
        if name not in by_name:
            by_name[name] = dict(item)

    # 将 HTML defaults 拆分结果写入同名 lv 字典变量 default_value（显式 defaults：覆盖）
    updated_count = 0
    created_count = 0
    inferred_applied_keys = 0
    for variable_name, incoming_default in result.split_defaults.items():
        name = str(variable_name or "").strip()
        if not name:
            continue
        if not isinstance(incoming_default, dict):
            raise ValueError(f"HTML defaults 的变量组不是字典：{name}（{type(incoming_default).__name__}）")
        incoming_default = _normalize_one_level_dict(incoming_default)

        current = by_name.get(name)
        if current is None:
            # 新建：只建字典变量（UI defaults 顶层只允许对象）
            by_name[name] = {
                "variable_id": _variable_id_for(package_id, scope="lv", variable_name=name),
                "variable_name": name,
                "variable_type": "字典",
                "default_value": dict(incoming_default),
                "is_global": True,
                "description": "UI 页面 data-ui-variable-defaults 默认值（由 extract/apply-ui-defaults 自动同步）",
                "metadata": {"category": "UI自动生成", "ui_defaults_managed_keys": sorted(incoming_default.keys())},
            }
            created_count += 1
            continue

        vtype = str(current.get("variable_type") or "").strip()
        if vtype != "字典":
            raise ValueError(f"关卡变量 {name!r} 不是字典类型（当前：{vtype or '<empty>'}），无法应用 UI defaults")
        existing_default = current.get("default_value")
        if existing_default is None:
            existing_default = {}
        if not isinstance(existing_default, dict):
            raise ValueError(
                f"关卡变量 {name!r} default_value 不是字典（当前：{type(existing_default).__name__}），无法应用 UI defaults"
            )

        merged_default = _merge_defaults_shallow(existing=existing_default, incoming=incoming_default)
        if merged_default != existing_default:
            current["default_value"] = merged_default
            updated_count += 1

        # 补齐描述（不覆盖用户自写的描述）
        desc = str(current.get("description") or "").strip()
        if not desc:
            current["description"] = "UI 页面 data-ui-variable-defaults 默认值（由 extract/apply-ui-defaults 自动同步）"

        meta = current.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
            current["metadata"] = meta
        if not str(meta.get("category") or "").strip():
            meta["category"] = "UI自动生成"
        # 记录 managed keys（用于可选 prune）
        managed_raw = meta.get("ui_defaults_managed_keys")
        managed: set[str] = set()
        if isinstance(managed_raw, list):
            managed = {str(x) for x in managed_raw if str(x or "").strip()}
        meta["ui_defaults_managed_keys"] = sorted(set(managed) | {str(k) for k in incoming_default.keys()})

    # ===== 补齐 progressbar 推导的缺省值（推导 defaults：只填缺失/空字符串，不覆盖显式）=====
    for variable_name, inferred_default in inferred_by_var.items():
        name = str(variable_name or "").strip()
        if not name:
            continue
        # 若该变量已在显式 defaults 中出现，则只补缺失 key（不覆盖）
        explicit_bucket = result.split_defaults.get(name)
        explicit_keys: set[str] = set()
        if isinstance(explicit_bucket, dict):
            explicit_keys = {str(k) for k in explicit_bucket.keys()}
        inferred_norm = _normalize_one_level_dict({k: v for k, v in inferred_default.items() if str(k) not in explicit_keys})
        if not inferred_norm:
            continue

        current = by_name.get(name)
        if current is None:
            by_name[name] = {
                "variable_id": _variable_id_for(package_id, scope="lv", variable_name=name),
                "variable_name": name,
                "variable_type": "字典",
                "default_value": dict(inferred_norm),
                "is_global": True,
                "description": "UI progressbar 绑定推导的默认值（由 apply-ui-defaults 自动补齐）",
                "metadata": {"category": "UI自动生成", "ui_defaults_managed_keys": sorted(inferred_norm.keys())},
            }
            created_count += 1
            inferred_applied_keys += len(inferred_norm)
            continue

        vtype = str(current.get("variable_type") or "").strip()
        if vtype != "字典":
            continue
        existing_default = current.get("default_value")
        if existing_default is None:
            existing_default = {}
        if not isinstance(existing_default, dict):
            continue
        merged_default2, applied = _apply_inferred_defaults_into_existing_dict(
            base=existing_default,
            inferred=inferred_norm,
        )
        if merged_default2 != existing_default:
            current["default_value"] = merged_default2
            updated_count += 1
        inferred_applied_keys += applied
        meta = current.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
            current["metadata"] = meta
        if not str(meta.get("category") or "").strip():
            meta["category"] = "UI自动生成"
        managed_raw = meta.get("ui_defaults_managed_keys")
        managed: set[str] = set()
        if isinstance(managed_raw, list):
            managed = {str(x) for x in managed_raw if str(x or "").strip()}
        meta["ui_defaults_managed_keys"] = sorted(set(managed) | {str(k) for k in inferred_norm.keys()})

    # 稳定排序：按 variable_name 排序
    final_vars = [by_name[k] for k in sorted(by_name.keys())]

    actions: list[ApplyUiDefaultsAction] = []
    if dry_run:
        actions.append(
            ApplyUiDefaultsAction(
                file_path=var_path,
                summary=(
                    f"[DRY-RUN] 将写入关卡变量文件：{file_id}（更新 {updated_count}，新增 {created_count}；"
                    f"progressbar 推导写入键 {inferred_applied_keys}；"
                    f"来源：{html_path.name}）"
                ),
            )
        )
        return actions

    _write_generated_variable_file(
        var_path,
        file_id=file_id,
        file_name=file_name,
        variables=final_vars,
    )
    actions.append(
        ApplyUiDefaultsAction(
            file_path=var_path,
            summary=(
                f"写入关卡变量文件：{file_id}（更新 {updated_count}，新增 {created_count}；"
                f"progressbar 推导写入键 {inferred_applied_keys}；来源：{html_path.name}）"
            ),
        )
    )
    return actions


def apply_ui_variable_defaults_to_level_variables_from_ui_source_dir(
    *,
    workspace_root: Path,
    package_id: str,
    ui_source_dir: Path,
    dry_run: bool,
    prune_managed_keys: bool,
) -> list[ApplyUiDefaultsAction]:
    """批量扫描 UI源码：对所有带 data-ui-variable-defaults 的 HTML 合并写入关卡变量默认值。

    设计目标：
    - 默认不删：只增/改（避免误删“无关内容”）
    - 可选删键：仅删除“曾被 defaults 管理过”的键，且本轮所有页面都不再声明该键（prune_managed_keys=True）
    """
    package_id = str(package_id or "").strip()
    if not package_id:
        raise ValueError("package_id 不能为空")

    ui_source_dir = Path(ui_source_dir)
    if not ui_source_dir.is_absolute():
        ui_source_dir = (Path(workspace_root) / ui_source_dir).resolve()
    else:
        ui_source_dir = ui_source_dir.resolve()
    if not ui_source_dir.is_dir():
        raise ValueError(f"UI源码目录不存在或不是目录：{ui_source_dir}")

    # 收集所有页面的拆分 defaults（按文件路径排序，保证写入稳定）
    explicit_by_var: dict[str, dict[str, Any]] = {}
    inferred_by_var: dict[str, dict[str, Any]] = {}
    html_files = sorted([p for p in ui_source_dir.rglob("*.html") if p.is_file()], key=lambda p: p.as_posix())
    used_html: list[Path] = []
    for html_path in html_files:
        # 约定：UI源码目录内可能出现导出派生物（如 *.flattened.html），默认跳过以避免“双写同一份 defaults”
        if html_path.name.endswith(".flattened.html"):
            continue
        text = html_path.read_text(encoding="utf-8")

        # progressbar 推导（即使页面没有 defaults 也能补齐）
        inferred_one = _infer_progressbar_defaults_from_html_text(text)
        for var_name, bucket in inferred_one.items():
            dest = inferred_by_var.setdefault(str(var_name), {})
            # 稳定：按文件顺序覆盖
            dest.update(_normalize_one_level_dict(bucket))

        extracted = try_extract_ui_variable_defaults_from_html(html_path)
        if extracted is None:
            continue
        used_html.append(html_path)
        for var_name, payload in extracted.split_defaults.items():
            if not isinstance(payload, dict):
                raise ValueError(f"HTML defaults 的变量组不是字典：{var_name}（{type(payload).__name__}）")
            payload_norm = _normalize_one_level_dict(payload)
            bucket2 = explicit_by_var.setdefault(str(var_name), {})
            # 后出现的页面覆盖同名 key（稳定：按路径排序）
            bucket2.update(payload_norm)

    if not explicit_by_var and not inferred_by_var:
        raise ValueError(f"未在 UI源码目录发现任何 data-ui-variable-defaults：{ui_source_dir}")

    package_root = (
        Path(workspace_root).resolve()
        / "assets"
        / "资源库"
        / "项目存档"
        / package_id
    )
    var_dir = package_root / "管理配置" / "关卡变量" / "自定义变量"
    var_path = var_dir / "UI_关卡变量_自动生成.py"

    file_id = f"ui_level_variables__{package_id}"
    file_name = f"UI_关卡变量_自动生成__{package_id}"

    existing_vars = _load_level_variables_by_file_id(package_id=package_id, file_id=file_id)
    by_name: dict[str, dict] = {}
    for item in existing_vars:
        name = str(item.get("variable_name") or "").strip()
        if not name:
            continue
        if name not in by_name:
            by_name[name] = dict(item)

    updated_count = 0
    created_count = 0
    pruned_key_count = 0
    inferred_applied_keys = 0

    # 统一处理：先显式 defaults 覆盖，再用 inferred 补缺失/空字符串
    all_var_names = sorted(set(explicit_by_var.keys()) | set(inferred_by_var.keys()))
    for variable_name in all_var_names:
        name = str(variable_name or "").strip()
        if not name:
            continue
        incoming_explicit = explicit_by_var.get(name, {})
        incoming_inferred = inferred_by_var.get(name, {})
        if not isinstance(incoming_explicit, dict):
            raise ValueError(f"合并后的 defaults 变量组不是字典：{name}（{type(incoming_explicit).__name__}）")
        if not isinstance(incoming_inferred, dict):
            raise ValueError(f"推导的 progressbar defaults 变量组不是字典：{name}（{type(incoming_inferred).__name__}）")

        current = by_name.get(name)
        if current is None:
            by_name[name] = {
                "variable_id": _variable_id_for(package_id, scope="lv", variable_name=name),
                "variable_name": name,
                "variable_type": "字典",
                "default_value": _apply_inferred_defaults_into_existing_dict(base=dict(incoming_explicit), inferred=dict(incoming_inferred))[0],
                "is_global": True,
                "description": "UI 页面 data-ui-variable-defaults 默认值（由 apply-ui-defaults --all 自动同步）",
                "metadata": {
                    "category": "UI自动生成",
                    "ui_defaults_managed_keys": sorted([str(k) for k in set(incoming_explicit.keys()) | set(incoming_inferred.keys())]),
                },
            }
            created_count += 1
            continue

        vtype = str(current.get("variable_type") or "").strip()
        if vtype != "字典":
            raise ValueError(f"关卡变量 {name!r} 不是字典类型（当前：{vtype or '<empty>'}），无法应用 UI defaults")

        existing_default = current.get("default_value")
        if existing_default is None:
            existing_default = {}
        if not isinstance(existing_default, dict):
            raise ValueError(
                f"关卡变量 {name!r} default_value 不是字典（当前：{type(existing_default).__name__}），无法应用 UI defaults"
            )

        meta = current.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
            current["metadata"] = meta
        if not str(meta.get("category") or "").strip():
            meta["category"] = "UI自动生成"

        managed_keys_raw = meta.get("ui_defaults_managed_keys")
        managed_keys: set[str] = set()
        if isinstance(managed_keys_raw, list):
            managed_keys = {str(x) for x in managed_keys_raw if str(x or "").strip()}

        # 显式 defaults：覆盖
        merged_default = _merge_defaults_shallow(existing=existing_default, incoming=incoming_explicit)
        # progressbar 推导：仅补缺失/空字符串
        merged_default, applied_keys = _apply_inferred_defaults_into_existing_dict(base=merged_default, inferred=incoming_inferred)
        inferred_applied_keys += applied_keys

        # 可选删：仅删“曾经被 defaults 管理过”的键，且本轮已不再声明
        if prune_managed_keys and managed_keys:
            incoming_keys = {str(k) for k in set(incoming_explicit.keys()) | set(incoming_inferred.keys())}
            for key in sorted(managed_keys):
                if key in incoming_keys:
                    continue
                if key in merged_default:
                    del merged_default[key]
                    pruned_key_count += 1

        if merged_default != existing_default:
            current["default_value"] = merged_default
            updated_count += 1

        # 扩展 managed_keys（只增不减：避免把“无关的”误标成可删；删键需要显式 prune）
        new_managed = sorted(set(managed_keys) | {str(k) for k in set(incoming_explicit.keys()) | set(incoming_inferred.keys())})
        meta["ui_defaults_managed_keys"] = new_managed

        desc = str(current.get("description") or "").strip()
        if not desc:
            current["description"] = "UI 页面 data-ui-variable-defaults 默认值（由 apply-ui-defaults --all 自动同步）"

    final_vars = [by_name[k] for k in sorted(by_name.keys())]

    actions: list[ApplyUiDefaultsAction] = []
    html_names = ", ".join([p.name for p in used_html]) if used_html else "<empty>"
    prune_text = "开启" if prune_managed_keys else "关闭"
    if dry_run:
        actions.append(
            ApplyUiDefaultsAction(
                file_path=var_path,
                summary=(
                    f"[DRY-RUN] 将写入关卡变量文件：{file_id}（更新 {updated_count}，新增 {created_count}，"
                    f"删键 {pruned_key_count}；progressbar 推导写入键 {inferred_applied_keys}；"
                    f"prune={prune_text}；来源：{html_names}）"
                ),
            )
        )
        return actions

    _write_generated_variable_file(
        var_path,
        file_id=file_id,
        file_name=file_name,
        variables=final_vars,
    )
    actions.append(
        ApplyUiDefaultsAction(
            file_path=var_path,
            summary=(
                f"写入关卡变量文件：{file_id}（更新 {updated_count}，新增 {created_count}，"
                f"删键 {pruned_key_count}；progressbar 推导写入键 {inferred_applied_keys}；"
                f"prune={prune_text}；来源：{html_names}）"
            ),
        )
    )
    return actions

