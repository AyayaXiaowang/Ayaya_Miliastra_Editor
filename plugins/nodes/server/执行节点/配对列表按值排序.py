from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="配对列表按值排序",
    category="执行节点",
    inputs=[
        ("流程入", "流程"),
        ("键列表", "泛型列表"),
        ("值列表", "泛型列表"),
        ("排序方式", "枚举"),
    ],
    outputs=[("流程出", "流程")],
    description="将配对的两个列表按值列表的数值进行联动排序，键列表与值列表位置保持对应",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 配对列表按值排序(game, 键列表, 值列表, 排序方式):
    """将配对的两个列表按值列表的数值进行联动排序。

    参数：
    - 键列表：类型索引或标识列表（如元素类型索引）
    - 值列表：对应的数值列表
    - 排序方式：升序/降序

    效果：
    - 按值列表数值进行排序，同时保持键列表与值列表的位置对应关系
    - 两个列表会被原地修改
    """
    if not isinstance(键列表, list) or not isinstance(值列表, list):
        log_info("[配对列表按值排序] 参数不是列表，跳过排序")
        return

    if len(键列表) != len(值列表):
        log_info(f"[配对列表按值排序] 键列表长度({len(键列表)})与值列表长度({len(值列表)})不一致，跳过排序")
        return

    if len(键列表) == 0:
        log_info("[配对列表按值排序] 列表为空，跳过排序")
        return

    # 组合为元组列表进行排序
    配对数据 = list(zip(键列表, 值列表))

    降序排列 = 排序方式 == "降序"
    配对数据.sort(key=lambda 元组: 元组[1], reverse=降序排列)

    # 将排序结果写回原列表
    键列表.clear()
    值列表.clear()
    for 键, 值 in 配对数据:
        键列表.append(键)
        值列表.append(值)

    log_info(f"[配对列表按值排序] {排序方式}: 键={键列表}, 值={值列表}")

