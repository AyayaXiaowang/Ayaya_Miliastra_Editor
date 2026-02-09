from __future__ import annotations

from pathlib import Path

from app.runtime.services.local_graph_simulator import GraphMountSpec, build_local_graph_sim_session
from engine.validate.node_graph_validator import validate_file as validate_node_graph_file
from tests._helpers.project_paths import get_repo_root


_GRAPH_MAIN_REL = "tests/local_sim/fixture_graph_local_sim_multi_a.py"
_GRAPH_EXTRA_REL = "tests/local_sim/fixture_graph_local_sim_multi_b.py"


def test_local_sim_multi_graph_mounts_multiple_handlers_on_same_event() -> None:
    repo_root = get_repo_root()
    graph_main = (repo_root / _GRAPH_MAIN_REL).resolve()
    graph_extra = (repo_root / _GRAPH_EXTRA_REL).resolve()

    for p in (graph_main, graph_extra):
        passed, errors, warnings = validate_node_graph_file(Path(p))
        assert passed, f"节点图校验失败（errors={len(errors)} warnings={len(warnings)}）：{errors[:5]}"

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=graph_main,
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(
                graph_code_file=graph_extra,
                owner_entity_name="服务实体",
            )
        ],
    )

    # 触发 click：主图与服务图都应收到同一事件，并分别写入各自 owner 实体的自定义变量。
    session.trigger_ui_click(data_ui_key="btn_allow")

    service = session.game.find_entity_by_name("服务实体")
    assert service is not None
    value_extra = session.game.custom_variables.get(service.entity_id, {}).get("extra_clicked")
    assert value_extra is True

    main = session.game.find_entity_by_name("自身实体")
    assert main is not None
    value_main = session.game.custom_variables.get(main.entity_id, {}).get("main_clicked")
    assert value_main is True

