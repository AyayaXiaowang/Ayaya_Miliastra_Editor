# ugc_file_tools/contracts 目录说明

## 目录用途
- 存放 **`.gia` 导出** 与 **`.gil` 写回** 共同依赖的“口径对齐/契约层”（single source of truth）。
- 目标：把高风险、跨模块散落的约定集中到一个明确的入口，避免“只改了一半”。

## 当前状态
- `node_graph_type_mappings.py`：node_data/index.json 的 `TypeMappings` 文本约定解析与映射解析：
  - 字典 K/V 双泛型：`S<K:...,V:...>`
  - 单泛型 T=字典：`S<T:D<K,V>>`
  - 单泛型 T（基础类型与 `L<...>` 列表）：`S<T:...>`（可解析 concrete_id，并在 indexOfConcrete 唯一时抽取 in/out 的 index 值；并兼容列表容器 VarType(L<T>)→元素 VarType(T) 的回退，用于列表家族节点的 concrete 推断）
- `signal_meta_binding.py`：信号 meta binding 的跨域约定（回归用例对齐：参数 pin 的 `i2(kernel)` 必须与 `i1(shell)` 一致，即 `kernel_index = slot_index`；并在写回/导出侧显式写入 index2，禁止依赖“省略 field_2 的默认 0”）。
- `__init__.py`：对外 re-export 契约层的稳定入口（供导出/写回/测试使用）。

## 注意事项
- 该目录只放“跨域共享的规则/解析器/常量”，不要放 IO、pipeline 编排、或导出/写回的流程实现。
- 不使用 try/except：契约不满足直接抛错（fail-fast），让测试能第一时间暴露口径漂移。

