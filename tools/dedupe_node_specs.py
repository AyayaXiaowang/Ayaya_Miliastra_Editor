"""去重实现文件中相邻的重复 @node_spec 装饰器（保留最后一个）。

用法：
    python -X utf8 tools/dedupe_node_specs.py
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parent.parent
IMPL_DIR = ROOT / "node_implementations"


def process_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    i = 0
    removed_lines = 0
    out: list[str] = []

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        # 非装饰器行，正常输出
        if not stripped.startswith("@node_spec("):
            out.append(line)
            i += 1
            continue

        # 进入一串连续的 @node_spec(...) 装饰器块，直到遇到下一条非空且非注释的行
        blocks: list[tuple[int, int]] = []  # (start_idx, end_idx_inclusive)
        while i < len(lines) and lines[i].lstrip().startswith("@node_spec("):
            start_idx = i
            # 解析当前装饰器块的结束位置：按括号配对
            depth = 0
            end_idx = i
            j = i
            while j < len(lines):
                segment = lines[j]
                # 简单括号计数（适用于本项目的装饰器格式）
                depth += segment.count('(')
                depth -= segment.count(')')
                end_idx = j
                j += 1
                if depth <= 0:
                    break
            blocks.append((start_idx, end_idx))
            i = end_idx + 1

        # 查看接下来是否紧跟着函数定义（顶级 def）
        k = i
        while k < len(lines) and lines[k].strip() == "":
            k += 1
        is_followed_by_def = (k < len(lines) and lines[k].startswith("def "))

        if is_followed_by_def and len(blocks) > 1:
            # 保留最后一个装饰器块，其余整块删除
            keep_start, keep_end = blocks[-1]
            # 输出之前的空白（如果有）
            for idx in range(keep_start, keep_end + 1):
                out.append(lines[idx])
            # 统计被删除的行数
            for (s, e) in blocks[:-1]:
                removed_lines += (e - s + 1)
        else:
            # 无需去重：按原样输出所有块
            for (s, e) in blocks:
                for idx in range(s, e + 1):
                    out.append(lines[idx])

    if removed_lines > 0:
        path.write_text("".join(out), encoding="utf-8")
    return removed_lines


def main() -> None:
    total_removed = 0
    for py in sorted(IMPL_DIR.glob("*_impl.py")):
        removed = process_file(py)
        if removed:
            print(f"[fix] {py.name} - removed {removed} duplicate decorator lines")
        total_removed += removed
    print(f"[DONE] removed total {total_removed} duplicate decorator lines")


if __name__ == "__main__":
    main()


