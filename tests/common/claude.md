## 目录用途
存放 app/common 这类“跨 UI/模型共享的轻量模块”相关测试，重点回归缓存/协议等全局一致性规则。

## 当前状态
- `test_in_memory_graph_payload_cache_contract.py`：回归 `in_memory_graph_payload_cache` 的 cache_key 规则、解析优先级与失效语义。
- `test_pagination_compute_lazy_pagination_target_index.py`：回归“懒加载分页目标索引”的计算语义（ensure_total 不回退、add_count 与 default_chunk 的回退策略、输入 clamp），用于支撑库页“加载更多/按需加载”逻辑的纯算法层回归。
- `test_selection_restore_policy.py`：回归“列表刷新后选中恢复”策略：previous_key 命中优先、找不到回退第一条、列表为空时 cleared/none 分叉，用于支撑库页统一的选中恢复行为与右侧面板收起策略。
- `test_decorations_merge_keep_world_trs.py`：回归“装饰物合并”在 source/target 存在 rotation/scale 时也能保持装饰物世界坐标（位置）不变（keep_world 重父级 + keep_world 居中补偿），并覆盖实例父级 scale 从 `metadata["ugc_scale"]` 读取的兼容口径（`.gia` 导入/写回一致）。
- `test_private_extension_loader_sys_modules.py`：回归“按文件路径加载扩展模块”时会写入 `sys.modules`，避免 dataclasses/typing 等依赖模块注册表的逻辑失败。
- `test_web_ui_workbench_progressbar_color_sanitize.py`：回归“千星沙箱网页处理工具”导出的进度条颜色会被归一化到写回链路认可的五色调色板，避免 `#FFFFFF` 等导致写回报错。
- `test_ui_variable_validator_progressbar_attrs.py`：回归 `validate-ui` 会校验进度条变量绑定属性 `data-progress-*-var` 的语法（允许 ps/lv/p1~p8 前缀；min/max 允许数字常量；**禁止** `ps.dict.key/lv.dict.key` 这类字典键路径写法）。
- `test_ui_html_bundle_ui_states_map.py`：回归 UI HTML bundle 导入会生成 `ui_states/*.ui_states.json`（从 widgets 的 `__ui_state_*` 汇总 state_group/state→ui_key 列表），用于节点图侧实现互斥显隐切换。
- `test_ui_workbench_static_dir_single_source.py`：回归 UI Workbench 静态前端单一真源：私有扩展后端应固定从 `assets/ui_workbench/` 提供静态资源（避免插件/测试/离线预览各用一份导致样式/层级漂移）。

## 注意事项
- 保持纯逻辑，不引入 PyQt6 与重型引擎依赖。
- 不使用 `try/except` 吞错，失败直接抛出由 pytest 记录。


