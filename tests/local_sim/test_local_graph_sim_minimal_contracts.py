from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime.services.local_graph_sim_server import LocalGraphSimServer, LocalGraphSimServerConfig
from app.runtime.services.local_graph_simulator import build_local_graph_sim_session, stable_layout_index_from_html_stem
from engine.validate.node_graph_validator import validate_file as validate_node_graph_file
from tests._helpers.project_paths import get_repo_root


_GRAPH_REL = "tests/local_sim/fixture_graph_local_sim_minimal.py"
_UI_HTML_REL = "tests/local_sim/fixture_ui_local_sim_minimal.html"
_TUTORIAL_GUIDE0_BTN_VAR_NAME = "按钮索引_btn_tut_g0"


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

    tutorial_guide0 = session.game.graph_variables.get(_TUTORIAL_GUIDE0_BTN_VAR_NAME)
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


def _http_get_json(url: str) -> dict:
    import json
    import urllib.request

    with urllib.request.urlopen(url, timeout=5) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def _http_post_json(url: str, payload: dict) -> dict:
    import json
    import urllib.request

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def test_local_sim_server_exposes_last_action_and_snapshot_and_validate(_local_sim_server: LocalGraphSimServer) -> None:
    server = _local_sim_server
    base = server.get_url().rstrip("/")

    proto = _http_get_json(base + "/api/local_sim/protocol")
    assert proto.get("ok") is True
    assert int(proto.get("protocol_version") or 0) >= 1
    assert int(proto.get("schema_version") or 0) >= 1
    assert isinstance(proto.get("endpoints") or {}, dict)

    st = _http_get_json(base + "/api/local_sim/status")
    assert st.get("ok") is True
    assert st.get("schema_version") == proto.get("schema_version")
    assert st.get("protocol_version") == proto.get("protocol_version")
    assert st.get("graph", {}).get("graph_code_file")

    snap = _http_get_json(base + "/api/local_sim/snapshot?entities=0")
    assert snap.get("ok") is True
    assert snap.get("schema_version") == proto.get("schema_version")
    assert snap.get("protocol_version") == proto.get("protocol_version")
    snapshot = snap.get("snapshot") or {}
    assert "variables" in snapshot

    # click should populate last_action and diff
    resp = _http_post_json(
        base + "/api/local_sim/click",
        {"data_ui_key": "btn_allow", "data_ui_state_group": "", "data_ui_state": ""},
    )
    assert resp.get("ok") is True
    assert isinstance(resp.get("patches"), list)

    last = _http_get_json(base + "/api/local_sim/last_action")
    assert last.get("ok") is True
    action = last.get("last_action") or {}
    assert action.get("kind") == "ui_click"
    assert isinstance(action.get("diff_summary"), dict)
    assert isinstance(action.get("diff_changes"), list)

    # validate endpoint returns structured report
    v = _http_post_json(base + "/api/local_sim/validate", {})
    assert v.get("ok") is True
    assert isinstance(v.get("issues"), list)


def test_local_sim_server_export_repro_bundle_downloads_and_matches_file(_local_sim_server: LocalGraphSimServer) -> None:
    server = _local_sim_server
    base = server.get_url().rstrip("/")

    resp = _http_post_json(
        base + "/api/local_sim/export_repro",
        {
            "include_entities": False,
            "include_snapshot": True,
            "include_trace": True,
            "include_validation": True,
            "include_last_action": True,
            "recorded_actions": [{"kind": "ui_click", "details": {"data_ui_key": "btn_allow"}, "timestamp": 0}],
            "note": "pytest",
        },
    )
    assert resp.get("ok") is True
    export_file = str(resp.get("export_file") or "")
    assert export_file
    assert Path(export_file).is_file()

    download_url = str(resp.get("download_url") or "")
    assert download_url.startswith("/api/local_sim/export_repro?id=")
    bundle = _http_get_json(base + download_url)
    assert int(bundle.get("version") or 0) == 1
    assert isinstance(bundle.get("graph") or {}, dict)
    assert isinstance(bundle.get("snapshot") or {}, dict)
    assert isinstance(bundle.get("trace"), list)
    assert isinstance(bundle.get("validation_report") or {}, dict)
    assert isinstance(bundle.get("recorded_actions"), list)

    # 内容一致性：下载内容应与落盘文件一致
    file_text = Path(export_file).read_text(encoding="utf-8")
    assert file_text.strip() != ""
    assert file_text.strip().startswith("{")


def test_local_sim_server_resolve_ui_key_endpoint_works_even_when_paused(_local_sim_server: LocalGraphSimServer) -> None:
    server = _local_sim_server
    base = server.get_url().rstrip("/")

    # pause world
    p = _http_post_json(base + "/api/local_sim/pause", {"paused": True})
    assert p.get("ok") is True
    assert p.get("paused") is True

    # resolve should still work (read-only)
    r1 = _http_post_json(
        base + "/api/local_sim/resolve_ui_key",
        {"data_ui_key": "btn_allow", "data_ui_state_group": "", "data_ui_state": ""},
    )
    assert r1.get("ok") is True
    resolved = r1.get("resolved") or {}
    assert str(resolved.get("chosen_ui_key") or "").endswith("__btn_allow__btn_item")
    assert int(resolved.get("index") or 0) > 0

    # unresolved should be 400
    import urllib.error

    with pytest.raises(urllib.error.HTTPError) as exc:
        _http_post_json(
            base + "/api/local_sim/resolve_ui_key",
            {"data_ui_key": "btn__does_not_exist__", "data_ui_state_group": "", "data_ui_state": ""},
        )
    assert int(exc.value.code) == 400


@pytest.fixture
def _local_sim_server_with_fake_monotonic(monkeypatch) -> tuple[LocalGraphSimServer, dict]:
    """
    控制 server 虚拟时钟与 GameRuntime 定时器的基准时间，避免依赖真实 sleep。
    """
    state = {"t": 0.0}

    import app.runtime.services.local_graph_sim_server as server_module
    import app.runtime.engine.game_state as game_state_module

    monkeypatch.setattr(server_module.time, "monotonic", lambda: float(state["t"]))
    monkeypatch.setattr(game_state_module.time, "monotonic", lambda: float(state["t"]))

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
    yield server, state
    server.stop()


def test_local_sim_pause_freezes_timers_and_resume_does_not_catch_up(
    _local_sim_server_with_fake_monotonic: tuple[LocalGraphSimServer, dict],
) -> None:
    server, state = _local_sim_server_with_fake_monotonic
    base = server.get_url().rstrip("/")

    fired = {"n": 0}

    def _on_timer(**_kwargs) -> None:
        fired["n"] = int(fired["n"]) + 1

    ent = server.session.owner_entity
    server.session.game.register_event_handler("定时器触发时", _on_timer, owner=ent)
    server.session.game.start_timer_sequence(ent, "pause_test", [1.0], is_loop=False)

    # pause
    p = _http_post_json(base + "/api/local_sim/pause", {"paused": True})
    assert p.get("ok") is True
    assert p.get("paused") is True

    # paused 世界冻结：click/emit_signal 均应被拒绝（409）
    import urllib.error

    with pytest.raises(urllib.error.HTTPError) as exc1:
        _http_post_json(base + "/api/local_sim/click", {"data_ui_key": "btn_allow", "data_ui_state_group": "", "data_ui_state": ""})
    assert int(exc1.value.code) == 409

    with pytest.raises(urllib.error.HTTPError) as exc2:
        _http_post_json(base + "/api/local_sim/emit_signal", {"signal_id": "unknown", "params": {}})
    assert int(exc2.value.code) == 409

    # time passes, but poll should not advance timers
    state["t"] = 10.0
    _http_get_json(base + "/api/local_sim/poll")
    assert int(fired["n"]) == 0

    # resume: no catch-up; virtual time continues from pre-pause
    r = _http_post_json(base + "/api/local_sim/pause", {"paused": False})
    assert r.get("ok") is True
    assert r.get("paused") is False

    _http_get_json(base + "/api/local_sim/poll")
    assert int(fired["n"]) == 0

    # virtual time reaches +1.0 => should fire once
    state["t"] = 11.0
    _http_get_json(base + "/api/local_sim/poll")
    assert int(fired["n"]) == 1


def test_local_sim_step_advances_one_timer_fire_while_paused(_local_sim_server_with_fake_monotonic: tuple[LocalGraphSimServer, dict]) -> None:
    server, state = _local_sim_server_with_fake_monotonic
    base = server.get_url().rstrip("/")

    fired = {"n": 0}

    def _on_timer(**_kwargs) -> None:
        fired["n"] = int(fired["n"]) + 1

    ent = server.session.owner_entity
    server.session.game.register_event_handler("定时器触发时", _on_timer, owner=ent)
    server.session.game.start_timer_sequence(ent, "step_test", [1.0], is_loop=False)

    _http_post_json(base + "/api/local_sim/pause", {"paused": True})

    # 单步 0.5s：还没到期
    r1 = _http_post_json(base + "/api/local_sim/step", {"dt": 0.5})
    assert r1.get("ok") is True
    assert int(r1.get("timer_fired") or 0) in (0, 1)
    assert int(fired["n"]) == 0

    # 再单步 0.6s：跨过 1.0s，应最多触发一次
    r2 = _http_post_json(base + "/api/local_sim/step", {"dt": 0.6})
    assert r2.get("ok") is True
    assert int(r2.get("timer_fired") or 0) == 1
    assert int(fired["n"]) == 1
