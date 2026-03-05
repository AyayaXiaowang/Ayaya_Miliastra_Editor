## 目录用途
`src/workbench_main/` 承载 Workbench 主页面的装配与交互编排（初始化、事件绑定、扁平化/导出控制器、与主程序 API 的可选桥接）。

## 当前状态
- `index.js`：Workbench 初始化入口，负责装配 preview / flatteningController / appApiController / groupTreeController，并绑定 DOM 事件；切换文件时保留当前预览模式（不强制回到“源码”）。
  - 重操作统一走 `run_queue.js`（校验/扁平/导出 bundle/导入/导出 GIL/GIA），用 **session key** 在“源码/选择变化”时跨操作取消旧任务，避免互相覆盖。
  - 校验/扁平/导出使用隐藏 compute iframe 做 computedStyle 采样；“校验并渲染/自动修正并校验”会通过 `preview_variant_switch.js` 刷新可视预览 iframe（渲染=展示），避免预览来回闪。
  - **字号一致性硬约束**：校验阶段会对 compute iframe 轮询 4 个画布尺寸，要求所有可见文本的 `font-size` 恒定；不满足会报错并阻断后续预扁平/导出。
  - 预热策略：当“校验通过（errors=0）”后，会自动预生成扁平化缓存；切到扁平模式时若缓存缺失/过期，将自动触发一次扁平化生成并显示“生成中”占位提示。
  - 浏览器模式下可自动预扁平化“项目 UI源码清单”：刷新清单后按项目列表逐个生成扁平缓存，列表默认仅展示已完成扁平化的项目文件。
  - 维护“按文件缓存”的扁平化结果（key: `scope::rel_path`），用于在列表/预览切换时复用并减少重算。
  - 打开文件后会尝试用“按文件缓存”回填扁平化输出（hash 匹配才生效），避免列表已完成但切换预览仍提示未生成。
  - browse 模式打开文件时若缓存缺失，会立即触发一次扁平化生成，确保切换“扁平模式”不会卡在空白占位。
- `events.js`：集中绑定 UI 按钮与快捷键事件，调用上层注入的 handler（validate/flatten/export bundle/import/export gil 等）。
- 预览支持“动态文本预览”开关：切换后会按当前预览变体重渲染，用于在原稿预览中显示 `data-ui-text` 绑定占位符。
- `flattening.js`：扁平化与“导出 UI布局 Bundle JSON”的控制器实现；扁平缓存以 **sourceHash** 作为唯一失效判定，避免比较整段 HTML 文本导致语义不一致。
  - 取消/并发控制统一由 `run_queue.js` 提供的 **token** 驱动（latest-wins + coalesce + session key）；`flatteningController` 本身不再维护第二套内部 token，只在关键 await 点检查外部 token 是否仍 active。
  - 导出 bundle 时会把 `dom_extract` 提取到的 `data-ui-variable-defaults` 合并写入 bundle 顶层 `variable_defaults`（用于写回端创建实体自定义变量的默认值）。
    - 约定：key 推荐使用 `lv.<变量名>`（关卡）/`ps.<变量名>`（玩家）；`ls` 前缀为旧写法，已禁用。
  - 导出 bundle 的 `layout_id/template_id` 采用**稳定 hash**（基于归一化 HTML 的 `source_hash` + 页面前缀/布局名/画布尺寸），避免 `Date.now()` 导致同一源码重复导出产生噪声 diff。
  - UI 多状态导出策略固定为“整态打组”（`ui_state_consolidation_mode="full_state_groups"`），与 `ui_app_ui_preview` / 导出中心口径一致，避免两边导出结果不一致。
  - 支持 silent 生成：可在“批量预扁平化”场景下只生成缓存，不写入可视 UI 面板。
  - 扁平化 HTML 输出默认会**替换 `<body>...</body>` 的内容**为扁平层（不再残留原始 DOM），避免原稿结构干扰点选/遮挡诊断；兼容兜底可回退为“注入”方式（仅用于极端环境）。
- `compute_fallback.js`：统一 compute iframe 提取为空时的回退策略（仅 **源码预览 + 当前尺寸** 允许回退到可视预览文档），供扁平化生成/导出 bundle/字号采样/分组树刷新复用；在需要时允许触发一次“确保源码预览就绪”以消除首轮时序问题。
- `group_tree.js`：分组树（扁平化调试）渲染与“列表 ↔ 画布”联动。
  - 为避免“切到扁平模式却被强制切回源码”的打架，分组树的 layer 提取改用 compute iframe（不写可视预览 srcdoc），仅在需要定位时读取可视预览中的 `.flat-*` 元素。
  - 可见性/导出排除开关会在用户点击时自动确保当前预览处于“扁平化”变体，避免出现“列表图标已切换但画布无变化”（原稿预览不包含 `.flat-*`）。
  - 可见性开关在内部会将“外部传入的 layerKey”归一化为“已索引到的预览 DOM layerKey”，修复因 z-index/舍入差异导致的“列表状态切换但画布元素未隐藏”。
  - 可见性切换会在执行前强制重建“预览 DOM 索引”（`.flat-*` → layerKey 映射），避免预览重渲染后索引仍指向旧 document 导致“图标变了但画布无变化”。
  - 可见性判定（isLayerHidden / 组隐藏聚合）同样按“归一化后的 DOM layerKey”口径判断，确保隐藏/显示可逆（不会出现“隐藏后点显示无反应”）。
  - 点击列表定位时，若“layerKey 精确匹配”失败（例如 z-index/舍入差异），会回退用“位置容差匹配”寻找最接近的 `.flat-*` 层并选中，避免出现“点击无反应”。
  - 画布点选联动时，若“点选层的 layerKey”在分组树中找不到（偶发的舍入/口径漂移），会按 `kind+rect` 做一次受控匹配并选中最接近条目，避免出现“检查器已更新但左下不高亮”的联动失效体验。
  - 当存在重叠层（常见：`text-level-name` 与 `text-level-author` 矩形高度重叠）导致“仅按 rect 最近邻”会选错时，会优先用 `data-debug-label` 做受控纠正（先按 debug label 过滤，再在候选里按 rect/z 最近邻），保证“点到谁就高亮谁”。
  - 若树中不存在同 kind 的条目（例如用户点到 `text` 层，但树里只有 `element` 主体层），会降级为“不限 kind”的最近邻匹配，至少保证用户能看到“跳转高亮”（避免完全无响应）。
  - 对外提供 `findPreviewElementByLayerKey(layerKey)`：供其它视图（例如 `ui_app_ui_preview` 的“导出控件”列表）复用同一套“容差匹配”能力，根治因浮点舍入差异导致的“精确 layerKey 找不到 → 误选到大遮罩层”。
  - `layerKey` 的构建/解析口径由 `src/layer_key.js` 统一提供；本目录与其它视图不得各自实现第二套 `split/join("__")` 逻辑，避免“同一层在 A 能定位、在 B 定位不到”。
  - UX：当 layer 提取结果为空时，分组树会显示明确的“失败/空结果”提示与排障建议，避免用户误以为扁平化正常但“没变化”。
  - 多状态分组（重要）：当元素标注 `data-ui-state-*` 时，分组 key 会优先按自身状态生成（不再被 `componentOwner*` 归属到 owner），从而在分组树中也能直观看到“不同状态拆成不同组件组”（与导出/写回口径一致）。
  - **稳定 key 单一来源**：分组树生成组件组 key（用于分组展示/联动）直接复用 `src/ui_export/keys.js`（`buildStableHtmlComponentKeyWithPrefix`），不在本文件重复实现规则，避免“分组树 key ≠ 写回端 __html_component_key 分组 key”的错位。
  - 可见性开关（隐藏/显示）维护为“单一真源（layerKey）”：
    - 内部不再维护独立的“group hidden set”；组级显隐通过“该组下 layerKeys 是否全部隐藏”推导，并在切换组显隐时对组内 layerKeys 批量 set/unset。
    - 对外仍保留 `isGroupHidden/setGroupHidden/isLayerHidden` 等接口，但其语义均落在 layerKey 真源上，避免“选中按 layerKey、显隐按 groupKey”出现分叉与跨组误伤。
  - 导出排除开关（垃圾桶）：维护为“单一真源”，对外暴露 `isGroupExcluded/isLayerExcluded/setGroupExcluded/setLayersExcluded` 等接口；不影响预览显隐，但用于导出 GIL/GIA 前过滤 widgets。
  - 交互外观：组与条目支持“左侧眼睛图标”显隐；多项组提供显式展开/折叠按钮并在重渲染后保持展开状态稳定；单项按“普通条目”展示（不使用组块包裹）。
  - 支持按过滤文本筛选分组/条目（由上层 UI 输入框驱动），避免控件多时难以定位。
  - 分组标题可读性增强：在命名推断时会优先尝试提取组内“短文本”（常见按钮文字）作为组标题；仍会在其它视图保留稳定 key 作为兜底/对照。
  - 互操作：对外提供“按 groupKey + rect 映射 layerKeys”的查询与批量显隐接口（供导出控件列表实现“单控件显隐”与分组树同步）。
  - 支持 `button_anchor`：分组树会索引 `.flat-button-anchor` 并为其生成/写入 `data-layer-key`，用于“视觉为空的按钮锚点”在列表/画布间实现 1:1 精确定位。
  - 选中行为：从“画布点击选中”会让左侧列表自动滚动居中以便定位；从“列表点击选中”仅高亮，不再强制把条目滚到列表中间；并提供 `scrollSelectionIntoView()` 用于在 Tab 切换/重渲染后恢复“当前选中项”的可见滚动与高亮。
  - 交互约定：**选中不改变显隐状态**。眼睛图标是显隐的唯一入口；即便条目已隐藏，仍允许“选中并定位”，预览侧会用扁平层的 style 矩形回退绘制选中框。
- `run_queue.js`：Workbench 全局重操作队列（单通道 + coalesce + token + **session key**），用于串行化校验/扁平/导出/导入/导出GIL/GIA；并在“源码/文件选择变化”时跨操作取消旧任务，避免多条链路写同一批共享资源导致互相覆盖。
- `app_api.js`：主程序 API（`/api/ui_converter/*`）桥接；当独立打开或批处理 CLI 场景下 `/api` 返回 404 时，必须视为“未连接主程序”，不可因解析 JSON 失败中断 Workbench 初始化；支持一键生成 `.gil` 与“布局资产 `.gia`”。
  - 未连接主程序时的提示文案统一引导用户从主程序打开“UI预览”入口（命名一致，避免误导为“转换器”仍存在）。
  - bundle 真源：导入/写回链路只读取 `index.js` 维护的结构化 `bundleState`（对象，包含 `sourceHash`），textarea 仅展示/复制，避免“旧/空 bundle”反向读取导致误导入。
  - 导入/导出 GIL/GIA 会优先 `ensureBundleState(sourceHash)`，并在 token 失效时避免继续更新 UI 状态文本，减少“切换文件后旧导出结果刷新到面板”的错觉。
  - 导入保护：若当前导出的 bundle 中 `templates` 为空，则前端会直接提示“导入跳过”，避免请求打到后端后被 `bundle.templates 为空` 规则拒绝并刷堆栈。
  - 生成 `.gil` 成功后会播放提示音，并自动复制输出文件名到剪贴板（优先使用后端返回的 `output_file_name`）。
- 浏览器式工作流（browse mode）：默认模式为 `browse`，左侧以“UI源码文件列表”作为主入口；点选文件后自动执行“自动修正并校验 → 生成扁平化 → 导出 bundle JSON”，保留“源码/扁平化”预览切换（不强制切换预览变体）。
  - 预热策略：当“校验通过（errors=0）”后，会自动预生成扁平化缓存；切到扁平模式时若缓存缺失/过期，将自动触发一次扁平化生成并显示“生成中”占位提示。
  - 校验输出已升级为结构化 Diagnostics（Issue 模型）。当 `errors>0` 时 browse 流水线会停止（不再继续扁平化/导入），并可一键复制“AI 修复包”让大模型按报错修到通过。
  - 导入：browse 的自动导入默认关闭，需显式勾选“Browse 自动导入”才会在导出 bundle 后触发“导入到当前项目存档”；批处理“一键处理并导入”会强制启用自动导入。导入接口使用 `/api/ui_converter/import_ui_page`（需要当前选择是项目 HTML）。
  - 预览切换：browse 流水线不再强制切换“源码/扁平”；预览变体属于纯显示，由用户按钮决定。computedStyle 采样改在隐藏 compute iframe 进行，避免预览来回闪。

## 注意事项
- 初始化时必须为 `flatteningController` 提供 `setLastGeneratedUiControlGroupJsonText` / `setLastUiControlGroupSourceHtmlText` 回调；否则导出 bundle 会触发未处理的 Promise rejection，导致 UI/CLI 导出超时并输出为空。
- `app_api.js` 的 `/api/ui_converter/status` 请求在独立静态服务下会 404，属于正常现象；不得让该分支抛异常影响纯前端能力（导出 bundle / 校验 / 扁平化）。
- `browse` 模式下不再依赖“粘贴/按钮驱动”的手工流程；若需要传统流程，可通过 URL 参数 `?mode=editor` 强制回到旧交互。
- `/api/ui_converter/import_ui_page` 负责同步维护 `management.ui_pages`（一个 HTML 一个入口对象）并触发增量落盘；`/api/ui_converter/import_layout` 保留为旧接口（不保证维护 ui_pages）。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

