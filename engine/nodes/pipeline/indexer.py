from __future__ import annotations

from typing import Dict, Any, Optional

from engine.utils.name_utils import make_valid_identifier


def build_index(library_by_key: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    基于合并后的字典构建查找索引。
    
    约定：
    - 提供按 key 的直查
    - 提供别名到标准键的映射（同一类别内）
    - 后续可扩展类别清单、作用域变体等
    """
    if not isinstance(library_by_key, dict):
        raise TypeError("library_by_key 必须是字典")

    def _split_scope_suffix(node_key: str) -> Optional[str]:
        """
        从 `类别/名称#scope` 中提取 scope 后缀。
        - 若不含 '#': 返回 None
        - 若含 '#': 返回 '#' 后的全部内容（不做合法值校验，校验由 validator/merger 负责）
        """
        key_text = str(node_key or "")
        if "#" not in key_text:
            return None
        return key_text.split("#", 1)[1] or None

    def _is_scoped_key(node_key: str) -> bool:
        return _split_scope_suffix(node_key) is not None

    def _should_override_alias(existing_key: str, new_key: str) -> bool:
        """
        alias 映射冲突时的覆盖策略（用于消除“遍历顺序依赖”）：
        - 已有映射为 scoped，新映射为 unscoped → 覆盖（确保 `类别/名称` 不会指向 `类别/名称#scope`）
        - 其它情况保持先到先得（冲突通常代表上游校验缺失）
        """
        if _is_scoped_key(existing_key) and (not _is_scoped_key(new_key)):
            return True
        return False

    def _put_alias(alias_to_key: Dict[str, str], alias_key: str, mapped_key: str) -> None:
        prev = alias_to_key.get(alias_key)
        if prev is None or prev == mapped_key:
            alias_to_key[alias_key] = mapped_key
            return
        if _should_override_alias(prev, mapped_key):
            alias_to_key[alias_key] = mapped_key
            return
        # 保持稳定：不覆盖既有映射，避免遍历顺序导致“拿错节点”
        return

    # 构建别名 -> 标准键 映射（限定在相同类别）
    # 关键约束：
    # - 不带 `#scope` 的 alias 只能指向不带 `#scope` 的基键（避免变体污染主别名）
    # - 带 `#scope` 的 alias 才允许指向 scoped 变体键
    alias_to_key: Dict[str, str] = {}
    for node_key, node_item in library_by_key.items():
        if not isinstance(node_item, dict):
            continue
        category_standard = str(node_item.get("category_standard", "") or "")
        name_text = str(node_item.get("name", "") or "")

        scope_suffix = _split_scope_suffix(str(node_key))
        is_scoped = scope_suffix is not None

        # 主键自身也记一份映射，便于统一入口
        if category_standard and name_text:
            if is_scoped and scope_suffix:
                _put_alias(alias_to_key, f"{category_standard}/{name_text}#{scope_suffix}", str(node_key))
            elif not is_scoped:
                _put_alias(alias_to_key, f"{category_standard}/{name_text}", str(node_key))

                # 兼容：若节点名包含 '/'，同时注入“去掉斜杠”的可调用别名（历史约定）。
                # 例如："设置背包掉落道具/货币数量" -> "设置背包掉落道具货币数量"
                slash_removed = name_text.replace("/", "")
                if slash_removed and slash_removed != name_text:
                    _put_alias(alias_to_key, f"{category_standard}/{slash_removed}", str(node_key))

                # 统一“可调用名”别名：将节点显示名称转换为合法的 Python 标识符。
                # 说明：
                # - Graph Code 中节点以函数调用形式出现，必须是合法标识符；
                # - 节点显示名可能包含 '/'、'：'、括号等字符；此处为其注入稳定别名；
                # - 仅对不带 '#scope' 的基键注入，遵循“unscoped alias 不得指向 scoped 变体”的约定。
                callable_alias = make_valid_identifier(name_text)
                if callable_alias and callable_alias != name_text:
                    _put_alias(alias_to_key, f"{category_standard}/{callable_alias}", str(node_key))

        for alias_text in list(node_item.get("aliases") or []):
            alias_str = str(alias_text or "")
            if not alias_str:
                continue
            if is_scoped and scope_suffix:
                _put_alias(alias_to_key, f"{category_standard}/{alias_str}#{scope_suffix}", str(node_key))
            elif not is_scoped:
                _put_alias(alias_to_key, f"{category_standard}/{alias_str}", str(node_key))

    return {
        "by_key": library_by_key,
        "alias_to_key": alias_to_key,
    }


