"""
CombatPlayerEditorPanel 拆分模块：节点图上下文与写回。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.ui.panels.combat_player_panel_sections_types import _GraphBindingContext


class CombatPlayerPanelSectionsGraphsMixin:
    current_template_data: Optional[Dict[str, Any]]
    current_package: Optional[Any]
    player_editor: Any

    player_graphs_tab: Any
    role_graphs_tab: Any
    player_graphs_context: Optional[_GraphBindingContext]
    role_graphs_context: Optional[_GraphBindingContext]

    def _setup_player_graphs_context(self) -> None:
        """根据 metadata.player_editor.player 为玩家层级构建节点图上下文。"""
        if not self.current_template_data or self.player_graphs_tab is None:
            self.player_graphs_context = None
            if self.player_graphs_tab is not None:
                self.player_graphs_tab.clear()
            return

        player_section = self.player_editor.player
        graphs_value = player_section.get("graphs")
        if not isinstance(graphs_value, list):
            graphs_value = []
            player_section["graphs"] = graphs_value

        overrides_value = player_section.get("graph_variable_overrides")
        if not isinstance(overrides_value, dict):
            overrides_value = {}
            player_section["graph_variable_overrides"] = overrides_value

        self.player_graphs_context = _GraphBindingContext(
            default_graphs=graphs_value,
            graph_variable_overrides=overrides_value,
        )
        self.player_graphs_tab.set_context(
            self.player_graphs_context,
            "template",
            self.current_package,
            force=True,
        )

    def _setup_role_graphs_context(self) -> None:
        """根据 metadata.player_editor.role 为角色层级构建节点图上下文。"""
        if not self.current_template_data or self.role_graphs_tab is None:
            self.role_graphs_context = None
            if self.role_graphs_tab is not None:
                self.role_graphs_tab.clear()
            return

        role_section = self.player_editor.role
        graphs_value = role_section.get("graphs")
        if not isinstance(graphs_value, list):
            graphs_value = []
            role_section["graphs"] = graphs_value

        overrides_value = role_section.get("graph_variable_overrides")
        if not isinstance(overrides_value, dict):
            overrides_value = {}
            role_section["graph_variable_overrides"] = overrides_value

        self.role_graphs_context = _GraphBindingContext(
            default_graphs=graphs_value,
            graph_variable_overrides=overrides_value,
        )
        self.role_graphs_tab.set_context(
            self.role_graphs_context,
            "template",
            self.current_package,
            force=True,
        )

    def _on_player_graphs_tab_changed(self) -> None:
        """玩家层级节点图变更时写回 metadata.player_editor.player."""
        if not self.current_template_data or not self.player_graphs_context:
            return
        player_section = self.player_editor.player
        player_section["graphs"] = self.player_graphs_context.default_graphs
        if self.player_graphs_context.graph_variable_overrides:
            player_section["graph_variable_overrides"] = (
                self.player_graphs_context.graph_variable_overrides
            )
        else:
            player_section.pop("graph_variable_overrides", None)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_role_graphs_tab_changed(self) -> None:
        """角色层级节点图变更时写回 metadata.player_editor.role."""
        if not self.current_template_data or not self.role_graphs_context:
            return
        role_section = self.player_editor.role
        role_section["graphs"] = self.role_graphs_context.default_graphs
        if self.role_graphs_context.graph_variable_overrides:
            role_section["graph_variable_overrides"] = (
                self.role_graphs_context.graph_variable_overrides
            )
        else:
            role_section.pop("graph_variable_overrides", None)
        self._mark_template_modified()
        self.data_changed.emit()


