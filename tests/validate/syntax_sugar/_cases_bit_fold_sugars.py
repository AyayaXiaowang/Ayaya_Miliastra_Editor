from __future__ import annotations

import ast

from engine.graph.utils.syntax_sugar_rewriter import rewrite_graph_code_syntax_sugars


def test_bit_read_fold_form1_is_rewritten_to_single_node_call_server() -> None:
    source = '''
from __future__ import annotations


class 按位读出折叠_形态1:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        值: "整数" = 255
        起始位: "整数" = 2
        结束位: "整数" = 5
        结果: "整数" = ((值 >> 起始位) & ((1 << (结束位 - 起始位 + 1)) - 1))
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server")
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("按位读出(") == 1
    assert "按位与(" not in rewritten_text
    assert "右移运算(" not in rewritten_text
    assert "左移运算(" not in rewritten_text


def test_bit_read_fold_form2_is_rewritten_to_single_node_call_server() -> None:
    source = '''
from __future__ import annotations


class 按位读出折叠_形态2:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        值: "整数" = 255
        起始位: "整数" = 2
        结束位: "整数" = 5
        结果: "整数" = ((值 & (((1 << (结束位 - 起始位 + 1)) - 1) << 起始位)) >> 起始位)
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server")
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("按位读出(") == 1
    assert "按位与(" not in rewritten_text
    assert "右移运算(" not in rewritten_text
    assert "左移运算(" not in rewritten_text


def test_bit_write_fold_inline_is_rewritten_to_single_node_call_server() -> None:
    source = '''
from __future__ import annotations


class 按位写入折叠_内联:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        被写入值: "整数" = 0
        写入值: "整数" = 3
        起始位: "整数" = 2
        结束位: "整数" = 5
        结果: "整数" = (被写入值 & ~(((1 << (结束位 - 起始位 + 1)) - 1) << 起始位)) | (写入值 << 起始位)
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server")
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("按位写入(") == 1
    assert "按位与(" not in rewritten_text
    assert "按位或(" not in rewritten_text
    assert "按位取补运算(" not in rewritten_text
    assert "左移运算(" not in rewritten_text


def test_bit_write_fold_two_step_template_is_rewritten_to_single_node_call_server() -> None:
    source = '''
from __future__ import annotations


class 按位写入折叠_两步模板:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        被写入值: "整数" = 0
        写入值: "整数" = 3
        起始位: "整数" = 2
        结束位: "整数" = 5

        掩码: "整数" = (((1 << (结束位 - 起始位 + 1)) - 1) << 起始位)
        结果: "整数" = (被写入值 & ~掩码) | (写入值 << 起始位)
        return
'''
    tree = ast.parse(source)
    rewritten_tree, rewrite_issues = rewrite_graph_code_syntax_sugars(tree, scope="server")
    assert not rewrite_issues

    rewritten_text = ast.unparse(rewritten_tree)
    assert rewritten_text.count("按位写入(") == 1
    assert "掩码" not in rewritten_text
    assert "按位与(" not in rewritten_text
    assert "按位或(" not in rewritten_text
    assert "按位取补运算(" not in rewritten_text
    assert "左移运算(" not in rewritten_text

