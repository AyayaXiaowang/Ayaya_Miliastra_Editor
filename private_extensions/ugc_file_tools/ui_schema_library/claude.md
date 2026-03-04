## 目录用途
- UI record/blob 的“结构沉淀库”（schema library）：把 dump-json（数值键结构）中的 UI 记录（`4/9/502`）按结构签名归档，沉淀可复用的模板 record。
- 目标：当我们遇到某一类 UI 控件/容器的 record 结构时，**自动记录一次**；之后同类结构可直接复用（以“克隆模板 record + 仅改 GUID/RectTransform/名称”等最小策略写回），减少重复逆向。

## 当前状态
- `recorder.py`：从 dump-json 中提取 UI record list，计算“结构签名（shape signature）”，并将：
  - `data/index.json`：schema 索引（schema_id → 统计/示例/来源）
  - `data/records/<schema_id>.record.json`：某个 schema 的代表性模板 record（原样保存，含 `<binary_data>` blob 字符串）
  写入到本目录的 `data/` 下。
- `recorder.py` 也会额外计算更粗粒度的 `family_id`（把 protobuf-like message 的 blob/dict 两种形态统一为“msg”），并在 `data/index.json` 输出 `families` 汇总表，用于观察“同一控件概念的多种写法/变体”。
- `library.py`：schema library 的读写辅助：按 `label` 查询/加载模板 record、以及给某个 schema 设置 `label`（写回到 `data/index.json`）。
  - 约定标签：`progressbar` / `textbox` / `item_display`；`ui import-web-template` 会优先复用这些已标注模板，从而避免长期依赖外部“模板存档”。

## 注意事项
- 该目录的 `data/` 为工具自动生成的沉淀库：会随你解析过的存档增长；可复制到别的机器复用。
- 不使用 try/except：若 dump-json 结构异常会直接抛错，避免“记录到一半但数据不一致”。