# node_data 目录说明

## 目录用途
- 存放项目内置的“节点静态数据索引”（node/type/enum 等），用于 `.gia/.gil` 节点图解析时补全：
  - `node_type_id → node_name / inputs / outputs`
  - `type_id → Expression(Int/Bol/...)` 等

## 当前状态
- `index.json`：节点/类型/枚举汇总数据（JSON），供 `ugc_file_tools/node_data_index.py` 读取。

## 注意事项
- 该目录为“数据快照”，用于运行时解析补全；数据更新应以“整文件替换”方式进行，保持结构稳定。
- 数据来源为第三方节点图工具的 `utils/node_data/index.json`（已拷贝到此处；运行时不依赖第三方目录路径）。


