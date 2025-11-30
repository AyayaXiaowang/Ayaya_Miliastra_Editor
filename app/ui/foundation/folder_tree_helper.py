"""通用文件夹树构建与展开状态工具。"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, Optional, Sequence, Set

from PyQt6 import QtWidgets, QtCore

FolderPath = str
ItemKeyGetter = Callable[[QtWidgets.QTreeWidgetItem], Optional[str]]
LabelFormatter = Callable[[str], str]
DataFactory = Callable[[str], object | None]


class FolderTreeBuilder:
    """帮助在 QTreeWidget 中快速构建多层文件夹节点."""

    def __init__(
        self,
        *,
        label_formatter: LabelFormatter | None = None,
        data_factory: DataFactory | None = None,
    ) -> None:
        self._label_formatter = label_formatter or (lambda name: f"📁 {name}")
        self._data_factory = data_factory

    def build(
        self,
        parent_item: QtWidgets.QTreeWidgetItem,
        folder_paths: Sequence[FolderPath] | Iterable[FolderPath],
    ) -> Dict[FolderPath, QtWidgets.QTreeWidgetItem]:
        """在 parent_item 下创建所有 folder_paths 节点并返回映射."""

        mapping: Dict[FolderPath, QtWidgets.QTreeWidgetItem] = {"": parent_item}
        for folder_path in sorted(folder_paths):
            if not folder_path:
                continue
            parts = folder_path.split("/")
            current_parent = parent_item
            current_path = ""
            for part in parts:
                current_path = f"{current_path}/{part}" if current_path else part
                existing_item = mapping.get(current_path)
                if existing_item is None:
                    new_item = QtWidgets.QTreeWidgetItem(current_parent)
                    new_item.setText(0, self._label_formatter(part))
                    if self._data_factory is not None:
                        new_item.setData(
                            0,
                            QtCore.Qt.ItemDataRole.UserRole,
                            self._data_factory(current_path),
                        )
                    mapping[current_path] = new_item
                    current_parent = new_item
                else:
                    current_parent = existing_item
        return mapping


def capture_expanded_paths(
    tree_widget: QtWidgets.QTreeWidget,
    key_getter: ItemKeyGetter,
) -> Set[str]:
    """记录当前树上处于展开状态的节点 key 集."""

    expanded: Set[str] = set()
    root = tree_widget.invisibleRootItem()
    if not root:
        return expanded

    stack = [root]
    while stack:
        item = stack.pop()
        for index in range(item.childCount()):
            child = item.child(index)
            stack.append(child)
            if not child.isExpanded():
                continue
            key = key_getter(child)
            if key:
                expanded.add(key)
    return expanded


def restore_expanded_paths(
    tree_widget: QtWidgets.QTreeWidget,
    expanded_keys: Set[str],
    key_getter: ItemKeyGetter,
) -> None:
    """根据 key 集合恢复树的展开状态."""

    root = tree_widget.invisibleRootItem()
    if not root or not expanded_keys:
        return

    stack = [root]
    while stack:
        item = stack.pop()
        key = key_getter(item)
        if key and key in expanded_keys:
            # PyQt6 中不再提供 QTreeWidget.setItemExpanded；
            # 直接对 QTreeWidgetItem 调用 setExpanded 即可恢复展开状态。
            item.setExpanded(True)
        for index in range(item.childCount()):
            stack.append(item.child(index))


