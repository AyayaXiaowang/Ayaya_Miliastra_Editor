# 节点图视图子模块
# 将大型 graph_view.py 按职责拆分为多个子模块

# 从父级 ui 模块导入 GraphView（避免同名冲突）
import sys
import importlib.util
from pathlib import Path

# 使用 importlib 加载同名的 .py 文件
_graph_view_file = Path(__file__).parent.parent / "graph_view.py"
_spec = importlib.util.spec_from_file_location("_graph_view_module", _graph_view_file)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
GraphView = _module.GraphView

# 导入子模块
from ui.graph.graph_view.animation.view_transform_animation import ViewTransformAnimation
from ui.graph.graph_view.overlays.minimap_widget import MiniMapWidget
from ui.graph.graph_view.overlays.ruler_overlay_painter import RulerOverlayPainter
from ui.graph.graph_view.popups.add_node_popup import AddNodePopup

__all__ = [
    "GraphView",
    "ViewTransformAnimation",
    "MiniMapWidget",
    "RulerOverlayPainter",
    "AddNodePopup",
]

