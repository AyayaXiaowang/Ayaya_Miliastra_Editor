from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.configs.resource_types import ResourceType


_UI_TEXT_PLACEHOLDER_RE = re.compile(r"\{\{([^{}]+)\}\}")


@dataclass(frozen=True, slots=True)
class _UiTextPlaceholderOccurrence:
    raw: str
    expr: str
    json_path: str


class _UiWorkbenchBridgePlaceholderValidationMixin:
    # --------------------------------------------------------------------- variable catalog (lv/ps)
    def get_variable_catalog_payload(self) -> dict:
        """返回当前项目可用于 UI 占位符的变量清单（lv/ps）。"""
        ok, ctx_or_error = self._try_build_placeholder_validation_context()
        if not ok:
            raise RuntimeError(str(ctx_or_error or "无法构建变量上下文"))
        ctx: dict[str, object] = ctx_or_error

        name_to_payloads: dict[str, list[dict]] = ctx["name_to_payloads"]  # type: ignore[assignment]
        variable_files: dict[str, object] = ctx["variable_files"]  # type: ignore[assignment]
        shared_custom_variable_file_ids: set[str] = ctx["shared_custom_variable_file_ids"]  # type: ignore[assignment]
        referenced_level_variable_ids: set[str] = ctx["referenced_level_variable_ids"]  # type: ignore[assignment]
        player_custom_variable_file_ids: set[str] = ctx["player_custom_variable_file_ids"]  # type: ignore[assignment]
        player_template_ids: list[str] = ctx["player_template_ids"]  # type: ignore[assignment]
        player_template_to_custom_file: dict[str, str] = ctx["player_template_to_custom_file"]  # type: ignore[assignment]

        from engine.resources.level_variable_schema_view import CATEGORY_CUSTOM, CATEGORY_INGAME_SAVE

        lv_items: list[dict[str, object]] = []
        ps_items: list[dict[str, object]] = []
        conflicts: list[str] = []

        for variable_name, payloads in name_to_payloads.items():
            if len(payloads) != 1:
                conflicts.append(variable_name)
                continue
            variable_payload = payloads[0]
            variable_id = str(variable_payload.get("variable_id") or "").strip()
            variable_file_id = str(variable_payload.get("variable_file_id") or "").strip()
            variable_type = str(variable_payload.get("variable_type") or "").strip()
            default_value = variable_payload.get("default_value")

            file_info = variable_files.get(variable_file_id)
            file_category = str(getattr(file_info, "category", "") or "") if file_info is not None else ""
            file_source_path = str(getattr(file_info, "source_path", "") or "") if file_info is not None else ""

            if file_category == CATEGORY_INGAME_SAVE:
                continue
            if file_category and file_category != CATEGORY_CUSTOM:
                continue

            lv_allowed = bool(
                variable_file_id
                and (
                    (variable_file_id in shared_custom_variable_file_ids)
                    or (variable_file_id in referenced_level_variable_ids)
                    or (variable_id and variable_id in referenced_level_variable_ids)
                )
            )
            ps_allowed = bool(variable_file_id and (variable_file_id in player_custom_variable_file_ids))

            item = {
                "variable_name": variable_name,
                "variable_type": variable_type,
                "default_value": default_value,
                "variable_id": variable_id,
                "variable_file_id": variable_file_id,
                "source_path": file_source_path,
                "ambiguous_without_prefix": bool(lv_allowed and ps_allowed),
            }

            if lv_allowed:
                lv_items.append(item)
            if ps_allowed:
                ps_items.append(item)

        lv_items.sort(key=lambda it: str(it.get("variable_name", "")).casefold())
        ps_items.sort(key=lambda it: str(it.get("variable_name", "")).casefold())
        conflicts.sort(key=lambda s: str(s).casefold())

        return {
            "ok": True,
            "current_package_id": str(ctx["current_package_id"]),
            "lv": lv_items,
            "ps": ps_items,
            "name_conflicts": conflicts,
            "debug_chain": {
                "referenced_level_variable_file_ids": sorted(referenced_level_variable_ids),
                "shared_custom_variable_file_ids_count": len(shared_custom_variable_file_ids),
                "player_template_ids": player_template_ids,
                "player_template_to_custom_file": player_template_to_custom_file,
                "player_custom_variable_file_ids": sorted(player_custom_variable_file_ids),
            },
        }

    def _try_build_placeholder_validation_context(self) -> tuple[bool, dict[str, object] | str]:
        """构建 UI 占位符校验所需的“可用变量集合”上下文（不扫描 UI payload）。

        用途：
        - Workbench 变量浏览器
        - 占位符校验的解释性错误信息（解析链路）
        """
        main_window = self._main_window
        if main_window is None:
            return False, "主窗口未绑定，无法构建 UI 占位符上下文。"

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            return False, "主窗口缺少 package_controller，无法构建 UI 占位符上下文。"

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            return False, "请先切换到某个【项目存档】再导入/导出（当前为 <共享资源>/未选择）。"

        resource_manager = getattr(package_controller, "resource_manager", None)
        if resource_manager is None:
            return False, "package_controller 缺少 resource_manager，无法构建 UI 占位符上下文。"

        package_index = getattr(package_controller, "current_package_index", None)
        if package_index is None:
            package_index_manager = getattr(package_controller, "package_index_manager", None)
            if package_index_manager is None:
                return False, "package_controller 缺少 package_index_manager，无法构建 UI 占位符上下文。"
            package_index = package_index_manager.load_package_index(current_package_id)
            if package_index is None:
                return False, f"未找到项目存档索引：{current_package_id}"

        from engine.resources.level_variable_schema_view import CATEGORY_CUSTOM, get_default_level_variable_schema_view

        schema_view = get_default_level_variable_schema_view()
        set_active = getattr(schema_view, "set_active_package_id", None)
        if callable(set_active):
            set_active(current_package_id)

        variable_files = schema_view.get_all_variable_files() or {}
        all_variables = schema_view.get_all_variables() or {}

        name_to_payloads: dict[str, list[dict]] = {}
        for _var_id, payload in all_variables.items():
            if not isinstance(payload, dict):
                continue
            variable_name = str(payload.get("variable_name") or payload.get("name") or "").strip()
            if not variable_name:
                continue
            name_to_payloads.setdefault(variable_name, []).append(payload)

        current_roots = getattr(resource_manager, "get_current_resource_roots", None)
        if not callable(current_roots):
            return False, "resource_manager 不支持 get_current_resource_roots，无法确定共享根。"
        roots = list(current_roots())
        if not roots:
            return False, "resource_manager 当前作用域下资源根目录为空，无法构建 UI 占位符上下文。"

        shared_root_dir = Path(roots[0]).resolve()
        shared_level_variable_dir = (shared_root_dir / "管理配置" / "关卡变量").resolve()

        shared_custom_variable_file_ids: set[str] = set()
        for file_id, info in variable_files.items():
            absolute_path = getattr(info, "absolute_path", None)
            if not isinstance(absolute_path, Path):
                continue
            abs_path = absolute_path.resolve()
            if not abs_path.is_relative_to(shared_level_variable_dir):
                continue
            category = str(getattr(info, "category", "") or "")
            if category == CATEGORY_CUSTOM:
                shared_custom_variable_file_ids.add(str(file_id))

        referenced_level_variable_ids: set[str] = set()
        resources = getattr(package_index, "resources", None)
        management_refs = getattr(resources, "management", {}) if resources is not None else {}
        if isinstance(management_refs, dict):
            raw_refs = management_refs.get("level_variables", [])
            if isinstance(raw_refs, list):
                for entry in raw_refs:
                    if isinstance(entry, str) and entry.strip():
                        referenced_level_variable_ids.add(entry.strip())

        player_custom_variable_file_ids: set[str] = set()
        player_template_to_custom_file: dict[str, str] = {}
        combat_presets = getattr(resources, "combat_presets", {}) if resources is not None else {}
        player_template_ids: list[str] = []
        if isinstance(combat_presets, dict):
            raw_player_templates = combat_presets.get("player_templates", [])
            if isinstance(raw_player_templates, list):
                for entry in raw_player_templates:
                    if isinstance(entry, str) and entry.strip() and entry.strip() not in player_template_ids:
                        player_template_ids.append(entry.strip())

        for player_template_id in player_template_ids:
            payload = resource_manager.load_resource(ResourceType.PLAYER_TEMPLATE, player_template_id)
            if not isinstance(payload, dict):
                continue
            meta = payload.get("metadata")
            if not isinstance(meta, dict):
                continue
            custom_file_id = str(meta.get("custom_variable_file") or "").strip()
            if custom_file_id:
                player_custom_variable_file_ids.add(custom_file_id)
                player_template_to_custom_file[player_template_id] = custom_file_id

        return True, {
            "current_package_id": current_package_id,
            "resource_manager": resource_manager,
            "package_index": package_index,
            "variable_files": variable_files,
            "name_to_payloads": name_to_payloads,
            "shared_custom_variable_file_ids": shared_custom_variable_file_ids,
            "referenced_level_variable_ids": referenced_level_variable_ids,
            "player_template_ids": player_template_ids,
            "player_custom_variable_file_ids": player_custom_variable_file_ids,
            "player_template_to_custom_file": player_template_to_custom_file,
        }

    def try_validate_text_placeholders_in_ui_payload(
        self,
        ui_payload: dict,
        *,
        autofix_missing_lv_variables: bool = False,
    ) -> tuple[bool, str]:
        """校验 UI JSON payload 中的 `{{...}}` 文本占位符是否引用到当前项目可用的自定义变量。"""
        if bool(autofix_missing_lv_variables):
            return (
                False,
                "autofix_missing_lv_variables 已移除（方案 S：自定义变量只在注册表单文件真源定义）。"
                "请在【自定义变量注册表.py】补齐缺失变量/默认结构，并确保玩家模板引用稳定变量文件。",
            )
        if not isinstance(ui_payload, dict):
            return False, "UI payload 必须是对象（dict）。"

        main_window = self._main_window
        if main_window is None:
            return False, "主窗口未绑定，无法校验 UI 占位符。"

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            return False, "主窗口缺少 package_controller，无法校验 UI 占位符。"

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            return False, "请先切换到某个【项目存档】再导入/导出（当前为 <共享资源>/未选择）。"

        resource_manager = getattr(package_controller, "resource_manager", None)
        if resource_manager is None:
            return False, "package_controller 缺少 resource_manager，无法校验 UI 占位符。"

        package_index = getattr(package_controller, "current_package_index", None)
        if package_index is None:
            package_index_manager = getattr(package_controller, "package_index_manager", None)
            if package_index_manager is None:
                return False, "package_controller 缺少 package_index_manager，无法校验 UI 占位符。"
            package_index = package_index_manager.load_package_index(current_package_id)
            if package_index is None:
                return False, f"未找到项目存档索引：{current_package_id}"

        from engine.resources.level_variable_schema_view import (
            CATEGORY_CUSTOM,
            CATEGORY_INGAME_SAVE,
            get_default_level_variable_schema_view,
        )

        schema_view = get_default_level_variable_schema_view()
        set_active = getattr(schema_view, "set_active_package_id", None)
        if callable(set_active):
            set_active(current_package_id)

        def _reload_schema_maps() -> tuple[dict, dict, dict[str, list[dict]]]:
            variable_files_local = schema_view.get_all_variable_files() or {}
            all_variables_local = schema_view.get_all_variables() or {}
            name_to_payloads_local: dict[str, list[dict]] = {}
            for _var_id, payload in all_variables_local.items():
                if not isinstance(payload, dict):
                    continue
                variable_name_value = str(payload.get("variable_name") or payload.get("name") or "").strip()
                if not variable_name_value:
                    continue
                name_to_payloads_local.setdefault(variable_name_value, []).append(payload)
            return variable_files_local, all_variables_local, name_to_payloads_local

        variable_files, _all_variables, name_to_payloads = _reload_schema_maps()

        # 共享根下的“关卡变量文件”自动可用（与 PackageView.management.level_variables 的聚合语义保持一致）
        current_roots = getattr(resource_manager, "get_current_resource_roots", None)
        if not callable(current_roots):
            return False, "resource_manager 不支持 get_current_resource_roots，无法确定共享根。"
        roots = list(current_roots())
        if not roots:
            return False, "resource_manager 当前作用域下资源根目录为空，无法校验。"
        shared_root_dir = Path(roots[0]).resolve()
        shared_level_variable_dir = (shared_root_dir / "管理配置" / "关卡变量").resolve()
        project_level_variable_dir = (
            self._workspace_root
            / "assets"
            / "资源库"
            / "项目存档"
            / current_package_id
            / "管理配置"
            / "关卡变量"
        ).resolve()

        shared_custom_variable_file_ids: set[str] = set()
        for file_id, info in variable_files.items():
            absolute_path = getattr(info, "absolute_path", None)
            if not isinstance(absolute_path, Path):
                continue
            abs_path = absolute_path.resolve()
            if not abs_path.is_relative_to(shared_level_variable_dir):
                continue
            category = str(getattr(info, "category", "") or "")
            if category == CATEGORY_CUSTOM:
                shared_custom_variable_file_ids.add(str(file_id))

        # 当前项目引用的关卡变量文件（VARIABLE_FILE_ID）
        referenced_level_variable_ids: set[str] = set()
        resources = getattr(package_index, "resources", None)
        management_refs = getattr(resources, "management", {}) if resources is not None else {}
        if isinstance(management_refs, dict):
            raw_refs = management_refs.get("level_variables", [])
            if isinstance(raw_refs, list):
                for entry in raw_refs:
                    if isinstance(entry, str) and entry.strip():
                        referenced_level_variable_ids.add(entry.strip())

        # 玩家模板引用的普通自定义变量文件（UI 只允许这些文件）
        player_custom_variable_file_ids: set[str] = set()
        combat_presets = getattr(resources, "combat_presets", {}) if resources is not None else {}
        player_template_ids: list[str] = []
        if isinstance(combat_presets, dict):
            raw_player_templates = combat_presets.get("player_templates", [])
            if isinstance(raw_player_templates, list):
                for entry in raw_player_templates:
                    if isinstance(entry, str) and entry.strip() and entry.strip() not in player_template_ids:
                        player_template_ids.append(entry.strip())

        for player_template_id in player_template_ids:
            payload = resource_manager.load_resource(ResourceType.PLAYER_TEMPLATE, player_template_id)
            if not isinstance(payload, dict):
                continue
            meta = payload.get("metadata")
            if not isinstance(meta, dict):
                continue
            custom_file_id = str(meta.get("custom_variable_file") or "").strip()
            if custom_file_id:
                player_custom_variable_file_ids.add(custom_file_id)

        # 收集占位符出现位置（用于报错定位）
        occurrences: list[_UiTextPlaceholderOccurrence] = []

        def _walk(node: object, path: str) -> None:
            if isinstance(node, str):
                for match in _UI_TEXT_PLACEHOLDER_RE.finditer(node):
                    raw = str(match.group(0) or "")
                    expr = str(match.group(1) or "").strip()
                    occurrences.append(_UiTextPlaceholderOccurrence(raw=raw, expr=expr, json_path=path))
                return
            if isinstance(node, list):
                for idx, item in enumerate(node):
                    _walk(item, f"{path}[{idx}]")
                return
            if isinstance(node, dict):
                for k, v in node.items():
                    key = str(k)
                    next_path = f"{path}.{key}" if path else f"${key}"
                    _walk(v, next_path)
                return

        _walk(ui_payload, "$")
        if not occurrences:
            return True, ""

        def _parse_placeholder_expr(expr: str) -> tuple[str, str, list[str], str]:
            text = str(expr or "").strip()
            if not text:
                return "", "", [], "占位符内容为空（{{}}）"

            scope = ""
            rest = text
            if rest.startswith("lv."):
                scope = "lv"
                rest = rest[3:]
            elif rest.startswith("ls" + "."):
                return "", "", [], "不支持 ls 前缀，请改用 lv."
            elif rest.startswith("ps."):
                scope = "ps"
                rest = rest[3:]

            parts = [p.strip() for p in rest.split(".") if p.strip()]
            if not parts:
                return scope, "", [], "占位符缺少变量名"
            return scope, parts[0], parts[1:], ""

        def _try_get_struct_id(variable_payload: dict) -> str:
            default_value = variable_payload.get("default_value")
            if isinstance(default_value, dict):
                value = default_value.get("struct_id") or default_value.get("structId")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            metadata_value = variable_payload.get("metadata")
            if isinstance(metadata_value, dict):
                value = metadata_value.get("struct_id") or metadata_value.get("structId")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return ""

        def _validate_field_path(variable_payload: dict, field_parts: list[str]) -> str:
            if not field_parts:
                return ""

            variable_type = str(variable_payload.get("variable_type") or "").strip()
            default_value = variable_payload.get("default_value")

            if variable_type == "字典":
                if not isinstance(default_value, dict):
                    return "字段路径仅支持 default_value 为 dict 的字典类型变量。"
                current: object = default_value
                for part in field_parts:
                    if not isinstance(current, dict):
                        return f"字段路径越界：{part!r} 的上级不是 dict。"
                    if part not in current:
                        keys_preview = ", ".join(list(sorted(current.keys()))[:12])
                        suffix = "..." if len(current.keys()) > 12 else ""
                        return f"字段不存在：{part!r}（可用键示例：{keys_preview}{suffix}）"
                    current = current.get(part)
                return ""

            if variable_type in {"结构体", "结构体列表"}:
                if len(field_parts) != 1:
                    return "结构体/结构体列表变量暂只支持单层字段路径（例如 {{lv.变量名.字段}}）。"
                struct_id = _try_get_struct_id(variable_payload)
                if not struct_id:
                    return "结构体变量缺少 struct_id（无法校验字段路径）。"
                from engine.struct import get_default_struct_repository

                repo = get_default_struct_repository()
                field_names = set(repo.get_field_names(struct_id))
                field = field_parts[0]
                if field not in field_names:
                    preview = ", ".join(list(sorted(field_names))[:12])
                    suffix = "..." if len(field_names) > 12 else ""
                    return f"字段不存在：{field!r}（struct_id={struct_id} 可用字段示例：{preview}{suffix}）"
                return ""

            return f"变量类型不支持字段路径：{variable_type or '<empty>'}（请移除 .字段 或改用 字典/结构体 变量）。"

        seen_expr: set[str] = set()
        for occ in occurrences:
            if occ.expr in seen_expr:
                continue
            seen_expr.add(occ.expr)

            scope, variable_name, field_parts, parse_error = _parse_placeholder_expr(occ.expr)
            if parse_error:
                return (
                    False,
                    f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，{parse_error}。",
                )

            payloads = name_to_payloads.get(variable_name, [])
            if not payloads:
                import difflib

                candidates = sorted(name_to_payloads.keys())
                suggestions = difflib.get_close_matches(variable_name, candidates, n=8, cutoff=0.6)
                suggestions_text = "、".join(suggestions) if suggestions else ""
                chain = (
                    f"解析链路："
                    f" referenced_level_variables={len(referenced_level_variable_ids)}"
                    f" player_templates={len(player_template_ids)}"
                    f" player_custom_files={len(player_custom_variable_file_ids)}"
                )
                hint = f"相似变量名建议：{suggestions_text}" if suggestions_text else "相似变量名建议：<none>"
                return (
                    False,
                    f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，变量名不存在：{variable_name!r}。{hint}。{chain}。\n"
                    "建议：在【自定义变量注册表.py】补齐该变量声明，并确保其 owner 正确（lv=level, ps=player）。",
                )
            if len(payloads) != 1:
                preview = ", ".join(
                    f"{str(p.get('variable_id') or '').strip() or '<empty>'}@{str(p.get('variable_file_id') or '').strip() or '<empty>'}"
                    for p in payloads[:6]
                    if isinstance(p, dict)
                )
                suffix = "..." if len(payloads) > 6 else ""
                return (
                    False,
                    f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，变量名不唯一：{variable_name!r}（匹配到 {len(payloads)} 条：{preview}{suffix}）。请先修复变量名冲突或改用带前缀的占位符明确来源。",
                )

            variable_payload = payloads[0]
            variable_id = str(variable_payload.get("variable_id") or "").strip()
            variable_file_id = str(variable_payload.get("variable_file_id") or "").strip()

            file_info = variable_files.get(variable_file_id)
            file_category = str(getattr(file_info, "category", "") or "") if file_info is not None else ""
            file_source_path = str(getattr(file_info, "source_path", "") or "") if file_info is not None else ""
            file_abs_path = getattr(file_info, "absolute_path", None) if file_info is not None else None
            is_project_level_variable_file = (
                isinstance(file_abs_path, Path)
                and file_abs_path.resolve().is_relative_to(project_level_variable_dir)
            )

            # UI：一律禁止局内存档变量
            if file_category == CATEGORY_INGAME_SAVE:
                return (
                    False,
                    f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，变量来自局内存档变量文件（UI 禁止使用）："
                    f"variable={variable_name!r} file_id={variable_file_id or '<empty>'} source={file_source_path or '<unknown>'}。",
                )

            is_custom_file = file_category == CATEGORY_CUSTOM
            if not is_custom_file:
                return (
                    False,
                    f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，变量文件分类非法："
                    f"variable={variable_name!r} file_id={variable_file_id or '<empty>'} category={file_category or '<empty>'}。",
                )

            # 关卡变量（lv）：共享根自动可用；项目级变量需要在 resources.management.level_variables 中引用变量文件 ID
            lv_allowed = bool(
                variable_file_id
                and (
                    (variable_file_id in shared_custom_variable_file_ids)
                    or (variable_file_id in referenced_level_variable_ids)
                    or (variable_id and variable_id in referenced_level_variable_ids)
                    or is_project_level_variable_file
                )
            )

            # 玩家变量（ps）：必须来自任意玩家模板的 metadata.custom_variable_file
            ps_allowed = bool(variable_file_id and (variable_file_id in player_custom_variable_file_ids))

            resolved_scope = scope
            if scope == "lv":
                if not lv_allowed:
                    return (
                        False,
                        f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，变量不在当前项目可用的关卡变量集合中。"
                        f"请将变量文件 ID 加入项目索引 resources.management.level_variables，或将该变量文件放入共享根。"
                        f" variable={variable_name!r} file_id={variable_file_id or '<empty>'} source={file_source_path or '<unknown>'}。"
                        f"解析链路：referenced_level_variables={len(referenced_level_variable_ids)} shared_custom_files={len(shared_custom_variable_file_ids)}。",
                    )
            elif scope == "ps":
                if not ps_allowed:
                    return (
                        False,
                        f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，变量不在任何玩家模板的普通自定义变量文件中。"
                        f"UI 只允许玩家模板 metadata.custom_variable_file；禁止 ingame_save_variable_file。"
                        f" variable={variable_name!r} file_id={variable_file_id or '<empty>'} source={file_source_path or '<unknown>'}。"
                        f"解析链路：player_templates={len(player_template_ids)} player_custom_files={len(player_custom_variable_file_ids)}。",
                    )
            else:
                # 兼容旧写法：{{变量名}} —— 但必须能唯一解析到 lv 或 ps 之一
                if ps_allowed and lv_allowed:
                    return (
                        False,
                        f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，变量同时可被解析为 lv 与 ps，来源不明确。"
                        f"请显式写成 {{lv.{variable_name}}} 或 {{ps.{variable_name}}}。",
                    )
                if ps_allowed:
                    resolved_scope = "ps"
                elif lv_allowed:
                    resolved_scope = "lv"
                else:
                    return (
                        False,
                        f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，变量在当前项目中不可用。"
                        f"请检查：关卡变量需在 resources.management.level_variables 引用变量文件；玩家变量需在任意玩家模板 metadata.custom_variable_file 引用变量文件。"
                        f" variable={variable_name!r} file_id={variable_file_id or '<empty>'} source={file_source_path or '<unknown>'}。",
                    )

            # 字段路径校验（可选）
            path_error = _validate_field_path(variable_payload, field_parts)
            if path_error:
                prefix = "lv" if resolved_scope == "lv" else "ps"
                return (
                    False,
                    f"UI占位符校验失败：{occ.json_path} 中发现 {occ.raw}，字段路径无效：{path_error}"
                    f"（建议写法：{{{prefix}.{variable_name}}} 或修正字段）。",
                )

        return True, ""

