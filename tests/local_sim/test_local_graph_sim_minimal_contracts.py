from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime.services.local_graph_sim_server import LocalGraphSimServer, LocalGraphSimServerConfig
from app.runtime.services.local_graph_simulator import build_local_graph_sim_session, stable_layout_index_from_html_stem
from engine.validate.node_graph_validator import validate_file as validate_node_graph_file
from tests._helpers.project_paths import get_repo_root


_GRAPH_REL = "tests/local_sim/fixture_graph_local_sim_minimal.py"
_UI_HTML_REL = "tests/local_sim/fixture_ui_local_sim_minimal.html"


def _graph_file(repo_root: Path) -> Path:
    return (repo_root / _GRAPH_REL).resolve()


def _ui_html_file(repo_root: Path) -> Path:
    return (repo_root / _UI_HTML_REL).resolve()


def test_local_sim_minimal_graph_validation_and_registry_contracts() -> None:
    repo_root = get_repo_root()
    graph_path = _graph_file(repo_root)

    passed, errors, warnings = validate_node_graph_file(graph_path)
    assert passed, f"节点图校验失败（errors={len(errors)} warnings={len(warnings)}）：{errors[:5]}"

    session = build_local_graph_sim_session(workspace_root=repo_root, graph_code_file=graph_path, present_player_count=1)

    allow_btn = session.game.graph_variables.get("按钮索引_btn_allow")
    assert isinstance(allow_btn, int) and allow_btn > 0
    assert session.ui_registry.try_get_key(int(allow_btn)) == "HTML导入_界面布局__btn_allow__btn_item"

    tutorial_guide0 = session.game.graph_variables.get("按钮索引_btn_tutorial_next_guide_0")
    assert isinstance(tutorial_guide0, int) and tutorial_guide0 > 0
    assert (
        session.ui_registry.try_get_key(int(tutorial_guide0))
        == "HTML导入_界面布局__tutorial_overlay__guide_0__btn_item"
    )

    layout_a = session.game.graph_variables.get("布局索引_页A")
    layout_b = session.game.graph_variables.get("布局索引_页B")
    assert isinstance(layout_a, int) and layout_a != 0
    assert isinstance(layout_b, int) and layout_b != 0
    assert int(layout_a) == stable_layout_index_from_html_stem("page_a")
    assert int(layout_b) == stable_layout_index_from_html_stem("page_b")

    # click 注入：应能触发事件回调并写回图变量
    session.trigger_ui_click(data_ui_key="btn_allow")
    last_clicked = session.game.graph_variables.get("最后一次点击GUID")
    assert int(last_clicked or 0) == int(allow_btn)


@pytest.fixture
def _local_sim_server(monkeypatch) -> LocalGraphSimServer:
    """启动本地测试 HTTP server（使用系统分配端口，避免端口占用/串服务）。"""
    monkeypatch.setenv("AYAYA_LOCAL_HTTP_PORT", "0")
    repo_root = get_repo_root()

    server = LocalGraphSimServer(
        LocalGraphSimServerConfig(
            workspace_root=repo_root,
            graph_code_file=_graph_file(repo_root),
            ui_html_file=_ui_html_file(repo_root),
            present_player_count=1,
        )
    )
    server.start()
    yield server
    server.stop()


def test_local_sim_server_bootstrap_injects_lv_defaults(_local_sim_server: LocalGraphSimServer) -> None:
    server = _local_sim_server
    assert server.port > 0

    assert isinstance(server.session.game.ui_lv_defaults.get("UI战斗_文本"), dict)
    assert isinstance(server.session.game.ui_lv_defaults.get("UI房间_文本"), dict)

    expected_index = stable_layout_index_from_html_stem("fixture_ui_local_sim_minimal")
    assert server.current_layout_index == expected_index
    assert server.get_layout_html_file(expected_index) == _ui_html_file(get_repo_root())

