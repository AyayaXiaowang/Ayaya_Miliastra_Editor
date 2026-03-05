## 目录用途
- 预留目录：用于未来可能落地的 **纯 Python** `.gil/.gia` 解析/导出/回写实现（按 `dtype.json` 驱动），目标与 C++ 工程 `Genshin-Impact-UGC-File-Converter` 能力对齐。

## 当前状态
- 当前仅保留说明文件，本目录暂无可执行脚本/模块（避免误用/误导）。
- 现有能力请优先看：
  - `ugc_file_tools/py_ugc_converter/`：dtype 驱动的 Python 解码器（只读）。
  - `ugc_file_tools/gil_dump_codec/`：基于 DLL dump-json 的 protobuf-like 编码/封装（用于写回链路）。
  - `ugc_file_tools/decode_gil.py` / `ugc_file_tools/gil_to_readable_json.py`：分析/可读 dump 工具。

## 注意事项
- 不使用 `try/except`；错误直接抛出，靠清晰的前置条件与结构校验定位问题。
- 若未来在此目录落地实现：必须保证与 dtype 语义、字段含义、JSON 结构口径一致，并避免巨型单文件。
