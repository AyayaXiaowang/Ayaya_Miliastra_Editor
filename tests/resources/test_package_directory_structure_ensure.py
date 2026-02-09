from __future__ import annotations

from pathlib import Path

from engine.resources.package_index_manager import PackageIndexManager


class _DummyResourceManager:
    """PackageIndexManager 初始化所需的最小 stub。

    本用例仅覆盖“目录骨架补齐”能力，不应触发 rebuild_index 等重逻辑。
    """

    def rebuild_index(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("test should not call ResourceManager.rebuild_index()")


def _make_dirs(root: Path, *parts: str) -> Path:
    p = root
    for part in parts:
        p = p / part
    p.mkdir(parents=True, exist_ok=True)
    return p


def test_ensure_package_directory_structure_mirrors_template_dirs(tmp_path: Path) -> None:
    workspace_root = tmp_path
    packages_root = workspace_root / "assets" / "资源库" / "项目存档"

    template_root = packages_root / "示例项目模板"
    _make_dirs(template_root, "节点图", "server", "实体节点图", "模板示例")
    _make_dirs(template_root, "节点图", "client", "技能节点图", "模板示例")
    # 这些目录应被忽略，不应镜像到目标包中
    _make_dirs(template_root, "节点图", "__pycache__")
    _make_dirs(template_root, "文档", "共享文档")

    target_package_id = "导入项目"
    target_root = packages_root / target_package_id
    target_root.mkdir(parents=True, exist_ok=True)

    manager = PackageIndexManager(workspace_path=workspace_root, resource_manager=_DummyResourceManager())
    manager.ensure_package_directory_structure(target_package_id)

    assert (target_root / "节点图" / "server" / "实体节点图" / "模板示例").is_dir()
    assert (target_root / "节点图" / "client" / "技能节点图" / "模板示例").is_dir()
    assert not (target_root / "节点图" / "__pycache__").exists()
    assert not (target_root / "文档" / "共享文档").exists()


def test_ensure_package_directory_structure_falls_back_without_template(tmp_path: Path) -> None:
    workspace_root = tmp_path
    packages_root = workspace_root / "assets" / "资源库" / "项目存档"

    target_package_id = "导入项目"
    target_root = packages_root / target_package_id
    target_root.mkdir(parents=True, exist_ok=True)

    manager = PackageIndexManager(workspace_path=workspace_root, resource_manager=_DummyResourceManager())
    manager.ensure_package_directory_structure(target_package_id)

    # fallback 至少补齐：节点图分类目录 + 常用资源根
    assert (target_root / "节点图" / "server" / "实体节点图").is_dir()
    assert (target_root / "节点图" / "client" / "技能节点图").is_dir()
    assert (target_root / "复合节点库").is_dir()
    assert (target_root / "元件库").is_dir()
    assert (target_root / "实体摆放").is_dir()
    assert (target_root / "管理配置" / "计时器").is_dir()


