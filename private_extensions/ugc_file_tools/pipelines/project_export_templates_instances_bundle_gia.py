from __future__ import annotations

"""
project_export_templates_instances_bundle_gia.py

项目存档 → 导出“元件模板+装饰物实例”的 bundle.gia（Root.field_1 templates / Root.field_2 instances）。

核心策略：
- 若模板 JSON 带有 `metadata.ugc.source_gia_file` 与 `source_template_root_id_int`，则优先走
  **wire-level 保真切片**：从 source bundle.gia 中导出该 template GraphUnit 与引用它的 instance GraphUnit。
- 若缺失 source 信息：本 pipeline 不尝试语义重建（风险太高且很难保证真源可见性），而是 fail-fast；
  上层（UI/CLI）可选择回退到“空模型元件模板导出”工具 `export_project_templates_to_gia`（仅用于自定义变量/占位）。

输出：
- 强制落到 `ugc_file_tools/out/<output_dir_name>/templates_instances/`。
- 文件名默认使用模板 `name`（sanitize 后）并以 `.gia` 结尾；同名冲突会 fail-fast（避免覆盖误判）。
"""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir


ProgressCb = Callable[[int, int, str], None]


@dataclass(frozen=True, slots=True)
class ProjectExportTemplatesInstancesBundleGiaPlan:
    project_archive_path: Path
    # 仅导出指定模板 JSON 文件（为空=导出全部 元件库/*.json）
    template_json_files: list[Path] | None = None
    output_dir_name_in_out: str = ""
    output_user_dir: Path | None = None
    check_gia_header: bool = False


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


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _extract_source_bundle_and_root_id(template_obj: Dict[str, Any], *, template_json: Path) -> tuple[Path, int]:
    meta = template_obj.get("metadata")
    if not isinstance(meta, dict):
        raise ValueError(f"模板缺少 metadata（无法定位 source_gia_file）：{str(template_json)}")
    ugc = meta.get("ugc")
    if not isinstance(ugc, dict):
        raise ValueError(f"模板缺少 metadata.ugc（无法定位 source_gia_file）：{str(template_json)}")
    source_gia_file = str(ugc.get("source_gia_file") or "").strip()
    if source_gia_file == "":
        raise ValueError(f"模板缺少 metadata.ugc.source_gia_file（无法做保真切片导出）：{str(template_json)}")
    rid = ugc.get("source_template_root_id_int")
    if not isinstance(rid, int):
        raise ValueError(
            f"模板缺少 metadata.ugc.source_template_root_id_int(int)（无法做保真切片导出）：{str(template_json)}"
        )
    return Path(source_gia_file).resolve(), int(rid)


def run_project_export_templates_instances_bundle_gia(
    *,
    plan: ProjectExportTemplatesInstancesBundleGiaPlan,
    progress_cb: ProgressCb | None = None,
) -> Dict[str, Any]:
    project_root = Path(plan.project_archive_path).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    package_id = str(project_root.name)
    explicit = [Path(p).resolve() for p in list(plan.template_json_files or []) if str(p).strip() != ""]
    template_files = explicit if explicit else _scan_template_json_files(project_root)
    if not template_files:
        raise ValueError(f"未找到可导出的元件模板 JSON：{str(project_root / '元件库')}")

    default_out = f"{package_id}_templates_instances_gia_export"
    out_dir_name = str(plan.output_dir_name_in_out or "").strip() or default_out
    output_dir = resolve_output_dir_path_in_out_dir(Path(out_dir_name))
    output_dir.mkdir(parents=True, exist_ok=True)
    out_bundle_dir = (output_dir / "templates_instances").resolve()
    out_bundle_dir.mkdir(parents=True, exist_ok=True)

    user_dir: Optional[Path] = None
    if plan.output_user_dir is not None:
        user_dir = Path(plan.output_user_dir).resolve()
        if not user_dir.is_absolute():
            raise ValueError("output_user_dir 必须是绝对路径（用于复制导出产物）")
        user_dir.mkdir(parents=True, exist_ok=True)

    from ugc_file_tools.gia.wire_templates_instances_slice_export import slice_templates_instances_bundle_gia_wire

    planned_names: Dict[str, str] = {}
    exported: List[Dict[str, Any]] = []

    total_steps = int(len(template_files))
    for idx, template_json in enumerate(list(template_files)):
        _emit_progress(progress_cb, idx + 1, total_steps, f"导出 bundle.gia：{Path(template_json).name}")
        obj = _read_json(Path(template_json))
        if not isinstance(obj, dict):
            raise TypeError(f"template json root must be dict: {str(template_json)}")

        template_name = str(obj.get("name") or "").strip() or str(obj.get("template_id") or "").strip()
        if template_name.strip() == "":
            raise ValueError(f"模板 name/template_id 为空：{str(template_json)}")

        source_bundle_gia, template_root_id_int = _extract_source_bundle_and_root_id(obj, template_json=Path(template_json))

        stem = sanitize_file_stem(template_name) or sanitize_file_stem(Path(template_json).stem) or "untitled"
        output_name = f"{stem}.gia"
        key = output_name.casefold()
        if key in planned_names:
            raise ValueError(
                "bundle.gia 导出存在同名输出文件（将发生覆盖）。"
                f"请调整模板 name 或改用更唯一的命名。\n"
                f"- output: {output_name!r}\n"
                f"- a: {planned_names[key]}\n"
                f"- b: {str(template_json)}"
            )
        planned_names[key] = str(template_json)

        output_gia_file = (out_bundle_dir / output_name).resolve()
        report = slice_templates_instances_bundle_gia_wire(
            input_bundle_gia=Path(source_bundle_gia),
            output_bundle_gia=Path(output_gia_file),
            template_root_id_int=int(template_root_id_int),
            check_header=bool(plan.check_gia_header),
        )

        copied_to: str = ""
        if user_dir is not None:
            target = (user_dir / output_gia_file.name).resolve()
            shutil.copy2(output_gia_file, target)
            copied_to = str(target)

        exported.append(
            {
                "template_json": str(Path(template_json).resolve()),
                "template_name": str(template_name),
                "source_bundle_gia": str(source_bundle_gia),
                "template_root_id_int": int(template_root_id_int),
                "output_gia_file": str(output_gia_file),
                "copied_to": copied_to,
                "slice_report": dict(report),
            }
        )

    return {
        "project_archive": str(project_root),
        "package_id": str(package_id),
        "templates_total": int(len(template_files)),
        "output_dir": str(output_dir),
        "templates_instances_dir": str(out_bundle_dir),
        "exported": exported,
        "copied_to_user_dir": str(user_dir) if user_dir is not None else "",
    }

