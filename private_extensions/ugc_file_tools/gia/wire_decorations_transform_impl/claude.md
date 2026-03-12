# wire_decorations_transform_impl 目录说明

## 目录用途
- 存放 `ugc_file_tools.gia.wire_decorations_transform` 的内部实现拆分（wire-level 解析/补丁、TRS 数学、GraphUnit/Accessory 结构操作、merge/center 算法编排）。
- 该目录不作为对外稳定 API，外部应只通过 `ugc_file_tools.gia.wire_decorations_transform.merge_and_center_decorations_gia_wire` 访问。

## 当前状态
- `__init__.py`：内部实现包标记（不对外导出稳定 API）。
- `api.py`：对内聚合入口（实现 `merge_and_center_decorations_gia_wire`，供门面层转发）。
- `constants.py`：字段号/线类型/阈值等常量（避免散落的魔法数字）。
- `wire_utils.py`：wire chunk 解析、varint 读写、message 探测等通用能力。
- `vector3_codec.py`：Vector3(fixed32) 的 wire-level 编解码。
- `math_trs.py`：TRS 与矩阵计算（Euler/Mat3/Mat4/分解）。
- `transform_codec.py`：Transform message 的提取与最小补丁（含 DFS 探测）。
- `graph_unit_codec.py`：GraphUnit 的 id/name/TRS/relatedIds 等提取与最小补丁。
- `accessory_codec.py`：Accessory payload 的 parent bind/transform 提取与最小补丁。
- `center_utils.py`：居中辅助（axes 解析与 bbox/mean 中心点计算）。
- `root_codec.py`：Root(filePath/field_1/field_2) 的解析与保真重建。
- `policies_move_decorations.py` / `policies_keep_world.py`：两种 center/merge 策略实现（分别负责 move_decorations 与 keep_world）。

## 注意事项
- fail-fast：结构不符合预期直接抛错，不吞异常。
- 尽量保持 wire-level “最小可解释差异”：只补丁必要字段，避免语义重编码导致真源不可见。

