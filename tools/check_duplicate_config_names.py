"""
检测 core/configs 目录下的重复类名

扫描所有 Python 文件，找出跨模块的同名类定义（可能导致命名冲突）。
"""

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 需要检查的目录
CONFIG_DIR = PROJECT_ROOT / "core" / "configs"

# 需要忽略的文件
IGNORE_FILES = {
    "__init__.py",  # 导出文件
    "__pycache__",
}

# 需要忽略的类名（已知的合理重复或向后兼容别名）
IGNORE_CLASS_NAMES = {
    "BaseModel",  # pydantic基类
    "Enum",  # 枚举基类
}


def extract_class_definitions(file_path: Path) -> List[Tuple[str, int]]:
    """
    从Python文件中提取所有类定义
    
    返回：[(类名, 行号), ...]
    """
    class_definitions = []
    
    with open(file_path, 'r', encoding='utf-8') as file:
        for line_number, line in enumerate(file, start=1):
            # 匹配类定义：class ClassName 或 class ClassName(BaseClass)
            match = re.match(r'^class\s+(\w+)', line)
            if match:
                class_name = match.group(1)
                if class_name not in IGNORE_CLASS_NAMES:
                    class_definitions.append((class_name, line_number))
    
    return class_definitions


def scan_config_directory() -> Dict[str, List[Tuple[str, int]]]:
    """
    扫描配置目录，收集所有类定义
    
    返回：{文件路径: [(类名, 行号), ...]}
    """
    file_classes = {}
    
    for root, dirs, files in os.walk(CONFIG_DIR):
        # 排除 __pycache__
        dirs[:] = [d for d in dirs if d not in IGNORE_FILES]
        
        for file in files:
            if file.endswith('.py') and file not in IGNORE_FILES:
                file_path = Path(root) / file
                classes = extract_class_definitions(file_path)
                if classes:
                    # 相对于项目根目录的路径
                    rel_path = file_path.relative_to(PROJECT_ROOT)
                    file_classes[str(rel_path)] = classes
    
    return file_classes


def find_duplicate_classes(file_classes: Dict[str, List[Tuple[str, int]]]) -> Dict[str, List[Tuple[str, int]]]:
    """
    找出重复的类名
    
    返回：{类名: [(文件路径, 行号), ...]}
    """
    class_locations = defaultdict(list)
    
    for file_path, classes in file_classes.items():
        for class_name, line_number in classes:
            class_locations[class_name].append((file_path, line_number))
    
    # 筛选出出现多次的类名
    duplicates = {
        class_name: locations
        for class_name, locations in class_locations.items()
        if len(locations) > 1
    }
    
    return duplicates


def format_duplicate_report(duplicates: Dict[str, List[Tuple[str, int]]]) -> str:
    """
    格式化重复类名报告
    """
    if not duplicates:
        return "✅ 未发现重复类名！所有配置类名唯一。"
    
    lines = []
    lines.append("=" * 80)
    lines.append(f"发现 {len(duplicates)} 个重复的类名")
    lines.append("=" * 80)
    lines.append("")
    
    # 按重复次数排序
    sorted_duplicates = sorted(
        duplicates.items(),
        key=lambda item: len(item[1]),
        reverse=True
    )
    
    for class_name, locations in sorted_duplicates:
        lines.append(f"类名: {class_name} （出现 {len(locations)} 次）")
        lines.append("-" * 80)
        
        for file_path, line_number in sorted(locations):
            lines.append(f"  - {file_path}:{line_number}")
        
        lines.append("")
    
    lines.append("=" * 80)
    lines.append("建议：")
    lines.append("1. 为同名类添加领域后缀（如 BackpackComponentConfig vs BackpackTemplateConfig）")
    lines.append("2. 在各子包的 __init__.py 中使用别名导出以区分来源")
    lines.append("3. 在类的文档字符串中明确说明其用途和与其他同名类的区别")
    lines.append("=" * 80)
    
    return "\n".join(lines)


def main():
    """主函数"""
    print("正在扫描 core/configs 目录...")
    file_classes = scan_config_directory()
    
    total_files = len(file_classes)
    total_classes = sum(len(classes) for classes in file_classes.values())
    print(f"扫描完成：{total_files} 个文件，{total_classes} 个类定义")
    print()
    
    duplicates = find_duplicate_classes(file_classes)
    report = format_duplicate_report(duplicates)
    print(report)
    
    # 返回状态码
    return len(duplicates)


if __name__ == "__main__":
    exit_code = main()
    exit(0 if exit_code == 0 else 1)

