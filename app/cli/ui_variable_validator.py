from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence, Tuple

from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs
from engine.resources.level_variable_schema_view import CATEGORY_CUSTOM, LevelVariableSchemaView
from engine.type_registry import is_dict_type_name


_MOUSTACHE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_BRACED_PATTERN = re.compile(r"\{(\d+)\s*:\s*([^{}]+?)\}")

# Workbench 约定：真实进度条可通过 data-* 属性绑定变量（语法与 moustache 占位符一致，但不带 {{}} 外壳）
# - data-progress-current-var="ps.xxx"
# - data-progress-min-var="lv.xxx" / "0"
# - data-progress-max-var="lv.xxx" / "100"
_PROGRESSBAR_BINDING_ATTR_PATTERN = re.compile(
    r"\bdata-progress-(current|min|max)-var\s*=\s*(\"|')([^\"']*?)\2",
    re.IGNORECASE,
)
_NUMBER_LITERAL_PATTERN = re.compile(r"^[+-]?\d+(\.\d+)?$")


@dataclass(frozen=True, slots=True)
class UiVariableIssue:
    file_path: Path
    line: int
    column: int
    raw_expr: str
    message: str
    token: str


KeyPath = Tuple[str, ...]


def _compute_line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    if last_newline < 0:
        column = offset + 1
    else:
        column = offset - last_newline
    return line, column


def _validate_expr(expr: str, *, allowed_scopes: set[str]) -> str | None:
    expr = expr.strip()
    if not expr:
        return "占位符为空：请使用 {{ps.xxx}} / {{p1.xxx}} / {{lv.xxx}} 或 {1:ps.xxx}"

    if any(ch.isspace() for ch in expr):
        return f"占位符包含空白字符：{expr!r}"

    scope, sep, rest = expr.partition(".")
    if sep != ".":
        return f"占位符缺少作用域前缀：{expr!r}（仅允许 ps./p1~p8./lv.）"
    if scope not in allowed_scopes:
        return f"占位符作用域不支持：{scope!r}（仅允许 {sorted(allowed_scopes)}）"
    if not rest:
        return f"占位符缺少路径：{expr!r}"

    if rest.startswith(".") or rest.endswith("."):
        return f"占位符路径非法（不能以 '.' 开头/结尾）：{expr!r}"

    segments = rest.split(".")
    if any(not seg for seg in segments):
        return f"占位符路径非法（存在空段/连续 '.'）：{expr!r}"

    return None


def _iter_placeholder_matches(text: str) -> Iterable[tuple[str, str, int]]:
    """返回 (token, expr, match_start_offset)。"""
    for match in _MOUSTACHE_PATTERN.finditer(text):
        raw_expr = match.group(1)
        token = match.group(0)
        yield token, raw_expr, match.start(0)

    for match in _BRACED_PATTERN.finditer(text):
        # {1:ps.xxx} -> expr=ps.xxx
        raw_expr = match.group(2)
        token = match.group(0)
        yield token, raw_expr, match.start(0)


def _is_number_literal(text: str) -> bool:
    return bool(_NUMBER_LITERAL_PATTERN.match(str(text or "").strip()))


def _normalize_progressbar_binding_expr(raw: str) -> str:
    """归一化进度条 data-* 绑定表达式：

    - 允许误用 moustache 包裹：{{ps.xxx}} -> ps.xxx
    - 仅做外壳剥离与首尾空白归一化；语法/作用域仍由 `_validate_expr` 负责
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    match = re.fullmatch(r"\{\{\s*([^{}]+?)\s*\}\}", text)
    if match:
        return str(match.group(1) or "").strip()
    return text


def _iter_progressbar_binding_attr_matches(text: str) -> Iterable[tuple[str, str, int]]:
    """返回 (token, expr, match_start_offset)。

    注：expr 为属性值（不带引号），语法按 `_validate_expr` 走（允许 ps./p1~p8./lv.），并额外允许数字常量。
    """
    for match in _PROGRESSBAR_BINDING_ATTR_PATTERN.finditer(text):
        token = match.group(0)
        raw_expr = match.group(3)
        yield token, _normalize_progressbar_binding_expr(raw_expr), match.start(0)


def _scope_set_default() -> set[str]:
    # 口径：
    # - 推荐：lv（关卡作用域）
    return {"ps", "lv", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"}


def normalize_scope(scope: str) -> str:
    return str(scope or "").strip().lower()


def parse_variable_path(expr: str) -> tuple[str, list[str]]:
    expr = expr.strip()
    scope_raw, _sep, rest = expr.partition(".")
    scope = normalize_scope(scope_raw)
    segments = [segment for segment in rest.split(".") if segment]
    return scope, segments


def crc32_hex(text: str) -> str:
    value = zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF
    return f"{value:08x}"


def _iter_valid_placeholders_in_text(
    text: str, *, allowed_scopes: set[str]
) -> Iterable[tuple[str, str, list[str], int, str]]:
    """返回通过语法校验的占位符：

    (token, scope, segments, match_start_offset, raw_expr)
    """
    for token, raw_expr, start_offset in _iter_placeholder_matches(text):
        message = _validate_expr(raw_expr, allowed_scopes=allowed_scopes)
        if message is not None:
            continue
        scope, segments = parse_variable_path(raw_expr)
        if scope not in allowed_scopes or not segments:
            continue
        yield token, scope, segments, start_offset, raw_expr.strip()


def _iter_valid_progressbar_bindings_in_text(
    text: str, *, allowed_scopes: set[str]
) -> Iterable[tuple[str, str, list[str], int, str]]:
    """返回通过语法校验的进度条绑定：

    (token, scope, segments, match_start_offset, raw_expr)
    """
    for token, raw_expr, start_offset in _iter_progressbar_binding_attr_matches(text):
        expr = _normalize_progressbar_binding_expr(raw_expr)
        if not expr:
            continue
        if _is_number_literal(expr):
            continue
        message = _validate_expr(expr, allowed_scopes=allowed_scopes)
        if message is not None:
            continue
        scope, segments = parse_variable_path(expr)
        if scope not in allowed_scopes or not segments:
            continue
        # 进度条 binding 不支持“字典键路径”（lv.dict.key）：
        # 真源结构仅有 (group + name) 字符串引用，没有 dict_key 字段，因此这里强制要求仅一段变量名。
        if len(segments) != 1:
            continue
        yield token, scope, segments, start_offset, expr


def _extract_dict_at_path(root: object, path: KeyPath) -> object | None:
    current = root
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _build_level_variable_name_index_for_package(*, package_id: str) -> dict[str, list[dict]]:
    """构建 {variable_name: [payload...]} 索引，仅包含普通自定义变量（排除局内存档变量）。"""
    schema_view = LevelVariableSchemaView()
    schema_view.set_active_package_id(str(package_id))
    all_vars = schema_view.get_all_variables()
    if not isinstance(all_vars, dict):
        return {}
    results: dict[str, list[dict]] = {}
    for _var_id, payload in all_vars.items():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("source_directory") or "").strip() != CATEGORY_CUSTOM:
            continue
        name = str(payload.get("variable_name") or "").strip()
        if not name:
            continue
        results.setdefault(name, []).append(payload)
    return results


def _build_custom_variable_name_index_for_package_by_owner(
    *,
    package_id: str,
    owner: str,
) -> dict[str, list[dict]]:
    """构建 {variable_name: [payload...]} 索引：仅包含普通自定义变量（排除局内存档变量），且 owner 匹配。

    说明：
    - 自定义变量注册表（单一真源）会派生虚拟变量文件并填充 payload.owner；
    - UI 占位符的 scope（lv/ps/p1..p8）与 payload.owner（level/player）是两套口径：
      - lv.* -> owner=level
      - ps/pN.* -> owner=player
    """
    package_id_text = str(package_id or "").strip()
    owner_text = str(owner or "").strip().lower()
    if not package_id_text or not owner_text:
        return {}

    schema_view = LevelVariableSchemaView()
    schema_view.set_active_package_id(package_id_text)
    all_vars = schema_view.get_all_variables()
    if not isinstance(all_vars, dict):
        return {}

    results: dict[str, list[dict]] = {}
    for _var_id, payload in all_vars.items():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("source_directory") or "").strip() != CATEGORY_CUSTOM:
            continue
        payload_owner = str(payload.get("owner") or "").strip().lower()
        if payload_owner != owner_text:
            continue
        name = str(payload.get("variable_name") or "").strip()
        if not name:
            continue
        results.setdefault(name, []).append(payload)
    return results


def _resolve_variable_file_payloads_for_package(*, package_id: str, refs: Sequence[str]) -> list[dict]:
    """按 file_id/source_path/stem 匹配引用，返回命中的变量 payload 列表（按引用顺序合并）。"""
    schema_view = LevelVariableSchemaView()
    schema_view.set_active_package_id(str(package_id))
    variable_files = schema_view.get_all_variable_files() or {}

    def _match_one(ref: str) -> list[dict]:
        ref_text = str(ref or "").strip()
        if not ref_text:
            return []
        normalized_ref = ref_text.replace("\\", "/")
        ref_stem = Path(normalized_ref).stem

        for file_id, file_info in variable_files.items():
            file_id_text = str(file_id or "").strip()
            if not file_id_text:
                continue
            candidates: list[str] = [file_id_text]
            source_path_value = getattr(file_info, "source_path", None)
            if isinstance(source_path_value, str) and source_path_value.strip():
                candidates.append(source_path_value.strip())
                candidates.append(Path(source_path_value.strip()).stem)

            for candidate in candidates:
                cand_text = str(candidate).replace("\\", "/").strip()
                if not cand_text:
                    continue
                if cand_text == normalized_ref or cand_text == ref_text or Path(cand_text).stem == ref_stem:
                    variables_value = getattr(file_info, "variables", None)
                    if not isinstance(variables_value, list):
                        return []
                    return [dict(v) for v in variables_value if isinstance(v, dict)]
        return []

    results_by_id: dict[str, dict] = {}
    ordered: list[str] = []
    for ref in refs:
        for payload in _match_one(ref):
            var_id = str(payload.get("variable_id") or "").strip()
            if not var_id:
                continue
            if var_id not in results_by_id:
                results_by_id[var_id] = payload
                ordered.append(var_id)
    return [results_by_id[var_id] for var_id in ordered]


@dataclass(frozen=True, slots=True)
class PlayerTemplateSnapshot:
    template_id: str
    template_name: str
    source_path: str
    payload: dict


def _discover_player_templates_for_package(
    *,
    workspace_root: Path,
    package_id: str,
    resource_manager: object | None = None,
    package_index_manager: object | None = None,
) -> list[PlayerTemplateSnapshot]:
    """发现当前项目存档“实际使用的”玩家模板集合（覆盖 共享 + 当前存档）。

    优先级：
    1) 使用 PackageIndex.resources.combat_presets.player_templates（最接近导出/生成链路）。
    2) fallback：扫描当前项目存档目录下 `战斗预设/玩家模板/*.json`（便于离线目录调试）。
    """
    package_id_text = str(package_id or "").strip()
    if not package_id_text:
        return []

    workspace = Path(workspace_root).resolve()

    # --- 1) 按 PackageIndex（共享 + 当前包作用域）
    if resource_manager is None or package_index_manager is None:
        from engine.resources import build_resource_index_context

        resource_manager, package_index_manager = build_resource_index_context(workspace)

    rm = resource_manager
    pim = package_index_manager

    rebuild_index = getattr(rm, "rebuild_index", None)
    if callable(rebuild_index):
        rebuild_index(active_package_id=package_id_text)

    invalidate_cache = getattr(pim, "invalidate_package_index_cache", None)
    if callable(invalidate_cache):
        invalidate_cache(package_id_text)

    load_index = getattr(pim, "load_package_index", None)
    if callable(load_index):
        package_index = load_index(package_id_text)
        if package_index is not None:
            resources_obj = getattr(package_index, "resources", None)
            combat_presets_value = getattr(resources_obj, "combat_presets", None) if resources_obj is not None else None
            template_ids: list[str] = []
            if isinstance(combat_presets_value, dict):
                raw_ids = combat_presets_value.get("player_templates", [])
                if isinstance(raw_ids, list):
                    for value in raw_ids:
                        text = str(value or "").strip()
                        if text and text not in template_ids:
                            template_ids.append(text)

            if template_ids:
                from engine.configs.resource_types import ResourceType

                id_to_path: dict[str, Path] = {}
                list_paths = getattr(rm, "list_resource_file_paths", None)
                if callable(list_paths):
                    raw_paths = list_paths(ResourceType.PLAYER_TEMPLATE) or {}
                    if isinstance(raw_paths, dict):
                        for k, v in raw_paths.items():
                            if isinstance(v, Path):
                                id_to_path[str(k)] = v

                snapshots: list[PlayerTemplateSnapshot] = []
                load_resource = getattr(rm, "load_resource", None)
                if callable(load_resource):
                    for template_id in template_ids:
                        payload = load_resource(ResourceType.PLAYER_TEMPLATE, template_id)
                        if not isinstance(payload, dict):
                            continue
                        template_name = str(payload.get("template_name") or payload.get("name") or template_id).strip()
                        if not template_name:
                            template_name = template_id
                        path = id_to_path.get(template_id)
                        source_path = str(path) if isinstance(path, Path) else template_id
                        snapshots.append(
                            PlayerTemplateSnapshot(
                                template_id=template_id,
                                template_name=template_name,
                                source_path=source_path,
                                payload=payload,
                            )
                        )
                if snapshots:
                    return snapshots

    # --- 2) fallback：仅当前包目录
    package_root = (
        workspace
        / "assets"
        / "资源库"
        / "项目存档"
        / package_id_text
    )
    template_dir = package_root / "战斗预设" / "玩家模板"
    if not template_dir.is_dir():
        return []

    fallback_snapshots: list[PlayerTemplateSnapshot] = []
    for template_path in sorted([p for p in template_dir.glob("*.json") if p.is_file()], key=lambda p: p.as_posix()):
        template_json = json.loads(template_path.read_text(encoding="utf-8"))
        if not isinstance(template_json, dict):
            continue
        template_id = str(template_json.get("template_id") or template_json.get("id") or template_path.stem).strip()
        if not template_id:
            template_id = template_path.stem
        template_name = str(template_json.get("template_name") or template_json.get("name") or template_id).strip() or template_id
        fallback_snapshots.append(
            PlayerTemplateSnapshot(
                template_id=template_id,
                template_name=template_name,
                source_path=str(template_path),
                payload=template_json,
            )
        )
    return fallback_snapshots


def validate_ui_html_file(file_path: Path, *, allowed_scopes: set[str] | None = None) -> list[UiVariableIssue]:
    text = file_path.read_text(encoding="utf-8")
    issues: list[UiVariableIssue] = []
    allowed = allowed_scopes or _scope_set_default()

    for token, raw_expr, start_offset in _iter_placeholder_matches(text):
        message = _validate_expr(raw_expr, allowed_scopes=allowed)
        if message is None:
            continue
        line, column = _compute_line_col(text, start_offset)
        issues.append(
            UiVariableIssue(
                file_path=file_path,
                line=line,
                column=column,
                raw_expr=raw_expr.strip(),
                message=message,
                token=token,
            )
        )

    # 进度条变量绑定（HTML data-* 属性）：语法与占位符一致，但允许数字常量（用于 min/max）。
    for token, raw_expr, start_offset in _iter_progressbar_binding_attr_matches(text):
        expr = _normalize_progressbar_binding_expr(raw_expr)
        if not expr:
            line, column = _compute_line_col(text, start_offset)
            issues.append(
                UiVariableIssue(
                    file_path=file_path,
                    line=line,
                    column=column,
                    raw_expr="",
                    message="进度条绑定值为空：请设置 ps./p1~p8./lv. 变量路径，或使用数字常量（如 0/100）。",
                    token=token,
                )
            )
            continue
        if _is_number_literal(expr):
            continue
        message = _validate_expr(expr, allowed_scopes=allowed)
        if message is not None:
            line, column = _compute_line_col(text, start_offset)
            issues.append(
                UiVariableIssue(
                    file_path=file_path,
                    line=line,
                    column=column,
                    raw_expr=expr,
                    message=message,
                    token=token,
                )
            )
            continue

        # 关键限制：进度条绑定只支持标量变量名（单段），不支持字典键路径（lv.dict.key）。
        # 进度条真源结构仅有 (group + name) 字符串引用，没有 dict_key 字段。
        scope, segments = parse_variable_path(expr)
        if len(segments) != 1:
            base = str(segments[0])
            key_path = ".".join(str(x) for x in segments[1:])
            mirror_name = base + "__" + "__".join(str(x) for x in segments[1:])
            suggestion = f"{scope}.{mirror_name}"
            line, column = _compute_line_col(text, start_offset)
            issues.append(
                UiVariableIssue(
                    file_path=file_path,
                    line=line,
                    column=column,
                    raw_expr=expr,
                    token=token,
                    message=(
                        f"进度条绑定不支持字典键路径：{expr!r}。\n"
                        "进度条只能绑定标量变量名（lv/ps/p1~p8 + 单段变量名），变量名中不允许再包含 '.'。\n"
                        f"建议：改为镜像标量变量（例如 {suggestion!r}），"
                        f"并在节点图里将字典 {base!r} 的键路径 {key_path!r} 同步写入该标量变量。"
                    ),
                )
            )

    return issues


def iter_ui_html_files(ui_source_dir: Path) -> Iterable[Path]:
    if not ui_source_dir.exists():
        return []
    if not ui_source_dir.is_dir():
        raise ValueError(f"UI源码路径存在但不是目录：{ui_source_dir}")
    # 约定：UI源码目录内可能存在 __hook_tests__ 夹具（用于 hooks/单测），不参与项目 UI 校验。
    html_files: list[Path] = []
    for p in ui_source_dir.rglob("*.html"):
        if not p.is_file():
            continue
        if "__hook_tests__" in p.parts:
            continue
        html_files.append(p)
    return sorted(html_files)


def validate_ui_source_dir(
    ui_source_dir: Path,
    *,
    allowed_scopes: set[str],
    workspace_root: Path | None = None,
    package_id: str | None = None,
    resource_manager: object | None = None,
    package_index_manager: object | None = None,
) -> list[UiVariableIssue]:
    all_issues: list[UiVariableIssue] = []
    html_files = list(iter_ui_html_files(ui_source_dir))
    for file_path in html_files:
        all_issues.extend(validate_ui_html_file(file_path, allowed_scopes=allowed_scopes))

    # 若语法已失败，先返回（避免后续存在性校验刷屏）
    if all_issues:
        return all_issues

    package_id_text = str(package_id or "").strip()
    if not package_id_text:
        return all_issues

    # ===== 关卡变量（lv）存在性 + 字典键路径 =====
    lv_index = _build_level_variable_name_index_for_package(package_id=package_id_text)
    for file_path in html_files:
        text = file_path.read_text(encoding="utf-8")
        refs = list(_iter_valid_placeholders_in_text(text, allowed_scopes=allowed_scopes))
        refs.extend(list(_iter_valid_progressbar_bindings_in_text(text, allowed_scopes=allowed_scopes)))
        for token, scope, segments, start_offset, raw_expr in refs:
            if scope != "lv":
                continue
            var_name = segments[0]
            key_path: KeyPath = tuple(segments[1:])

            candidates = lv_index.get(var_name, [])
            if not candidates:
                line, column = _compute_line_col(text, start_offset)
                all_issues.append(
                    UiVariableIssue(
                        file_path=file_path,
                        line=line,
                        column=column,
                        raw_expr=raw_expr,
                        token=token,
                        message=(
                            f"lv 变量未定义：{var_name!r}。\n"
                            "建议：在【管理配置/关卡变量/自定义变量】定义该变量，或运行："
                            f"python -X utf8 -m app.cli.graph_tools validate-ui --package-id \"{package_id_text}\" --fix"
                        ),
                    )
                )
                continue

            # 说明：
            # - 关卡变量最终以 variable_id 被实例引用，但 UI 占位符语法仅携带 variable_name；
            # - 当同名变量在多个文件中重复出现时，若其类型与默认结构一致，则 UI 语义等价，可视为合法；
            # - 若存在结构不一致（例如类型不同、字典键缺失等），则仍需报错避免 UI 运行期出现不可预期来源。
            payload = candidates[0]
            if len(candidates) > 1:
                types = {str(p.get("variable_type") or "").strip() for p in candidates if isinstance(p, dict)}
                if len(types) != 1:
                    line, column = _compute_line_col(text, start_offset)
                    source_files = sorted(
                        {
                            str(p.get("source_path") or p.get("source_file") or p.get("variable_file_id") or "")
                            for p in candidates
                        }
                    )
                    source_files = [x for x in source_files if x]
                    all_issues.append(
                        UiVariableIssue(
                            file_path=file_path,
                            line=line,
                            column=column,
                            raw_expr=raw_expr,
                            token=token,
                            message=(
                                f"lv 同名变量类型不一致：{var_name!r}。\n"
                                f"- 类型集合：{sorted(types)}\n"
                                f"- 来源文件：{', '.join(source_files)}\n"
                                "建议：统一类型/默认结构，或重命名以避免 UI 来源不明确。"
                            ),
                        )
                    )
                    continue
                # 类型一致时允许重复；若后续存在键路径，则要求所有候选都满足键路径。
                payload = candidates[0]

            if not key_path:
                continue

            vtype = str(payload.get("variable_type") or "").strip()
            if not is_dict_type_name(vtype):
                line, column = _compute_line_col(text, start_offset)
                all_issues.append(
                    UiVariableIssue(
                        file_path=file_path,
                        line=line,
                        column=column,
                        raw_expr=raw_expr,
                        token=token,
                        message=(
                            f"lv 变量 {var_name!r} 不是字典类型，不能使用键路径：{'.'.join(key_path)}"
                            f"（当前类型：{vtype or '<empty>'}）"
                        ),
                    )
                )
                continue

            def _has_key_path_in_payload(p: dict) -> bool:
                if not key_path:
                    return True
                dv = p.get("default_value")
                lp = _extract_dict_at_path(dv, key_path[:-1]) if len(key_path) > 1 else dv
                leaf = key_path[len(key_path) - 1]
                return isinstance(lp, dict) and leaf in lp

            # 单定义：照旧检查；重复定义：要求所有候选都满足键路径（否则 UI 仍然不确定会命中哪个结构）。
            if len(candidates) == 1:
                if not _has_key_path_in_payload(payload):
                    line, column = _compute_line_col(text, start_offset)
                    all_issues.append(
                        UiVariableIssue(
                            file_path=file_path,
                            line=line,
                            column=column,
                            raw_expr=raw_expr,
                            token=token,
                            message=(
                                f"lv 字典键不存在：{var_name!r} 缺少键路径 {'.'.join(key_path)!r}。\n"
                                "建议：在【自定义变量注册表.py】补齐该字典的 default_value 结构（唯一真源）。"
                            ),
                        )
                    )
                continue

            missing_sources: list[str] = []
            for p in candidates:
                if not isinstance(p, dict):
                    continue
                if not _has_key_path_in_payload(p):
                    src = str(p.get("source_path") or p.get("source_file") or p.get("variable_file_id") or "").strip()
                    missing_sources.append(src or "<unknown>")
            if missing_sources:
                line, column = _compute_line_col(text, start_offset)
                all_issues.append(
                    UiVariableIssue(
                        file_path=file_path,
                        line=line,
                        column=column,
                        raw_expr=raw_expr,
                        token=token,
                        message=(
                            f"lv 字典键不存在：{var_name!r} 缺少键路径 {'.'.join(key_path)!r}。\n"
                            f"缺失来源（同名变量的部分定义未包含该键）：{', '.join(sorted(set(missing_sources)))}\n"
                            "建议：统一补齐这些定义的默认值结构，或重命名避免 UI 来源不明确。"
                        ),
                    )
                )

    # ===== 玩家变量（ps/p1~p8）：注册表真源（owner=player）存在性 + 字典键路径 =====
    if workspace_root is None:
        return all_issues

    # 先快速探测：是否存在玩家占位符；若没有，跳过玩家变量校验
    first_player_placeholder: tuple[Path, int, str] | None = None  # (file_path, start_offset, raw_expr)
    for file_path in html_files:
        text = file_path.read_text(encoding="utf-8")
        refs2 = list(_iter_valid_placeholders_in_text(text, allowed_scopes=allowed_scopes))
        refs2.extend(list(_iter_valid_progressbar_bindings_in_text(text, allowed_scopes=allowed_scopes)))
        for _token, scope, _segments, start_offset, raw_expr in refs2:
            if scope == "lv":
                continue
            first_player_placeholder = (file_path, start_offset, raw_expr)
            break
        if first_player_placeholder is not None:
            break

    if first_player_placeholder is None:
        return all_issues

    player_index = _build_custom_variable_name_index_for_package_by_owner(
        package_id=package_id_text,
        owner="player",
    )
    for file_path in html_files:
        text = file_path.read_text(encoding="utf-8")
        refs3 = list(_iter_valid_placeholders_in_text(text, allowed_scopes=allowed_scopes))
        refs3.extend(list(_iter_valid_progressbar_bindings_in_text(text, allowed_scopes=allowed_scopes)))
        for token, scope, segments, start_offset, raw_expr in refs3:
            if scope == "lv":
                continue
            var_name = segments[0]
            key_path = tuple(segments[1:])
            candidates = player_index.get(var_name, [])
            if not candidates:
                line, column = _compute_line_col(text, start_offset)
                all_issues.append(
                    UiVariableIssue(
                        file_path=file_path,
                        line=line,
                        column=column,
                        raw_expr=raw_expr,
                        token=token,
                        message=(
                            f"玩家变量未定义：{var_name!r}。\n"
                            "建议：在【管理配置/关卡变量/自定义变量注册表.py】补齐 owner='player' 的变量声明/默认结构。"
                        ),
                    )
                )
                continue

            payload = candidates[0]
            if len(candidates) > 1:
                types = {str(p.get("variable_type") or "").strip() for p in candidates if isinstance(p, dict)}
                if len(types) != 1:
                    line, column = _compute_line_col(text, start_offset)
                    source_files = sorted(
                        {
                            str(p.get("source_path") or p.get("source_file") or p.get("variable_file_id") or "")
                            for p in candidates
                        }
                    )
                    source_files = [x for x in source_files if x]
                    all_issues.append(
                        UiVariableIssue(
                            file_path=file_path,
                            line=line,
                            column=column,
                            raw_expr=raw_expr,
                            token=token,
                            message=(
                                f"玩家同名变量类型不一致：{var_name!r}。\n"
                                f"- 类型集合：{sorted(types)}\n"
                                f"- 来源文件：{', '.join(source_files)}\n"
                                "建议：统一类型/默认结构，或重命名以避免 UI 来源不明确。"
                            ),
                        )
                    )
                    continue
                payload = candidates[0]

            if not key_path:
                continue

            vtype = str(payload.get("variable_type") or "").strip()
            if not is_dict_type_name(vtype):
                line, column = _compute_line_col(text, start_offset)
                all_issues.append(
                    UiVariableIssue(
                        file_path=file_path,
                        line=line,
                        column=column,
                        raw_expr=raw_expr,
                        token=token,
                        message=(
                            f"玩家变量不是字典类型：{var_name!r}，但 UI 使用了键路径 {'.'.join(key_path)!r}。\n"
                            "建议：将变量类型改为 typed dict alias（例如 字符串-字符串字典），并补齐 default_value 键集合。"
                        ),
                    )
                )
                continue

            default_value = payload.get("default_value")
            leaf_parent = _extract_dict_at_path(default_value, key_path[:-1]) if len(key_path) > 1 else default_value
            leaf = key_path[len(key_path) - 1]
            if not isinstance(leaf_parent, dict) or leaf not in leaf_parent:
                line, column = _compute_line_col(text, start_offset)
                all_issues.append(
                    UiVariableIssue(
                        file_path=file_path,
                        line=line,
                        column=column,
                        raw_expr=raw_expr,
                        token=token,
                        message=(
                            f"玩家字典键不存在：{var_name!r} 缺少键路径 {'.'.join(key_path)!r}。\n"
                            "建议：在【自定义变量注册表.py】补齐 default_value 的键集合（typed dict）。"
                        ),
                    )
                )

    return all_issues


def format_ui_issues_text(issues: Sequence[UiVariableIssue]) -> str:
    if not issues:
        return "✅ UI 变量校验通过：未发现非法占位符。\n"

    lines: list[str] = []
    lines.append(f"❌ UI 变量校验失败：发现 {len(issues)} 个问题。\n")
    for issue in issues:
        rel = str(issue.file_path)
        lines.append(f"- {rel}:{issue.line}:{issue.column}")
        lines.append(f"  - token: {issue.token}")
        lines.append(f"  - expr: {issue.raw_expr}")
        lines.append(f"  - {issue.message}")
    lines.append("")
    return "\n".join(lines)

