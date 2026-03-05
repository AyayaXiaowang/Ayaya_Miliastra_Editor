from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict

from ugc_file_tools.fs_naming import sanitize_file_stem


ProgressCallback = Callable[[int, int, str], None]


def _emit_progress(cb: ProgressCallback | None, current: int, total: int, label: str) -> None:
    if cb is None:
        return
    cb(int(current), int(total), str(label or ""))


def _set_last_opened_package(*, graph_generater_root: Path, package_id: str) -> None:
    state_file = Path(graph_generater_root).resolve() / "app" / "runtime" / "package_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        obj = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            obj = {}
    else:
        obj = {}
    obj["last_opened_package_id"] = str(package_id)
    state_file.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _refresh_graph_dir_claude(*, graph_dir: Path, scope: str) -> None:
    graph_files = [
        path
        for path in Path(graph_dir).rglob("*.py")
        if path.is_file() and (not path.name.startswith("_")) and ("校验" not in path.stem)
    ]
    graph_count = len(graph_files)

    scope_text = str(scope or "").strip().lower()
    scope_label = "client" if scope_text == "client" else "server"

    lines: list[str] = []
    lines.append("## 目录用途")
    lines.append(f"- 存放 {scope_label} 侧节点图（Graph Code，Python 类结构）。")
    lines.append("")
    lines.append("## 当前状态")
    lines.append(f"- 当前包含 {graph_count} 个节点图文件（不含辅助脚本）。")
    lines.append("")
    lines.append("## 注意事项")
    lines.append("- 节点图文件需通过 `python -X utf8 -m app.cli.graph_tools validate-file <path>` 或 validate-graphs 校验后再投入使用。")
    lines.append("- 本文件不记录修改历史，仅保持用途/状态/注意事项的实时描述。")
    lines.append("")
    lines.append("---")
    lines.append("注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。")
    lines.append("")
    (Path(graph_dir) / "claude.md").write_text("\n".join(lines), encoding="utf-8")


@dataclass(frozen=True, slots=True)
class ImportGiaNodeGraphsPlan:
    input_gia_file: Path
    project_archive_path: Path
    package_id: str

    overwrite_graph_code: bool = False
    check_header: bool = False
    decode_max_depth: int = 32
    node_data_index_path: Path | None = None
    mapping_path: Path | None = None

    validate_after_import: bool = True
    graph_generater_root_for_validation: Path | None = None
    set_last_opened: bool = False


def run_import_gia_node_graphs_to_project_archive(
    *,
    plan: ImportGiaNodeGraphsPlan,
    progress_cb: ProgressCallback | None = None,
) -> Dict[str, object]:
    input_gia_path = Path(plan.input_gia_file).resolve()
    if not input_gia_path.is_file():
        raise FileNotFoundError(str(input_gia_path))

    output_package_root = Path(plan.project_archive_path).resolve()
    output_package_root.parent.mkdir(parents=True, exist_ok=True)
    output_package_root.mkdir(parents=True, exist_ok=True)

    total_steps = 2  # 解析+生成
    if bool(plan.validate_after_import):
        total_steps += 1
    if bool(plan.set_last_opened):
        total_steps += 1

    current = 0
    _emit_progress(progress_cb, current, total_steps, "准备导入节点图…")

    current += 1
    _emit_progress(progress_cb, current, total_steps, "正在解析 .gia NodeGraph…")
    from ugc_file_tools.graph.node_graph.gia_graph_ir import read_graph_irs_from_gia_file

    graph_irs = read_graph_irs_from_gia_file(
        input_gia_path,
        node_data_index_path=plan.node_data_index_path,
        check_header=bool(plan.check_header),
        decode_max_depth=int(plan.decode_max_depth),
    )
    if not graph_irs:
        raise ValueError(f"输入 .gia 中未找到可解析的 NodeGraph GraphUnit：{str(input_gia_path)}")

    current += 1
    _emit_progress(progress_cb, current, total_steps, "正在生成节点图代码（Graph Code）…")
    from ugc_file_tools.graph.node_graph.graph_ir_to_graph_model import build_graph_model_from_graph_ir
    from ugc_file_tools.graph_codegen import ExecutableCodeGenerator
    from ugc_file_tools.repo_paths import resolve_graph_generater_root

    gg_root = resolve_graph_generater_root(output_package_root)
    codegen = ExecutableCodeGenerator(gg_root.resolve())

    written_files: list[str] = []
    skipped_files: list[str] = []

    for graph_ir in graph_irs:
        graph_model, metadata = build_graph_model_from_graph_ir(
            package_root=output_package_root,
            graph_ir=dict(graph_ir),
            mapping_path=plan.mapping_path,
        )
        graph_type = str(metadata.get("graph_type") or "server").strip().lower()
        if graph_type not in {"server", "client"}:
            raise ValueError(f"unsupported graph_type: {graph_type!r}")

        graph_id_int = graph_ir.get("graph_id_int")
        graph_name = str(graph_ir.get("graph_name") or "").strip() or f"导入_节点图_{graph_id_int}"
        file_stem = sanitize_file_stem(f"导入_节点图_{graph_id_int}_{graph_name}", max_length=120)

        output_dir = output_package_root / "节点图" / graph_type
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = (output_dir / f"{file_stem}.py").resolve()

        if output_path.exists() and (not bool(plan.overwrite_graph_code)):
            skipped_files.append(str(output_path))
            continue

        code_text = codegen.generate_code(graph_model, metadata=metadata)
        output_path.write_text(code_text, encoding="utf-8")
        written_files.append(str(output_path))

    server_dir = output_package_root / "节点图" / "server"
    client_dir = output_package_root / "节点图" / "client"
    server_dir.mkdir(parents=True, exist_ok=True)
    client_dir.mkdir(parents=True, exist_ok=True)
    _refresh_graph_dir_claude(graph_dir=server_dir, scope="server")
    _refresh_graph_dir_claude(graph_dir=client_dir, scope="client")

    validation_summary: object = None
    if bool(plan.validate_after_import):
        current += 1
        _emit_progress(progress_cb, current, total_steps, "正在校验项目存档…")
        from ugc_file_tools.gil_package_exporter.graph_validation import (
            find_graph_generater_root_from_output_package_root,
            validate_graph_generater_single_package,
        )

        root_for_validation = (
            Path(plan.graph_generater_root_for_validation).resolve()
            if plan.graph_generater_root_for_validation is not None
            else find_graph_generater_root_from_output_package_root(output_package_root)
        )
        if root_for_validation is None:
            raise ValueError(f"无法定位 Graph_Generater 根目录用于校验：output_package_root={str(output_package_root)}")
        validation_summary = validate_graph_generater_single_package(
            graph_generater_root=Path(root_for_validation),
            package_id=str(plan.package_id),
        )

    if bool(plan.set_last_opened):
        current += 1
        _emit_progress(progress_cb, current, total_steps, "正在设置最近打开存档…")
        from ugc_file_tools.gil_package_exporter.graph_validation import find_graph_generater_root_from_output_package_root

        root_for_state = (
            Path(plan.graph_generater_root_for_validation).resolve()
            if plan.graph_generater_root_for_validation is not None
            else find_graph_generater_root_from_output_package_root(output_package_root)
        )
        if root_for_state is None:
            raise ValueError(
                f"无法定位 Graph_Generater 根目录用于写入 package_state.json：output_package_root={str(output_package_root)}"
            )
        _set_last_opened_package(graph_generater_root=Path(root_for_state), package_id=str(plan.package_id))

    return {
        "input_gia": str(input_gia_path),
        "output_package_root": str(output_package_root),
        "graphs_count": len(graph_irs),
        "written_graph_code_files": written_files,
        "skipped_graph_code_files": skipped_files,
        "validate_after_import": bool(plan.validate_after_import),
        "validation_summary": validation_summary,
        "set_last_opened": bool(plan.set_last_opened),
        "package_id": str(plan.package_id),
    }


__all__ = [
    "ImportGiaNodeGraphsPlan",
    "run_import_gia_node_graphs_to_project_archive",
]

