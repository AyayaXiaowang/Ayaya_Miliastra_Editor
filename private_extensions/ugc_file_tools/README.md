# ugc_file_tools

一组与原神/千星 UGC 存档相关的工具集合，覆盖：
- `.gil` / `.gia` 的解析、导出、分析
- Graph_Generater 项目存档（“项目存档/包”）的提取与再解析
- 节点图（Graph）IR/Model/Code 的生成与校验
- 部分能力的 `.gil` 写回（结构体定义、节点图局部改写、UI 相关增量修改）

> 推荐入口（从仓库根目录，最稳定）：`python -X utf8 private_extensions/run_ugc_file_tools.py --help`。  
> 兼容入口：`python -X utf8 -m ugc_file_tools --help`（等价于 `python ugc_file_tools/ugc_unified.py --help`，但依赖 `ugc_file_tools` 可被 import）。  
> 单工具清单与风险说明见 `tools/工具索引.md`。  
> 运行单工具：`python -X utf8 private_extensions/run_ugc_file_tools.py tool <工具名> --help`。

## 术语与核心数据流

### 输入/输出对象
- **`.gil`**：UGC 主存档容器（含 UI、节点图、结构体等多段 payload）
- **`.gia`**：节点图文件（常用于节点图单独交换/导出）
- **项目存档（package root）**：Graph_Generater 可识别的目录结构（`extract_gil_to_package.py` 导出产物）

### 常用流水线（从左到右）
- **解析导出（全包）**：`.gil` → 项目存档目录 → `parse_package.py`/`parse_gil_to_model.py` 输出结构化摘要 JSON
- **节点图分析**：项目存档 → `export_graph_ir_from_package.py` 导出 Graph IR（JSON/Markdown）
- **反编译生成 Graph Code**：项目存档 → `generate_graph_code_from_package.py` 生成 Python Graph Code → `graph_code_validation.py` 校验
- **`.gia` 节点图解析**：`.gia` → `parse_gia_to_graph_ir.py` → Graph IR（JSON）
- **写回（结构体定义）**：项目存档（结构体数据源）→ `ugc_unified.py project import*` → 新 `.gil`

## 真源对齐与同步策略（重要）

### 角色定位：真源 vs 模拟器
- **真源（唯一事实来源）**：官方编辑器/运行期能导入并正确工作的 `.gil/.gia` 与其行为表现。
  - `ugc_file_tools` 的解析/写回必须以此为准：样本能出现的结构都要能读出来；写回产物要以“可导入/可编辑/不丢数据”为验收标准。
- **模拟器（高质量规格实现）**：`Graph_Generater`。
  - `Graph_Generater` 把大量规则显式化（类型体系、校验规则、Graph Code → GraphModel 的建模），能显著减少从零反推的成本。
  - 但它不是永远正确：若与真源冲突，优先修正模拟器或在写回侧记录差异（见下文）。

### 同步原则：用模拟器加速，但永远不“覆盖真源”
- **默认策略（保守生成）**：写回时尽量复用 `Graph_Generater` 的“单一真源”规则（尤其是类型体系），降低生成形态的自由度，从而提高导入成功率与可维护性。
- **差异策略（真源驱动修正）**：当真源样本表现与模拟器规则不一致时：
  - **优先**：补齐/修正 `Graph_Generater` 的规则或数据模型（让模拟器更像真源，长期收益最大）。
  - **备选**：在 `ugc_file_tools` 侧显式记录“已知差异补丁层”（避免到处临时 if，保证差异可追踪）。

### 本仓库中与“节点图变量写回”相关的关键约定
- **节点图变量定义表位置**：`.gil` 的节点图 entry 内 `GraphEntry['6']`（变量定义表，用于编辑器解析【获取/设置节点图变量】的端口具体类型）。
- **图变量支持类型口径**：以 `Graph_Generater/engine/type_registry.py` 的 `VARIABLE_TYPES` 与别名字典解析 `parse_typed_dict_alias` 为准。
  - 结论：`枚举/局部变量/泛型家族` 不作为“节点图变量类型”写回（它们属于端口/运行期机制的范畴）。
- **结构体类图变量绑定**：
  - `Graph_Generater` 的 `GraphVariableConfig` 已扩展支持 `struct_name`（结构体/结构体列表图变量用于绑定既有结构体定义）。
  - 常见默认值为 `None`（在运行期通过【拼装结构体】赋值）；当提供**非空**结构体默认值时，必须同时提供有效 `struct_name` 并能在结构体定义库中找到对应定义（Graph_Generater 侧已加入校验规则）。
- **字典类型约定**：
  - Graph_Generater 支持别名字典类型：`键类型-值类型字典` / `键类型_值类型字典`；
  - 写回时必须能解析出 key/value 的具体类型（禁止用泛型绕过）。

### 产物与回归（建议工作流）
- **样本/真源基准**：建议将关键 `.gil` 真源样本放在 `ugc_file_tools/save/`（本地样本库，默认不对外），并将对应的 DLL dump-json/自研解码摘要放在 `ugc_file_tools/out/` 便于回归对比。
- **内置 seed（默认依赖）**：运行必需/默认依赖的最小 seed 版本化收口在 `ugc_file_tools/builtin_resources/`（对外仓库应包含）。
- **合约测试思路**：
  - `Graph Code/GraphModel(JSON)` → 写回 `.gil` →（可选）`dump-json` 或自研扫描器 → 校验关键不变量（GraphEntry['6'] 类型集合、keyType/valueType、结构体绑定可解析等）。
  - 推荐工具：
    - `check_graph_variable_writeback_contract`：对写回产物做合约校验（失败直接抛错，报告写入 `out/`）。
    - `report_graph_variable_truth_diff`：扫描真源样本并与 Graph_Generater `VARIABLE_TYPES` 做差异对比（报告写入 `out/`）。
  - 当新增类型/新结构出现时，先补样本，再补规则/写回映射，避免“拍脑袋支持”。
- **同步路线图（下一步做什么）**：见 `ugc_file_tools/解析器与Graph_Generater同步路线图.md`。

## 目录地图（按职责分区）

### 入口（统一入口 + 单工具命令）
- `ugc_unified.py`：统一入口（UI / project / entity / tool / gui）。
- `commands/`：单工具入口模块（与 `tool_registry.py` 的工具名一一对应）。
  - 统一运行方式：`python -X utf8 -m ugc_file_tools tool <name> --help`
  - 示例模块：`commands/extract_gil_to_package.py`、`commands/parse_package.py`、`commands/graph_model_json_to_gil_node_graph.py`。
- `apps/gui_app.py`：Tkinter 简易 GUI（`python -X utf8 -m ugc_file_tools gui`）。

> 经验：如果你只是“想跑起来”，优先 `python -X utf8 -m ugc_file_tools --help`；其余单工具用于针对某一条链路的分析/生成/写回。

### 可复用模块（建议当库用）
- `gil_package_exporter/`：项目存档导出核心实现（扫描、解码、导出、报告、parse_status）
- `package_parser/`：项目存档加载与归一化解析（node graphs 等）
- `graph_codegen/`：Graph Code 生成器（可复用的代码拼装/可执行模板生成）
- `gil_dump_codec/`：对 dump-json（数值键结构）的重新编码/封装写回能力

### 配置/数据沉淀
- `graph_ir/`：节点图语义映射等可维护配置（例如 `node_type_semantic_map.json`）
- `node_data/`：节点类型画像索引（`index.json`），供 IR 导出补全 type_id→名字/端口提示

### UI 相关
- `ui_parsers/` / `ui_patchers/` / `ui_readable_dump.py`：UI JSON 可读化与补丁逻辑

### 外部子项目（工具依赖/配套）
- `UGC-File-Generate-Utils`：历史实体生成/解析工具集（已移除；二维码实体 `.gia` 生成已收敛到 `gia_export/qrcode_entity/`，统一 CLI 不再依赖其 `sys.path` 注入）
- `builtin_resources/dtype/dtype.json`：默认 dtype（字段/类型描述），供 `.gil/.gia` 解析与导出链路读取；其上游来源为 `Genshin-Impact-UGC-File-Converter`（许可证副本见 `LICENSES/`）。
- `py_ugc_converter/` / `py_gil_converter/`：Python 转换/解码相关

### 工作区与产物
- `out/`：生成产物默认输出目录（包导出、IR、codegen 中间文件等）
- `builtin_resources/`：运行必需/默认依赖的最小 seed（对外仓库应包含）
- `save/`：样本 `.gil`/说明文档等（输入用；目录可为空；建议保持只读思维，操作前先备份）
- `parse_status/`：解析状态文档的统一落点（按包聚合）

## 运行与依赖提示
- 大多数入口脚本都支持 `--help`；统一入口参考：
  - `python ugc_file_tools/ugc_unified.py --help`
- `UGC-File-Generate-Utils` 目录名包含 `-`，不适合作为标准 Python package 导入；当前主线工具链不再依赖其注入逻辑（历史目录已移除）。
- UI 相关能力已支持纯 Python dump/写回闭环（不要求额外 DLL）。


