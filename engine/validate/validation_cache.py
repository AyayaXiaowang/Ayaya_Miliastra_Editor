from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
import json
import inspect

from engine.utils.cache.cache_paths import get_validation_cache_file
from engine.utils.graph.graph_utils import compute_stable_md5_from_data

from .issue import EngineIssue


def _normalize_file_key(file_path: Path, workspace: Path) -> str:
    """将文件路径标准化为缓存键（优先使用相对工作区的路径）。"""
    resolved_file = file_path.resolve()
    resolved_workspace = workspace.resolve()
    if hasattr(resolved_file, "is_relative_to") and resolved_file.is_relative_to(
        resolved_workspace
    ):
        relative = resolved_file.relative_to(resolved_workspace)
        return str(relative).replace("\\", "/")
    return str(resolved_file)


def build_rules_hash(
    config: Dict[str, Any],
    standard_rules: Sequence[Any],
    composite_rules: Sequence[Any],
) -> str:
    """基于配置与规则实现构建稳定的规则签名哈希。

    规则变化判断逻辑：
        - 配置内容变化：直接纳入签名数据。
        - 规则实现变化：通过规则所在模块文件的修改时间参与签名。
    """
    module_mtimes: Dict[str, float] = {}
    all_rules: List[Any] = []
    all_rules.extend(list(standard_rules))
    all_rules.extend(list(composite_rules))
    for rule in all_rules:
        rule_type = rule.__class__
        module_name = getattr(rule_type, "__module__", "")
        module = inspect.getmodule(rule_type)
        file_path = ""
        if module is not None and hasattr(module, "__file__"):
            file_path = str(getattr(module, "__file__"))
        mtime_value = 0.0
        if file_path:
            mtime_value = float(Path(file_path).stat().st_mtime)
        key = module_name or file_path or rule_type.__name__
        if key not in module_mtimes:
            module_mtimes[key] = mtime_value
    signature_data = {
        "config": config,
        "rule_modules": sorted(module_mtimes.items()),
    }
    return compute_stable_md5_from_data(signature_data)


def load_validation_cache(workspace: Path) -> Dict[str, Any]:
    """读取工作区级别的验证缓存文件（若不存在则返回空结构）。"""
    cache_file = get_validation_cache_file(workspace)
    if not cache_file.exists():
        return {"version": 1, "rules_hash": "", "files": {}}
    text = cache_file.read_text(encoding="utf-8")
    data = json.loads(text)
    version_value = int(data.get("version", 1))
    rules_hash_value = str(data.get("rules_hash", ""))
    files_section = data.get("files") or {}
    files_dict: Dict[str, Any] = {}
    for key, value in files_section.items():
        files_dict[str(key)] = value
    return {
        "version": version_value,
        "rules_hash": rules_hash_value,
        "files": files_dict,
    }


def save_validation_cache(workspace: Path, cache: Dict[str, Any]) -> None:
    """将验证缓存结构写回磁盘。"""
    cache_file = get_validation_cache_file(workspace)
    cache_dir = cache_file.parent
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": int(cache.get("version", 1)),
        "rules_hash": str(cache.get("rules_hash", "")),
        "files": cache.get("files", {}),
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    cache_file.write_text(serialized, encoding="utf-8")


def try_load_cached_issues_for_file(
    workspace: Path,
    file_path: Path,
    cache: Dict[str, Any],
    current_rules_hash: str,
) -> Optional[List[EngineIssue]]:
    """在规则签名一致且文件状态未变更时，从缓存中还原该文件的 Issue 列表。

    条件：
        - 缓存中的 rules_hash 必须与 current_rules_hash 一致；
        - 文件键存在，且 mtime 与 size 均与当前一致。
    """
    cached_rules_hash = str(cache.get("rules_hash", ""))
    if cached_rules_hash != current_rules_hash:
        return None
    files_section = cache.get("files") or {}
    key = _normalize_file_key(file_path, workspace)
    entry = files_section.get(key)
    if not isinstance(entry, dict):
        return None
    metadata = entry.get("meta") or {}
    stored_mtime = float(metadata.get("mtime", 0.0))
    stored_size = int(metadata.get("size", 0))
    stat = file_path.stat()
    current_mtime = float(stat.st_mtime)
    current_size = int(stat.st_size)
    if (stored_mtime != current_mtime) or (stored_size != current_size):
        return None
    raw_issues = entry.get("issues") or []
    issues: List[EngineIssue] = []
    for payload in raw_issues:
        if isinstance(payload, dict):
            issues.append(EngineIssue.from_dict(payload))
    for issue in issues:
        if issue.level == "error":
            return None
    return issues


def update_validation_cache_for_file(
    workspace: Path,
    file_path: Path,
    cache: Dict[str, Any],
    current_rules_hash: str,
    issues: Iterable[EngineIssue],
) -> None:
    """将单个文件的最新验证结果写入缓存结构（内存中的 cache 字典）。"""
    files_section = cache.get("files")
    if not isinstance(files_section, dict):
        files_section = {}
        cache["files"] = files_section
    key = _normalize_file_key(file_path, workspace)
    stat = file_path.stat()
    current_mtime = float(stat.st_mtime)
    current_size = int(stat.st_size)
    issue_dicts: List[Dict[str, Any]] = []
    for issue in issues:
        issue_dicts.append(issue.to_dict())
    files_section[key] = {
        "meta": {
            "mtime": current_mtime,
            "size": current_size,
        },
        "issues": issue_dicts,
    }
    cache["rules_hash"] = current_rules_hash



