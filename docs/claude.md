# docs（公开文档）

## 目录用途
- 存放公开文档入口与专题说明（文档入口索引见 `docs/README.md`）。
- 诊断与证据链：`docs/diagnostics/`。
- 快照归档：`tests/snapshots/`（用于测试/接口快照；可为空）。

## 当前状态
- 文档入口索引：`docs/README.md`。
- 面向使用者的入口 `docs/用户必读.md` 默认以“资源库包化目录结构”为准：`assets/资源库/共享/` + `assets/资源库/项目存档/<package_id>/`（其中实体摆放目录为 `实体摆放/`）。
- UI 工作流专题：`docs/UI_工作流_一个HTML一个功能页_自动派生.md`（以 UI源码 为唯一输入、其余 UI 布局/控件模板/交互映射/GUID 映射为自动派生产物；强调目录骨架/目录文档/校验三道护栏以防遗漏）。
- 节点图+UI 本地测试专题：`docs/节点图UI_本地测试_信号与交互闭环.md`（以可执行代码生成 + MockRuntime 为核心，跑通信号与按钮交互的最短闭环；UI 变化以 patch 回显，不要求真实游戏语义）。
- `.gia` 导出入口梳理与收敛方案：`docs/GIA导出链路_收敛与兼容方案.md`（按资产类型分类入口与底层实现，明确“门面层 + 兼容壳”的非破坏收敛策略）。
- 本目录除公开入口外，可能还包含“结构说明/专题设计”等内部文档（例如 `docs/目标目录结构与项目背景.md`）；是否纳入仓库分发以 `.gitignore` 白名单为准。
- 节点图逆向生成（语义一致）方案：`docs/反向生成GraphCode_从JSON语义一致方案.md`（基于现有 `GraphCodeParser/IR` 解析协议，反向生成可被正向解析闭环的类结构 Python）。
- 节点/端口稳定标识蓝图：`docs/节点稳定标识.md`（已落地：全链路 NodeDef 定位完全去 title 依赖；固化 canonical NodeDef Key 契约；旧数据缺失 `node_def_ref` 时强制重建 cache；`.gia` 导出与 UI/自动化/校验统一走 `node_def_ref`）。
- 派生文档（自动生成）：`docs/generated/node_library/`（由内部生成脚本生成；禁止手工编辑生成产物）。
- 节点手写说明（doc_reference 落点）：
  - `docs/服务器节点/**`
  - `docs/客户端节点/**`
  - `docs/复合节点.md`（含复合节点作用域与校验入口说明）
- 资源系统专题：`docs/资源系统_统一解析层与GUID作用域.md`（统一解析层、GUID 包内作用域、调用侧收敛、迁移策略与校验规则前置；文档内落地状态为全 ✅）。
- 信号系统专题：`docs/信号系统设计.md`（信号定义/绑定、`GraphSemanticPass` 单一写入 `signal_bindings`、综合校验 `SignalUsageRule`、schema 哈希与端口同步策略）。
- Graph Code 写 Python 转节点图：`docs/GraphCode_写Python转节点图_事件入口与信号监听.md`（事件入口一致性问题复盘；澄清“Python DSL ≠ 任意 Python”；推荐用 `register_handlers` 显式绑定信号，避免 `on_<信号名>` 误导并支持同信号多处理器）。

## 注意事项
- 本文件仅描述“目录用途 / 当前状态 / 注意事项”，不记录修改历史。
- 本目录文档（含 `claude.md`）默认视为公开内容：不得写入未公开资源路径、私有存档、账号信息、Token、个人环境细节等敏感信息。
- 文档统一 UTF-8，保持精简；诊断文档需提供最小但完整证据链（现象→定义→解析/校验路径→产物证据→结论/操作指引）。
- 本目录不保留“已完成的一次性实施清单/待办计划”类文档；此类内容应沉到可执行工具脚本、CI 与测试中，必要证据链放入 `docs/diagnostics/`。
- 常用校验入口（PowerShell 逐行执行）：
  - `python -X utf8 -m app.cli.graph_tools validate-project`
  - `python -X utf8 -m app.cli.graph_tools validate-graphs --all`
