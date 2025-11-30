from __future__ import annotations

import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_NODES_DIR = WORKSPACE_ROOT / "plugins" / "nodes"


def iter_python_files() -> list[Path]:
    if not PLUGINS_NODES_DIR.exists():
        print(f"[ERROR] 目录不存在：{PLUGINS_NODES_DIR}")
        return []
    results: list[Path] = []
    for path in PLUGINS_NODES_DIR.rglob("*.py"):
        results.append(path)
    return results


def scan_usages() -> int:
    total_matches = 0
    for path in iter_python_files():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for index, line in enumerate(lines, start=1):
            if "node_implementations.shared" in line:
                rel = path.relative_to(WORKSPACE_ROOT)
                print(f"{rel}:{index}: {line.rstrip()}")
                total_matches += 1
    print(f"[INFO] 共发现 {total_matches} 处包含 'node_implementations.shared' 的代码行")
    return total_matches


def apply_fixes() -> int:
    changed_files = 0
    for path in iter_python_files():
        text = path.read_text(encoding="utf-8")
        if "node_implementations.shared" not in text:
            continue
        new_text = text.replace(
            "from node_implementations.shared.",
            "from plugins.nodes.shared.",
        ).replace(
            "import node_implementations.shared.",
            "import plugins.nodes.shared.",
        )
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            rel = path.relative_to(WORKSPACE_ROOT)
            print(f"[FIXED] 已修正导入路径：{rel}")
            changed_files += 1
    print(f"[INFO] 本次共修改 {changed_files} 个文件")
    return changed_files


def main() -> int:
    args = sys.argv[1:]
    if "--apply" in args:
        print("[MODE] 批量替换模式：将 node_implementations.shared.* 改为 plugins.nodes.shared.*")
        changed = apply_fixes()
        remaining = scan_usages()
        if remaining > 0:
            print("[WARN] 仍存在未替换的 node_implementations.shared 引用，请手动检查上述输出")
            return 1
        print("[OK] 所有 node_implementations.shared 引用已替换为 plugins.nodes.shared")
        return 0
    else:
        print("[MODE] 搜索模式（仅列出匹配，不做修改）")
        matches = scan_usages()
        return 0 if matches >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())



