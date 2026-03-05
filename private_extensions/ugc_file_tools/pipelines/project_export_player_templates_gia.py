from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir
from ugc_file_tools.var_type_map import map_server_port_type_text_to_var_type_id_or_raise


ProgressCb = Callable[[int, int, str], None]


@dataclass(frozen=True, slots=True)
class ProjectExportPlayerTemplatesGiaPlan:
    """
    项目存档 → 导出“玩家模板（含自定义变量）”为 `.gia`。

    约束与设计：
    - template-driven：基于一份真源导出的 base 玩家模板 `.gia` 克隆结构，再写入名称/ID 与自定义变量列表；
    - 产物落盘到 `ugc_file_tools/out/<output_dir_name_in_out>/player_templates/`；
      若提供 `output_user_dir`（绝对路径），会额外复制一份过去（常用：Beyond_Local_Export）。
    """

    project_archive_path: Path
    # 必选：真源导出的 base 玩家模板 `.gia`（结构模板）。
    base_player_template_gia_file: Path
    # 可选：仅导出指定玩家模板 JSON 文件（可为空=导出全部 战斗预设/玩家模板/*.json）
    player_template_json_files: list[Path] | None = None
    # 输出到 ugc_file_tools/out/ 下的子目录名（默认：<package_id>_player_template_gia_export）
    output_dir_name_in_out: str = ""
    # 绝对目录：额外复制一份过去（为空则不复制）
    output_user_dir: Path | None = None
    # 解码 base `.gia` 的递归深度（越大越可能把 bytes 当作嵌套 message 解开）
    base_decode_max_depth: int = 16


def _emit_progress(progress_cb: ProgressCb | None, current: int, total: int, label: str) -> None:
    if callable(progress_cb):
        progress_cb(int(current), int(total), str(label or "").strip())


def _should_ignore_player_template_file(p: Path) -> bool:
    if not p.is_file():
        return True
    name = p.name
    if name.startswith(".") or name.startswith("_"):
        return True
    if name.lower() == "claude.md":
        return True
    if name.lower().endswith("_index.json") or name.lower().endswith("index.json"):
        # 兼容未来可能出现的索引文件
        return True
    if p.suffix.lower() != ".json":
        return True
    return False


def _scan_player_template_json_files(project_root: Path) -> list[Path]:
    directory = (Path(project_root).resolve() / "战斗预设" / "玩家模板").resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"项目存档缺少 战斗预设/玩家模板 目录：{str(directory)}")
    out: list[Path] = []
    for p in sorted(directory.rglob("*.json"), key=lambda x: x.as_posix().casefold()):
        if _should_ignore_player_template_file(p):
            continue
        out.append(Path(p).resolve())
    return out


def _coerce_non_empty_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if text == "":
        raise ValueError(f"{field_name} 不能为空")
    return text


def _load_player_template_json(path: Path) -> Dict[str, Any]:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError(f"player template json root must be dict: {str(p)}")
    return obj


def _load_variable_files_from_level_variables_dir(level_variables_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """
    从给定的 `管理配置/关卡变量/` 目录加载所有变量文件（*.py），返回：
      {VARIABLE_FILE_ID: [LevelVariableDefinition.serialize()...]}

    说明：
    - 该加载器只依赖“变量文件约定”（VARIABLE_FILE_ID / LEVEL_VARIABLES），不依赖资源库作用域；
    - 用于支持 export 工具对“任意 project_root”运行（不要求必须位于 assets/资源库/项目存档 下）。
    """
    base_dir = Path(level_variables_dir).resolve()
    if not base_dir.is_dir():
        return {}

    from importlib.machinery import SourceFileLoader

    from engine.graph.models.package_model import LevelVariableDefinition

    out: Dict[str, List[Dict[str, Any]]] = {}
    py_paths = sorted((p for p in base_dir.rglob("*.py") if p.is_file()), key=lambda p: p.as_posix())
    for py_path in py_paths:
        if "校验" in py_path.stem:
            continue
        module_name = f"code_level_variable_{abs(hash(py_path.as_posix()))}"
        loader = SourceFileLoader(module_name, str(py_path))
        module = loader.load_module()
        file_id = getattr(module, "VARIABLE_FILE_ID", None)
        if not isinstance(file_id, str) or str(file_id).strip() == "":
            raise ValueError(f"无效的 VARIABLE_FILE_ID（{py_path}）")
        if file_id in out:
            raise ValueError(f"重复的变量文件 ID：{file_id}")

        vars_list = getattr(module, "LEVEL_VARIABLES", None)
        if not isinstance(vars_list, list):
            raise ValueError(f"LEVEL_VARIABLES 未定义为列表（{py_path}）")

        variables: List[Dict[str, Any]] = []
        for entry in vars_list:
            if isinstance(entry, LevelVariableDefinition):
                variables.append(entry.serialize())
                continue
            if isinstance(entry, dict):
                variables.append(dict(entry))
                continue
            raise ValueError(f"无效的关卡变量条目类型（{py_path}）：{type(entry)!r}")

        out[str(file_id).strip()] = variables

    return out


def run_project_export_player_templates_to_gia(
    *,
    plan: ProjectExportPlayerTemplatesGiaPlan,
    progress_cb: ProgressCb | None = None,
) -> Dict[str, Any]:
    project_root = Path(plan.project_archive_path).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    base_gia = Path(plan.base_player_template_gia_file).resolve()
    if not base_gia.is_file() or base_gia.suffix.lower() != ".gia":
        raise FileNotFoundError(str(base_gia))

    package_id = str(project_root.name)

    explicit = [Path(p).resolve() for p in list(plan.player_template_json_files or []) if str(p).strip() != ""]
    if explicit:
        template_files = []
        for p in explicit:
            if not p.is_file():
                raise FileNotFoundError(str(p))
            if p.suffix.lower() != ".json":
                raise ValueError(f"player_template_json_files 必须为 .json：{str(p)}")
            template_files.append(p)
    else:
        template_files = _scan_player_template_json_files(project_root)

    if not template_files:
        raise ValueError(f"未找到可导出的玩家模板 JSON：{str(project_root / '战斗预设' / '玩家模板')}")

    total_steps = 1 + int(len(template_files)) + int(len(template_files))  # base + parse + export

    default_out = f"{package_id}_player_template_gia_export"
    out_dir_name = str(plan.output_dir_name_in_out or "").strip() or default_out
    output_dir = resolve_output_dir_path_in_out_dir(Path(out_dir_name))
    output_dir.mkdir(parents=True, exist_ok=True)

    templates_dir = (output_dir / "player_templates").resolve()
    templates_dir.mkdir(parents=True, exist_ok=True)

    user_dir: Optional[Path] = None
    if plan.output_user_dir is not None:
        user_dir = Path(plan.output_user_dir).resolve()
        if not user_dir.is_absolute():
            raise ValueError("output_user_dir 必须是绝对路径（用于复制导出产物）")
        user_dir.mkdir(parents=True, exist_ok=True)

    # 读取 base bundle（只做一次）
    from ugc_file_tools.gia_export.player_templates import (
        build_player_template_low16,
        build_player_template_role_editor_root_id_int,
        build_player_template_root_id_int,
        build_player_template_gia_bytes_from_base_bundle,
        bump_player_template_low16,
        load_player_template_base_bundle_from_gia,
    )
    from ugc_file_tools.gia_export.templates import CustomVariableDef

    _emit_progress(progress_cb, 0, total_steps, "准备导出玩家模板 .gia…")
    _emit_progress(progress_cb, 1, total_steps, "解析 base 玩家模板 .gia…")
    base_bundle = load_player_template_base_bundle_from_gia(
        base_gia,
        max_depth=int(plan.base_decode_max_depth),
        prefer_raw_hex_for_utf8=True,
    )

    # 加载关卡变量文件（用于解析 metadata.custom_variable_file 引用）
    from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs
    from engine.utils.workspace import resolve_workspace_root

    # 1) project scope（优先）
    project_level_var_dir = (project_root / "管理配置" / "关卡变量").resolve()
    project_var_files = _load_variable_files_from_level_variables_dir(project_level_var_dir)

    # 2) shared scope（可选）
    workspace_root = resolve_workspace_root(start_paths=[Path(__file__).resolve()])
    shared_level_var_dir = (workspace_root / "assets" / "资源库" / "共享" / "管理配置" / "关卡变量").resolve()
    shared_var_files = _load_variable_files_from_level_variables_dir(shared_level_var_dir)

    # 合并（严格：重复 file_id 直接抛错，避免“引用同名但内容不同”悄悄混用）
    variable_files: Dict[str, List[Dict[str, Any]]] = {}
    for file_id, vars_list in shared_var_files.items():
        variable_files[str(file_id)] = list(vars_list)
    for file_id, vars_list in project_var_files.items():
        if str(file_id) in variable_files:
            raise ValueError(f"变量文件 ID 在 shared 与 project 中重复：{file_id!r}")
        variable_files[str(file_id)] = list(vars_list)

    exported: List[Dict[str, Any]] = []

    planned_names: Dict[str, str] = {}
    parsed: list[tuple[Path, str, str, list[str], list[CustomVariableDef], int, int]] = []
    used_low16: set[int] = set()

    for idx, template_json in enumerate(template_files):
        _emit_progress(progress_cb, 1 + idx + 1, total_steps, f"解析玩家模板：{template_json.name}")
        obj = _load_player_template_json(template_json)

        template_id = str(obj.get("template_id") or "").strip()
        template_name = str(obj.get("template_name") or "").strip()
        if template_name == "":
            template_name = str(obj.get("name") or "").strip()
        if template_name == "":
            template_name = str(template_id).strip()
        template_name = _coerce_non_empty_text(template_name, field_name="player_template.template_name")

        stem = sanitize_file_stem(template_name)
        if stem == "":
            stem = sanitize_file_stem(Path(template_json).stem) or "untitled"

        output_name = f"{stem}.gia"
        key = output_name.casefold()
        if key in planned_names:
            raise ValueError(
                "玩家模板导出存在同名输出文件（将发生覆盖）。"
                f"请调整模板 name 或改用更唯一的命名。\n"
                f"- output: {output_name!r}\n"
                f"- a: {planned_names[key]}\n"
                f"- b: {str(template_json)}"
            )
        planned_names[key] = str(template_json)

        metadata = obj.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        raw_refs = metadata.get("custom_variable_file")
        refs = normalize_custom_variable_file_refs(raw_refs)

        # 将引用的变量文件扁平化为 CustomVariableDef 列表（按 variable_name 去重）
        custom_variables: list[CustomVariableDef] = []
        seen_names: set[str] = set()
        for ref in list(refs):
            vars_list = variable_files.get(str(ref))
            if vars_list is None:
                raise FileNotFoundError(
                    "玩家模板 custom_variable_file 引用的变量文件不存在："
                    f"{ref!r}\n"
                    "解决方案：在该项目存档的 管理配置/关卡变量/自定义变量/ 下创建对应变量文件，并设置 VARIABLE_FILE_ID。"
                )
            for var_payload in list(vars_list or []):
                if not isinstance(var_payload, dict):
                    continue
                var_name = str(var_payload.get("variable_name") or "").strip()
                if var_name == "":
                    continue
                if var_name in seen_names:
                    raise ValueError(f"玩家模板变量名重复：{var_name!r}（file={str(template_json)} refs={refs!r}）")
                seen_names.add(var_name)
                var_type_text = str(var_payload.get("variable_type") or "").strip()
                var_type_text = _coerce_non_empty_text(var_type_text, field_name=f"{var_name}.variable_type")
                var_type_int = map_server_port_type_text_to_var_type_id_or_raise(var_type_text)
                default_value = var_payload.get("default_value")
                custom_variables.append(
                    CustomVariableDef(
                        name=str(var_name),
                        var_type_text=str(var_type_text),
                        var_type_int=int(var_type_int),
                        default_value=default_value,
                    )
                )

        template_key = template_id or template_name
        low16 = int(build_player_template_low16(template_key=str(template_key)))
        while low16 in used_low16:
            low16 = int(bump_player_template_low16(int(low16)))
        used_low16.add(int(low16))

        template_root_id_int = int(build_player_template_root_id_int(low16=int(low16)))
        role_editor_root_id_int = int(build_player_template_role_editor_root_id_int(low16=int(low16)))

        parsed.append(
            (
                Path(template_json).resolve(),
                str(template_id),
                str(template_name),
                list(refs),
                custom_variables,
                int(template_root_id_int),
                int(role_editor_root_id_int),
            )
        )

    for idx, (template_json, template_id, template_name, refs, custom_variables, template_root_id_int, role_editor_root_id_int) in enumerate(parsed):
        _emit_progress(progress_cb, 1 + len(parsed) + idx + 1, total_steps, f"导出玩家模板：{template_name}")

        stem = sanitize_file_stem(template_name) or sanitize_file_stem(Path(template_json).stem) or "untitled"

        gia_bytes = build_player_template_gia_bytes_from_base_bundle(
            base_bundle,
            template_name=str(template_name),
            custom_variables=list(custom_variables),
            template_root_id_int=int(template_root_id_int),
            role_editor_root_id_int=int(role_editor_root_id_int),
            output_file_stem=str(stem),
        )

        output_gia_file = (templates_dir / f"{stem}.gia").resolve()
        output_gia_file.write_bytes(gia_bytes)

        copied_to: str = ""
        if user_dir is not None:
            target = (user_dir / output_gia_file.name).resolve()
            shutil.copy2(output_gia_file, target)
            copied_to = str(target)

        exported.append(
            {
                "player_template_json": str(Path(template_json).resolve()),
                "template_id": str(template_id),
                "template_name": str(template_name),
                "custom_variable_file_refs": list(refs),
                "custom_variables_count": int(len(custom_variables)),
                "template_root_id_int": int(template_root_id_int),
                "role_editor_root_id_int": int(role_editor_root_id_int),
                "output_gia_file": str(output_gia_file),
                "copied_to": copied_to,
            }
        )

    return {
        "project_archive": str(project_root),
        "package_id": str(package_id),
        "base_player_template_gia_file": str(base_gia),
        "player_templates_total": int(len(template_files)),
        "output_dir": str(output_dir),
        "player_templates_dir": str(templates_dir),
        "exported_player_templates": exported,
        "copied_to_user_dir": str(user_dir) if user_dir is not None else "",
    }


__all__ = [
    "ProjectExportPlayerTemplatesGiaPlan",
    "run_project_export_player_templates_to_gia",
]

