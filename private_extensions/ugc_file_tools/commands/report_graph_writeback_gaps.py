from __future__ import annotations

"""
report_graph_writeback_gaps.py

用途：
- 对比 “GraphModel(JSON) 需要写回的内容” vs “当前模板样本库（template_gil + 可选 template_library_dir）”
  输出一份可重复的 gap 报告，帮助你在补充真源样本后立即看到覆盖提升。

报告范围（目前聚焦 server 写回链路最关键的 3 类缺口）：
- 缺 node type_id 模板：GraphModel 里出现了某节点，但模板库无对应 type_id 的 node 样本可克隆。
- 缺 record 形态/覆盖：
  - data-link record：dst_type_id + slot_index 的模板 record 是否存在（模板缺失时会退化为 schema 兜底写入）。
  - OutParam record：type_id + out_index + var_type 的模板 record 是否存在（缺失时当前实现不会凭空新增）。
- 缺默认值写回规则：
  - 当前 input_constants 写回不支持 “字典”(VarType=27) 常量；若 GraphModel 常量端口类型为字典，会在写回阶段报错。
  - 列表常量若以字符串形式提供（例如 "[1,2,3]"），仅部分列表类型支持解析；其余类型要求上游提供真正的 list/tuple。

约束：
- 不使用 try/except；失败直接抛错（fail-closed）。
"""
from ugc_file_tools.commands.reports.report_graph_writeback_gaps import build_report, main

__all__ = ["build_report", "main"]


if __name__ == "__main__":
    main()


