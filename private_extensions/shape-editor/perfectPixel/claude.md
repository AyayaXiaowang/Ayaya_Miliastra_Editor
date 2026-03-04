## 目录用途
- 像素网格自动检测与修复工具（PerfectPixel）所在目录：包含上游源码与本项目用于 Win10/PowerShell 的最小运行脚本与示例图片。

## 当前状态
- 上游源码位于 `src/perfect_pixel/`（核心算法实现）。
- 提供本地脚本：
  - `run_one.py`：对单张图片做网格检测与矫正，输出像素对齐结果图。
  - `run_horse.ps1`：默认处理目录内示例图并生成输出。
- 本仓库将其作为 vendored 第三方源码使用（不保留嵌套仓库 `.git/`）。
- 许可证副本：`LICENSES/perfectPixel.MIT.txt`（上游在 `readme.md` / `pyproject.toml` 声明 MIT）。

## 注意事项
- 依赖：Python 3.x、numpy、Pillow（可选：OpenCV）。
- 运行脚本会直接抛错，不做吞错处理；遇到报错优先检查输入路径与 Python 依赖是否齐全。
- 输出图默认与输入同目录，文件名追加 `.perfect` 后缀（例如 `马儿.perfect.png`）。
- 最小使用：
  - 处理默认图片（PowerShell）：`powershell -ExecutionPolicy Bypass -File private_extensions\shape-editor\perfectPixel\run_horse.ps1`
  - 处理任意图片：`python private_extensions\shape-editor\perfectPixel\run_one.py "<输入路径>" -o "<输出路径>"`
