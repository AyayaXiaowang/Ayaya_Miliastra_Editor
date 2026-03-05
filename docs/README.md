# docs（公开文档入口）

- **使用者（只写节点图）**：请从 `docs/用户必读.md` 开始。
- **开发者（资源/校验/编辑器）**：请从 `docs/资源系统_统一解析层与GUID作用域.md` 开始。
- **开发者（资源库共享规范）**：`docs/资源库_共享目录规范.md`（共享目录用途与禁止事项：测试资源不得进入共享）。
- **新手（收到 `.gia/.gil` 怎么读）**：`docs/GIA_GIL_新手指引_收到文件怎么读.md`（先转 Graph IR / readable JSON）。
- **开发者（节点图逆向生成）**：`docs/反向生成GraphCode_从JSON语义一致方案.md`（从 JSON 反向生成类结构 Graph Code 的可维护设计与实施路线）。
- **开发者（Graph Code 写 Python）**：`docs/GraphCode_写Python转节点图_事件入口与信号监听.md`（澄清“Python DSL ≠ 任意 Python”；信号事件入口的推荐写法与迁移建议）。
- **开发者（UI Web-first 工作流）**：`docs/UI_工作流_一个HTML一个功能页_自动派生.md`（一个 HTML=一个功能页；其余资源自动派生；用校验护栏防遗漏）。
- **开发者（节点图+UI 本地测试）**：`docs/节点图UI_本地测试_信号与交互闭环.md`（在不接入真实游戏语义的前提下，跑通信号/按钮交互与 UI 状态切换的最短闭环方案）。
- **开发者（Cursor hooks 校验改造）**：`docs/Cursor_Hooks_校验改造方案.md`（把节点图/UI/项目存档校验分层落到 afterFileEdit 与 git commit 前拦截，形成可执行闭环）。
- **开发者（GIA 导出链路收敛）**：`docs/GIA导出链路_收敛与兼容方案.md`（解释“为什么导出 `.gia` 入口很多”、如何用兼容层做架构收敛而不破坏现有功能）。


