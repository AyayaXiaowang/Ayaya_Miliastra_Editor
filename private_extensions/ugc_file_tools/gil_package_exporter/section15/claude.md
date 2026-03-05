## 目录用途
- 承载 `section15_exporter.py` 的模块化实现：负责从 pyugc `root4/15/1`（section15 资源条目）导出 Graph_Generater 项目存档资源。
- 目标：按资源类型拆分（技能/道具/单位状态/护盾/关卡设置等），避免单文件过长；旧入口 `section15_exporter.py` 保持为薄 wrapper。

## 当前状态
- `exporter.py`：对外核心入口 `_export_section15_resources_from_pyugc_dump(...)`（编排、目录准备、索引落盘、引用图索引）。
- `context.py`：导出上下文（输出目录、namespace、引用图来源聚合）。
- `decoded_values.py`：decode_gil/通用解码结果的轻量提取工具（utf8/int/float/message 等）。
- `skills.py`：type_code=6（技能）导出与技能挂载图引用扫描。
- `items.py`：type_code=9/10（道具/装备类条目）导出。
- `unit_statuses.py`：type_code=1（单位状态）导出。
- `growth_curves.py`：type_code=5（成长曲线）导出。
- `equipment_slot_templates.py`：type_code=13（装备栏模板）导出。
- `shields.py`：type_code=22（护盾）导出与语义抽取。
- `unit_tags.py`：type_code=15（单位标签）导出。
- `equipment_data.py`：type_code=16（装备数据）导出与语义抽取。
- `level_settings.py`：type_code=26（关卡设置）导出（含出生点预设点派生）。
- `unclassified.py`：未识别 type_code 的原始条目落盘与索引。

## 注意事项
- 不使用 try/except；解析失败直接抛错，便于定位与保证数据一致性。
- 仅做“尽量语义化”：无法稳定映射的字段应落在 `metadata.ugc` 与 `原始解析/` 中，保持可追溯。


