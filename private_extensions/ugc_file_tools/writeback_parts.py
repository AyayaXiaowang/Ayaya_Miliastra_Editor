from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class WritebackPartId(str, Enum):
    """
    项目存档 → 写回 .gil 的“写回段”枚举。

    注意：这不是 Graph_Generater 的 ResourceType（资源种类）；而是 ugc_file_tools 当前实现的写回能力点。
    """

    # === 已支持写回 ===
    TEMPLATES = "templates"
    INSTANCES = "instances"
    STRUCTS = "structs"
    SIGNALS = "signals"
    GRAPHS = "graphs"
    UI_WIDGET_TEMPLATES = "ui_widget_templates"

    # === 暂不支持写回（仅 UI 置灰展示用）===
    BATTLE_PRESETS = "battle_presets"
    UI_LAYOUTS = "ui_layouts"
    OTHER_MANAGEMENT = "other_management"


@dataclass(frozen=True, slots=True)
class WritebackPartSpec:
    part_id: WritebackPartId
    title: str
    supported: bool
    plan_flag: str | None = None
    empty_hint: str = "（无数据）"
    tooltip: str = ""


WRITEBACK_PART_SPECS: tuple[WritebackPartSpec, ...] = (
    WritebackPartSpec(
        part_id=WritebackPartId.TEMPLATES,
        title="元件库模板",
        supported=True,
        plan_flag="export_templates",
    ),
    WritebackPartSpec(
        part_id=WritebackPartId.INSTANCES,
        title="实体摆放",
        supported=True,
        plan_flag="export_instances",
    ),
    WritebackPartSpec(
        part_id=WritebackPartId.STRUCTS,
        title="结构体定义",
        supported=True,
        plan_flag="export_structs",
    ),
    WritebackPartSpec(
        part_id=WritebackPartId.SIGNALS,
        title="信号定义",
        supported=True,
        plan_flag="export_signals",
    ),
    WritebackPartSpec(
        part_id=WritebackPartId.GRAPHS,
        title="节点图",
        supported=True,
        plan_flag="export_graphs",
    ),
    WritebackPartSpec(
        part_id=WritebackPartId.UI_WIDGET_TEMPLATES,
        title="界面（HTML/UI源码 或 raw_template）",
        supported=True,
        plan_flag="export_ui_widget_templates",
        empty_hint="（缺少 UI源码 Workbench 产物 / raw_template）",
        tooltip="把 UI 写进 base .gil：优先使用 UI源码（__workbench_out__/*.ui_bundle.json）写回；若存在 raw_template(record bundle) 则走更保守的 raw_template 写回。",
    ),
    WritebackPartSpec(
        part_id=WritebackPartId.BATTLE_PRESETS,
        title="战斗预设",
        supported=False,
        plan_flag=None,
        empty_hint="",
        tooltip="暂不支持写回（不会修改 base .gil 的对应段）。",
    ),
    WritebackPartSpec(
        part_id=WritebackPartId.UI_LAYOUTS,
        title="界面布局",
        supported=False,
        plan_flag=None,
        empty_hint="",
        tooltip="暂不支持写回（不会修改 base .gil 的对应段）。",
    ),
    WritebackPartSpec(
        part_id=WritebackPartId.OTHER_MANAGEMENT,
        title="其它管理配置段",
        supported=False,
        plan_flag=None,
        empty_hint="",
        tooltip="暂不支持写回（不会修改 base .gil 的对应段）。",
    ),
)


def iter_supported_writeback_part_specs() -> tuple[WritebackPartSpec, ...]:
    return tuple(spec for spec in WRITEBACK_PART_SPECS if bool(spec.supported))


def iter_unsupported_writeback_part_specs() -> tuple[WritebackPartSpec, ...]:
    return tuple(spec for spec in WRITEBACK_PART_SPECS if not bool(spec.supported))


def get_supported_writeback_plan_flags() -> dict[WritebackPartId, str]:
    return {
        spec.part_id: str(spec.plan_flag)
        for spec in iter_supported_writeback_part_specs()
        if spec.plan_flag is not None
    }


def _iter_project_json_files(project_dir: Path, *, ignore_names: set[str], ignore_prefixes: tuple[str, ...]) -> list[Path]:
    if not project_dir.is_dir():
        return []
    out: list[Path] = []
    for p in project_dir.glob("*.json"):
        if not p.is_file():
            continue
        if p.name in ignore_names:
            continue
        if any(p.name.startswith(prefix) for prefix in ignore_prefixes):
            continue
        out.append(p)
    return out


def _has_non_trivial_py_files(dir_path: Path) -> bool:
    if not dir_path.is_dir():
        return False
    for p in dir_path.rglob("*.py"):
        if not p.is_file():
            continue
        if p.name == "__init__.py":
            continue
        if p.name.startswith("_"):
            continue
        if p.parent.name == "__pycache__":
            continue
        return True
    return False


def _detect_templates(project_root: Path) -> bool:
    return bool(
        _iter_project_json_files(
            project_root / "元件库",
            ignore_names={"templates_index.json"},
            ignore_prefixes=(),
        )
    )


def _detect_instances(project_root: Path) -> bool:
    # 约定：自研_*.json 为工具输出/临时文件，默认不参与写回。
    has_instance_files = bool(
        _iter_project_json_files(
            project_root / "实体摆放",
            ignore_names={"instances_index.json"},
            ignore_prefixes=("自研_", "shape_editor_"),
        )
    )
    if has_instance_files:
        return True
    return False


def _detect_graphs(project_root: Path) -> bool:
    graphs_dir = project_root / "节点图"
    if not graphs_dir.is_dir():
        return False
    for p in graphs_dir.rglob("*.py"):
        if not p.is_file():
            continue
        if p.name == "__init__.py":
            continue
        if p.name.startswith("_"):
            continue
        return True
    return False


def _detect_ui_widget_templates(project_root: Path) -> bool:
    ui_dir = project_root / "管理配置" / "UI控件模板"
    has_template_json = bool(
        _iter_project_json_files(
            ui_dir,
            ignore_names={"ui_widget_templates_index.json"},
            ignore_prefixes=(),
        )
    )
    if not has_template_json:
        # 新链路：UI源码（HTML）→ Workbench 输出（ui_bundle.json）→ 写回 .gil
        src_out_dir = project_root / "管理配置" / "UI源码" / "__workbench_out__"
        if src_out_dir.is_dir() and any(src_out_dir.glob("*.ui_bundle.json")):
            return True
        return False

    # UI控件模板写回依赖“原始解析 raw_bundle”（record 级模板），否则无法稳定写回到 .gil。
    raw_dir = ui_dir / "原始解析"
    if not raw_dir.is_dir():
        # 没有 raw_bundle 时，尝试走 UI源码（HTML）链路（如果存在 Workbench 产物）
        src_out_dir = project_root / "管理配置" / "UI源码" / "__workbench_out__"
        return bool(src_out_dir.is_dir() and any(src_out_dir.glob("*.ui_bundle.json")))
    if any(raw_dir.glob("ugc_ui_widget_template_*.raw.json")):
        return True

    # 有模板 JSON 但缺 raw_bundle：仍允许走 UI源码链路（你们当前主用）
    src_out_dir = project_root / "管理配置" / "UI源码" / "__workbench_out__"
    return bool(src_out_dir.is_dir() and any(src_out_dir.glob("*.ui_bundle.json")))


def _detect_signals(project_root: Path, *, workspace_root: Path) -> bool:
    project_signal_dir = project_root / "管理配置" / "信号"
    if _has_non_trivial_py_files(project_signal_dir):
        return True
    shared_signal_dir = workspace_root / "assets" / "资源库" / "共享" / "管理配置" / "信号"
    return _has_non_trivial_py_files(shared_signal_dir)


def _detect_structs(project_root: Path) -> bool:
    decoded_dir = project_root / "管理配置" / "结构体定义" / "原始解析"
    has_decoded = bool(list(decoded_dir.glob("struct_def_*_*.decoded.json"))) if decoded_dir.is_dir() else False
    if has_decoded:
        return True

    basic_dir = project_root / "管理配置" / "结构体定义" / "基础结构体"
    if _has_non_trivial_py_files(basic_dir):
        return True

    ingame_dir = project_root / "管理配置" / "结构体定义" / "局内存档结构体"
    return _has_non_trivial_py_files(ingame_dir)


def compute_writeback_availability(*, project_root: Path, workspace_root: Path) -> dict[WritebackPartId, bool]:
    """
    计算“当前项目存档”下，每个【已支持写回】段是否可用。

    - 仅返回 supported 的 part_id；
    - workspace_root 用于检测共享信号等“共享根”数据源。
    """
    project_root = Path(project_root).resolve()
    workspace_root = Path(workspace_root).resolve()

    return {
        WritebackPartId.TEMPLATES: _detect_templates(project_root),
        WritebackPartId.INSTANCES: _detect_instances(project_root),
        WritebackPartId.STRUCTS: _detect_structs(project_root),
        WritebackPartId.SIGNALS: _detect_signals(project_root, workspace_root=workspace_root),
        WritebackPartId.GRAPHS: _detect_graphs(project_root),
        WritebackPartId.UI_WIDGET_TEMPLATES: _detect_ui_widget_templates(project_root),
    }

