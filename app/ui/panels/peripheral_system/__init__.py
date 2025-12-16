"""外围系统面板拆分子包。

该子包提供三个 Tab 组件，供 `ui.panels.peripheral_system_panel.PeripheralSystemManagementPanel`
进行组合与上下文切换。
"""

from app.ui.panels.peripheral_system.achievement_tab import PeripheralAchievementTab
from app.ui.panels.peripheral_system.leaderboard_tab import PeripheralLeaderboardTab
from app.ui.panels.peripheral_system.rank_tab import PeripheralRankTab

__all__ = [
    "PeripheralAchievementTab",
    "PeripheralLeaderboardTab",
    "PeripheralRankTab",
]


