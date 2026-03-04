from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._common import IdRefPlaceholderUsage


@dataclass(slots=True)
class ExportCenterDialogRuntimeState:
    """
    导出中心对话框（export_wizard）运行期状态。

    说明：
    - 该结构只保存“运行期缓存/用户选择”等状态，不负责持久化；
    - 避免在 controller 内使用 nonlocal/闭包变量分散状态，降低“操作顺序触发 bug”的风险。
    """

    # ---- selection-derived caches ----
    id_ref_usage_for_selected_graphs: IdRefPlaceholderUsage = field(
        default_factory=lambda: IdRefPlaceholderUsage(entity_names=frozenset(), component_names=frozenset())
    )
    ui_keys_for_selected_graphs: frozenset[str] = field(default_factory=frozenset)
    ui_key_layout_hints_by_key: dict[str, frozenset[str]] = field(default_factory=dict)

    # record_id -> record (opaque)
    ui_export_records_by_id: dict[str, Any] = field(default_factory=dict)

    # ---- UI choice caches ----
    write_ui_user_choice: bool = False

    # ---- backfill/repair caches ----
    repair_last_auto_output: str = ""
    backfill_last_signature_gia: tuple = field(default_factory=tuple)
    backfill_last_signature_gil: tuple = field(default_factory=tuple)

    # 最近一次“识别”返回的 report（用于后续交互：例如缺失行双击→选择 ID）。
    backfill_last_identify_report: dict[str, Any] | None = None
    # 当前选择下的“待识别依赖行”（用于 UI 表格初始展示与识别结果合并）。
    backfill_pending_rows: list[dict[str, str]] = field(default_factory=list)
    # 当前回填表展示的行（用于“手动覆盖后重新分组到标签页”等纯 UI 更新）。
    backfill_current_rows: list[dict[str, object]] = field(default_factory=list)

    # ---- IDRef 手动覆盖（entity_key/component_key）----
    # key：占位符中的 name（entity_key:<name> / component_key:<name>）
    # value：用户手动选择的 ID（来自参考/地图 .gil）
    id_ref_override_component_name_to_id: dict[str, int] = field(default_factory=dict)
    id_ref_override_entity_name_to_guid: dict[str, int] = field(default_factory=dict)

    # ---- ID 候选缓存（避免重复解码/扫描同一份 .gil）----
    # key：gil_path.resolve().as_posix().casefold()
    id_ref_template_candidates_by_gil_cf: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    id_ref_instance_candidates_by_gil_cf: dict[str, list[tuple[str, int]]] = field(default_factory=dict)


__all__ = ["ExportCenterDialogRuntimeState"]

