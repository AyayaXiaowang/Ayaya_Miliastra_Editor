# preview_merge 目录说明

## 目录用途
- 面向“选关预览/关卡展示元件”的合并工具链：把同一关卡的多元件（模板/实体摆放）合并成一个新母体，并按 `keep_world` 口径保持装饰物在预览空间中的相对位置不变。
- 典型输入来源：项目存档 `测试项目` 的选关页控制图（GraphVariableConfig 默认值）+ 元件库模板 JSON。

## 当前状态
- 提供纯逻辑实现（不依赖 UI）：从 Graph Code 抽取“关卡→元件ID/偏移/旋转”表，合并两元件关卡（第 4/5/8 关）生成新模板，并同步改写控制图的 GraphVariables（将双元件改为单元件）。
- 合并时会确保 decorations 的 `def_id` 不发生冲突：必要时会为冲突的 `instanceId/source_gia.unit_id_int` 分配新的稳定 ID。
- 支持实例侧 keep_world 合并：可将多个 `实体摆放/*.json`（实例）引用模板的 decorations 合并为一个新模板，并生成一个新实例引用该模板（不删除旧资源）。
- 执行图补丁的 guard 识别支持两种写法：`if 预览元件ID2 == 0` 或 `if 预览元件ID2 == 空元件ID`（其中 `空元件ID=0`），避免因实现细节差异误判为“未补丁”。
- shared helpers：`level_select_preview_components_merger.py` 暴露了若干跨模块复用的公共 helper（无下划线命名），用于满足 ugc_file_tools import-policy（禁止跨模块 from-import 私有函数）。

## 注意事项
- fail-fast：不吞异常；输入 GraphVariables/模板 decorations 结构不符合预期直接抛错。
- 该目录只维护“预览元件合并”相关能力，不承载通用 `.gia` wire-level 变换逻辑（后者在 `ugc_file_tools/gia/`）。

