from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class ViewportRect:
    width: int
    height: int

    def center(self) -> Tuple[int, int]:
        return int(self.width // 2), int(self.height // 2)


class ViewState:
    """
    维护节点图画布到视口的映射关系与拖拽导致的平移。

    坐标空间：
    - 模拟坐标 S：来自节点图代码的逻辑坐标。
    - 画布坐标 C：游戏内节点图的真实平面坐标（与 S 线性同构，仅尺度差异）。
    - 视口坐标 V：窗口客户区内的像素坐标。

    映射模型（固定缩放、可变平移）：
    V_xy = client_origin_xy + (S_xy * scale + canvas_to_viewport_offset_xy)

    画布拖拽两种等价更新方式：
    - 用户拖拽向量 d_user（鼠标从 A→B）：内容相对视口移动为 -d_user。
    - 实测内容位移 d_content（由相位相关或特征匹配得到）：内容 A→B 的位移。

    更新规则：
    canvas_to_viewport_offset_xy -= d_content
    """

    def __init__(
        self,
        viewport_width: int,
        viewport_height: int,
        scale: float = 1.0,
    ) -> None:
        if viewport_width <= 0 or viewport_height <= 0:
            raise ValueError("viewport size must be positive")
        if scale <= 0.0:
            raise ValueError("scale must be positive")

        self._viewport = ViewportRect(viewport_width, viewport_height)
        self._scale: float = float(scale)
        self._offset_x: float = 0.0  # canvas_to_viewport_offset.x（像素）
        self._offset_y: float = 0.0  # canvas_to_viewport_offset.y（像素）

        # 若需要将客户区坐标换算为屏幕绝对坐标，可设置该值。
        self._client_origin_x: int = 0
        self._client_origin_y: int = 0

    # ---------- 视口与缩放 ----------
    def set_viewport_size(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("viewport size must be positive")
        self._viewport = ViewportRect(width, height)

    def viewport_center(self) -> Tuple[int, int]:
        return self._viewport.center()

    def set_scale(self, scale: float) -> None:
        if scale <= 0.0:
            raise ValueError("scale must be positive")
        self._scale = float(scale)

    def scale(self) -> float:
        return self._scale

    # ---------- 客户区原点（转屏幕绝对坐标时使用） ----------
    def set_client_origin(self, x: int, y: int) -> None:
        self._client_origin_x = int(x)
        self._client_origin_y = int(y)

    def client_origin(self) -> Tuple[int, int]:
        return self._client_origin_x, self._client_origin_y

    # ---------- 画布平移状态 ----------
    def canvas_offset(self) -> Tuple[float, float]:
        return self._offset_x, self._offset_y

    # 由相位相关得到的内容位移（内容 A→B），用于高精度纠偏
    def apply_content_motion(self, delta_x: float, delta_y: float) -> None:
        self._offset_x -= float(delta_x)
        self._offset_y -= float(delta_y)

    # 用户拖拽向量（鼠标从 A→B），内容相对视口移动为 -drag
    def apply_user_drag(self, drag_x: float, drag_y: float) -> None:
        self.apply_content_motion(-float(drag_x), -float(drag_y))

    # ---------- 坐标换算 ----------
    def to_viewport(self, sim_xy: Tuple[float, float]) -> Tuple[int, int]:
        sim_x, sim_y = float(sim_xy[0]), float(sim_xy[1])
        vx = sim_x * self._scale + self._offset_x
        vy = sim_y * self._scale + self._offset_y
        return int(round(vx)), int(round(vy))

    def to_client(self, sim_xy: Tuple[float, float]) -> Tuple[int, int]:
        vx, vy = self.to_viewport(sim_xy)
        return vx, vy

    def to_screen(self, sim_xy: Tuple[float, float]) -> Tuple[int, int]:
        cx, cy = self.client_origin()
        vx, vy = self.to_viewport(sim_xy)
        return cx + vx, cy + vy

    def viewport_to_sim(self, viewport_xy: Tuple[float, float]) -> Tuple[float, float]:
        vx, vy = float(viewport_xy[0]), float(viewport_xy[1])
        sx = (vx - self._offset_x) / self._scale
        sy = (vy - self._offset_y) / self._scale
        return sx, sy

    def client_to_sim(self, client_xy: Tuple[float, float]) -> Tuple[float, float]:
        return self.viewport_to_sim(client_xy)

    def screen_to_sim(self, screen_xy: Tuple[float, float]) -> Tuple[float, float]:
        cx, cy = self.client_origin()
        vx = float(screen_xy[0]) - float(cx)
        vy = float(screen_xy[1]) - float(cy)
        return self.viewport_to_sim((vx, vy))

    # ---------- 可见性辅助 ----------
    def is_viewport_inside(self, viewport_xy: Tuple[int, int]) -> bool:
        x, y = int(viewport_xy[0]), int(viewport_xy[1])
        return 0 <= x < self._viewport.width and 0 <= y < self._viewport.height

    def clamp_to_viewport(self, viewport_xy: Tuple[int, int]) -> Tuple[int, int]:
        x, y = int(viewport_xy[0]), int(viewport_xy[1])
        if x < 0:
            x = 0
        elif x >= self._viewport.width:
            x = self._viewport.width - 1
        if y < 0:
            y = 0
        elif y >= self._viewport.height:
            y = self._viewport.height - 1
        return x, y


