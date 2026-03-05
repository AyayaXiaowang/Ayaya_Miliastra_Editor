## 目录用途
`演示项目/`：对外/回归用的最小“演示包”资源集，用于 UI 预览、资源索引与基础导入链路验证。

## 当前状态
- 当前包含：
  - `复合节点库/`：少量复合节点示例（用于节点图/复合节点链路回归）。
  - `节点图/`：最小可校验的服务器节点图样例（用于 Packages 页“预览其它存档仍可看到节点图”回归）。

## 注意事项
- 本包是演示/回归夹具，不承载业务逻辑；修改后建议跑：
  - `python -X utf8 -m app.cli.graph_tools validate-project --package-id 演示项目`
  - `python -X utf8 -m pytest tests/ui/library/test_package_library_widget_preview.py`

