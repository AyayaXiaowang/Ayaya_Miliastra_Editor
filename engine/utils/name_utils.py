from __future__ import annotations

import re
from typing import Iterable, List, Sequence, TypeVar


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


T = TypeVar("T")


def dedupe_preserve_order(items: Sequence[T]) -> List[T]:
    """按首次出现顺序对序列去重。

    说明：
    - 输入为任意可下标访问序列，元素需可作为 dict 的键（与原有用法一致）；
    - 返回列表中元素顺序与它们在原序列中的首次出现顺序一致。
    """
    if not items:
        return []
    # 利用 dict 的插入顺序实现“去重但保序”
    return list(dict.fromkeys(items))


def make_valid_identifier(name: str) -> str:
    """
    将任意字符串转换为合法的Python标识符（用于函数/变量名）。
    规则：
    - 常见分隔与标点统一替换为下划线
    - 折叠连续下划线并去除首尾下划线
    - 若为空或以数字开头，则添加前缀 'node_'
    """
    result = str(name)
    replacements = {
        '/': '_', '-': '_', '：': '_', ':': '_',
        '（': '_', '）': '_', '(': '_', ')': '_',
        ' ': '_', '、': '_', '+': '_', '~': '_',
        '！': '_', '!': '_', '？': '_', '?': '_',
        '，': '_', ',': '_', '。': '_', '.': '_',
        '；': '_', ';': '_', '"': '_', "'": '_',
        '【': '_', '】': '_', '[': '_', ']': '_',
        '《': '_', '》': '_', '<': '_', '>': '_',
        '=': '_', '&': '_', '|': '_', '#': '_',
        '@': '_', '$': '_', '%': '_', '^': '_',
        '*': '_',
    }
    for old, new in replacements.items():
        result = result.replace(old, new)

    result = re.sub(r'_+', '_', result)
    result = result.strip('_')

    if not result or result[0].isdigit():
        result = 'node_' + result

    return result


def sanitize_class_name(name: str) -> str:
    """
    将任意名称转换为有效的Python类名。
    策略：
    - 非单词字符统一为下划线
    - 若首字符非字母，则添加 'G_'
    - 下划线切分后采用驼峰拼接
    """
    sanitized = re.sub(r'[^\w]', '_', str(name))
    if sanitized and not sanitized[0].isalpha():
        sanitized = 'G_' + sanitized
    parts = sanitized.split('_')
    class_name = ''.join(word.capitalize() for word in parts if word)
    return class_name or 'NodeGraph'


def sanitize_node_filename(name: str) -> str:
    """
    将“节点显示名称”转换为文件系统安全的文件名（不含扩展名）。
    
    约定：
    - 无视路径分隔符：'/' 与 '\\' 直接移除（避免形成子目录）
    - Windows 非法字符（<>:"\\|?*）替换为下划线
    - 空白统一为单个下划线，折叠多重下划线并去除首尾下划线
    - 末尾点号去除
    - 全部清理后为空则回退为 '未命名节点'
    """
    text = str(name or "")
    # 无视路径分隔符（不产生任何层级）
    text = text.replace("/", "").replace("\\", "")
    # 替换 Windows 非法字符（其余符号由调用方自主决定是否保留）
    for ch in '<>:"|?*':
        text = text.replace(ch, "_")
    # 空白 → 下划线
    text = re.sub(r"\s+", "_", text)
    # 折叠下划线并清理首尾分隔符与点号
    text = re.sub(r"_+", "_", text).strip("_").strip(".")
    return text if text else "未命名节点"


def _strip_forbidden(
    text: str,
    *,
    invalid_chars: str = '<>:"/\\|?*',
    replacement: str = "_",
) -> str:
    result = text
    for char in invalid_chars:
        result = result.replace(char, replacement)
    return result


def sanitize_windows_filename(
    name: str,
    *,
    default: str = "未命名",
    collapse_whitespace: bool = True,
    replacement: str = "_",
    extra_reserved_names: Iterable[str] | None = None,
) -> str:
    """
    将任意字符串转换为 Windows 允许的文件名（不含扩展名）。

    - 统一替换 Windows 非法字符
    - 可选：空白折叠为单个 replacement
    - 清理路径分隔符，防止意外创建子目录
    - 处理保留名称（CON/PRN/...）与结尾的点号
    """
    text = str(name or "").strip()
    if not text:
        text = default
    text = text.replace("/", replacement).replace("\\", replacement)
    if collapse_whitespace:
        text = re.sub(r"\s+", replacement, text)
    text = _strip_forbidden(text, replacement=replacement)
    text = re.sub(rf"{re.escape(replacement)}+", replacement, text).strip(replacement)
    text = text.strip(".")
    if not text:
        text = default
    if text.endswith("."):
        text = f"{text[:-1]}{replacement}"
    reserved = set(WINDOWS_RESERVED_NAMES)
    if extra_reserved_names:
        reserved.update(name.upper() for name in extra_reserved_names)
    if text.upper() in reserved:
        text = f"_{text}"
    return text or default


def sanitize_package_filename(name: str) -> str:
    """存档文件名（不含 `pkg_` 前缀）的统一清洗规则。"""
    return sanitize_windows_filename(name, default="未命名存档")


def sanitize_resource_filename(name: str) -> str:
    """普通资源文件名的统一清洗规则。"""
    return sanitize_windows_filename(name, default="未命名")


def sanitize_composite_filename(name: str) -> str:
    """
    复合节点文件名清洗：先保留中文/字母/数字/下划线，再套用 Windows 清洗规则。
    """
    text = str(name or "")
    text = text.replace(" ", "_")
    text = re.sub(r"[^\w\u4e00-\u9fff]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = "复合节点"
    return sanitize_windows_filename(text, default="复合节点")


def generate_unique_name(
    base_name: str,
    existing_names: Iterable[str],
    *,
    separator: str = "_",
    start_index: int = 1,
) -> str:
    """
    基于给定的基础名称与已存在名称集合生成唯一名称。

    规则：
    - 若 `base_name` 本身尚未被占用，则直接返回 `base_name`
    - 若已存在同名项，则依次尝试 `base_name_1`、`base_name_2` …
    - 分隔符与起始序号可通过参数定制（默认为下划线与从1开始）

    用途示例：
    - UI 表格中“新变量”/“新字段”等默认名称的自动避重
    - 批量生成临时名称时避免简单重复
    """
    existing_set = {str(name) for name in existing_names}
    if base_name not in existing_set:
        return base_name

    index = int(start_index)
    if index < 0:
        index = 0
    while True:
        candidate = f"{base_name}{separator}{index}"
        if candidate not in existing_set:
            return candidate
        index += 1


__all__ = [
    "WINDOWS_RESERVED_NAMES",
    "dedupe_preserve_order",
    "make_valid_identifier",
    "sanitize_class_name",
    "sanitize_node_filename",
    "sanitize_windows_filename",
    "sanitize_package_filename",
    "sanitize_resource_filename",
    "sanitize_composite_filename",
    "generate_unique_name",
]


