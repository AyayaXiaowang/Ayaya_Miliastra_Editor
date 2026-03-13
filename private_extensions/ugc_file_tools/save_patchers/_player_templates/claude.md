## 目录用途
- `save_patchers.player_templates` 的内部实现拆分：将玩家模板写回相关逻辑按职责拆成多个小模块，由上层兼容层统一 re-export。

## 当前状态
- `common.py`：共享常量/模型/通用遍历与玩家索引解析。
- `structured_entries.py`：root4/root5 结构化提取与生效玩家写回。
- `structured_variables.py`：自定义变量定义（group1）写回（dict-level）。
- `io_ops.py`：报告/读取/写回与 payload_root 搜索辅助。
- `wire_helpers.py`：wire-level chunk 解析与定点 patch 基元。
- `wire_patchers.py`：玩家模板变量定义的 wire-level 安全补丁（避免 payload drift）。

## 注意事项
- fail-fast：结构不符直接抛错，不吞异常。
- wire-level patch 仅替换目标字段相关 bytes，其它字段保持原样。
- 本目录不作为稳定对外 API；对外入口以 `save_patchers/player_templates.py` 为准。

