"""示例脚本：创建带“信号全参数类型”用例的示例存档包。

职责：
- 使用 ResourceManager / PackageIndexManager 创建一个示例存档包（不手改 JSON）；
- 将新建存档包的关卡实体挂载示例节点图
  `server_signal_all_types_example_01`（模板示例_信号全类型_发送与监听）；
- 在存档索引中声明当前包引用 `signal_all_supported_types_example` 信号。

用法（在项目根目录执行）：
    python -X utf8 tools/create_example_signal_all_types_package.py
"""

from __future__ import annotations

import sys
import io
from pathlib import Path

# 统一工作空间根目录（脚本位于 tools/ 下）
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# 添加项目根路径到 sys.path（保持 tools 目录优先）
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(1, str(WORKSPACE_ROOT))

from engine.resources import ResourceManager, PackageIndexManager, PackageView


def main() -> None:
    workspace_path = WORKSPACE_ROOT

    resource_manager = ResourceManager(workspace_path)
    package_index_manager = PackageIndexManager(workspace_path, resource_manager)

    package_name = "示例_信号全参数类型"
    package_description = "演示 signal_all_supported_types_example 信号的发送与监听（覆盖全部参数类型）的示例存档包。"

    # 若已存在同名示例包，则复用；否则创建新的示例存档包
    existing_package_id: str | None = None
    for info in package_index_manager.list_packages():
        if not isinstance(info, dict):
            continue
        if info.get("name") == package_name:
            candidate_id = info.get("package_id")
            if isinstance(candidate_id, str) and candidate_id:
                existing_package_id = candidate_id
                break

    if existing_package_id is not None:
        package_id = existing_package_id
        print(f"[INFO] 发现已存在的示例存档包，复用: {package_name} ({package_id})")
    else:
        package_id = package_index_manager.create_package(package_name, package_description)
        print(f"[INFO] 已创建示例存档包: {package_name} ({package_id})")

    package_index = package_index_manager.load_package_index(package_id)
    if package_index is None:
        raise RuntimeError(f"无法加载刚创建的存档索引: {package_id}")

    package_view = PackageView(package_index, resource_manager)

    # 挂载示例节点图到当前存档的关卡实体
    graph_id = "server_signal_all_types_example_01"
    level_entity = package_view.level_entity
    if level_entity is None:
        raise RuntimeError("新建示例存档未找到关卡实体实例。")

    if graph_id not in level_entity.additional_graphs:
        level_entity.additional_graphs.append(graph_id)
        package_view.update_level_entity(level_entity)
        print(f"[INFO] 已在关卡实体上挂载节点图: {graph_id}")
    else:
        print(f"[INFO] 关卡实体已挂载节点图: {graph_id}")

    # 在存档索引中登记本包引用的节点图 ID（resources.graphs）与信号 ID
    graph_added = False
    if graph_id not in package_index.resources.graphs:
        package_index.add_graph(graph_id)
        graph_added = True
        print(f"[INFO] 已在存档索引 resources.graphs 中登记节点图引用: {graph_id}")
    else:
        print(f"[INFO] 存档索引 resources.graphs 已包含节点图引用: {graph_id}")

    signal_id = "signal_all_supported_types_example"
    signal_added = False
    if signal_id not in package_index.signals:
        package_index.signals[signal_id] = {}
        signal_added = True
        print(f"[INFO] 已在存档索引中登记信号引用: {signal_id}")
    else:
        print(f"[INFO] 存档索引已包含信号引用: {signal_id}")

    if graph_added or signal_added:
        package_index_manager.save_package_index(package_index)

    print(f"[OK] 示例存档包创建与挂载完成，package_id = {package_id}")


if __name__ == "__main__":
    main()


