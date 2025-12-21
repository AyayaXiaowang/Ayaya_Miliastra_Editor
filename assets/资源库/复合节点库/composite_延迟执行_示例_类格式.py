"""
composite_id: composite_延迟执行_示例_类格式
node_name: 延迟执行_示例
node_description: 延迟一段时间后通过流程出口（逻辑同 composite_延迟执行_类格式，用于示例存档包）
scope: server
"""

from __future__ import annotations

import sys
from pathlib import Path

# 复合节点库位于 `.../Graph_Generater/assets/资源库/复合节点库/`，
# 因此当前文件向上 3 层即为项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = PROJECT_ROOT / "app"
ASSETS_ROOT = PROJECT_ROOT / "assets"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))
if str(ASSETS_ROOT) not in sys.path:
    sys.path.insert(2, str(ASSETS_ROOT))

from runtime.engine.graph_prelude_server import *
from engine.nodes.composite_spec import composite_class, flow_entry, event_handler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入,数据出


@composite_class
class 延迟执行_示例_类格式:
    """延迟执行复合节点（单流程入口 + 事件处理器，示例版）
    
    功能与 `composite_延迟执行_类格式` 完全一致：
    - 流程入口：启动定时器并记录标识
    - 事件处理器：定时器触发时校验标识，匹配则走流程出
    
    两个流共享定时器标识（实例变量），本文件仅作为示例包复用与教学示例使用。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        # 存储定时器标识，供事件处理器使用
        self._定时器标识 = ""

        # 必需：在运行时开启严格校验开关后，对当前复合节点代码做一次严格校验
        # 复用与普通节点图相同的验证入口，底层会根据文件路径识别为“复合节点文件”并应用对应规则
        from runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    @flow_entry()
    def 延迟执行(self, 目标实体, 延迟秒数, 定时器标识):
        """延迟执行流程：启动定时器并等待事件回调"""
        流程入("流程入")
        数据入("目标实体", pin_type="实体")
        数据入("延迟秒数", pin_type="浮点数")
        数据入("定时器标识", pin_type="字符串")

        # 保存定时器标识，供事件处理器校验
        self._定时器标识 = 定时器标识

        定时器序列 = 拼装列表(self.game, 延迟秒数)
        启动定时器(
            self.game,
            目标实体=目标实体,
            定时器名称=定时器标识,
            是否循环=False,
            定时器序列=定时器序列,
        )

    # ========== 流2：事件处理器（定时器触发时）- 内部实现 ==========
    @event_handler(event="定时器触发时")
    def on_定时器触发时(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        触发的定时器名称: "字符串",
        定时器序列序号: "整数",
        循环次数: "整数",
    ):
        """流2：定时器触发时，判断名称匹配后走流程出口
        
        说明：
        - 事件参数仅在内部使用，不会暴露为虚拟引脚
        - 通过 self._定时器标识 获取流1传入的定时器标识
        - 比较触发的定时器名称和启动时的标识，匹配才走流程出口
        """

        # 判断触发的定时器名称是否匹配我们启动的
        名称匹配 = 是否相等(
            self.game,
            输入1=触发的定时器名称,
            输入2=self._定时器标识,
        )

        if 名称匹配:
            # 名称匹配，流程从"触发完成"出口出去
            流程出("触发完成")


if __name__ == "__main__":
    import sys
    import pathlib
    from runtime.engine.node_graph_validator import validate_file

    自身文件路径 = pathlib.Path(__file__).resolve()
    是否通过, 错误列表, 警告列表 = validate_file(自身文件路径)
    print("=" * 80)
    print(f"复合节点自检: {自身文件路径.name}")
    print(f"文件: {自身文件路径}")
    if 是否通过:
        print("结果: 通过")
    else:
        print(f"结果: 未通过（错误: {len(错误列表)}，警告: {len(警告列表)}）")
        if 错误列表:
            print("\n错误明细:")
            for 序号, 错误文本 in enumerate(错误列表, start=1):
                print(f"  [{序号}] {错误文本}")
        if 警告列表:
            print("\n警告明细:")
            for 序号, 警告文本 in enumerate(警告列表, start=1):
                print(f"  [{序号}] {警告文本}")
    print("=" * 80)
    if not 是否通过:
        sys.exit(1)


