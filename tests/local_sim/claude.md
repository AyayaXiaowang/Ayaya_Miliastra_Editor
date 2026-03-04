## 目录用途
- 存放“本地测试（Local Graph Sim）”相关回归测试：在 **纯 Python** 环境下使用 `GameRuntime` 驱动节点图事件/信号/定时器，覆盖 UI 索引占位符（`ui_key:`）解析、布局切换与关键交互闭环。

## 当前状态
- 覆盖最小夹具节点图 `tests/local_sim/fixture_graph_local_sim_minimal.py`：
  - `ui_key:` 占位符解析 → 稳定 index，并可回映射到原始 key（用于离线模拟 UI click/patch）。
  - “布局索引_*” fallback：从描述里的 `page_a.html/page_b.html` 推导稳定 layout_index。
  - click 注入：通过 `LocalGraphSimSession.trigger_ui_click(...)` 触发“界面控件组触发时”并写回图变量。
- 覆盖多图挂载回归：
  - 夹具：`fixture_graph_local_sim_multi_a.py`（主图）+ `fixture_graph_local_sim_multi_b.py`（额外挂载图）
  - 用例：`test_local_graph_sim_multi_graph_mounts.py` 校验同一会话内挂载多图后，同一事件可触发多个回调，且额外挂载图能写入其 owner 实体自定义变量（用于断言挂载与执行链路）。
- 覆盖本地模拟 HTTP server（`LocalGraphSimServer`）启动与 UI HTML `data-ui-variable-defaults` 注入：
  - 使用 `tests/local_sim/fixture_ui_local_sim_minimal.html` 提供 `lv.*` 默认结构，启动时写入 `GameRuntime.ui_lv_defaults`。
  - 对齐 server 逻辑：入口页优先，合并同目录多页 HTML 的 `lv.*` 默认值（只补缺，不覆盖入口页已有值），避免跨页切换/流程变量首次读取时得到 `None`。
  - 覆盖协议自描述：`GET /api/local_sim/protocol` 返回 `schema_version/protocol_version` 与 endpoints，并断言 `status/snapshot` 等响应携带版本字段以形成强契约
- 覆盖复现包导出（`/api/local_sim/export_repro`）：
  - 生成 JSON 落盘并提供下载接口，便于把“输入/输出/校验/trace”打包给他人复现
- 覆盖暂停/继续（`/api/local_sim/pause`）：
  - 暂停期间虚拟时间不推进，轮询不会推进定时器；恢复后不会补触发
  - 冻结世界：暂停时 click/emit_signal 会被拒绝（用于断言“没有东西会偷偷跑”）
  - 单步：`/api/local_sim/step` 推进虚拟时间并最多触发 1 次定时器事件（用于逐步回归）
- 覆盖选关页“开始关卡”信号参数回归：
  - `test_local_sim_level_select_start_level_param.py`：点击关卡按钮写入 `ui_sel_level`，点击 `投票此关` 后断言广播 `关卡大厅_开始关卡(第X关)` 参数与当前选中关卡一致（用例以 `rect_level_03` 作为样例；本地模拟需显式设置玩家当前布局为选关页）。
- 覆盖第七关真实节点图闭环（`tests/local_sim/test_local_sim_level7_gameplay.py`）：
  - 教程“下一步”逐步切换遮罩状态 + “完成”闭环、妈妈纸条线索写回、帮助按钮回顾教程。
  - 线索区：标题 + 6 条线索（标签/正文）逐条写回，确保与数据服务下发一致。
    - 妈妈纸条线索正文长度约束：单条 **≤10 字**（离线生成/导入阶段保证，测试侧同步断言）。
  - 门控图（开/关门 + 运动器停止事件触发关门完成）与“关门完成→请求并生成亲戚→开门进场”联动闭环。
  - 对话按钮：对白按本回合数据服务下发顺序循环写回，并断言跨回合会清空避免残留。
  - 亲戚元件实体生成：断言 `第七关_亲戚_*实体` 写入与实体存在；回合推进时断言旧实体销毁并替换新实体；退出回选关断言清理不残留。
  - 允许/拒绝正确/错误结算（分数 + HUD + 揭晓遮罩），并校验惩罚：
    - 完整度按投错扣减
    - 手办存活仅在“放小孩进来”时扣减（外观_身体=小孩马 + 结果允许）
  - 顶部按钮 `退出/关卡选择` 均可回选关并重置状态。
  - 揭晓遮罩“继续”可推进下一回合并刷新“剩余亲戚”计数。
  - 多人投票：投票后审判庭状态即时刷新、投票者按钮禁用；仅在全员完成选择后揭晓，并校验多人计分与扣除按票数生效。
  - 单回合进入结算页后，结算页按钮在“当前布局门控”下可用（依赖 `获取玩家当前界面布局` 的本地语义）；支持 `返回大厅/再来一年` 回选关闭环，其中“再来一年”会重置回合/阶段/玩家选择/分数与结算统计当前值。

## 注意事项
- 测试不得依赖 PyQt6/主程序入口（如 `run_app.py`），仅使用 `app/runtime/services/*` 与 `app/runtime/engine/*` 的离线模拟能力。
- 图/HTML 夹具应放在 `tests/local_sim/` 内（或使用版本化的 `assets/资源库/项目存档/示例项目模板/`），不要依赖被 `.gitignore` 忽略的本地项目存档目录。

