from __future__ import annotations

"""
复合节点引脚声明辅助函数

这些函数仅用于**声明**虚拟引脚，方便在 Python 代码中以接近节点图的语法
描述“流程入/流程出/数据入/数据出”。在运行时它们不会产生任何效果，也不会
修改参数值——调用它们就像写一条注释，pure no-op。

示例：

    @flow_entry()
    def 批量设置(self, 目标实体: "实体", 延迟秒数: "浮点数"):
        流程入("入口A")
        数据出("最终状态", "字符串")
        流程出("执行完成")
        最终状态 = 获取自定义变量(...)

注意：
1. 仅在编译/解析阶段被 AST 扫描器识别；运行期请不要依赖返回值。
2. Pin 名称需使用字符串字面量，保持可静态分析。
3. 同名引脚只会生成一次，可在多处调用以强调图结构。
"""

__all__ = [
    "流程入",
    "流程入引脚",
    "流程出",
    "流程出引脚",
    "数据入",
    "数据出",
]


def _no_effect(*_, **__) -> None:
    """统一的 no-op，确保运行期调用这些辅助函数不会产生副作用。"""
    return None


def 流程入(pin_name: str = "流程入", *, pin_type: str = "流程") -> None:
    """声明一个流程入引脚（仅用于语法提示，无运行期效果）。"""
    return _no_effect(pin_name, pin_type)


def 流程入引脚(pin_name: str = "流程入", *, pin_type: str = "流程") -> None:
    """`流程入` 的别名，便于使用不同表述。"""
    return _no_effect(pin_name, pin_type)


def 流程出(pin_name: str = "流程出", *, pin_type: str = "流程") -> None:
    """声明一个流程出口（仅用于语法提示，无运行期效果）。"""
    return _no_effect(pin_name, pin_type)


def 流程出引脚(pin_name: str = "流程出", *, pin_type: str = "流程") -> None:
    """`流程出` 的别名。"""
    return _no_effect(pin_name, pin_type)


def 数据入(pin_name: str, *, pin_type: str = "泛型") -> None:
    """声明一个数据输入引脚，通常与方法形参同名。"""
    return _no_effect(pin_name, pin_type)


def 数据出(pin_name: str, *, pin_type: str = "泛型", variable: str | None = None) -> None:
    """声明一个数据输出引脚，variable 参数仅用于增强可读性。"""
    return _no_effect(pin_name, pin_type, variable)


