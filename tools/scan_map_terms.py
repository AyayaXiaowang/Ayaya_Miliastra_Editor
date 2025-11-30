from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


TARGET_KEYWORD = "地图"


@dataclass
class MatchRecord:
    file_path: Path
    line_number: int
    category: str
    line_text: str


def should_scan_file(file_path: Path) -> bool:
    extension = file_path.suffix.lower()
    if extension in {".py", ".md", ".json"}:
        return True
    return False


def classify_line(line_text: str) -> str:
    stripped = line_text.strip()

    if "小地图" in stripped or "minimap" in stripped:
        return "minimap"

    if "assets" in stripped and "资源库" in stripped:
        return "resource_path"

    if "地图索引" in stripped:
        if "assets" in stripped or "资源库" in stripped or "Path(" in stripped:
            return "index_path"
        return "index_other"

    return "generic"


def iter_repository_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if "runtime" in path.parts and "cache" in path.parts:
            continue
        if ".venv" in path.parts or "venv" in path.parts:
            continue
        if not should_scan_file(path):
            continue
        yield path


def scan_file(file_path: Path) -> List[MatchRecord]:
    text = file_path.read_text(encoding="utf-8")
    if TARGET_KEYWORD not in text:
        return []

    lines = text.splitlines()
    matches: List[MatchRecord] = []

    for index, line_text in enumerate(lines, start=1):
        if TARGET_KEYWORD not in line_text:
            continue
        category = classify_line(line_text)
        matches.append(
            MatchRecord(
                file_path=file_path,
                line_number=index,
                category=category,
                line_text=line_text,
            )
        )

    return matches


def format_match(record: MatchRecord) -> str:
    relative_path = record.file_path.as_posix()
    preview = record.line_text.replace("\t", "    ")
    return f"{relative_path}:{record.line_number}:[{record.category}] {preview}"


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    all_matches: List[MatchRecord] = []

    for file_path in iter_repository_files(root):
        file_matches = scan_file(file_path)
        if file_matches:
            all_matches.extend(file_matches)

    all_matches.sort(key=lambda record: (str(record.file_path), record.line_number))

    for record in all_matches:
        print(format_match(record))


if __name__ == "__main__":
    main()


