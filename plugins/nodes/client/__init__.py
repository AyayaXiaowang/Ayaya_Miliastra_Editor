"""客户端侧节点实现包：一节点一文件结构。

子目录按类别组织：事件节点/执行节点/查询节点/流程控制节点/运算节点。
"""


from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import inspect


def _export_nodes_from_directory(category_dir: Path) -> None:
	for file_path in category_dir.glob("*.py"):
		if file_path.name == "__init__.py":
			continue
		stem_safe = file_path.stem.replace(".", "_").replace("：", "_").replace(":", "_")
		module_name = f"{__name__}.__loaded__.{stem_safe}"
		spec = spec_from_file_location(module_name, str(file_path))
		if spec is None or spec.loader is None:
			raise RuntimeError(f"无法为节点实现创建模块说明：{file_path}")
		module = module_from_spec(spec)
		spec.loader.exec_module(module)  # type: ignore[attr-defined]
		for attr_name in dir(module):
			if attr_name.startswith("_"):
				continue
			attr_value = getattr(module, attr_name)
			if inspect.isfunction(attr_value):
				globals()[attr_name] = attr_value


_base_dir = Path(__file__).parent
for _sub in ["事件节点", "执行节点", "查询节点", "流程控制节点", "运算节点"]:
	_export_nodes_from_directory(_base_dir / _sub)

__all__ = [name for name, obj in globals().items() if inspect.isfunction(obj)]
