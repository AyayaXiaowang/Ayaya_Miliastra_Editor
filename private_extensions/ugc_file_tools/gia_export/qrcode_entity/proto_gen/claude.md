## 目录用途
- 本目录存放二维码实体 `.gia` 所需的最小 protobuf 生成物（asset/entity/gia）。
- 仅用于 `gia_export/qrcode_entity` 域构造 GIACollection message，并最终由 `ugc_file_tools.gia.container.wrap_gia_container` 封装为 `.gia` 文件。

## 当前状态
- `asset_pb2.py` / `entity_pb2.py` / `gia_pb2.py`：由 proto 编译生成的 Python 定义（做了相对导入适配以支持包内引用）。

## 注意事项
- 仅用于本域：不要把这些 pb2 当成全仓通用 schema 入口（主线 `.gia` 仍以 `protobuf-like` 编解码与 NodeEditorPack 画像为准）。
- 不使用 try/except；依赖缺失或 schema 不匹配时直接抛错（fail-fast）。

