## 目录用途
存放“故意写错”的 Graph Code（节点图类结构 Python）负例语料，用于人工跑 `app.cli.graph_tools validate-graphs` 时观察**错误码覆盖面**与**报错信息质量**。

## 当前状态
- 该目录下的 `.py` 文件**预期全部校验失败**（包含多类极端/边界错误：条件表达式、range 用法、列表/字典字面量边界、方法/函数调用禁用、事件回调命名与签名、局部变量/字典写回语义等）。
- 覆盖重点（不列具体文件清单）：
  - if 条件：不支持的 Compare 形态（链式比较、is/is not 等）、直接调用【逻辑非运算】等
  - range：非 for 迭代器位置调用、关键字参数、step 参数、内联算术
  - list/dict：空容器、超过上限、展开语法、for 迭代器位置字面量
  - 语法形态：f-string、lambda、match/case pattern 非字面量
  - 结构/契约：缺少必填入参、可变参数节点空参数、节点图变量未声明、未知类型名、端口同型约束、return 后不可达代码
- 不参与资源库节点图（`assets/资源库/共享/节点图/...`、`assets/资源库/项目存档/<package_id>/节点图/...`）的全量扫描与发布资源，仅作为校验器回归语料使用。

## 注意事项
- 运行校验（PowerShell 不用 `&&`）：
  - `python -X utf8 -m app.cli.graph_tools validate-graphs tests/validate/negative_graphs`
- 这些文件的目标是“触发尽可能多的校验规则”，因此**不要修到能通过**；如某条规则不再报错，应调整语料以保持覆盖。
- 负例语料应保持 **Python 语法可编译**（避免在 `compile` 阶段就 SyntaxError 退出）；若需要覆盖 match/case 的“非字面量 pattern”规则，优先使用“单个 case 的 capture pattern”或其他语法合法的 pattern 形态。


