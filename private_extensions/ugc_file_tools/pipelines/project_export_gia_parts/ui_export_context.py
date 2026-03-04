from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object
from ugc_file_tools.ui.guid_resolution import UiRecordIndex as _UiRecordIndex
from ugc_file_tools.ui.guid_resolution import build_ui_record_index_from_record_list as _build_ui_record_index_from_record_list

from .types import ProjectExportGiaPlan


@dataclass(frozen=True, slots=True)
class UiExportContext:
    record_id_text: str
    selected_ui_export_record: dict[str, object] | None
    ui_key_to_guid_registry: dict[str, int]
    selected_ui_export_record_ui_index: _UiRecordIndex | None
    selected_ui_export_record_ui_guids: set[int] | None
    layout_name_to_export_pos: dict[str, int]


def build_ui_export_context(*, plan: ProjectExportGiaPlan, gg_root: Path, package_id: str) -> UiExportContext:
    """
    构造 UI 回填所需上下文：
    - 选择 UI 导出记录（record_id/ latest / 自动选最新一条）
    - 加载 registry snapshot（ui_key→guid）
    - 若记录绑定了 output_gil_file，则读取 UI records 构建索引以便“按 layout root name”反查 GUID
    - 解析导出记录 extra.layout_names，用于 LayoutIndex 旧口径桥接
    """
    # 可选：UI 导出记录（用于 ui_key 回填）：
    # - 显式传入 record_id / latest：按用户指定；
    # - 未传入：若存在记录则自动选最新一条；否则不回填（除非 allow_unresolved_ui_keys=True）。
    selected_ui_export_record: dict[str, object] | None = None
    selected_ui_export_record_ui_guids: set[int] | None = None
    selected_ui_export_record_ui_index: _UiRecordIndex | None = None

    record_id_text = str(plan.ui_export_record_id or "").strip()
    if record_id_text == "":
        from ugc_file_tools.ui.export_records import load_ui_export_records

        recs = load_ui_export_records(workspace_root=Path(gg_root).resolve(), package_id=str(package_id))
        if recs:
            record_id_text = str(recs[0].record_id)

    if record_id_text.lower() == "latest":
        from ugc_file_tools.ui.export_records import load_ui_export_records

        recs = load_ui_export_records(workspace_root=Path(gg_root).resolve(), package_id=str(package_id))
        if not recs:
            raise ValueError(
                "ui_export_record_id='latest' 但当前项目不存在任何 UI 导出记录。\n"
                f"- package_id: {str(package_id)!r}\n"
                "解决方案：先从网页导出一次 GIL（会自动生成记录），或在导出对话框中选择其它 UI 导出记录。"
            )
        record_id_text = str(recs[0].record_id)

    ui_key_to_guid_registry: dict[str, int] = {}
    if record_id_text != "":
        from ugc_file_tools.ui.export_records import load_ui_guid_registry_snapshot, try_get_ui_export_record_by_id

        rec = try_get_ui_export_record_by_id(
            workspace_root=Path(gg_root).resolve(),
            package_id=str(package_id),
            record_id=str(record_id_text),
        )
        if rec is None:
            raise ValueError(
                "未找到指定的 UI 导出记录（record_id 不存在或已被清理）。\n"
                f"- record_id: {record_id_text!r}\n"
                f"- records_file: {str(Path(gg_root).resolve() / 'app' / 'runtime' / 'cache' / 'ui_artifacts' / str(package_id) / 'ui_export_records.json')}\n"
                "解决方案：重新从网页导出一次 GIL 以生成记录，或在导出对话框中改选其它记录。"
            )
        selected_ui_export_record = dict(rec.payload)

        snap_path_text = str(selected_ui_export_record.get("ui_guid_registry_snapshot_path") or "").strip()
        if snap_path_text == "":
            raise ValueError(f"UI 导出记录缺少 snapshot 路径（内部错误）：record_id={record_id_text!r}")
        snap_path = Path(snap_path_text).resolve()
        if not snap_path.is_file():
            raise FileNotFoundError(str(snap_path))

        ui_key_to_guid_registry = load_ui_guid_registry_snapshot(snap_path)

        # 额外校验：若记录包含 output_gil_file，则可用其 UI records 反查 GUID 是否存在，避免回填到“不属于该存档”的控件
        out_gil_text = str(selected_ui_export_record.get("output_gil_file") or "").strip()
        if out_gil_text != "":
            out_gil_path = Path(out_gil_text).resolve()
            if out_gil_path.is_file():
                base_raw_dump_object = dump_gil_to_raw_json_object(out_gil_path)
                root_data = base_raw_dump_object.get("4")
                field9 = root_data.get("9") if isinstance(root_data, dict) else None
                record_list = field9.get("502") if isinstance(field9, dict) else None
                if isinstance(record_list, list):
                    ui_index = _build_ui_record_index_from_record_list(list(record_list))
                    if ui_index is not None:
                        selected_ui_export_record_ui_index = ui_index
                        selected_ui_export_record_ui_guids = set(ui_index.guid_set)

    # UI 导出记录中包含 layout_names（导出顺序），用于 LayoutIndex 旧口径桥接
    layout_name_to_export_pos: dict[str, int] = {}
    if selected_ui_export_record is not None:
        extra = selected_ui_export_record.get("extra")
        if isinstance(extra, dict):
            layout_names = extra.get("layout_names")
            if isinstance(layout_names, list):
                for idx, n0 in enumerate(layout_names):
                    name = str(n0 or "").strip()
                    if name != "" and name not in layout_name_to_export_pos:
                        layout_name_to_export_pos[str(name)] = int(idx)

    return UiExportContext(
        record_id_text=str(record_id_text),
        selected_ui_export_record=selected_ui_export_record,
        ui_key_to_guid_registry=ui_key_to_guid_registry,
        selected_ui_export_record_ui_index=selected_ui_export_record_ui_index,
        selected_ui_export_record_ui_guids=selected_ui_export_record_ui_guids,
        layout_name_to_export_pos=layout_name_to_export_pos,
    )

