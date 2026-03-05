## 目录用途
- 生成“二维码方块墙”实体 `.gia`（Entity Asset），供 `ugc_file_tools` 的 `entity qrcode` 子命令使用。
- 该实现从历史工具集 `UGC-File-Generate-Utils` 收敛而来：提供可 import 的稳定入口，避免在 CLI 中做 `sys.path` 注入。

## 当前状态
- `api.py`：对外门面：文本 → blocks → GIACollection(proto bytes) → `.gia` 容器 bytes，并提供写盘函数。
- `qrcode_helper.py`：二维码像素生成与像素→方块（BlockModel）转换（第三方依赖延迟导入）。
- `block_assembler.py`：方块列表 → GIACollection protobuf bytes（仅本域使用最小 proto 定义）。
- `proto_gen/`：最小 protobuf 生成物（asset/entity/gia），仅供本域构造 message 使用。

## 注意事项
- 依赖（仅在调用时导入）：`qrcode`、`Pillow`、`protobuf`；缺失会直接抛错（fail-fast）。
- 不使用 try/except；输入不合法或依赖缺失时直接抛异常，调用方（CLI）负责退出码与提示。

