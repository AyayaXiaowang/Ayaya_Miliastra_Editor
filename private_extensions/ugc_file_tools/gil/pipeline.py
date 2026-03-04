from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ugc_file_tools.gil_package_exporter.paths import resolve_default_dtype_path
from ugc_file_tools.gil_package_exporter.runner import export_gil_to_package
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.package_parser import load_parsed_package
from ugc_file_tools.package_parser.json_io import write_json_file


@dataclass(frozen=True)
class GilToPackageExportConfig:
    input_gil_file_path: Path
    output_package_root: Path
    dtype_path: Path
    enable_dll_dump: bool
    data_blob_min_bytes_for_decode: int
    generic_scan_min_bytes: int
    focus_graph_id: Optional[int]


def add_gil_to_package_export_arguments(argument_parser: argparse.ArgumentParser) -> None:
    """
    为“导出 .gil → 项目存档目录（package root）”添加统一的参数集合。

    注意：导出的“项目存档目录”必须位于 Graph_Generater 资源库下：
      <Graph_Generater>/assets/资源库/项目存档/<package_id>

    原因：
    - 导出器会在导出后调用引擎的 `ComprehensiveValidator` 做综合校验；
    - 引擎资源索引只会从 `assets/资源库/项目存档/` 加载包，因此输出目录必须落在该根目录下。
    """

    argument_parser.add_argument(
        "--input-gil",
        dest="input_gil_file",
        required=True,
        help="输入 .gil 文件路径",
    )
    argument_parser.add_argument(
        "--output-package",
        dest="output_package_root",
        required=True,
        help=(
            "输出项目存档目录（必须为 Graph_Generater/assets/资源库/项目存档/<package_id> 的一级子目录）。"
            "也可直接传 package_id（例如 '__tmp_validate__foo'），会自动写入 assets/资源库/项目存档/<package_id>。"
        ),
    )
    argument_parser.add_argument(
        "--dtype",
        dest="dtype_path",
        default=str(resolve_default_dtype_path()),
        help="dtype.json 路径（默认使用 ugc_file_tools/builtin_resources/dtype/dtype.json）",
    )
    argument_parser.add_argument(
        "--enable-dll-dump",
        dest="enable_dll_dump",
        action="store_true",
        help="额外执行一次 dump-json，并从中提取 UI 相关数据（用于导出 UI 控件模板）",
    )
    argument_parser.add_argument(
        "--data-min-bytes",
        dest="data_min_bytes",
        type=int,
        default=512,
        help="对 data blob 进行二次解码的最小字节阈值（默认 512）",
    )
    argument_parser.add_argument(
        "--generic-scan-min-bytes",
        dest="generic_scan_min_bytes",
        type=int,
        default=256,
        help="通用解码扫描的最小字节阈值（默认 256，会做 utf8 统计与关键字命中定位）",
    )
    argument_parser.add_argument(
        "--focus-graph-id",
        dest="focus_graph_id",
        type=int,
        help="可选：定向定位某个节点图/节点ID（例如 1073741832），会额外导出命中 @data 的通用解码结果。",
    )


def add_parsed_summary_output_argument(argument_parser: argparse.ArgumentParser) -> None:
    argument_parser.add_argument(
        "--parsed-output",
        dest="parsed_output_json",
        default="",
        help="可选：解析摘要 JSON 输出路径（默认写入到输出项目存档目录下 <package>_parsed_summary.json）。",
    )


def _resolve_output_package_root(*, output_package_root: str) -> Path:
    raw = str(output_package_root or "").strip()
    if raw == "":
        raise ValueError("output_package_root 不能为空")

    from ugc_file_tools.repo_paths import graph_generater_root

    gg_root = graph_generater_root()
    project_archive_root = (gg_root / "assets" / "资源库" / "项目存档").resolve()
    if not project_archive_root.is_dir():
        raise FileNotFoundError(str(project_archive_root))

    p = Path(raw)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        # 只允许传 package_id（单段），避免误把任意相对路径写入资源库根之外。
        if any(str(part) == ".." for part in p.parts):
            raise ValueError("output_package_root must not contain '..'")
        if len(p.parts) != 1:
            raise ValueError(
                "output_package_root 只能是 package_id（单段，如 '__tmp_validate__foo'）或绝对路径："
                f"got={raw!r}"
            )
        resolved = (project_archive_root / str(p.parts[0])).resolve()

    if resolved.parent.resolve() != project_archive_root:
        raise ValueError(
            "输出目录必须是 Graph_Generater 项目存档的一级子目录："
            f"{str(project_archive_root.as_posix())}/<package_id>"
        )
    return Path(resolved).resolve()


def resolve_gil_to_package_export_config(arguments: argparse.Namespace) -> GilToPackageExportConfig:
    input_gil_file_path = Path(arguments.input_gil_file)
    if not input_gil_file_path.is_file():
        raise FileNotFoundError(f"input gil file not found: {str(input_gil_file_path)!r}")

    output_package_root = _resolve_output_package_root(output_package_root=str(arguments.output_package_root))
    dtype_path = Path(arguments.dtype_path)

    focus_graph_id = int(arguments.focus_graph_id) if arguments.focus_graph_id is not None else None

    return GilToPackageExportConfig(
        input_gil_file_path=input_gil_file_path,
        output_package_root=output_package_root,
        dtype_path=dtype_path,
        enable_dll_dump=bool(arguments.enable_dll_dump),
        data_blob_min_bytes_for_decode=int(arguments.data_min_bytes),
        generic_scan_min_bytes=int(arguments.generic_scan_min_bytes),
        focus_graph_id=focus_graph_id,
    )


def run_export_gil_to_package(config: GilToPackageExportConfig) -> None:
    export_gil_to_package(
        input_gil_file_path=config.input_gil_file_path,
        output_package_root=config.output_package_root,
        dtype_path=config.dtype_path,
        enable_dll_dump=bool(config.enable_dll_dump),
        data_blob_min_bytes_for_decode=int(config.data_blob_min_bytes_for_decode),
        generic_scan_min_bytes=int(config.generic_scan_min_bytes),
        focus_graph_id=(int(config.focus_graph_id) if config.focus_graph_id is not None else None),
    )


def load_parsed_summary_dict(*, package_root: Path) -> Dict[str, Any]:
    parsed_package = load_parsed_package(Path(package_root).resolve())
    return parsed_package.to_dict()


def write_parsed_summary_json(
    *,
    output_package_root: Path,
    parsed_summary: Dict[str, Any],
    parsed_output_json: str,
) -> Path:
    parsed_output_text = str(parsed_output_json or "").strip()
    if parsed_output_text != "":
        parsed_output_path = resolve_output_file_path_in_out_dir(Path(parsed_output_text))
    else:
        parsed_output_path = Path(output_package_root).resolve() / f"{Path(output_package_root).name}_parsed_summary.json"

    write_json_file(parsed_output_path, parsed_summary)
    return parsed_output_path


