from __future__ import annotations

import ast

from engine.graph.utils.syntax_sugar_rewriter import rewrite_graph_code_syntax_sugars


def test_mod_operator_is_rewritten_to_positive_mod_template_server_when_shared_composite_disabled() -> None:
    source = '''
from __future__ import annotations


class 正模_百分号_自动改写:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        a: "整数" = -1
        b: "整数" = 4
        r: "整数" = a % b
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server", enable_shared_composite_sugars=False)
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert "%" not in rewritten_text
    assert rewritten_text.count("模运算(") == 2
    assert rewritten_text.count("加法运算(") == 1


def test_mod_operator_is_rewritten_to_shared_positive_mod_composite_call_server() -> None:
    source = '''
from __future__ import annotations


class 正模_百分号_共享复合_自动改写:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        a: "整数" = -1
        b: "整数" = 4
        r: "整数" = a % b
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server", enable_shared_composite_sugars=True)
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert "%" not in rewritten_text
    assert rewritten_text.count("整数_正模运算(") == 1
    assert rewritten_text.count("_共享复合_整数_正模运算") >= 2  # __init__ 注入 + 调用点
    assert rewritten_text.count(".计算(") == 1
    assert "模运算(self.game" not in rewritten_text
    assert "加法运算(" not in rewritten_text


def test_mod_node_call_is_not_rewritten_server() -> None:
    source = '''
from __future__ import annotations


class 正模_显式模运算节点调用_保持原语义:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        a: "整数" = -1
        r: "整数" = 模运算(self.game, 被模数=a, 模数=4)
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server", enable_shared_composite_sugars=True)
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("模运算(") == 1
    assert "加法运算(" not in rewritten_text
    assert "_共享复合_整数_正模运算" not in rewritten_text

