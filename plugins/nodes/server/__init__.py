"""服务器侧节点实现包：一节点一文件结构。

子目录按类别组织：事件节点/执行节点/查询节点/流程控制节点/运算节点。
"""


from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import inspect


def _export_nodes_from_directory(category_dir: Path) -> None:
	for file_path in category_dir.glob("*.py"):
		if file_path.name == "__init__.py":
			continue
		# 以文件名派生一个安全的临时模块名，避免中文/标点问题
		stem_safe = file_path.stem.replace(".", "_").replace("：", "_").replace(":", "_")
		module_name = f"{__name__}.__loaded__.{stem_safe}"
		spec = spec_from_file_location(module_name, str(file_path))
		module = module_from_spec(spec)
		assert spec is not None and spec.loader is not None
		spec.loader.exec_module(module)  # type: ignore[attr-defined]
		# 导出模块内的节点函数（公开、顶层定义）
		for attr_name in dir(module):
			if attr_name.startswith("_"):
				continue
			attr_value = getattr(module, attr_name)
			if inspect.isfunction(attr_value):
				globals()[attr_name] = attr_value

# 按子目录分类导出所有节点函数
_base_dir = Path(__file__).parent
for _sub in ["事件节点", "执行节点", "查询节点", "流程控制节点", "运算节点"]:
	_export_nodes_from_directory(_base_dir / _sub)

# 可选：导出名列表（便于静态工具识别）
__all__ = [name for name, obj in globals().items() if inspect.isfunction(obj)]
