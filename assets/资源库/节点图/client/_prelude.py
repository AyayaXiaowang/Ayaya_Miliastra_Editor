from __future__ import annotations

import sys
from pathlib import Path

# 注入项目根、app/ 与 assets/ 到 sys.path，保证 runtime、plugins 与资源库可导入
PROJECT_ROOT = Path(__file__).resolve().parents[4]
APP_DIR = PROJECT_ROOT / "app"
ASSETS_ROOT = PROJECT_ROOT / "assets"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))
if str(ASSETS_ROOT) not in sys.path:
    sys.path.insert(2, str(ASSETS_ROOT))

# 透出 GameRuntime、所有 client 节点函数与占位类型
from runtime.engine.graph_prelude_client import *  # noqa: F401,F403
from runtime.engine.graph_prelude_client import GameRuntime  # noqa: F401



