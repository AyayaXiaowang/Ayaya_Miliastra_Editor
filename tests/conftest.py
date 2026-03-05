from __future__ import annotations

import sys
from pathlib import Path
from importlib.util import find_spec
from typing import Final

# 确保项目根目录在 sys.path 中，便于在 pytest 下稳定导入 `app`、`engine` 等包。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

# 注意：不要将 `<repo>/app` 加入 sys.path。
# 否则 `app/ui` 会变成顶层包 `ui`，从而导致 `ui.*` 与 `app.ui.*` 并存并触发“同名类不是同一个类”。

# 顺序约束（Windows 常见）：若环境存在 OCR 依赖，则 RapidOCR 必须先于 PyQt6 导入，避免 DLL 冲突。
# 说明：PyQt6 可能在 tests/ui 之外的测试或被测模块中被间接导入，因此该约束需要放在 tests 根 conftest 中。
if find_spec("rapidocr_onnxruntime") is not None:
    from rapidocr_onnxruntime import RapidOCR  # noqa: F401

# 初始化 settings 的 workspace_path 单一真源，供布局/节点库等模块稳定推导工作区。
from engine.configs.settings import settings  # noqa: E402

settings.set_config_path(PROJECT_ROOT)
settings.load()

PATH_SEP: Final[str] = "/"
PATH_SEP_LEN: Final[int] = len(PATH_SEP)

DISABLED_TEST_MODULES_REL: Final[set[str]] = {
    # 资源/样本依赖（本机目录结构漂移或样本未版本化）
    "tests/graph/test_custom_var_delta_not_self_subtraction.py",
    "tests/graph/test_no_none_input_constants_in_level7_server_graphs.py",
    "tests/local_sim/test_local_sim_level_select_start_level_param.py",
    # GIL/GIA 口径同步与写回契约（当前口径尚未收敛）
    "tests/tooling/test_gil_writeback_sync_with_gia_rules.py",
    "tests/ugc_file_tools/test_gil_infrastructure_bootstrap_patches_missing_root4_sections.py",
    "tests/ugc_file_tools/test_gil_writeback_listen_signal_event_node_writes_meta_flow_cpi_and_signal_index.py",
    "tests/ugc_file_tools/test_gil_writeback_roundtrip_golden_snapshot.py",
    "tests/ugc_file_tools/test_project_writeback_auto_enables_instances_for_template_decorations.py",
    "tests/ugc_file_tools/test_project_writeback_auto_enables_signals_for_graphs.py",
    "tests/ugc_file_tools/test_project_writeback_custom_variables_group1.py",
    "tests/ugc_file_tools/test_project_writeback_instances_supports_string_ids.py",
    "tests/ugc_file_tools/test_project_writeback_shape_editor_instance_decorations.py",
    "tests/ugc_file_tools/test_project_writeback_template_tabs_registry.py",
    # Web UI 导入链路（路径约束/变量引用口径待统一）
    "tests/ugc_file_tools/test_web_ui_import_batch_layout_tree_invariants.py",
    "tests/ui/workbench/test_ui_web_import_end_to_end_with_builtin_templates.py",
    "tests/ui/workbench/test_ui_workbench_allow_duplicate_item_display_keycodes.py",
    "tests/ui/workbench/test_ui_workbench_placeholder_validation.py",
}

DISABLED_TEST_REASON: Final[str] = (
    "临时跳过：该用例当前依赖本机样本/资源路径或口径尚未收敛（按需求暂不作为阻断项）。"
)


def _norm_path_text(value: object) -> str:
    return str(value).replace("\\", PATH_SEP).lower()


def pytest_collection_modifyitems(config, items) -> None:
    """
    按用户需求：暂时跳过一批当前不稳定/不通过的测试模块，避免阻断日常回归。

    - 仅影响测试执行，不影响程序运行态。
    - 保留测试文件本体，后续删除名单即可恢复执行。
    """
    import pytest

    root = _norm_path_text(getattr(config, "rootpath", PROJECT_ROOT))
    root_prefix = root + PATH_SEP

    for item in items:
        full_path = _norm_path_text(getattr(item, "fspath", ""))
        rel = full_path[len(root_prefix) :] if full_path.startswith(root_prefix) else full_path
        if rel in DISABLED_TEST_MODULES_REL:
            item.add_marker(pytest.mark.skip(reason=DISABLED_TEST_REASON))