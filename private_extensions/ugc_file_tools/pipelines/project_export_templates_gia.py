from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir


ProgressCb = Callable[[int, int, str], None]


@dataclass(frozen=True, slots=True)
class ProjectExportTemplatesGiaPlan:
    """
    项目存档 → 导出“元件模板（含自定义变量）”为 `.gia`。

    说明：
    - 该链路是“只导出资产”的链路，不会修改 `.gil`；
    - 导出采用 template-driven：基于一份真源导出的 base 元件 `.gia` 克隆结构，再写入名称与自定义变量列表；
    - 产物会强制落盘到 `ugc_file_tools/out/<output_dir_name_in_out>/templates/`；
      若提供 `output_user_dir`（绝对路径），会额外复制一份过去（常用：Beyond_Local_Export）。
    """

    project_archive_path: Path
    # 可选：提供真源导出的 base 元件 `.gia` 作为结构模板；留空则使用内置 base（空模型元件）。
    base_template_gia_file: Path | None
    # 可选：仅导出指定模板 JSON 文件（可为空=导出全部 元件库/*.json）
    template_json_files: list[Path] | None = None
    # 输出到 ugc_file_tools/out/ 下的子目录名（默认：<package_id>_template_gia_export）
    output_dir_name_in_out: str = ""
    # 绝对目录：额外复制一份过去（为空则不复制）
    output_user_dir: Path | None = None
    # 解码 base `.gia` 的递归深度（越大越可能把 bytes 当作嵌套 message 解开）
    base_decode_max_depth: int = 24


def _emit_progress(progress_cb: ProgressCb | None, current: int, total: int, label: str) -> None:
    if callable(progress_cb):
        progress_cb(int(current), int(total), str(label or "").strip())


def _should_ignore_template_file(p: Path) -> bool:
    if not p.is_file():
        return True
    name = p.name
    if name.startswith(".") or name.startswith("_"):
        return True
    if name.lower() == "claude.md":
        return True
    if p.suffix.lower() != ".json":
        return True
    return False


def _scan_template_json_files(project_root: Path) -> list[Path]:
    templates_dir = (Path(project_root).resolve() / "元件库").resolve()
    if not templates_dir.is_dir():
        raise FileNotFoundError(f"项目存档缺少 元件库 目录：{str(templates_dir)}")
    out: list[Path] = []
    for p in sorted(templates_dir.rglob("*.json"), key=lambda x: x.as_posix().casefold()):
        if _should_ignore_template_file(p):
            continue
        out.append(Path(p).resolve())
    return out


def run_project_export_templates_to_gia(
    *,
    plan: ProjectExportTemplatesGiaPlan,
    progress_cb: ProgressCb | None = None,
) -> Dict[str, Any]:
    project_root = Path(plan.project_archive_path).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    base_gia: Path | None = None
    if plan.base_template_gia_file is not None:
        base_gia = Path(plan.base_template_gia_file).resolve()
        if not base_gia.is_file() or base_gia.suffix.lower() != ".gia":
            raise FileNotFoundError(str(base_gia))

    package_id = str(project_root.name)

    explicit = [Path(p).resolve() for p in list(plan.template_json_files or []) if str(p).strip() != ""]
    if explicit:
        template_files = []
        for p in explicit:
            if not p.is_file():
                raise FileNotFoundError(str(p))
            if p.suffix.lower() != ".json":
                raise ValueError(f"template_json_files 必须为 .json：{str(p)}")
            template_files.append(p)
    else:
        template_files = _scan_template_json_files(project_root)

    if not template_files:
        raise ValueError(f"未找到可导出的元件模板 JSON：{str(project_root / '元件库')}")

    total_steps = 1 + int(len(template_files)) + int(len(template_files))  # base + parse + export

    default_out = f"{package_id}_template_gia_export"
    out_dir_name = str(plan.output_dir_name_in_out or "").strip() or default_out
    output_dir = resolve_output_dir_path_in_out_dir(Path(out_dir_name))
    output_dir.mkdir(parents=True, exist_ok=True)

    templates_dir = (output_dir / "templates").resolve()
    templates_dir.mkdir(parents=True, exist_ok=True)

    user_dir: Optional[Path] = None
    if plan.output_user_dir is not None:
        user_dir = Path(plan.output_user_dir).resolve()
        if not user_dir.is_absolute():
            raise ValueError("output_user_dir 必须是绝对路径（用于复制导出产物）")
        user_dir.mkdir(parents=True, exist_ok=True)

    # 读取 base bundle（只做一次）
    from ugc_file_tools.gia_export.templates import (
        build_component_gia_bytes_from_base_bundle,
        build_component_template_root_id_int,
        load_component_base_bundle_from_gia,
        load_builtin_component_base_bundle,
        load_component_template_config_from_json_file,
    )

    _emit_progress(progress_cb, 0, total_steps, "准备导出元件 .gia…")
    if base_gia is not None:
        _emit_progress(progress_cb, 1, total_steps, "解析 base 元件模板 .gia…")
        base_bundle = load_component_base_bundle_from_gia(
            base_gia,
            max_depth=int(plan.base_decode_max_depth),
            prefer_raw_hex_for_utf8=True,
        )
    else:
        _emit_progress(progress_cb, 1, total_steps, "加载内置 base 元件模板…")
        base_bundle = load_builtin_component_base_bundle(prefer_raw_hex_for_utf8=True)

    exported: List[Dict[str, Any]] = []

    # 解析模板（一次）+ 输出文件名去重：防止同名覆盖
    planned_names: Dict[str, str] = {}
    parsed: list[tuple[Path, Any, str, int]] = []
    used_template_root_ids: set[int] = set()

    def _bump_template_root_id_int(value: int) -> int:
        base = int(value) & 0xFFFF0000
        low = int(value) & 0xFFFF
        low2 = int(low) + 1
        if low2 > 0x7FFF:
            low2 = 0x4000
        if low2 < 0x4000:
            low2 = 0x4000
        return int(base | int(low2))

    for idx, template_json in enumerate(template_files):
        _emit_progress(progress_cb, 1 + idx + 1, total_steps, f"解析模板：{template_json.name}")
        cfg = load_component_template_config_from_json_file(template_json)
        stem = sanitize_file_stem(cfg.template_name)
        if stem == "":
            stem = sanitize_file_stem(template_json.stem) or "untitled"
        output_name = f"{stem}.gia"
        key = output_name.casefold()
        if key in planned_names:
            raise ValueError(
                "元件模板导出存在同名输出文件（将发生覆盖）。"
                f"请调整模板 name 或改用更唯一的命名。\n"
                f"- output: {output_name!r}\n"
                f"- a: {planned_names[key]}\n"
                f"- b: {str(template_json)}"
            )
        planned_names[key] = str(template_json)

        template_key = str(getattr(cfg, "template_id", "") or "").strip() or str(cfg.template_name)
        template_root_id_int = int(build_component_template_root_id_int(template_key=template_key))
        while template_root_id_int in used_template_root_ids:
            template_root_id_int = _bump_template_root_id_int(template_root_id_int)
        used_template_root_ids.add(int(template_root_id_int))

        parsed.append((Path(template_json).resolve(), cfg, str(stem), int(template_root_id_int)))

    for idx, (template_json, cfg, stem, template_root_id_int) in enumerate(parsed):
        _emit_progress(progress_cb, 1 + len(parsed) + idx + 1, total_steps, f"导出元件：{cfg.template_name}")

        gia_bytes = build_component_gia_bytes_from_base_bundle(
            base_bundle,
            template_name=cfg.template_name,
            custom_variables=cfg.custom_variables,
            template_root_id_int=int(template_root_id_int),
            output_file_stem=stem,
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
                "template_json": str(Path(template_json).resolve()),
                "template_name": str(cfg.template_name),
                "custom_variables_count": int(len(cfg.custom_variables)),
                "template_root_id_int": int(template_root_id_int),
                "output_gia_file": str(output_gia_file),
                "copied_to": copied_to,
            }
        )

    return {
        "project_archive": str(project_root),
        "package_id": str(package_id),
        "base_template_gia_file": str(base_gia) if base_gia is not None else "<builtin>",
        "templates_total": int(len(template_files)),
        "output_dir": str(output_dir),
        "templates_dir": str(templates_dir),
        "exported_templates": exported,
        "copied_to_user_dir": str(user_dir) if user_dir is not None else "",
    }

