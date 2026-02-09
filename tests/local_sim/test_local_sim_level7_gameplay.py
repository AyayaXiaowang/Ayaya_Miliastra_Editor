from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest

import app.runtime.engine.game_state as game_state_module
from app.runtime.services.local_graph_sim_server import _extract_lv_defaults_from_ui_html
from app.runtime.services.local_graph_simulator import GraphMountSpec, build_local_graph_sim_session, stable_layout_index_from_html_stem
from engine.validate.node_graph_validator import validate_file as validate_node_graph_file
from tests._helpers.project_paths import get_repo_root


_LEVEL7_GRAPH_DIR_REL = "assets/资源库/项目存档/测试项目/节点图/server/实体节点图/第七关"
_LEVEL7_UI_DIR_REL = "assets/资源库/项目存档/测试项目/管理配置/UI源码"

_GRAPH_GAME_IN_REL = f"{_LEVEL7_GRAPH_DIR_REL}/UI第七关_游戏中_交互逻辑.py"
_GRAPH_DOOR_REL = f"{_LEVEL7_GRAPH_DIR_REL}/第七关_门控制.py"
_GRAPH_DATA_REL = f"{_LEVEL7_GRAPH_DIR_REL}/第七关_亲戚数据服务.py"
_GRAPH_RESULT_REL = f"{_LEVEL7_GRAPH_DIR_REL}/UI第七关_结算_交互逻辑.py"

_UI_GAME_IN_REL = f"{_LEVEL7_UI_DIR_REL}/第七关-游戏中.html"
_UI_RESULT_REL = f"{_LEVEL7_UI_DIR_REL}/第七关-结算.html"

_LEVEL_ENTITY_GUID = "1094713345"


def _p(repo_root: Path, rel: str) -> Path:
    return (repo_root / rel).resolve()


class _UiButtonKeyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.keys: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs or [])
        if str(d.get("data-ui-role") or "").strip() != "button":
            return
        key = str(d.get("data-ui-key") or "").strip()
        if key:
            self.keys.add(key)


def _extract_ui_button_keys_from_html(html_file: Path) -> set[str]:
    text = Path(html_file).read_text(encoding="utf-8")
    parser = _UiButtonKeyParser()
    parser.feed(text)
    return set(parser.keys)


@pytest.fixture
def _clock(monkeypatch):
    """
    控制 MockRuntime 的时间：确保定时器的 start_time 与 tick 使用同一时间基准，
    避免“推进到很远的 now 导致新定时器立刻连环触发”引发用例不稳定。
    """
    state = {"t": 0.0}
    monkeypatch.setattr(game_state_module.time, "monotonic", lambda: float(state["t"]))
    # 抑制 MockRuntime 的大量 print（事件/定时器/实体等），避免回归用例被 I/O 拖慢或卡住退出。
    monkeypatch.setattr(game_state_module, "print", lambda *args, **kwargs: None, raising=False)

    def advance(dt: float) -> float:
        state["t"] = float(state["t"]) + float(dt)
        return float(state["t"])

    return state, advance


def _find_owner_entity_for_graph(session, graph_path: Path):
    g = Path(graph_path).resolve()
    for item in list(session.mounted_graphs or []):
        if Path(item.graph_code_file).resolve() == g:
            ent = session.game.get_entity(str(item.owner_entity_id))
            if ent is not None:
                return ent
            ent2 = session.game.find_entity_by_name(str(item.owner_entity_name))
            assert ent2 is not None
            return ent2
    raise AssertionError(f"未找到挂载图：{g}")


def _seed_level7_data_service(session, *, truth_allow_first: bool, first_body: str = "瘦马") -> dict:
    repo_root = get_repo_root()
    data_graph = _p(repo_root, _GRAPH_DATA_REL)
    store = _find_owner_entity_for_graph(session, data_graph)

    visits = 10
    roles = ["大姨", "二舅", "三叔", "四姑", "五伯", "六婶", "七叔", "八姑", "九舅", "十姨"]
    assert len(roles) == visits

    truths = [bool(truth_allow_first)] + [bool(truth_allow_first) for _ in range(visits - 1)]

    # 这些外观字段必须落在《UI第七关_游戏中_交互逻辑》的映射字典 key 内，否则查表会失败。
    body = ["瘦马"] * visits
    body[0] = str(first_body)
    hair = ["大背头"] * visits
    beard = ["无"] * visits
    glasses = ["无"] * visits
    clothes = ["西装"] * visits
    neckwear = ["领带"] * visits

    l1 = [f"{r}：你好，我来拜年（1）" for r in roles]
    l2 = [f"{r}：我带了礼物（2）" for r in roles]
    l3 = [f"{r}：今年一定顺利（3）" for r in roles]
    l4 = [f"{r}：快让我进门吧（4）" for r in roles]

    clue_title = "测试纸条"
    clue_tags = ["T1", "T2", "T3", "T4", "T5", "T6"]
    clue_texts = ["X1", "X2", "X3", "X4", "X5", "X6"]

    session.game.set_custom_variable(store, "l7_rounds_count", 1, trigger_event=False)
    session.game.set_custom_variable(store, "l7_clue_title", clue_title, trigger_event=False)
    session.game.set_custom_variable(
        store,
        "l7_clue_tags_flat",
        list(clue_tags),
        trigger_event=False,
    )
    session.game.set_custom_variable(
        store,
        "l7_clue_texts_flat",
        list(clue_texts),
        trigger_event=False,
    )
    session.game.set_custom_variable(store, "l7_visit_role_flat", list(roles), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_truth_allow_flat", list(truths), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_body_flat", list(body), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_hair_flat", list(hair), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_beard_flat", list(beard), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_glasses_flat", list(glasses), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_clothes_flat", list(clothes), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_neckwear_flat", list(neckwear), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_dialogue_l1_flat", list(l1), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_dialogue_l2_flat", list(l2), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_dialogue_l3_flat", list(l3), trigger_event=False)
    session.game.set_custom_variable(store, "l7_visit_dialogue_l4_flat", list(l4), trigger_event=False)

    return {
        "visits": int(visits),
        "roles": list(roles),
        "truth_allow": list(truths),
        "clue_title": str(clue_title),
        "clue_tags": list(clue_tags),
        "clue_texts": list(clue_texts),
        "dialogue_l1": list(l1),
        "dialogue_l2": list(l2),
        "dialogue_l3": list(l3),
        "dialogue_l4": list(l4),
    }


def _start_level7(session) -> None:
    p = session.player_entity
    session.game.trigger_event(
        "关卡大厅_开始关卡",
        事件源实体=p,
        事件源GUID=0,
        信号来源实体=p,
        第X关=7,
    )
    session.drain_ui_patches()


def _finish_tutorial(session) -> None:
    for state in ("guide_0", "guide_1", "guide_2", "guide_3", "guide_4", "guide_5", "guide_6", "done"):
        session.trigger_ui_click(
            data_ui_key="btn_tutorial_next",
            data_ui_state_group="tutorial_overlay",
            data_ui_state=state,
        )
    session.drain_ui_patches()


def _finish_tutorial_for_player(session, player_entity) -> None:
    for state in ("guide_0", "guide_1", "guide_2", "guide_3", "guide_4", "guide_5", "guide_6", "done"):
        session.trigger_ui_click(
            data_ui_key="btn_tutorial_next",
            data_ui_state_group="tutorial_overlay",
            data_ui_state=state,
            player_entity=player_entity,
        )
    session.drain_ui_patches()


def _advance_and_tick(session, advance, dt: float) -> int:
    advance(float(dt))
    return int(session.game.tick())


def _level_entity(session):
    ent = session.game.get_entity(_LEVEL_ENTITY_GUID)
    assert ent is not None
    return ent


def _get_ui_text_dict(session, var_name: str) -> dict:
    level = _level_entity(session)
    value = session.game.get_custom_variable(level, var_name)
    assert isinstance(value, dict)
    return value


def _apply_lv_defaults(session, html_file: Path) -> None:
    text = Path(html_file).read_text(encoding="utf-8")
    defaults = _extract_lv_defaults_from_ui_html(text)
    session.game.set_ui_lv_defaults(defaults)


def test_local_sim_level7_graphs_validate() -> None:
    repo_root = get_repo_root()
    graphs = [
        _p(repo_root, _GRAPH_GAME_IN_REL),
        _p(repo_root, _GRAPH_DOOR_REL),
        _p(repo_root, _GRAPH_DATA_REL),
        _p(repo_root, _GRAPH_RESULT_REL),
    ]
    for path in graphs:
        passed, errors, warnings = validate_node_graph_file(path)
        assert passed, f"节点图校验失败（errors={len(errors)} warnings={len(warnings)}）：{errors[:5]}"


def test_local_sim_level7_door_controller_timer_fallback_emits_close_complete(_clock) -> None:
    """
    显式断言门控图在本地测试下可开关门，并能通过“兜底定时器”触发关门完成信号。

    注意：离线 MockRuntime 下不保证存在真实“基础运动器停止”事件，因此这里验证 timer fallback 路径。
    """
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_DOOR_REL),
        owner_entity_name="门控制实体",
        present_player_count=1,
    )

    session.emit_signal(signal_id="第七关_门_动作", params={"目标状态": "打开"})
    assert str(session.game.graph_variables.get("门_运动目标状态") or "") == "打开"
    assert session.game.graph_variables.get("门_等待关闭完成") is False

    session.emit_signal(signal_id="第七关_门_动作", params={"目标状态": "关闭"})
    assert str(session.game.graph_variables.get("门_运动目标状态") or "") == "关闭"
    assert session.game.graph_variables.get("门_等待关闭完成") is True

    wait = float(session.game.graph_variables.get("门动作等待秒") or 0.6)
    _advance_and_tick(session, advance, wait - 0.1)
    assert session.game.graph_variables.get("门_等待关闭完成") is True

    _advance_and_tick(session, advance, 0.2)
    assert session.game.graph_variables.get("门_等待关闭完成") is False


def test_local_sim_level7_ui_html_button_keys_are_expected() -> None:
    repo_root = get_repo_root()
    html_file = _p(repo_root, _UI_GAME_IN_REL)
    keys = _extract_ui_button_keys_from_html(html_file)
    assert keys == {
        "btn_allow",
        "btn_dialogue",
        "btn_exit",
        "btn_help",
        "btn_level_select",
        "btn_reject",
        "btn_reveal_close_result",
        "btn_tutorial_next",
    }


def test_local_sim_level7_ui_result_html_button_keys_are_expected() -> None:
    repo_root = get_repo_root()
    html_file = _p(repo_root, _UI_RESULT_REL)
    keys = _extract_ui_button_keys_from_html(html_file)
    assert keys == {
        "btn_back",
        "btn_exit",
        "btn_level_select",
        "btn_retry",
    }


def test_local_sim_level7_tutorial_countdown_auto_starts_game_without_click(_clock) -> None:
    """
    覆盖“新手教学倒计时到 0 自动开局”的链路：
    - 不点击任何教程按钮；
    - 倒计时归 0 后应广播开局信号，关闭遮罩/倒计时，解锁帮助；
    - 随后门控兜底定时器触发关门完成，推进到进场阶段并生成首位亲戚。
    """
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)

    tutorial_total = int(session.game.graph_variables.get("新手教程倒计时秒数") or 0)
    assert tutorial_total > 0
    _advance_and_tick(session, advance, float(tutorial_total))

    assert session.game.graph_variables.get("已广播开局信号") is True

    level = _level_entity(session)
    battle_int = session.game.get_custom_variable(level, "UI战斗_整数")
    assert isinstance(battle_int, dict)
    assert int(battle_int.get("新手教程_剩余秒") or 0) == 0

    # 开局后：遮罩隐藏、倒计时隐藏、帮助显示
    pid = session.player_entity.entity_id
    help_hidden = int(session.game.graph_variables.get("帮助按钮_hidden组") or 0)
    help_show = int(session.game.graph_variables.get("帮助按钮_show组") or 0)
    countdown_hidden = int(session.game.graph_variables.get("新手教程倒计时_hidden组") or 0)
    countdown_show = int(session.game.graph_variables.get("新手教程倒计时_show组") or 0)
    tut_hidden = int(session.game.graph_variables.get("新手教程_hidden组") or 0)
    tut_wait = int(session.game.graph_variables.get("新手教程_wait_others组") or 0)
    assert all(x > 0 for x in (help_hidden, help_show, countdown_hidden, countdown_show, tut_hidden, tut_wait))

    states = session.game.ui_widget_state_by_player.get(pid, {})
    assert states.get(help_hidden) == "界面控件组状态_关闭"
    assert states.get(help_show) == "界面控件组状态_开启"
    assert states.get(countdown_show) == "界面控件组状态_关闭"
    assert states.get(countdown_hidden) == "界面控件组状态_开启"
    assert states.get(tut_wait) == "界面控件组状态_关闭"
    assert states.get(tut_hidden) == "界面控件组状态_开启"

    # 门控兜底：推进一次 tick 即可完成关门并生成首位亲戚，进入进场阶段
    _advance_and_tick(session, advance, 1.0)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 1


def test_local_sim_level7_tutorial_next_writes_clues_and_help_opens_review(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    seeded = _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)

    # 开局前：教程应默认打开 guide_0
    guide0 = int(session.game.graph_variables.get("新手教程_guide_0组") or 0)
    assert guide0 > 0
    pid = session.player_entity.entity_id
    assert session.game.ui_widget_state_by_player.get(pid, {}).get(guide0) == "界面控件组状态_开启"

    _finish_tutorial(session)

    # 教程完成应广播开局信号，并由数据服务下发妈妈纸条 → 写回 UI战斗_文本 的线索区
    battle_text = _get_ui_text_dict(session, "UI战斗_文本")
    assert battle_text.get("线索标题") == str(seeded.get("clue_title") or "")
    clue_tags = list(seeded.get("clue_tags") or [])
    clue_texts = list(seeded.get("clue_texts") or [])
    assert len(clue_tags) == 6
    assert len(clue_texts) == 6
    for i in range(1, 7):
        assert battle_text.get(f"线索{i}标") == clue_tags[i - 1]
        assert battle_text.get(f"线索{i}文") == clue_texts[i - 1]

    # 关门完成后会请求下一位亲戚（门控图用定时器兜底），推进一次 tick 即可触发
    _advance_and_tick(session, advance, 1.0)

    # 帮助按钮：应写回对白提示，并打开教程回顾（guide_0）
    session.trigger_ui_click(data_ui_key="btn_help", data_ui_state_group="help_btn_state", data_ui_state="show")
    battle_text2 = _get_ui_text_dict(session, "UI战斗_文本")
    assert battle_text2.get("对话") == "提示：先点击『对话』获取线索，再在投票阶段选择『允许/拒绝』。"
    assert session.game.ui_widget_state_by_player.get(pid, {}).get(guide0) == "界面控件组状态_开启"


def test_local_sim_level7_tutorial_next_switches_overlay_groups_in_order(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)

    pid = session.player_entity.entity_id

    g0 = int(session.game.graph_variables.get("新手教程_guide_0组") or 0)
    g1 = int(session.game.graph_variables.get("新手教程_guide_1组") or 0)
    g2 = int(session.game.graph_variables.get("新手教程_guide_2组") or 0)
    g3 = int(session.game.graph_variables.get("新手教程_guide_3组") or 0)
    g4 = int(session.game.graph_variables.get("新手教程_guide_4组") or 0)
    g5 = int(session.game.graph_variables.get("新手教程_guide_5组") or 0)
    g6 = int(session.game.graph_variables.get("新手教程_guide_6组") or 0)
    done = int(session.game.graph_variables.get("新手教程_done组") or 0)
    assert all(x > 0 for x in (g0, g1, g2, g3, g4, g5, g6, done))

    def _is_open(group_guid: int) -> bool:
        return session.game.ui_widget_state_by_player.get(pid, {}).get(group_guid) == "界面控件组状态_开启"

    assert _is_open(g0)

    session.trigger_ui_click(data_ui_key="btn_tutorial_next", data_ui_state_group="tutorial_overlay", data_ui_state="guide_0")
    assert _is_open(g1) and (not _is_open(g0))

    session.trigger_ui_click(data_ui_key="btn_tutorial_next", data_ui_state_group="tutorial_overlay", data_ui_state="guide_1")
    assert _is_open(g2) and (not _is_open(g1))

    session.trigger_ui_click(data_ui_key="btn_tutorial_next", data_ui_state_group="tutorial_overlay", data_ui_state="guide_2")
    assert _is_open(g3) and (not _is_open(g2))

    session.trigger_ui_click(data_ui_key="btn_tutorial_next", data_ui_state_group="tutorial_overlay", data_ui_state="guide_3")
    assert _is_open(g4) and (not _is_open(g3))

    session.trigger_ui_click(data_ui_key="btn_tutorial_next", data_ui_state_group="tutorial_overlay", data_ui_state="guide_4")
    assert _is_open(g5) and (not _is_open(g4))

    session.trigger_ui_click(data_ui_key="btn_tutorial_next", data_ui_state_group="tutorial_overlay", data_ui_state="guide_5")
    assert _is_open(g6) and (not _is_open(g5))

    session.trigger_ui_click(data_ui_key="btn_tutorial_next", data_ui_state_group="tutorial_overlay", data_ui_state="guide_6")
    assert _is_open(done) and (not _is_open(g6))

    session.trigger_ui_click(data_ui_key="btn_tutorial_next", data_ui_state_group="tutorial_overlay", data_ui_state="done")
    assert int(session.game.get_custom_variable(session.player_entity, "ui_tut_done") or 0) == 1
    assert not _is_open(done)

    # 单人：推进一点 tick，确保能进入后续流程（避免“教程完成但未开局”残留）
    _advance_and_tick(session, advance, 1.0)


def test_local_sim_level7_dialogue_button_cycles_dialogue_lines(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)
    _finish_tutorial(session)

    # 门关闭完成 → 下发亲戚数据（包含对白列表）
    _advance_and_tick(session, advance, 1.0)

    battle_text0 = _get_ui_text_dict(session, "UI战斗_文本")
    assert battle_text0.get("对话") == " "

    session.trigger_ui_click(data_ui_key="btn_dialogue")
    text1 = str(_get_ui_text_dict(session, "UI战斗_文本").get("对话") or "")
    assert text1.strip() != ""

    session.trigger_ui_click(data_ui_key="btn_dialogue")
    text2 = str(_get_ui_text_dict(session, "UI战斗_文本").get("对话") or "")
    assert text2 != text1

    # 4 句对白，点击 5 次应回到第 1 句
    session.trigger_ui_click(data_ui_key="btn_dialogue")
    session.trigger_ui_click(data_ui_key="btn_dialogue")
    session.trigger_ui_click(data_ui_key="btn_dialogue")
    text5 = str(_get_ui_text_dict(session, "UI战斗_文本").get("对话") or "")
    assert text5 == text1


def test_local_sim_level7_dialogue_copywriting_matches_each_relative_in_order(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    seeded = _seed_level7_data_service(session, truth_allow_first=True)

    visits = int(seeded.get("visits") or 0)
    assert visits == 10
    session.game.set_graph_variable("总回合数", visits, trigger_event=False)

    d1 = list(seeded.get("dialogue_l1") or [])
    d2 = list(seeded.get("dialogue_l2") or [])
    d3 = list(seeded.get("dialogue_l3") or [])
    d4 = list(seeded.get("dialogue_l4") or [])
    assert all(len(x) == visits for x in (d1, d2, d3, d4))

    _start_level7(session)
    _finish_tutorial(session)

    # 首回合：关门完成 → 下发亲戚数据（包含对白列表）
    _advance_and_tick(session, advance, 1.0)

    for visit_i in range(visits):
        battle_text0 = _get_ui_text_dict(session, "UI战斗_文本")
        assert battle_text0.get("对话") == " "

        expected_lines = [d1[visit_i], d2[visit_i], d3[visit_i], d4[visit_i]]
        for expected in expected_lines:
            session.trigger_ui_click(data_ui_key="btn_dialogue")
            got = str(_get_ui_text_dict(session, "UI战斗_文本").get("对话") or "")
            assert got == expected

        # 进场倒计时（1~5s）结束后进入投票阶段
        _advance_and_tick(session, advance, 5.0)
        assert int(session.game.graph_variables.get("当前阶段") or 0) == 2

        # 本用例只关心“对白/文案写回”：统一投允许推进回合
        session.trigger_ui_click(data_ui_key="btn_allow")
        assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

        if visit_i == visits - 1:
            break

        # 继续 → 推进下一位亲戚，并断言对白已清空（防止残留）
        session.trigger_ui_click(
            data_ui_key="btn_reveal_close_result",
            data_ui_state_group="battle_settlement_overlay",
            data_ui_state="result",
        )
        _advance_and_tick(session, advance, 1.0)
        assert int(session.game.graph_variables.get("当前阶段") or 0) == 1
        assert int(session.game.graph_variables.get("当前回合序号") or 0) == visit_i + 2


def _reach_voting_stage(session, advance) -> None:
    # 关门完成 → 下发亲戚数据并启动进场倒计时（1~5s）
    _advance_and_tick(session, advance, 1.0)
    _advance_and_tick(session, advance, 5.0)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 2


def test_local_sim_level7_allow_correct_settlement(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    session.trigger_ui_click(data_ui_key="btn_allow")

    # 本地逻辑：单人投票会立即结算并展示揭晓遮罩
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    p = session.player_entity
    pts = session.game.get_custom_variable(p, "ui_battle_points")
    assert int(pts or 0) == 100

    battle_text = _get_ui_text_dict(session, "UI战斗_文本")
    assert battle_text.get("压岁钱") == "100"
    assert battle_text.get("审判1态") == "允许"

    reveal = _get_ui_text_dict(session, "UI战斗_揭晓")
    assert reveal.get("结果_判定") == "判断正确"
    assert reveal.get("结果_真相") == "真亲戚"

    result_group = int(session.game.graph_variables.get("揭晓遮罩_result组") or 0)
    assert result_group > 0
    pid = session.player_entity.entity_id
    assert session.game.ui_widget_state_by_player.get(pid, {}).get(result_group) == "界面控件组状态_开启"


def test_local_sim_level7_reject_correct_settlement(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=False)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    session.trigger_ui_click(data_ui_key="btn_reject")

    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    p = session.player_entity
    pts = session.game.get_custom_variable(p, "ui_battle_points")
    assert int(pts or 0) == 100

    battle_text = _get_ui_text_dict(session, "UI战斗_文本")
    assert battle_text.get("压岁钱") == "100"
    assert battle_text.get("审判1态") == "拒绝"

    reveal = _get_ui_text_dict(session, "UI战斗_揭晓")
    assert reveal.get("结果_判定") == "判断正确"
    assert reveal.get("结果_真相") == "年兽伪装"


def test_local_sim_level7_exit_switches_to_level_select_and_resets_state(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    patches = session.trigger_ui_click(data_ui_key="btn_exit")

    expected = int(session.game.graph_variables.get("布局索引_选关页") or 0)
    assert expected == stable_layout_index_from_html_stem("关卡大厅-选关界面")
    assert any(p.get("op") == "switch_layout" and int(p.get("layout_index") or 0) == expected for p in patches)

    assert int(session.game.graph_variables.get("当前阶段", -1)) == 0
    assert session.game.graph_variables.get("已初始化") is False
    assert session.game.graph_variables.get("已广播开局信号") is False


def test_local_sim_level7_relative_entities_spawn_and_exit_cleans_them(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)
    _finish_tutorial(session)

    # 关门完成（兜底定时器）→ 请求并下发亲戚数据 → 创建元件并进入进场阶段
    _advance_and_tick(session, advance, 1.0)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 1

    level = _level_entity(session)
    key_to_entity_id: dict[str, str] = {}
    for k in (
        "第七关_亲戚_身体实体",
        "第七关_亲戚_头发实体",
        "第七关_亲戚_衣服实体",
        "第七关_亲戚_领带实体",
    ):
        ent = session.game.get_custom_variable(level, k)
        assert isinstance(ent, game_state_module.MockEntity)
        assert str(ent.entity_id) in session.game.entities
        key_to_entity_id[k] = str(ent.entity_id)

    # 默认外观：胡子/眼镜=无 → 0 表示不创建
    assert session.game.get_custom_variable(level, "第七关_亲戚_胡子实体") in (0, None)
    assert session.game.get_custom_variable(level, "第七关_亲戚_眼睛实体") in (0, None)

    session.trigger_ui_click(data_ui_key="btn_exit")

    for k in key_to_entity_id.keys():
        assert session.game.get_custom_variable(level, k) == 0
    for eid in key_to_entity_id.values():
        assert str(eid) not in session.game.entities


def test_local_sim_level7_relative_entities_are_replaced_on_next_round(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    session.game.set_graph_variable("总回合数", 2, trigger_event=False)

    _start_level7(session)
    _finish_tutorial(session)

    _advance_and_tick(session, advance, 1.0)
    level = _level_entity(session)
    body1 = session.game.get_custom_variable(level, "第七关_亲戚_身体实体")
    assert isinstance(body1, game_state_module.MockEntity)
    body1_id = str(body1.entity_id)

    _advance_and_tick(session, advance, 5.0)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 2

    session.trigger_ui_click(data_ui_key="btn_allow")
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    session.trigger_ui_click(
        data_ui_key="btn_reveal_close_result",
        data_ui_state_group="battle_settlement_overlay",
        data_ui_state="result",
    )
    _advance_and_tick(session, advance, 1.0)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 1

    body2 = session.game.get_custom_variable(level, "第七关_亲戚_身体实体")
    assert isinstance(body2, game_state_module.MockEntity)
    body2_id = str(body2.entity_id)
    assert body2_id != body1_id
    assert body1_id not in session.game.entities


def test_local_sim_level7_level_select_button_switches_to_level_select_and_resets_state(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    patches = session.trigger_ui_click(data_ui_key="btn_level_select")

    expected = int(session.game.graph_variables.get("布局索引_选关页") or 0)
    assert expected == stable_layout_index_from_html_stem("关卡大厅-选关界面")
    assert any(p.get("op") == "switch_layout" and int(p.get("layout_index") or 0) == expected for p in patches)

    assert int(session.game.graph_variables.get("当前阶段", -1)) == 0
    assert session.game.graph_variables.get("已初始化") is False
    assert session.game.graph_variables.get("已广播开局信号") is False


def test_local_sim_level7_allow_wrong_settlement_applies_score_and_resource_penalties(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=False)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    level = _level_entity(session)
    integrity0 = int(session.game.get_custom_variable(level, "UI结算_整数__完整度_当前") or 0)
    figures0 = int(session.game.get_custom_variable(level, "UI结算_整数__手办_当前") or 0)
    deduct_integrity_each = int(session.game.graph_variables.get("结算_完整度_每次错误扣除") or 0)
    deduct_figures_each = int(session.game.graph_variables.get("结算_手办_每次放错扣除") or 0)

    session.trigger_ui_click(data_ui_key="btn_allow")

    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    p = session.player_entity
    pts = int(session.game.get_custom_variable(p, "ui_battle_points") or 0)
    assert pts == -50

    integrity1 = int(session.game.get_custom_variable(level, "UI结算_整数__完整度_当前") or 0)
    figures1 = int(session.game.get_custom_variable(level, "UI结算_整数__手办_当前") or 0)
    assert integrity1 == integrity0 - deduct_integrity_each
    # 手办：只有放小孩进来才扣；默认 body=瘦马 → 不应扣
    assert figures1 == figures0

    battle_text = _get_ui_text_dict(session, "UI战斗_文本")
    assert battle_text.get("压岁钱") == "-50"
    assert battle_text.get("审判1态") == "允许"
    assert battle_text.get("完整度") == str(integrity1)
    figures_map = session.game.graph_variables.get("手办存活数到文本") or {}
    assert isinstance(figures_map, dict)
    assert battle_text.get("存活") == str(figures_map.get(figures1))

    reveal = _get_ui_text_dict(session, "UI战斗_揭晓")
    assert reveal.get("结果_判定") == "判断错误"
    assert reveal.get("结果_真相") == "年兽伪装"
    assert reveal.get("变化_完整度") == str(-deduct_integrity_each)
    assert reveal.get("变化_存活") == "0"


def test_local_sim_level7_allow_wrong_child_deducts_figures(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=False, first_body="小孩马")

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    level = _level_entity(session)
    integrity0 = int(session.game.get_custom_variable(level, "UI结算_整数__完整度_当前") or 0)
    figures0 = int(session.game.get_custom_variable(level, "UI结算_整数__手办_当前") or 0)
    deduct_integrity_each = int(session.game.graph_variables.get("结算_完整度_每次错误扣除") or 0)
    deduct_figures_each = int(session.game.graph_variables.get("结算_手办_每次放错扣除") or 0)

    session.trigger_ui_click(data_ui_key="btn_allow")

    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3
    assert session.game.graph_variables.get("本回合_是否小孩") is True

    p = session.player_entity
    pts = int(session.game.get_custom_variable(p, "ui_battle_points") or 0)
    assert pts == -50

    integrity1 = int(session.game.get_custom_variable(level, "UI结算_整数__完整度_当前") or 0)
    figures1 = int(session.game.get_custom_variable(level, "UI结算_整数__手办_当前") or 0)
    assert integrity1 == integrity0 - deduct_integrity_each
    assert figures1 == figures0 - deduct_figures_each

    reveal = _get_ui_text_dict(session, "UI战斗_揭晓")
    assert reveal.get("结果_判定") == "判断错误"
    assert reveal.get("结果_真相") == "年兽伪装"
    assert reveal.get("变化_完整度") == str(-deduct_integrity_each)
    assert reveal.get("变化_存活") == str(-deduct_figures_each)


def test_local_sim_level7_reject_wrong_settlement_applies_score_and_integrity_penalty_only(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    level = _level_entity(session)
    integrity0 = int(session.game.get_custom_variable(level, "UI结算_整数__完整度_当前") or 0)
    figures0 = int(session.game.get_custom_variable(level, "UI结算_整数__手办_当前") or 0)
    deduct_integrity_each = int(session.game.graph_variables.get("结算_完整度_每次错误扣除") or 0)

    session.trigger_ui_click(data_ui_key="btn_reject")

    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    p = session.player_entity
    pts = int(session.game.get_custom_variable(p, "ui_battle_points") or 0)
    assert pts == -50

    integrity1 = int(session.game.get_custom_variable(level, "UI结算_整数__完整度_当前") or 0)
    figures1 = int(session.game.get_custom_variable(level, "UI结算_整数__手办_当前") or 0)
    assert integrity1 == integrity0 - deduct_integrity_each
    assert figures1 == figures0

    battle_text = _get_ui_text_dict(session, "UI战斗_文本")
    assert battle_text.get("压岁钱") == "-50"
    assert battle_text.get("审判1态") == "拒绝"
    assert battle_text.get("完整度") == str(integrity1)
    figures_map = session.game.graph_variables.get("手办存活数到文本") or {}
    assert isinstance(figures_map, dict)
    assert battle_text.get("存活") == str(figures_map.get(figures1))

    reveal = _get_ui_text_dict(session, "UI战斗_揭晓")
    assert reveal.get("结果_判定") == "判断错误"
    assert reveal.get("结果_真相") == "真亲戚"
    assert reveal.get("变化_完整度") == str(-deduct_integrity_each)
    assert reveal.get("变化_存活") == "0"


def test_local_sim_level7_continue_advances_next_round_and_updates_remaining_relatives(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    # 两回合：第 1 回合揭晓后点继续，应进入第 2 回合并刷新剩余亲戚
    session.game.set_graph_variable("总回合数", 2, trigger_event=False)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    session.trigger_ui_click(data_ui_key="btn_allow")
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    session.trigger_ui_click(
        data_ui_key="btn_reveal_close_result",
        data_ui_state_group="battle_settlement_overlay",
        data_ui_state="result",
    )
    _advance_and_tick(session, advance, 1.0)

    assert int(session.game.graph_variables.get("当前阶段") or 0) == 1
    assert int(session.game.graph_variables.get("当前回合序号") or 0) == 2

    room_text = _get_ui_text_dict(session, "UI房间_文本")
    assert room_text.get("剩余亲戚_总") == "2"
    assert room_text.get("剩余亲戚_当前") == "1"

    _advance_and_tick(session, advance, 5.0)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 2


def test_local_sim_level7_settlement_hold_timer_auto_advances_next_round_without_click(_clock) -> None:
    """
    覆盖“结算停留定时器自动推进”的链路（不点揭晓遮罩的『继续』）：
    - 本回合结算后自动关门；
    - 关门完成后推进下一回合并重新进场。
    """
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    # 两回合：第 1 回合结算后不点继续，也应自动进入第 2 回合
    session.game.set_graph_variable("总回合数", 2, trigger_event=False)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    session.trigger_ui_click(data_ui_key="btn_allow")
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    hold_total = int(session.game.graph_variables.get("结算停留秒数") or 0)
    assert hold_total > 0
    _advance_and_tick(session, advance, float(hold_total))
    assert int(session.game.graph_variables.get("当前回合序号") or 0) == 2

    # 关门完成（兜底定时器）→ 生成下一位亲戚并进入进场阶段
    _advance_and_tick(session, advance, 1.0)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 1


def test_local_sim_level7_settlement_hold_timer_auto_enters_settlement_on_last_round(_clock) -> None:
    """
    覆盖“最后一回合结算后，结算停留定时器到 0 自动进入结算页”的链路（不点继续）。
    """
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    session.game.set_graph_variable("总回合数", 1, trigger_event=False)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    session.trigger_ui_click(data_ui_key="btn_allow")
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    hold_total = int(session.game.graph_variables.get("结算停留秒数") or 0)
    assert hold_total > 0
    _advance_and_tick(session, advance, float(hold_total))

    # 门关闭完成后应切到结算页布局
    _advance_and_tick(session, advance, 1.0)
    settlement_idx = int(session.game.graph_variables.get("布局索引_结算页") or 0)
    assert settlement_idx == stable_layout_index_from_html_stem("第七关-结算")
    pid = session.player_entity.entity_id
    assert int(session.game.ui_current_layout_by_player.get(pid, 0) or 0) == settlement_idx


def test_local_sim_level7_multiplayer_tutorial_shows_wait_others_until_all_done(_clock) -> None:
    """
    覆盖“多人教程完成门槛”的链路：
    - 任意一名玩家完成后，显示 wait_others；
    - 未全员完成前，不应广播开局信号；
    - 全员完成后应立即开局，并对所有玩家收起遮罩/倒计时，进入后续流程。
    """
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=2,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)

    players = session.game.get_present_player_entities()
    assert len(players) >= 2
    p1, p2 = players[0], players[1]

    wait_others = int(session.game.graph_variables.get("新手教程_wait_others组") or 0)
    tut_hidden = int(session.game.graph_variables.get("新手教程_hidden组") or 0)
    assert wait_others > 0 and tut_hidden > 0

    _finish_tutorial_for_player(session, p1)
    assert session.game.graph_variables.get("已广播开局信号") is False
    assert session.game.ui_widget_state_by_player.get(p1.entity_id, {}).get(wait_others) == "界面控件组状态_开启"

    _finish_tutorial_for_player(session, p2)
    assert session.game.graph_variables.get("已广播开局信号") is True
    assert session.game.ui_widget_state_by_player.get(p1.entity_id, {}).get(wait_others) == "界面控件组状态_关闭"
    assert session.game.ui_widget_state_by_player.get(p2.entity_id, {}).get(wait_others) == "界面控件组状态_关闭"
    assert session.game.ui_widget_state_by_player.get(p1.entity_id, {}).get(tut_hidden) == "界面控件组状态_开启"
    assert session.game.ui_widget_state_by_player.get(p2.entity_id, {}).get(tut_hidden) == "界面控件组状态_开启"

    # 确保能进入后续流程（关门完成→进场阶段）
    _advance_and_tick(session, advance, 1.0)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 1


def test_local_sim_level7_multiplayer_vote_reveals_only_after_all_players_voted(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=3,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)

    players = session.game.get_present_player_entities()
    assert len(players) >= 3
    p1, p2, p3 = players[0], players[1], players[2]

    _finish_tutorial_for_player(session, p1)
    _finish_tutorial_for_player(session, p2)
    _finish_tutorial_for_player(session, p3)

    _reach_voting_stage(session, advance)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 2

    # 让得分排序稳定：预先打散初始分
    session.game.set_custom_variable(p1, "ui_battle_points", 0, trigger_event=False)
    session.game.set_custom_variable(p2, "ui_battle_points", 30, trigger_event=False)
    session.game.set_custom_variable(p3, "ui_battle_points", 60, trigger_event=False)

    level = _level_entity(session)
    integrity0 = int(session.game.get_custom_variable(level, "UI结算_整数__完整度_当前") or 0)
    figures0 = int(session.game.get_custom_variable(level, "UI结算_整数__手办_当前") or 0)
    deduct_integrity_each = int(session.game.graph_variables.get("结算_完整度_每次错误扣除") or 0)

    result_group = int(session.game.graph_variables.get("揭晓遮罩_result组") or 0)
    assert result_group > 0

    # 玩家1投允许：未全员完成选择，不应揭晓
    session.trigger_ui_click(data_ui_key="btn_allow", player_entity=p1)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 2
    assert session.game.ui_widget_state_by_player.get(p1.entity_id, {}).get(result_group) != "界面控件组状态_开启"

    # 玩家2投拒绝：仍不揭晓
    session.trigger_ui_click(data_ui_key="btn_reject", player_entity=p2)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 2

    # 玩家3投允许：此时全员完成选择，应进入结算并揭晓
    session.trigger_ui_click(data_ui_key="btn_allow", player_entity=p3)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    # 计分：真相为允许 → allow +100；reject -50
    assert int(session.game.get_custom_variable(p1, "ui_battle_points") or 0) == 100
    assert int(session.game.get_custom_variable(p2, "ui_battle_points") or 0) == -20
    assert int(session.game.get_custom_variable(p3, "ui_battle_points") or 0) == 160

    integrity1 = int(session.game.get_custom_variable(level, "UI结算_整数__完整度_当前") or 0)
    figures1 = int(session.game.get_custom_variable(level, "UI结算_整数__手办_当前") or 0)
    assert integrity1 == integrity0 - deduct_integrity_each
    assert figures1 == figures0

    reveal = _get_ui_text_dict(session, "UI战斗_揭晓")
    assert reveal.get("结果_判定") == "判断正确"
    assert reveal.get("结果_真相") == "真亲戚"

def test_local_sim_level7_multiplayer_vote_updates_status_and_disables_buttons_per_player(_clock) -> None:
    """
    用户关切点：
    - 其他玩家点“允许/拒绝”后，其状态（思考中/允许/拒绝）是否会立刻写回到审判庭；
    - 投票后按钮是否会变为 disabled（避免重复投票）。
    """
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=3,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    _start_level7(session)

    players = session.game.get_present_player_entities()
    assert len(players) >= 3
    p1, p2, p3 = players[0], players[1], players[2]

    _finish_tutorial_for_player(session, p1)
    _finish_tutorial_for_player(session, p2)
    _finish_tutorial_for_player(session, p3)
    _reach_voting_stage(session, advance)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 2

    # 让得分排序稳定（避免 ties 导致 slot 不稳定）
    session.game.set_custom_variable(p1, "ui_battle_points", 0, trigger_event=False)
    session.game.set_custom_variable(p2, "ui_battle_points", 30, trigger_event=False)
    session.game.set_custom_variable(p3, "ui_battle_points", 60, trigger_event=False)

    allow_enabled = int(session.game.graph_variables.get("允许按钮_enabled组") or 0)
    allow_disabled = int(session.game.graph_variables.get("允许按钮_disabled组") or 0)
    reject_enabled = int(session.game.graph_variables.get("拒绝按钮_enabled组") or 0)
    reject_disabled = int(session.game.graph_variables.get("拒绝按钮_disabled组") or 0)
    assert all(x > 0 for x in (allow_enabled, allow_disabled, reject_enabled, reject_disabled))

    def _ranked() -> list:
        return sorted(
            [p1, p2, p3],
            key=lambda p: int(session.game.get_custom_variable(p, "ui_battle_points") or 0),
            reverse=True,
        )

    def _slot_of(player) -> int:
        ranked = _ranked()
        return int(ranked.index(player)) + 1

    def _expect_state(choice: int) -> str:
        if int(choice) == 0:
            return "思考中"
        if int(choice) == 1:
            return "允许"
        return "拒绝"

    def _assert_player_state_in_judge_table(player, expected_choice: int) -> None:
        slot = _slot_of(player)
        battle_text = _get_ui_text_dict(session, "UI战斗_文本")
        assert battle_text.get(f"审判{slot}态") == _expect_state(expected_choice)

    def _assert_buttons_disabled(player) -> None:
        states = session.game.ui_widget_state_by_player.get(player.entity_id, {})
        assert states.get(allow_enabled) == "界面控件组状态_关闭"
        assert states.get(allow_disabled) == "界面控件组状态_开启"
        assert states.get(reject_enabled) == "界面控件组状态_关闭"
        assert states.get(reject_disabled) == "界面控件组状态_开启"

    # 玩家1投允许：应立刻更新审判庭状态，并禁用该玩家按钮（但仍未全员完成选择，不应揭晓）
    session.trigger_ui_click(data_ui_key="btn_allow", player_entity=p1)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 2
    assert int(session.game.get_custom_variable(p1, "ui_battle_choice") or 0) == 1
    _assert_player_state_in_judge_table(p1, 1)
    _assert_player_state_in_judge_table(p2, 0)
    _assert_player_state_in_judge_table(p3, 0)
    _assert_buttons_disabled(p1)

    # 玩家2投拒绝：应立刻更新审判庭状态，并禁用该玩家按钮（仍不揭晓）
    session.trigger_ui_click(data_ui_key="btn_reject", player_entity=p2)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 2
    assert int(session.game.get_custom_variable(p2, "ui_battle_choice") or 0) == 2
    _assert_player_state_in_judge_table(p1, 1)
    _assert_player_state_in_judge_table(p2, 2)
    _assert_player_state_in_judge_table(p3, 0)
    _assert_buttons_disabled(p2)

    # 玩家3投允许：全员完成选择 → 应进入结算并揭晓；同时按钮禁用
    session.trigger_ui_click(data_ui_key="btn_allow", player_entity=p3)
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3
    assert int(session.game.get_custom_variable(p3, "ui_battle_choice") or 0) == 1
    _assert_buttons_disabled(p3)

    # 计分后：真相为允许 → allow +100；reject -50（初始分为 0/30/60）
    assert int(session.game.get_custom_variable(p1, "ui_battle_points") or 0) == 100
    assert int(session.game.get_custom_variable(p2, "ui_battle_points") or 0) == -20
    assert int(session.game.get_custom_variable(p3, "ui_battle_points") or 0) == 160

    # 计分后审判庭会按新分重排：p3(160) > p1(100) > p2(-20)
    battle_text_final = _get_ui_text_dict(session, "UI战斗_文本")
    assert battle_text_final.get("审判1态") == "允许"
    assert battle_text_final.get("审判2态") == "允许"
    assert battle_text_final.get("审判3态") == "拒绝"


def test_local_sim_level7_continue_enters_settlement_and_settlement_back_works(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_RESULT_REL), owner_entity_name="结算UI实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    # 为了让 1 回合直接进入结算：总回合数改为 1
    session.game.set_graph_variable("总回合数", 1, trigger_event=False)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    session.trigger_ui_click(data_ui_key="btn_allow")
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    # 点击继续：应关门并在门关闭完成后切到结算页
    session.trigger_ui_click(
        data_ui_key="btn_reveal_close_result",
        data_ui_state_group="battle_settlement_overlay",
        data_ui_state="result",
    )
    _advance_and_tick(session, advance, 1.0)

    settlement_idx = int(session.game.graph_variables.get("布局索引_结算页") or 0)
    assert settlement_idx == stable_layout_index_from_html_stem("第七关-结算")
    pid = session.player_entity.entity_id
    assert int(session.game.ui_current_layout_by_player.get(pid, 0) or 0) == settlement_idx

    # 结算页图会在点击时写榜单：用结算页 HTML 的 lv 默认值补齐 `UI结算_文本` 等 UI 变量
    _apply_lv_defaults(session, _p(repo_root, _UI_RESULT_REL))

    # 结算榜单读取玩家变量 `ui_battle_points`：这里用一个“非默认值”确保写回链路真的生效
    session.game.set_custom_variable(session.player_entity, "ui_battle_points", 123, trigger_event=False)

    patches = session.trigger_ui_click(data_ui_key="btn_back")
    result_text = _get_ui_text_dict(session, "UI结算_文本")
    assert result_text.get("榜1名次") == "1"
    assert str(result_text.get("榜1名") or "").strip() != ""
    assert result_text.get("榜1分") == "123"
    assert result_text.get("榜2名") == "—"
    assert result_text.get("榜2分") == "0"

    level_select_idx = int(session.game.graph_variables.get("布局索引_选关页") or 0)
    assert any(p.get("op") == "switch_layout" and int(p.get("layout_index") or 0) == level_select_idx for p in patches)


def test_local_sim_level7_settlement_retry_resets_round_and_stats_and_returns_level_select(_clock) -> None:
    _, advance = _clock
    repo_root = get_repo_root()

    session = build_local_graph_sim_session(
        workspace_root=repo_root,
        graph_code_file=_p(repo_root, _GRAPH_GAME_IN_REL),
        owner_entity_name="自身实体",
        present_player_count=1,
        extra_graph_mounts=[
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DOOR_REL), owner_entity_name="门控制实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_DATA_REL), owner_entity_name="数据服务实体"),
            GraphMountSpec(graph_code_file=_p(repo_root, _GRAPH_RESULT_REL), owner_entity_name="结算UI实体"),
        ],
    )
    _apply_lv_defaults(session, _p(repo_root, _UI_GAME_IN_REL))
    _seed_level7_data_service(session, truth_allow_first=True)

    # 为了让 1 回合直接进入结算：总回合数改为 1
    session.game.set_graph_variable("总回合数", 1, trigger_event=False)

    _start_level7(session)
    _finish_tutorial(session)
    _reach_voting_stage(session, advance)

    session.trigger_ui_click(data_ui_key="btn_allow")
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 3

    # 点击继续：应关门并在门关闭完成后切到结算页
    session.trigger_ui_click(
        data_ui_key="btn_reveal_close_result",
        data_ui_state_group="battle_settlement_overlay",
        data_ui_state="result",
    )
    _advance_and_tick(session, advance, 1.0)

    settlement_idx = int(session.game.graph_variables.get("布局索引_结算页") or 0)
    assert settlement_idx == stable_layout_index_from_html_stem("第七关-结算")
    pid = session.player_entity.entity_id
    assert int(session.game.ui_current_layout_by_player.get(pid, 0) or 0) == settlement_idx

    # 用结算页 HTML 的 lv 默认值补齐 `UI结算_文本`（结算图在点击时会写榜单）
    _apply_lv_defaults(session, _p(repo_root, _UI_RESULT_REL))

    # 构造“非满值”统计，确保 retry 会把当前值回填为最大值
    level = _level_entity(session)
    session.game.set_custom_variable(level, "UI结算_整数__完整度_最大", 10, trigger_event=False)
    session.game.set_custom_variable(level, "UI结算_整数__完整度_当前", 7, trigger_event=False)
    session.game.set_custom_variable(level, "UI结算_整数__手办_最大", 5, trigger_event=False)
    session.game.set_custom_variable(level, "UI结算_整数__手办_当前", 3, trigger_event=False)

    # 构造“非初始”玩家状态，确保 retry 会清空选择/分数
    p = session.player_entity
    session.game.set_custom_variable(p, "ui_battle_choice", 2, trigger_event=False)
    session.game.set_custom_variable(p, "ui_battle_points", 123, trigger_event=False)

    patches = session.trigger_ui_click(data_ui_key="btn_retry")
    level_select_idx = int(session.game.graph_variables.get("布局索引_选关页") or 0)
    assert any(p.get("op") == "switch_layout" and int(p.get("layout_index") or 0) == level_select_idx for p in patches)

    assert int(session.game.graph_variables.get("当前回合序号") or 0) == 1
    assert int(session.game.graph_variables.get("当前阶段") or 0) == 0
    assert int(session.game.get_custom_variable(p, "ui_battle_choice") or 0) == 0
    assert int(session.game.get_custom_variable(p, "ui_battle_points") or 0) == 0

    assert int(session.game.get_custom_variable(level, "UI结算_整数__完整度_当前") or 0) == 10
    assert int(session.game.get_custom_variable(level, "UI结算_整数__手办_当前") or 0) == 5
