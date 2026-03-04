from __future__ import annotations

"""
兼容入口：`extract_gil_to_package.py`

历史上该脚本将全部解析/导出逻辑写在一个文件里，难以维护。
目前核心实现已模块化迁移到 `ugc_file_tools/gil_package_exporter/`，
本文件仅保留 CLI 入口与对外函数转发，避免破坏既有调用方式与命令行用法。
"""

from ugc_file_tools.gil_package_exporter.runner import export_gil_to_package, main

__all__ = ["export_gil_to_package", "main"]


if __name__ == "__main__":
    main()


