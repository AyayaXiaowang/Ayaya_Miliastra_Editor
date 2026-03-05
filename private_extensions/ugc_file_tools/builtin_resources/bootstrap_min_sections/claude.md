## 目录用途
- 存放用于 UI 写回链路的**极简 JSON 夹具**（从较大的 seed `.gil` 中提取的最小段），用于在 base `.gil` 缺失关键段时 bootstrap。
- 本目录内容应可公开、可版本化；禁止包含本机绝对路径与未授权业务数据。

## 当前状态
- `min_ui_node9.json`：最小 UI 段夹具（`root4/9` 的必要子结构）：只包含库根 record + 一个布局 root 原型 record + 精简 registry，供 `web_ui_import_prepare.py` 在 base 缺失 `4/9` 时注入。

## 注意事项
- 夹具应保持“最小且不污染输出产物”：避免携带多余布局/children GUID 列表，避免后续 GUID 分配撞号导致串页。
- 如需更新夹具，请确保 `meta` 字段仅包含可公开的相对路径/说明信息，不写入 `E:\...` 等绝对路径。

