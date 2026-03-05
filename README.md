# Ayaya_Miliastra_Editor（小王千星工坊）

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

**仓库地址**：[AyayaXiaowang/Ayaya_Miliastra_Editor](https://github.com/AyayaXiaowang/Ayaya_Miliastra_Editor)

---

## 项目简介

**Ayaya_Miliastra_Editor** 是一款面向原神“千星奇域”的**离线沙箱编辑器 + Graph Code 工具链**。
本项目旨在将“难维护、难协作、难重构”的节点图视觉编程环境，转换为 AI 和程序员更熟悉的**代码工作流（Graph Code）**。

通过编写类结构的 Python 代码描述节点图逻辑，由内置引擎负责解析、验证并自动排版，最终一键导出并应用到游戏中。

### 核心特性

- **Graph Code（代码即节点图）**：使用 Python 编写节点逻辑，充分利用 AI 辅助生成、代码重构工具与 Git 版本控制。
- **自动验证与排版**：内置引擎对参数类型、端口连线及节点有效性进行严格校验，并基于代码结构自动生成清晰的视觉布局。
- **可视化 UI**：提供独立工具端，支持实时预览渲染出的节点图、复合节点、信号与结构体（仅供查看，修改需在源码中进行）。
- **HTML UI 源码支持**：支持以 HTML 格式作为 UI 源码，并可直接导出为 `.gil`。
- **一键导出（推荐）**：内置项目导入/导出中心，支持一键将资产导出为 `.gil`（覆盖本地缓存）或 `.gia`（项目交付），过程自动进行关联分析与严格校验。

---

## 快速开始

### 1. 最小环境与版本矩阵

为了确保依赖的稳定性（特别是视觉与 OCR 模块），本项目对运行环境有严格约束：

| 维度 | 要求说明 |
| :--- | :--- |
| **操作系统** | Windows 10/11（中文界面） |
| **显示设置** | 分辨率 1080p/2K/4K，缩放 100%/125%（影响旧版 UI 自动化功能） |
| **Python 环境** | **3.10 - 3.12**（推荐 3.10.x；因约束锁不支持 Python 3.13） |
| **关键依赖** | 已在 `constraints.txt` 严格锁定版本（PyQt6 / onnxruntime 等） |

### 2. 获取代码与安装

```powershell
git clone https://github.com/AyayaXiaowang/Ayaya_Miliastra_Editor.git
cd Ayaya_Miliastra_Editor
pip install -r requirements.txt -c constraints.txt
```

### 3. 启动 UI

```powershell
python -X utf8 -m app.cli.run_app
```

*(VSCode 用户也可按 F5 调试执行 `run_app_debug.py`)*

---

## 核心工作流（Graph Code）

1. **编写代码**：在 `assets/资源库/` 下对应目录（如 `节点图/server/`），创建 `.py` 文件，用类结构编写逻辑。建议全程由 AI 辅助编写。
1. **本地验证（必需）**：执行校验命令，根据报错修复参数、类型或连线错误。

```powershell
python -X utf8 -m app.cli.graph_tools validate-file <对应文件路径>
```

1. **导出应用**：点击 UI 顶部“导出”，在向导中选择内容并导出为 `.gil`（写回覆盖）或 `.gia`（交付）。导出/导入能力由扩展 `private_extensions/ugc_file_tools` 提供。

---

## 常用命令参考

| 操作 | 对应命令 | 说明 |
| :--- | :--- | :--- |
| **全量验证** | `python -X utf8 -m app.cli.graph_tools validate-graphs --all` | 验证全量节点图与复合节点。 |
| **单文件验证** | `python -X utf8 -m app.cli.graph_tools validate-file <path>` | 适合开发期单点调试。 |
| **存档验证** | `python -X utf8 -m app.cli.graph_tools validate-project` | 校验目录存档级的资源引用健康度。 |
| **单元测试** | `python -X utf8 -m pytest` | 跑通现有测试（要求安装 `requirements-dev.txt`）。 |

---

## 目录结构

```text
repo_root/
├── app/             # UI 渲染、CLI 入口与自动化控制
├── engine/          # 核心引擎（解析、验证、布局算法）
├── plugins/         # 节点实现注册表（包含 server/client/shared）
├── assets/          # 资产资源库（图代码、信号、复合节点、OCR 模板等）
```

*(注意：日常开发只需关注 `assets/资源库/`，切勿随意修改 `engine/` 等核心组件。)*

---

## 常见问题（FAQ）

**Q：为什么 UI 里只能看不能连线？**
A：我们的核心理念是“**用代码维护逻辑，用 UI 审阅逻辑**”。所有的逻辑构建与修改都应通过 Python 文件进行（便于 Git 管理和系统性重构），UI 仅作为不可变的实时投射面板。

**Q：为什么节点图全是中文编程？**
A：为了降低新手理解门槛并增强逻辑自说明能力，项目仅在 `assets/资源库/` 内采用纯中文命名体系，此机制同时与大语言模型（LLM）的生成特性高度契合。

**Q：导出 `.gil` 直接覆盖会有风险吗？**
A：本项目通过强大的导出校验确保文件合规，但覆盖前**务必手动备份源存档**，避免误操作导致存档损坏。

---

## 开源协议与第三方致谢

本项目遵循 **[GNU GPL v3.0](https://www.gnu.org/licenses/gpl-3.0)** 开源许可。

**免责声明**：本项目属于第三方辅助工具。若使用任何向游戏客户端直接操作的自动化功能，使用者需自行评估合规风险并承担相应后果。

**致谢以下优秀的开源项目 / 运行期依赖**：

- **核心依赖**：[PyQt6](https://www.riverbankcomputing.com/software/pyqt/) / [RapidOCR](https://github.com/RapidAI/RapidOCR) / [numpy](https://github.com/numpy/numpy) / [opencv-python](https://github.com/opencv/opencv-python) / [Pillow](https://github.com/python-pillow/Pillow) / [pytest](https://github.com/pytest-dev/pytest) 等
- **对照分析与生态协同**：曾在开发期间提供启发与参考的外部项目：[genshin-ts](https://github.com/josStorer/genshin-ts) (MIT) / [Genshin-Impact-Miliastra-Wonderland-Code-Node-Editor-Pack](https://github.com/Wu-Yijun/Genshin-Impact-Miliastra-Wonderland-Code-Node-Editor-Pack) (MIT) / `Genshin-Impact-UGC-File-Converter` (MIT) / [perfectPixel](https://github.com/theamusing/perfectPixel) (MIT)

**第三方派生报告（可选/可重建，不参与主流程强依赖）**：

- 来自 `genshin-ts` / NodeEditorPack 的导出报告（MIT，可按需生成到 `private_extensions/ugc_file_tools/refs/genshin_ts/`）：
  - `genshin_ts__struct_field_type_ids.report.json`
  - `genshin_ts__node_schema.report.json`
  - 对应许可证副本：`LICENSES/genshin-ts.MIT.txt`、`LICENSES/NodeEditorPack.MIT.txt`

*(注：各第三方项目版权与授权以其独立声明或原仓库 `LICENSE` 为准)*
