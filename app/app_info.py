"""应用元信息（版本号与上游仓库信息）。

约定：
- 发布版本应与 GitHub tag 保持一致（推荐 tag 形如：vX.Y.Z；不要求创建 Release）。
- 源码开发态可保持 APP_VERSION="dev"；此时“检查更新”会优先尝试使用本地 git HEAD 与
  远端参考点（最新 tag 或分支 head）对应的 commit 做精确对比。
"""

from __future__ import annotations

APP_DISPLAY_NAME = "小王千星工坊"

# 上游仓库（用于“检查更新”按钮）
APP_REPO_FULL_NAME = "AyayaXiaowang/Ayaya_Miliastra_Editor"
APP_REPO_URL = "https://github.com/AyayaXiaowang/Ayaya_Miliastra_Editor"

# 更新检查策略：
# - "default_branch_head"：对比远端默认分支最新 commit（适合“用户自行编译源码”的分发方式）
# - "latest_release"：对比 GitHub 最新 Release（需要仓库存在正式 Release）
# - "latest_release_version"：仅对比“本地版本号 vs 最新 Release tag”（不使用 git commit 判定）
# - "latest_release_or_tag"：优先对比最新正式 Release；仓库暂无 Release 时退化为 latest_tag
# - "latest_tag"：对比 GitHub 最新语义版本 tag（不需要创建 Release，但需要打 tag）
APP_UPDATE_CHECK_MODE = "latest_release_version"

# 本地版本号（发布版请与 GitHub Release tag 同步；开发态可用 "dev"）
APP_VERSION = "0.1.0-beta"


__all__ = [
    "APP_DISPLAY_NAME",
    "APP_REPO_FULL_NAME",
    "APP_REPO_URL",
    "APP_UPDATE_CHECK_MODE",
    "APP_VERSION",
]


