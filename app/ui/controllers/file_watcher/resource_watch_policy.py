from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.configs.resource_types import ResourceType
from engine.utils.path_utils import normalize_slash
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir


def _build_allowed_resource_top_level_dir_names_lower() -> frozenset[str]:
    """允许被资源库 watcher 递归监控/参与自动刷新的“资源顶层目录名”（小写）。

    约定：
    - ResourceType.value 使用 "/" 作为逻辑分隔符；资源库实际为多级目录；
    - 仅取第一级目录名作为“顶层目录”；
    - 额外纳入“复合节点库”（不属于 ResourceType，但影响节点库与复合节点管理）。
    """
    allowed: set[str] = set()
    for resource_type in ResourceType:
        dir_value = str(resource_type.value or "")
        top_level = dir_value.split("/")[0].strip()
        if top_level:
            allowed.add(normalize_slash(top_level).strip("/").lower())
    allowed.add("复合节点库".lower())
    return frozenset(allowed)


_ALLOWED_TOP_LEVEL_DIR_NAMES_LOWER: frozenset[str] = _build_allowed_resource_top_level_dir_names_lower()


@dataclass(frozen=True, slots=True)
class ResourceWatchPolicy:
    """资源库 watcher 的路径过滤策略（单一真源）。

    该策略同时用于：
    - FileWatcherManager：过滤 directoryChanged（哪些目录事件需要参与指纹复核/刷新）；
    - ResourceWatchRegistry：过滤 addPath（哪些目录需要建立 watcher）；
    - ResourceWatchDirScanThread：扫描时剪枝（只遍历资源顶层目录子树）。
    """

    resource_root_dir: Path
    packages_root_dir: Path
    shared_root_dir: Path
    active_package_id: str | None
    allowed_top_level_dir_names_lower: frozenset[str]

    resource_root_text: str
    packages_root_text: str
    shared_root_text: str

    @staticmethod
    def _normalize_path_text(path: Path) -> str:
        return normalize_slash(str(path.resolve())).rstrip("/").lower()

    @classmethod
    def create(cls, *, resource_root_dir: Path, active_package_id: str | None) -> "ResourceWatchPolicy":
        normalized_active_package_id = str(active_package_id or "").strip() or None
        packages_root_dir = get_packages_root_dir(resource_root_dir)
        shared_root_dir = get_shared_root_dir(resource_root_dir)
        return cls(
            resource_root_dir=resource_root_dir,
            packages_root_dir=packages_root_dir,
            shared_root_dir=shared_root_dir,
            active_package_id=normalized_active_package_id,
            allowed_top_level_dir_names_lower=_ALLOWED_TOP_LEVEL_DIR_NAMES_LOWER,
            resource_root_text=cls._normalize_path_text(resource_root_dir),
            packages_root_text=cls._normalize_path_text(packages_root_dir),
            shared_root_text=cls._normalize_path_text(shared_root_dir),
        )

    def is_allowed_top_level_dir_name(self, dir_name: str) -> bool:
        normalized_name = str(dir_name or "").strip().lower()
        if not normalized_name:
            return False
        return normalized_name in self.allowed_top_level_dir_names_lower

    def should_watch_directory(self, directory_path: Path) -> bool:
        """判断某个目录是否属于 watcher/自动刷新关注的“资源目录子树”。

        规则：
        - resource_root / packages_root / shared_root 本身允许；
        - shared/<top_level>/... 仅允许 top_level 在 allowed 集合中；
        - packages/<package_id>/<top_level>/... 仅允许 package_id==active_package_id 且 top_level 在 allowed 集合中；
        - packages/<package_id> 仅允许 package_id==active_package_id；
        - 其它路径一律不处理（避免非资源目录引发目录事件风暴）。
        """
        if directory_path is None:
            return False

        dir_text = self._normalize_path_text(directory_path)
        if dir_text in {self.resource_root_text, self.packages_root_text, self.shared_root_text}:
            return True

        shared_prefix = self.shared_root_text + "/"
        if dir_text.startswith(shared_prefix):
            rel = dir_text[len(shared_prefix) :]
            first = rel.split("/", 1)[0] if rel else ""
            return bool(first and first in self.allowed_top_level_dir_names_lower)

        packages_prefix = self.packages_root_text + "/"
        if dir_text.startswith(packages_prefix):
            rel = dir_text[len(packages_prefix) :]
            parts = [p for p in rel.split("/") if p]
            if not parts:
                return True
            # <package_id>
            if len(parts) == 1:
                if self.active_package_id is None:
                    return False
                return parts[0] == self.active_package_id
            # <package_id>/<top_level>
            package_id = parts[0]
            if self.active_package_id is None:
                return False
            if package_id != self.active_package_id:
                return False
            top_level = parts[1]
            return bool(top_level and top_level in self.allowed_top_level_dir_names_lower)

        return False


