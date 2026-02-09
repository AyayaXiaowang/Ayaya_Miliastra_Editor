from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _write_graph_code(tmp_dir: Path, filename: str, source: str) -> Path:
    target = tmp_dir / filename
    target.write_text(source, encoding="utf-8")
    return target


def test_pull_eval_reevaluation_hazard_reports_warning_simple(tmp_path: Path) -> None:
    """简单案例：读-改-写后仍复用同一个读取节点，应给出 warning。"""
    graph_code = '''
"""
graph_id: graph_pull_eval_hazard_01
graph_name: 拉取式重复求值风险_示例
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 拉取式重复求值风险_示例:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前击杀数: "整数" = 获取自定义变量(self.game, 目标实体=事件源实体, 变量名="击杀数")
        新击杀数: "整数" = 加法运算(self.game, 左值=当前击杀数, 右值=1)
        设置自定义变量(self.game, 目标实体=事件源实体, 变量名="击杀数", 变量值=新击杀数, 是否触发事件=False)

        达到胜利条件: "布尔值" = 数值大于等于(self.game, 左值=新击杀数, 右值=10)
        if 达到胜利条件:
            打印字符串(self.game, 字符串="win")

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_pull_eval_hazard_01.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    hits = [issue for issue in report.issues if issue.code == "CODE_PULL_EVAL_REEVAL_AFTER_WRITE"]
    assert hits, "应产生 CODE_PULL_EVAL_REEVAL_AFTER_WRITE warning，用于提醒拉取式执行器重复求值风险"
    assert any(issue.level == "warning" for issue in hits)


def test_pull_eval_reevaluation_hazard_reports_warning_complex_control_flow(tmp_path: Path) -> None:
    """复杂案例：for + match + if 的组合结构下，仍应能识别“写入后复用同一读取节点”的风险。"""
    graph_code = '''
"""
graph_id: graph_pull_eval_hazard_02
graph_name: 拉取式重复求值风险_复杂控制流
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 拉取式重复求值风险_复杂控制流:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前击杀数: "整数" = 获取自定义变量(self.game, 目标实体=事件源实体, 变量名="击杀数")
        新击杀数: "整数" = 加法运算(self.game, 左值=当前击杀数, 右值=1)
        设置自定义变量(self.game, 目标实体=事件源实体, 变量名="击杀数", 变量值=新击杀数, 是否触发事件=False)

        for 循环索引 in range(0, 3):
            match 循环索引:
                case 0:
                    条件0: "布尔值" = 数值大于等于(self.game, 左值=新击杀数, 右值=10)
                    if 条件0:
                        打印字符串(self.game, 字符串="case0")
                case 1:
                    条件1: "布尔值" = 数值大于等于(self.game, 左值=新击杀数, 右值=20)
                    if 条件1:
                        打印字符串(self.game, 字符串="case1")
                case _:
                    pass

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_pull_eval_hazard_02.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    hits = [issue for issue in report.issues if issue.code == "CODE_PULL_EVAL_REEVAL_AFTER_WRITE"]
    assert hits, "复杂控制流下也应产生 CODE_PULL_EVAL_REEVAL_AFTER_WRITE warning"
    assert any(issue.level == "warning" for issue in hits)


def test_pull_eval_reevaluation_hazard_not_reported_when_write_after_branch(tmp_path: Path) -> None:
    """写入发生在分支之后：即便有重复求值，也不会在“写入之后再复用同一读取节点”，不应提示。"""
    graph_code = '''
"""
graph_id: graph_pull_eval_safe_01
graph_name: 拉取式重复求值风险_不触发
graph_type: server
"""

from __future__ import annotations

from _prelude import *


class 拉取式重复求值风险_不触发:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前击杀数: "整数" = 获取自定义变量(self.game, 目标实体=事件源实体, 变量名="击杀数")
        新击杀数: "整数" = 加法运算(self.game, 左值=当前击杀数, 右值=1)
        达到胜利条件: "布尔值" = 数值大于等于(self.game, 左值=新击杀数, 右值=10)
        if 达到胜利条件:
            打印字符串(self.game, 字符串="win")
        设置自定义变量(self.game, 目标实体=事件源实体, 变量名="击杀数", 变量值=新击杀数, 是否触发事件=False)

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)
'''
    workspace = _workspace_root()
    graph_path = _write_graph_code(tmp_path, "graph_pull_eval_safe_01.py", graph_code)
    report = validate_files([graph_path], workspace, strict_entity_wire_only=False, use_cache=False)

    hits = [issue for issue in report.issues if issue.code == "CODE_PULL_EVAL_REEVAL_AFTER_WRITE"]
    assert not hits, "写入在分支之后且后续未复用读取节点时，不应产生该风险提示"


