"""
private_extensions

本目录用于承载本机私有扩展（默认不入库）。
作为 Python package 的目的仅是为了让少量私有脚本可以使用稳定的绝对导入路径：
`private_extensions.<name>.*`
"""

"""
Private extensions (local tools / experiments).

This package wrapper exists so tools under this folder can be executed with `python -m ...`
from the repository root.
"""

