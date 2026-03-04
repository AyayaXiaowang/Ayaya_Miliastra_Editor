"""
graph_id: client_template_syntax_sugar_random_vector_01
graph_name: 模板示例_语法糖归一化_随机与向量
graph_type: client
folder_path: 技能节点图/模板示例
description: |
  客户端侧教学示例：演示 client 作用域可用的 Python 原生写法如何在校验/解析入口被自动归一化为等价的节点调用。

  本示例覆盖（client）：
  - random.uniform -> 【获取随机数】
  - math.radians / math.degrees -> 【角度转弧度】/【弧度转角度】
  - 三维向量运算符：+ / - / *（缩放）/ @（点乘）/ abs（模）
  - not 条件 / -x
"""

from __future__ import annotations

import math
import random

import sys
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir()))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / 'assets'))

from app.runtime.engine.graph_prelude_client import *  # noqa: F401,F403

class 模板示例_语法糖归一化_随机与向量:
    """客户端侧：语法糖归一化示例（random/math/向量运算符/not/一元负号）。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        validate_node_graph(self.__class__)

    def on_节点图开始(self):
        # ---------------------------------------------------------------------
        # 1) random.uniform（client）：会改写为【获取随机数】
        # ---------------------------------------------------------------------
        随机数: "浮点数" = random.uniform(0.0, 1.0)

        # ---------------------------------------------------------------------
        # 2) math.radians/math.degrees（client）：会改写为【角度转弧度】/【弧度转角度】
        # ---------------------------------------------------------------------
        角度: "浮点数" = 90.0
        弧度: "浮点数" = math.radians(角度)
        角度回转: "浮点数" = math.degrees(弧度)

        # ---------------------------------------------------------------------
        # 3) 三维向量运算符：+ / - / * / @ / abs
        # ---------------------------------------------------------------------
        向量A: "三维向量" = (1.0, 2.0, 3.0)
        向量B: "三维向量" = (4.0, 5.0, 6.0)

        向量和: "三维向量" = 向量A + 向量B
        向量差: "三维向量" = 向量A - 向量B
        向量缩放: "三维向量" = 向量A * 2.0
        点乘: "浮点数" = 向量A @ 向量B
        向量模: "浮点数" = abs(向量A)

        # ---------------------------------------------------------------------
        # 4) not / 一元负号
        # ---------------------------------------------------------------------
        点乘为正: "布尔值" = 点乘 > 0.0
        not结果: "布尔值" = not 点乘为正
        负数点乘: "浮点数" = -点乘

        # 写入局部变量便于观察（不会影响业务逻辑）
        设置局部变量(self.game, 变量名="示例_随机数", 变量值=随机数)
        设置局部变量(self.game, 变量名="示例_角度回转", 变量值=角度回转)
        设置局部变量(self.game, 变量名="示例_向量点乘", 变量值=点乘)
        设置局部变量(self.game, 变量名="示例_向量模", 变量值=向量模)
        设置局部变量(self.game, 变量名="示例_not", 变量值=not结果)
        设置局部变量(self.game, 变量名="示例_负数点乘", 变量值=负数点乘)

        # 防止变量被“误读为无用”：把向量也落一次局部变量
        设置局部变量(self.game, 变量名="示例_向量和", 变量值=向量和)
        设置局部变量(self.game, 变量名="示例_向量差", 变量值=向量差)
        设置局部变量(self.game, 变量名="示例_向量缩放", 变量值=向量缩放)

    def register_handlers(self):
        # client 节点图通常由外部调度触发；此示例不显式注册事件
        return

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
