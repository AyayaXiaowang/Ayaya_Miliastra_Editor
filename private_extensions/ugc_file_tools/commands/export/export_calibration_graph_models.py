from __future__ import annotations

"""
export_calibration_graph_models.py

目标：
- 批量将 Graph_Generater 资源库中的“校准_全节点覆盖_v1”图集（Graph Code, .py）解析为 GraphModel(JSON)；
- 输出 `*.graph_model.typed.json` 到 `ugc_file_tools/out/`（用于后续写回 `.gil`、预检与差异分析）。

说明：
- 复用 `export_graph_model_json_from_graph_code.py` 的解析与端口类型推断逻辑；
- 不使用 try/except；失败直接抛错，便于定位。
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root

from ugc_file_tools.commands.export_graph_model_json_from_graph_code import export_graph_model_json_from_graph_code


def _normalize_scope(scope: str) -> str:
    t = str(scope or "").strip().lower()
    if t in {"server", "s"}:
        return "server"
    if t in {"client", "c"}:
        return "client"
    raise ValueError(f"scope 不支持：{scope!r}（可选：server/client）")


def _resolve_default_graph_generater_root_from_this_file() -> Path:
    return repo_root().resolve()


def _resolve_default_calibration_dir(*, graph_generater_root: Path, package_id: str, scope: str) -> Path:
    gg_root = Path(graph_generater_root).resolve()
    scope_text = _normalize_scope(scope)
    category_dir = "实体节点图" if scope_text == "server" else "技能节点图"
    return (
        gg_root
        / "assets"
        / "资源库"
        / "项目存档"
        / str(package_id)
        / "节点图"
        / scope_text
        / category_dir
        / "校准_全节点覆盖_v1"
    ).resolve()


def _iter_graph_code_files(target_dir: Path) -> List[Path]:
    d = Path(target_dir).resolve()
    if not d.is_dir():
        raise FileNotFoundError(str(d))
    files = [p for p in d.glob("*.py") if p.is_file() and p.name != "__init__.py"]
    files.sort(key=lambda p: p.name)
    return files


def _build_output_rel_path(*, package_id: str, scope: str, graph_code_file: Path) -> Path:
    scope_text = _normalize_scope(scope)
    stem = str(Path(graph_code_file).stem)
    # 避免 server/client 同名覆盖：分 scope 子目录
    return Path("calibration_graph_models") / str(package_id) / scope_text / f"{stem}.graph_model.typed.json"


def export_calibration_graph_models(
    *,
    graph_generater_root: Path,
    package_id: str,
    scope: str,
    calibration_dir: Optional[Path],
    output_report_json: Path,
    strict: bool = True,
) -> Dict[str, Any]:
    scope_text = _normalize_scope(scope)
    gg_root = Path(graph_generater_root).resolve()
    if not gg_root.is_dir():
        raise FileNotFoundError(str(gg_root))

    calib_dir = (
        Path(calibration_dir).resolve()
        if calibration_dir is not None
        else _resolve_default_calibration_dir(graph_generater_root=gg_root, package_id=package_id, scope=scope_text)
    )
    graph_code_files = _iter_graph_code_files(calib_dir)

    per_file: List[Dict[str, Any]] = []
    for code_file in graph_code_files:
        output_rel = _build_output_rel_path(package_id=package_id, scope=scope_text, graph_code_file=code_file)
        report = export_graph_model_json_from_graph_code(
            graph_code_file=code_file,
            output_json_file=output_rel,
            graph_generater_root=gg_root,
            strict=bool(strict),
        )
        per_file.append(
            {
                "graph_code_file": str(code_file),
                "output_json": str(report.get("output_json")),
                "graph_name": str(report.get("graph_name") or ""),
                "nodes_count": int(report.get("nodes_count") or 0),
                "edges_count": int(report.get("edges_count") or 0),
            }
        )

    report_obj: Dict[str, Any] = {
        "inputs": {
            "graph_generater_root": str(gg_root),
            "package": str(package_id),
            "scope": scope_text,
            "calibration_dir": str(calib_dir),
            "strict": bool(strict),
            "graph_code_files": [str(p) for p in graph_code_files],
        },
        "stats": {
            "files": int(len(graph_code_files)),
        },
        "exports": per_file,
    }

    out_path = resolve_output_file_path_in_out_dir(Path(output_report_json))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    report_obj["report_json"] = str(out_path)
    return report_obj


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="批量导出 Graph_Generater 资源库的“校准_全节点覆盖_v1”图集为 GraphModel(JSON,含端口类型推断)，写入 ugc_file_tools/out/。"
    )
    parser.add_argument("--package", dest="package_id", default="test2", help="项目存档目录名（默认 test2）")
    parser.add_argument(
        "--scope",
        dest="scope",
        default="all",
        choices=["server", "client", "all"],
        help="导出范围：server/client/all（默认 all）",
    )
    parser.add_argument(
        "--graph-generater-root",
        dest="graph_generater_root",
        default=str(_resolve_default_graph_generater_root_from_this_file()),
        help="Graph_Generater 根目录（默认 <repo>/Graph_Generater）",
    )
    parser.add_argument(
        "--calibration-dir",
        dest="calibration_dir",
        default="",
        help="可选：显式指定校准图目录（仅当 --scope=server 或 client 时生效）；默认按 Graph_Generater/assets/资源库/项目存档/<package>/节点图/<scope>/<分类目录>/校准_全节点覆盖_v1 推导。",
    )
    parser.add_argument(
        "--output-report-json",
        dest="output_report_json",
        default="calibration_graph_models/export_calibration_graph_models.report.json",
        help="输出报告 JSON（强制写入 ugc_file_tools/out/，允许子目录）。",
    )
    parser.add_argument(
        "--non-strict",
        dest="non_strict",
        action="store_true",
        help="非严格解析：允许图结构校验不通过（用于批量诊断/差异分析；默认严格 fail-closed）。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    package_id = str(args.package_id or "").strip() or "test2"
    gg_root = Path(str(args.graph_generater_root)).resolve()
    report_path = Path(str(args.output_report_json))

    scope_raw = str(args.scope or "all").strip().lower()
    scopes: Tuple[str, ...]
    if scope_raw == "all":
        scopes = ("server", "client")
    else:
        scopes = (_normalize_scope(scope_raw),)

    calibration_dir_text = str(args.calibration_dir or "").strip()
    calibration_dir = Path(calibration_dir_text).resolve() if calibration_dir_text else None
    if calibration_dir is not None and len(scopes) != 1:
        raise ValueError("--calibration-dir 仅允许在 --scope=server 或 --scope=client 时使用")

    merged: Dict[str, Any] = {
        "inputs": {
            "graph_generater_root": str(gg_root),
            "package": package_id,
            "scopes": list(scopes),
            "strict": (not bool(getattr(args, "non_strict", False))),
        },
        "per_scope": {},
    }

    total_files = 0
    for scope_text in scopes:
        scope_report = export_calibration_graph_models(
            graph_generater_root=gg_root,
            package_id=package_id,
            scope=scope_text,
            calibration_dir=calibration_dir,
            output_report_json=Path(f"calibration_graph_models/{package_id}/{scope_text}.report.json"),
            strict=(not bool(getattr(args, "non_strict", False))),
        )
        merged["per_scope"][scope_text] = {
            "stats": dict(scope_report.get("stats") or {}),
            "report_json": str(scope_report.get("report_json") or ""),
        }
        total_files += int((scope_report.get("stats") or {}).get("files") or 0)

    merged["stats"] = {"total_files": int(total_files)}
    merged_out_path = resolve_output_file_path_in_out_dir(report_path)
    merged_out_path.parent.mkdir(parents=True, exist_ok=True)
    merged_out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("校准图集 GraphModel(JSON) 批量导出完成：")
    print(f"- package: {package_id}")
    print(f"- scopes: {list(scopes)}")
    print(f"- graph_generater_root: {str(gg_root)}")
    print(f"- total_files: {total_files}")
    for scope_text in scopes:
        scope_info = (merged.get("per_scope") or {}).get(scope_text, {})
        print(f"- report[{scope_text}]: {scope_info.get('report_json')}")
    print(f"- merged_report: {str(merged_out_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()




