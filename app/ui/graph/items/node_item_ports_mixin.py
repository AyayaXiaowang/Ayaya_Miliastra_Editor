"""NodeGraphicsItem：端口访问/类型解析相关逻辑。"""

from __future__ import annotations

from typing import Optional

from app.ui.graph.items.port_item import PortGraphicsItem


class NodePortsMixin:
    def iter_all_ports(self) -> list[PortGraphicsItem]:
        """返回该节点的所有端口（含流程端口）。"""
        ports: list[PortGraphicsItem] = []
        ports.extend(self._ports_in)
        ports.extend(self._ports_out)
        if self._flow_in:
            ports.append(self._flow_in)
        if self._flow_out:
            ports.append(self._flow_out)
        return [port for port in ports if port is not None]

    def get_port_by_name(self, port_name: str, *, is_input: Optional[bool] = None) -> Optional[PortGraphicsItem]:
        """根据端口名查找图形项，可限定输入/输出侧。"""
        if port_name == "流程入":
            return self._flow_in
        if port_name == "流程出":
            return self._flow_out
        if is_input is True:
            candidates = self._ports_in
        elif is_input is False:
            candidates = self._ports_out
        else:
            candidates = self.iter_all_ports()
        for port in candidates:
            if getattr(port, "name", None) == port_name:
                return port
        return None

    def _get_port_type(self, port_name: str, is_input: bool) -> str:
        """获取端口的类型

        Args:
            port_name: 端口名称
            is_input: 是否为输入端口

        Returns:
            端口类型字符串，如"整数"、"布尔值"、"向量3"等
        """
        # 统一走“有效类型解析”：与任务清单/端口类型气泡共用同一套规则来源。
        # 这样可以根除 `input_types/output_types`（常量字符串污染）导致的画布展示漂移。
        from app.ui.graph.items.port_type_resolver import resolve_effective_port_type_for_scene

        scene = self.scene()
        if scene is None:
            return "泛型"

        # 常量编辑控件只会出现在数据端口行，但这里仍显式传 is_flow=False 以保证口径一致。
        return resolve_effective_port_type_for_scene(
            scene,
            self.node,
            port_name,
            is_input=is_input,
            is_flow=False,
        )

