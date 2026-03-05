from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional, Sequence

from ugc_file_tools.gil_signal_repair.from_imported_gia import repair_gil_signals_from_imported_gia
from ugc_file_tools.console_encoding import configure_console_encoding


def _read_json_file(path: Path) -> Any:
    report_path = Path(path).resolve()
    if not report_path.is_file():
        raise FileNotFoundError(str(report_path))
    return json.loads(report_path.read_text(encoding="utf-8"))


def _pick_gia_path_from_exported_graph_item(item: dict) -> Path:
    copied_output = str(item.get("copied_output_gia_file") or "").strip()
    output = str(item.get("output_gia_file") or "").strip()
    chosen = copied_output or output
    if chosen == "":
        graph_id_int = item.get("graph_id_int")
        graph_name = str(item.get("graph_name") or "").strip()
        raise ValueError(f"export report graph missing output_gia_file: graph_id_int={graph_id_int}, graph_name={graph_name!r}")
    path = Path(chosen).resolve()
    if path.suffix.lower() != ".gia":
        raise ValueError(f"export report graph output file must be .gia: {str(path)!r}")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def _extract_imported_gia_files_from_export_report(report_payload: Any) -> list[Path]:
    if not isinstance(report_payload, dict):
        raise ValueError("export report JSON must be an object")
    exported_graphs = report_payload.get("exported_graphs")
    if not isinstance(exported_graphs, list) or not exported_graphs:
        raise ValueError("export report JSON missing exported_graphs list")

    out: list[Path] = []
    seen: set[str] = set()
    for item in exported_graphs:
        if not isinstance(item, dict):
            raise ValueError("export report exported_graphs item must be an object")
        path = _pick_gia_path_from_exported_graph_item(item)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)

    if not out:
        raise ValueError("no .gia files extracted from export report")
    return out


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description=(
            "Repair signal damage in .gil based on an export_project_graphs_to_gia report JSON: "
            "auto-collect imported .gia files and run the same repair logic as repair_gil_signals_from_imported_gia."
        )
    )
    parser.add_argument("input_gil_file", help="Input .gil file path")
    parser.add_argument("output_gil_file", help="Output .gil file path (must differ from input)")
    parser.add_argument(
        "--export-report",
        dest="export_report_json_file",
        required=True,
        help="export_project_graphs_to_gia report JSON file path (contains exported_graphs[].output_gia_file)",
    )
    parser.add_argument(
        "--no-prune-placeholder-orphans",
        dest="no_prune_placeholder_orphans",
        action="store_true",
        help="Disable pruning of unreferenced placeholder signal node_defs",
    )
    parser.add_argument(
        "--report",
        dest="report_json_file",
        default="",
        help="Optional JSON report output file path",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    export_report_path = Path(str(args.export_report_json_file)).resolve()
    export_report_payload = _read_json_file(export_report_path)
    imported_gia_files = _extract_imported_gia_files_from_export_report(export_report_payload)

    report = repair_gil_signals_from_imported_gia(
        input_gil_file_path=Path(str(args.input_gil_file)),
        output_gil_file_path=Path(str(args.output_gil_file)),
        imported_gia_files=imported_gia_files,
        prune_placeholder_orphans=(not bool(args.no_prune_placeholder_orphans)),
    )
    report["export_report_json_file"] = str(export_report_path)

    report_path_text = str(args.report_json_file or "").strip()
    if report_path_text:
        report_path = Path(report_path_text).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



