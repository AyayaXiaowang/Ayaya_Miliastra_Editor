"""节点图变量管理对话框 - 管理节点图级别的局部变量"""

from PyQt6 import QtCore

from app.ui.foundation.info_snippets import GRAPH_VARIABLE_INFO
from engine.graph.models.graph_model import GraphModel
from engine.configs.resource_types import ResourceType
from engine.configs.specialized.struct_definitions_data import list_struct_ids
from app.ui.widgets.graph_variable_table_widget import GraphVariableTableWidget
from app.ui.dialogs.management_dialog_base import ManagementDialogBase


class GraphVariableDialog(ManagementDialogBase):
    """节点图变量管理对话框"""

    # 信号：变量配置已更新
    variables_updated = QtCore.pyqtSignal()

    def __init__(self, graph_model: GraphModel, parent=None, resource_manager=None):
        self.graph_model = graph_model
        self._resource_manager = resource_manager
        if self._resource_manager is None and parent is not None:
            candidate = getattr(parent, "resource_manager", None)
            if candidate is not None:
                self._resource_manager = candidate
        super().__init__(
            title_text=f"📊 节点图变量 - {graph_model.graph_name}",
            info_text=GRAPH_VARIABLE_INFO,
            width=700,
            height=500,
            parent=parent,
        )

        self.variable_widget = GraphVariableTableWidget(self)
        struct_ids = list_struct_ids(self._resource_manager)
        self.variable_widget.set_struct_id_options(struct_ids)
        self.variable_widget.set_graph_model(self.graph_model)
        self.variable_widget.variables_changed.connect(self.variables_updated.emit)
        self.add_body_widget(self.variable_widget)