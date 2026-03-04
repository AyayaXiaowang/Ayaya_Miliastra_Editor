# ugc_file_tools/gia 目录说明

## 目录用途
- `.gia` 领域的底层库与语义/编解码工具：容器封装、protobuf-like 解码、VarBase 语义、以及装饰物/资产包等结构的共享处理逻辑。
- 该目录代码应尽量保持“可复用、少 IO、fail-fast”，供 `gia_export/`（门面层）与 `commands/`（入口层）共同复用。

## 当前状态
- `container.py`：`.gia` 容器封装/解包与头尾校验。
- `varbase_semantics.py`：从 decoded field map 抽取 VarBase 的 Python 语义值（字段号口径对齐真源 NodeEditorPack `gia.proto`）；并能从 length-delimited 的 `raw_hex` 反解嵌套 message，且区分“未设置的字符串 empty bytes”(返回 None) 与“显式空字符串”(返回 "")，避免把连线输入误读为被清空。
- 装饰物/实体/资产包：
  - `decorations_bundle.py`：基于 base `.gia` 结构模板做语义重编码生成装饰物 bundle。
  - `asset_bundle_decorations.py`：资产包结构（Root.field_1 为 GraphUnit 列表）下的装饰物生成。
  - `decorations_variants.py`：批量导出变体用于二分定位真源导入约束。
  - `wire_decorations_bundle.py`：wire-level 保真克隆/生成装饰物 bundle（最小补丁思路）。
  - `wire_decorations_transform.py`：wire-level 装饰物变换（居中/多 parent 合并为同一空物体；`keep_world` 按完整 TRS(position/rotation/scale) 计算与补偿，保证旋转/缩放存在时装饰物世界变换不变；尽量保持真源可见性）。
  - `entity_decorations_writer.py`：wire-level 生成“带装饰物的实体类” `.gia`（含 relatedIds + packed accessories id 列表补丁等）。
- `wire_preview_pack_processor.py`：wire-level 处理“打包 .gia”内预览实体（居中/同关合并/可选实体化）。
  - 对 Root.field_2 的 instances(GraphUnit class=1,type=14,which=28) 使用 **instance 专用的 Transform 路径** 提取/补丁 position，避免 payload 内其它 Vector3-like message 被 DFS 误读/误写导致真源不可见。
- `wire_templates_instances_convert.py`：wire-level “元件模板+实体摆放(实例)” bundle.gia 转换（元件↔实体）。
- `wire_templates_instances_slice_export.py`：wire-level “元件模板+实体摆放(实例)” bundle.gia 按 `template_root_id_int` 切片导出（仅保留目标模板 GraphUnit 与引用它的 instances；用于保真导出，避免语义重建导致装饰物不可见）。
- `wire_patch.py`：通用 wire-level 最小补丁（例如 Root.filePath）。

## 注意事项
- 不使用 try/except；结构不符合预期直接抛错（fail-fast）。
- wire-level 修改尽量保持“最小可解释差异”：只改必要字段，避免重编码导致真源不可见。

