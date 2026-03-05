## 目录用途
- 存放 Web Workbench 导出的 JSON → `.gil` 的 UI 写回实现（按模块拆分）：布局导入、控件导入（进度条/文本框/道具展示等）、组件打组、UIKey→GUID 映射与导入后校验。
- 本目录为“实现层”：对外稳定入口在 `ugc_file_tools/ui_patchers/web_ui/web_ui_import.py`（门面层）。

## 当前状态
- 主入口：`web_ui_import_main.py`（调度各阶段与 report 输出）。
- 控件类型导入：`web_ui_import_widget_*.py`（按控件种类落盘 record + RectTransform）。
- 控件模板来源（`web_ui_import_templates.py`）：
  - 优先从输入 `.gil` 现有 record 选择可克隆模板；
  - 次选复用 `ui_schema_library` 中已标注模板（`progressbar` / `textbox` / `item_display`）；
  - 若仍缺失，会自动使用内置样本 seed（`ugc_file_tools/builtin_resources/空的界面控件组/{进度条样式.gil, 文本框样式.gil, 道具展示.gil}`）提取模板并沉淀到 schema library，再继续写回。
  - TextBox 模板选择会跳过 `component_list[1]` 为空/非结构化的 record（避免克隆时扩散“空槽位 component1”导致网页文本/样式缺失）。
- 组件打组：`web_ui_import_component_groups.py` / `web_ui_import_component_groups_finalize.py` / `web_ui_import_grouping.py`。
- 固有控件初始显隐（HTML 真源）：支持从同级源码 HTML 读取 `data-ui-builtin-visibility`（JSON object，仅 5 个固有控件），并将对应固有控件 record 的初始隐藏标记落盘；缺失/不完整/包含未知键会 fail-fast 报错。
  - 允许“布局内不存在某些固有控件”的场景（例如空/极简 base `.gil` 或某些页面不含对应 HUD）：该次覆盖会在 report 中标记 `not_found`，但不抛错。
  - 该步骤允许由上层显式关闭（例如导出中心“项目存档→写回 `.gil`”链路默认关闭）；关闭时 report 会标记 skipped。
- 校验：`web_ui_import_verify.py`（写回后验证 UI 树/children/关键字段一致性）。
- 空/极简基底兼容：
  - 当 base `.gil` 缺失 UI 段（`root4/9=None`）时，会在 `web_ui_import_prepare.py` 注入最小 UI 段，再继续创建新布局并写回控件：
  - 优先夹具：`ugc_file_tools/builtin_resources/bootstrap_min_sections/min_ui_node9.json`
  - 兜底 seed：`ugc_file_tools/builtin_resources/empty_base_samples/empty_base_with_infra.gil`（用于提供完整 root4 段，并包含可写入的 4/5 段，支持补齐 10/11/12 等关键段）
  - 注入策略（最小且避免污染）：只保留“布局原型 + 库根”两条 root record，并将 layout registry 初始化为 `[默认布局(1073741825), 库根(1073741838)]`（库根固定在末尾）。
  - 关键护栏：bootstrap 时会**清空库根 record 的 children(varint)**，避免 seed/夹具携带的“预置 children GUID”与后续分配 GUID 撞号，导致库根意外引用布局内控件而出现“控件跑到别的页面/库里”的混乱。
  - 关键补齐：对“极空存档”（root4 仅有少数字段、缺失大量段）会从 seed `.gil` **补齐缺失的 root4 其它段**（不覆盖 base 已有字段，仅补缺失）。该补齐不仅在“缺失 4/9 需要 bootstrap UI 段”时触发，也会在 base 已有 4/9 但仍缺关键段（至少 10/11/12）时触发，避免编辑器侧出现“布局切换异常/页面叠加显示（看起来像每页都有上一页的文字）”。
  - 兼容键类型：prepare 阶段会将 payload_root/seed_root 的 numeric_message 顶层键归一化为 `str(key)`，避免不同 dump/桥接路径返回 int-key dict 导致“缺段误判/seed 缺段误报”。
- 新建布局 clone_children 过滤：克隆 base_layout 的“固有 children”时会跳过**纯组容器**record（`is_group_container_record_shape`），避免把上一页组件组容器连同旧 children GUID 一起带到新布局导致串页/parent mismatch。
- 写回前不变量（fail-fast）：`web_ui_import_main.py` 在写回前校验 `4/9/502` GUID 唯一、layout.children→child.parent(504) 一致；不做“写回后去重/修剪”。

## 注意事项
- 不使用 try/except；失败直接抛错（fail-fast）。
- 跨模块复用必须走公开 API（无下划线）：低层 UI record/children/varint stream 操作统一从 `ui_patchers/layout/layout_templates_parts/shared.py` 的公开函数导入，禁止 `from ... import _private_name`。
- 产物统一写入 `ugc_file_tools/out/`，避免覆盖原始 `.gil`。
- 本文件不记录修改历史，仅保持“目录用途 / 当前状态 / 注意事项”的实时描述。

