"""GitHub Release 版本检查与更新包下载（纯 Python，无 PyQt 依赖）。

设计目标：
- UI 侧只关心“结果是什么”和“要展示什么链接”，不在 UI 线程里堆网络/解析/版本对比细节。
- 不使用 try/except：网络/解析/子进程错误应直接抛出，由上层统一处理或让错误显式暴露。

能力范围（刻意收敛）：
- 只支持“本地版本号 vs GitHub 最新 Release tag”的语义版本号对比（vX.Y.Z / X.Y.Z）；
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Sequence
import json
import urllib.request
import zipfile


UpdateStatus = Literal[
    "up_to_date",
    "update_available",
    "ahead_of_remote",
    "diverged",
    "unknown",
]

UpdateCheckMode = Literal[
    "latest_release_version",
]

UpdateRemoteKind = Literal["latest_release"]


@dataclass(frozen=True, slots=True)
class GitHubReleaseInfo:
    """GitHub Release 的关键字段（latest）。"""

    repo_full_name: str
    tag_name: str
    html_url: str
    published_at: str
    name: str
    is_prerelease: bool
    is_draft: bool


@dataclass(frozen=True, slots=True)
class GitHubReleaseAsset:
    """GitHub Release Asset（用于自动下载更新包）。"""

    name: str
    browser_download_url: str
    size_bytes: int
    content_type: str


@dataclass(frozen=True, slots=True)
class GitHubReleaseWithAssets:
    """GitHub Release 信息 + assets 列表（latest）。"""

    repo_full_name: str
    tag_name: str
    html_url: str
    published_at: str
    name: str
    is_prerelease: bool
    is_draft: bool
    assets: tuple[GitHubReleaseAsset, ...]


@dataclass(frozen=True, slots=True)
class UpdateRemoteInfo:
    """用于 UI 展示的“远端参考点”信息（release/tag 或分支最新 commit）。"""

    kind: UpdateRemoteKind
    repo_full_name: str

    ref: str
    commit_sha: str

    overview_url: str
    commit_url: str

    published_at: str
    title: str


@dataclass(frozen=True, slots=True)
class UpdateCheckReport:
    """对外输出的检查结果（供 UI 展示）。"""

    repo_full_name: str
    local_version: str
    local_git_head_sha: str | None
    remote: UpdateRemoteInfo
    compare_url: str | None

    status: UpdateStatus


def fetch_latest_release(repo_full_name: str, *, timeout_seconds: float = 6.0) -> GitHubReleaseInfo:
    """获取 GitHub 最新正式 Release 信息（非 draft / 非 prerelease）。

    说明：
    - 不使用 releases/latest 接口：该接口在仓库暂无 Release 时会返回 404；
    - 这里使用 releases 列表接口过滤最新正式 Release，从而在“无 Release”场景下给出更明确的错误信息。
    """
    payload = _fetch_latest_release_payload(repo_full_name, timeout_seconds=float(timeout_seconds))
    return GitHubReleaseInfo(
        repo_full_name=repo_full_name,
        tag_name=str(payload.get("tag_name", "")).strip(),
        html_url=str(payload.get("html_url", "")).strip(),
        published_at=str(payload.get("published_at", "")).strip(),
        name=str(payload.get("name", "")).strip(),
        is_prerelease=bool(payload.get("prerelease", False)),
        is_draft=bool(payload.get("draft", False)),
    )


def fetch_latest_release_with_assets(
    repo_full_name: str,
    *,
    timeout_seconds: float = 6.0,
) -> GitHubReleaseWithAssets:
    """获取 GitHub 最新正式 Release（非 draft / 非 prerelease），并包含 assets 列表。"""
    payload = _fetch_latest_release_payload(repo_full_name, timeout_seconds=float(timeout_seconds))

    assets_raw = payload.get("assets", [])
    if not isinstance(assets_raw, list):
        assets_raw = []

    assets: list[GitHubReleaseAsset] = []
    for asset_payload in assets_raw:
        if not isinstance(asset_payload, dict):
            continue
        name_value = str(asset_payload.get("name", "")).strip()
        url_value = str(asset_payload.get("browser_download_url", "")).strip()
        size_value = int(asset_payload.get("size", 0) or 0)
        content_type_value = str(asset_payload.get("content_type", "")).strip()
        if not name_value or not url_value:
            continue
        assets.append(
            GitHubReleaseAsset(
                name=name_value,
                browser_download_url=url_value,
                size_bytes=size_value,
                content_type=content_type_value,
            )
        )

    return GitHubReleaseWithAssets(
        repo_full_name=repo_full_name,
        tag_name=str(payload.get("tag_name", "")).strip(),
        html_url=str(payload.get("html_url", "")).strip(),
        published_at=str(payload.get("published_at", "")).strip(),
        name=str(payload.get("name", "")).strip(),
        is_prerelease=bool(payload.get("prerelease", False)),
        is_draft=bool(payload.get("draft", False)),
        assets=tuple(assets),
    )


def _fetch_latest_release_payload(repo_full_name: str, *, timeout_seconds: float) -> dict:
    """返回最新正式 Release 的原始 payload（非 draft / 非 prerelease）。"""
    api_url = f"https://api.github.com/repos/{repo_full_name}/releases?per_page=20"
    request = _build_github_api_request(api_url)
    with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
        payload_list = _read_json_list_payload(response.read())

    for payload in payload_list:
        if not isinstance(payload, dict):
            continue
        if bool(payload.get("draft", False)):
            continue
        if bool(payload.get("prerelease", False)):
            continue

        tag_name_value = str(payload.get("tag_name", "")).strip()
        if not tag_name_value:
            continue
        return payload

    raise ValueError("GitHub releases 列表中未找到可用的正式 Release（非 draft/非 prerelease）")


def parse_semantic_version(version_text: str) -> tuple[int, int, int] | None:
    """解析形如 vX.Y.Z / X.Y.Z 的语义版本号（仅取前三段）。"""
    normalized = str(version_text).strip()
    if not normalized:
        return None
    if normalized.startswith(("v", "V")):
        normalized = normalized[1:].strip()

    parts = normalized.split(".")
    if not parts:
        return None

    numbers: list[int] = []
    for part in parts[:3]:
        prefix_digits = _leading_digits(part)
        if prefix_digits is None:
            return None
        numbers.append(prefix_digits)

    while len(numbers) < 3:
        numbers.append(0)

    return numbers[0], numbers[1], numbers[2]


def compare_semantic_versions(local_version: str, remote_version: str) -> int | None:
    """比较两个语义版本号：返回 -1/0/1；无法解析则返回 None。"""
    local_tuple = parse_semantic_version(local_version)
    remote_tuple = parse_semantic_version(remote_version)
    if local_tuple is None or remote_tuple is None:
        return None
    if local_tuple == remote_tuple:
        return 0
    if local_tuple < remote_tuple:
        return -1
    return 1


def check_for_updates(
    *,
    workspace_path: Path,
    repo_full_name: str,
    local_version: str,
    timeout_seconds: float = 6.0,
    mode: UpdateCheckMode = "latest_release_version",
) -> UpdateCheckReport:
    """检查是否存在更新。

说明：
- latest_release_version：**仅**对比“本地版本号(local_version) vs 最新 Release tag”，不使用 git commit 做判定。
- 其余模式：优先使用本地 git HEAD 与远端 ref 的 commit 做精确对比；若本地 git 不可用，则在 tag/release 模式下退化为语义版本号对比。
"""
    if mode != "latest_release_version":
        raise ValueError(f"未知的更新检查模式：{mode}")

    latest_release = fetch_latest_release(repo_full_name, timeout_seconds=float(timeout_seconds))
    remote_kind: UpdateRemoteKind = "latest_release"
    remote_ref = latest_release.tag_name
    remote_overview_url = (
        latest_release.html_url.strip()
        if latest_release.html_url.strip()
        else f"https://github.com/{repo_full_name}/releases"
    )
    remote_published_at = latest_release.published_at
    remote_title = latest_release.name

    remote = UpdateRemoteInfo(
        kind=remote_kind,
        repo_full_name=repo_full_name,
        ref=remote_ref,
        commit_sha="",
        overview_url=remote_overview_url,
        commit_url="",
        published_at=remote_published_at,
        title=remote_title,
    )

    local_git_head_sha = None

    status: UpdateStatus = "unknown"
    compare_url: str | None = None

    version_compare = compare_semantic_versions(local_version, remote.ref)
    if version_compare == 0:
        status = "up_to_date"
    elif version_compare == -1:
        status = "update_available"
    elif version_compare == 1:
        status = "ahead_of_remote"
    else:
        status = "unknown"

    return UpdateCheckReport(
        repo_full_name=repo_full_name,
        local_version=str(local_version),
        local_git_head_sha=local_git_head_sha,
        remote=remote,
        compare_url=compare_url,
        status=status,
    )


def _build_github_api_request(api_url: str) -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Ayaya_Miliastra_Editor",
    }
    return urllib.request.Request(api_url, headers=headers, method="GET")


def _build_github_download_request(url: str) -> urllib.request.Request:
    headers = {
        "User-Agent": "Ayaya_Miliastra_Editor",
    }
    return urllib.request.Request(url, headers=headers, method="GET")


def select_windows_portable_zip_asset(assets: Sequence[GitHubReleaseAsset]) -> GitHubReleaseAsset:
    """从 release assets 中选择默认的 Windows 便携版 zip（基于命名约定的启发式）。"""
    asset_list = list(assets or [])
    if not asset_list:
        raise ValueError("Release 不包含任何 assets，无法自动下载更新包")

    def _is_zip(asset: GitHubReleaseAsset) -> bool:
        return str(asset.name).lower().endswith(".zip")

    zip_assets = [a for a in asset_list if _is_zip(a)]
    if not zip_assets:
        raise ValueError("Release assets 中未找到 .zip，无法自动下载更新包")

    # 优先：README 约定的 windows_portable 命名
    preferred = [a for a in zip_assets if "windows_portable" in str(a.name).lower()]
    if preferred:
        return max(preferred, key=lambda a: int(a.size_bytes or 0))

    # 次优：包含 portable + win/windows
    secondary = [
        a
        for a in zip_assets
        if ("portable" in str(a.name).lower()) and ("win" in str(a.name).lower() or "windows" in str(a.name).lower())
    ]
    if secondary:
        return max(secondary, key=lambda a: int(a.size_bytes or 0))

    # 兜底：取体积最大的 zip
    return max(zip_assets, key=lambda a: int(a.size_bytes or 0))


def download_url_to_file(
    url: str,
    out_path: Path,
    *,
    timeout_seconds: float = 30.0,
    chunk_size: int = 1024 * 1024,
    progress_callback: Callable[[int, int | None], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> bool:
    """下载 URL 到本地文件。

    返回：
    - True：下载完成
    - False：用户取消（由 should_cancel 判断）
    """
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    request = _build_github_download_request(str(url))
    with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
        raw_total = response.headers.get("Content-Length")
        total_bytes = int(raw_total) if (raw_total is not None and str(raw_total).strip().isdigit()) else None

        downloaded = 0
        if progress_callback is not None:
            progress_callback(downloaded, total_bytes)

        cancelled = False
        with out_path.open("wb") as f:
            while True:
                if should_cancel is not None and bool(should_cancel()):
                    cancelled = True
                    break

                chunk = response.read(int(chunk_size))
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback is not None:
                    progress_callback(downloaded, total_bytes)

        if cancelled:
            if out_path.exists():
                out_path.unlink()
            return False

    if progress_callback is not None:
        progress_callback(downloaded, total_bytes)
    return True


def extract_zip_file(zip_path: Path, out_dir: Path) -> None:
    """辅助函数：处理 zip 文件到目标目录。"""
    zip_path = zip_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        zf.extractall(str(out_dir))


def _read_json_payload(raw_bytes: bytes) -> dict:
    decoded_text = raw_bytes.decode("utf-8")
    payload = json.loads(decoded_text)
    if not isinstance(payload, dict):
        raise ValueError("GitHub API 返回不是 JSON object")
    return payload


def _read_json_list_payload(raw_bytes: bytes) -> list:
    decoded_text = raw_bytes.decode("utf-8")
    payload = json.loads(decoded_text)
    if not isinstance(payload, list):
        raise ValueError("GitHub API 返回不是 JSON array")
    return payload


def _leading_digits(text: str) -> int | None:
    stripped = str(text).strip()
    if not stripped:
        return None
    digits: list[str] = []
    for ch in stripped:
        if ch.isdigit():
            digits.append(ch)
            continue
        break
    if not digits:
        return None
    return int("".join(digits))


__all__ = [
    "GitHubReleaseAsset",
    "GitHubReleaseInfo",
    "GitHubReleaseWithAssets",
    "UpdateCheckMode",
    "UpdateCheckReport",
    "UpdateRemoteInfo",
    "UpdateRemoteKind",
    "UpdateStatus",
    "check_for_updates",
    "compare_semantic_versions",
    "download_url_to_file",
    "extract_zip_file",
    "fetch_latest_release",
    "fetch_latest_release_with_assets",
    "parse_semantic_version",
    "select_windows_portable_zip_asset",
]


