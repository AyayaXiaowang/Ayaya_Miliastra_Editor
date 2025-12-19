# Graph_Generater（小王千星工坊 / Ayaya_Miliastra_Editor）

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

**仓库地址**：[AyayaXiaowang/Ayaya_Miliastra_Editor](https://github.com/AyayaXiaowang/Ayaya_Miliastra_Editor)

---

## 项目状态（Beta）

- 本项目目前处于 **Beta** 阶段，迭代可能会非常快：**API、校验规则、资源结构、CLI 参数**都可能调整。
- 当 README 与实际行为不一致时，优先以以下内容为准：
  - `claude.md`（根目录与各子目录的约束/入口说明）
  - CLI 脚本自身的报错提示与 `--help`
  - `tools.validate.*` / `engine.validate` 的实现与校验输出

### 展示型发布说明（重要）
- 本仓库采用“展示型”策略：**`docs/` 不随仓库分发**（避免误公开私有文档/工程内容）。
- **`tests/` 会公开并用于 CI**（基础回归以 `pytest` 为准）。
- 资源库 `assets/资源库/` 默认“全量忽略 + 白名单放行示例/模板示例”；请勿扩大白名单范围，除非明确确认资源可公开且不会泄露隐私。

### 反馈与交流
- BUG 反馈交流QQ群：`1073774505`

面向原神千星奇域的 **离线沙箱编辑器 + Graph Code 工具链**：用 Python 代码描述节点图，由内置引擎负责解析、验证、自动排版，再配合自动化脚本把步骤精准落到真实编辑器。

---

## 这个项目在解决什么问题？

> 把“难维护、难协作、难重构”的节点图世界，翻译成 AI 和程序员都熟悉的代码世界。

### 节点图维护困难、跳转成本极高

- **痛点**：一个功能拆散在多个节点图、多个分支里，想改一个逻辑，需要在编辑器里层层点开、来回跳转，人脑要记一堆上下文。
- **解决**：用代码统一表达逻辑，再自动转换成节点图，大部分维护工作都回到了“写代码”这一熟悉场景里。

### AI 时代，纯手工 debug 成本过高

- **痛点**：已经习惯用 AI 总结、解释、生成代码的人，很难再回到“在节点图里搬砖、一点点试”的工作方式。
- **解决**：把节点图问题转化为代码问题，就能充分利用 AI 的生态：让 AI 帮你查 bug、写测试、做重构，再反向生成节点图。

### 多人协作与版本管理体验差

- **痛点**：节点图本质是复杂的结构化数据，Git diff / review 非常困难，合并冲突基本只能“谁最后覆盖谁”。
- **解决**：代码是文本，适配现有的版本管理、Code Review 流程，再由程序负责把“最终认可的版本”转换为节点图，协作成本显著降低。

### 难以做系统化的重构与大规模改动

- **痛点**：在节点图里做全局改名、跨图重构、流程拆分/合并，基本靠人工点点点，非常容易遗漏。
- **解决**：当逻辑在代码中，用正则、脚本、静态分析工具，甚至让 AI 生成重构方案，再自动映射到节点图，大改动变得更安全、更可控。

### 学习效率受限，AI 难以直接教学节点图

- **痛点**：就算新人学习速度再快，也很难靠“老师口述 + 自己点节点图”高效掌握复杂项目，更别说让 AI 手把手教你“怎么连线”——当前 AI 几乎无法直接生成高质量节点图。
- **解决**：把逻辑变成代码后，AI 可以像正常教写代码一样：讲解、改写、补全、重构、加注释，甚至按你的节奏出练习；新人在 AI 辅助下学会这套 Graph Code，再由工具自动生成节点图，上手速度远高于直接学节点图。

### 复杂节点图的可读性与排版问题

- **痛点**：手工排版复杂图，线会绕来绕去，稍一修改就打乱布局，很难保持长期整洁。
- **解决**：自动排版算法可以根据代码结构生成层次清晰的布局，逻辑修改后重新排版，始终保持“可读版本”。

### 重复性机械操作多，易出错

- **痛点**：手动搭节点、连线，本质是大量重复的机械操作，既浪费时间，又容易在复制过程中漏连/误连。
- **解决**：程序通过模拟鼠标自动创建节点图，把机械劳动从人手中拿走，人只需要审阅与调整关键细节。

### AI 对接节点图生态的鸿沟

- **痛点**：AI 很难直接生成高质量的节点图结构（尤其是带有复杂约束的编辑器），中间缺少“标准接口”。
- **解决**：把所有节点抽象为 Python 函数 + 转换器，等于给 AI 提供了一个稳定的“代码 → 节点图”桥梁，AI 能在自己最擅长的代码空间工作。

---

## 这个项目能做什么？

| 功能 | 说明 |
| --- | --- |
| **用 Python 写节点图（Graph Code）** | 把节点图逻辑写成类结构 Python 代码，AI 和开发者都能直接读写 |
| **自动转换成节点图** | 引擎解析 Graph Code，生成 UGC 编辑器可用的节点图结构与布局 |
| **自动验证** | 检查节点是否存在、端口连线是否正确、参数类型是否匹配 |
| **自动排版** | 根据代码结构生成清晰的节点图布局，保持长期可读性 |
| **可视化查看** | 在 UI 中查看节点图、复合节点、信号、结构体等 |
| **自动搭图** | 自动化脚本模拟鼠标，在真实 UGC 编辑器中批量搭建节点图 |
| **友好的 AI 工作流** | 用代码作为中间层，让 AI 负责生成与重构，工具链负责验证与落地 |

---

## 安全与合规声明

> ⚠️ **重要提示**

- 本项目的“执行/同步”能力主要通过**截图/OCR + 键鼠模拟**，在《原神》客户端内的**千星沙箱（UGC 编辑器）**执行编辑操作，用于将本项目生成的任务清单步骤同步到编辑器
- 使用该能力等价于对游戏客户端界面进行自动化操作；请务必遵守官方用户协议与相关规则，并自行评估可能的风险与后果
- 本项目不支持、也不鼓励将自动化用于 UGC 编辑器之外的任何游戏玩法场景

---

## 运行环境

| 要求 | 说明 |
| --- | --- |
| **操作系统** | Windows 10/11（中文界面，推荐 4K 或 2K 分辨率） |
| **Python** | 3.10 - 3.12（推荐 3.10.x；当前依赖锁不支持 Python 3.13） |
| **终端** | PowerShell 7 |
| **其他** | 确保安装 Visual C++ 运行库 |

补充说明：
- **CI 基线**：Python 3.10
- **本地验证**：当前仓库已在 Python 3.12.3 下跑通 `pytest`
- **重要**：`constraints.txt` 钉死的 `rapidocr-onnxruntime==1.4.4` 声明 `Requires-Python: <3.13`，因此 **Python 3.13 会在安装阶段直接失败**

### 最小可运行版本矩阵（锁定基线）

| 维度 | 基线 |
| --- | --- |
| OS | Windows 10/11 |
| Python | 3.10 - 3.12（推荐 3.10.x） |
| 关键依赖版本 | 见 `constraints.txt`（PyQt6 / onnxruntime / opencv / numpy 等已钉死） |

---

## 安装依赖

### 依赖安装（已提供版本约束锁）

本仓库提供以下文件作为**单一权威依赖清单 + 可复现约束锁**：

- `requirements.txt`：运行期直接依赖（不写版本）
- `constraints.txt`：版本锁（钉死关键原生依赖版本）
- `requirements-dev.txt`：开发/测试依赖（已钉死 pytest 版本）

安装运行期依赖：

```powershell
pip install -r requirements.txt -c constraints.txt
```

如果你遇到类似下面的错误（`ResolutionImpossible` / `rapidocr-onnxruntime` 冲突）：

- 先检查 `python --version`：**必须是 3.10 - 3.12**（Python 3.13 不支持 `rapidocr-onnxruntime==1.4.4`）
- 确保你在正确的 venv 里安装（不要混用多个 Python 的 venv）

安装开发/测试依赖：

```powershell
pip install -r requirements-dev.txt -c constraints.txt
```

### 依赖说明

| 库 | 作用 |
| --- | --- |
| `PyQt6` | UI 主程序框架 |
| `rapidocr-onnxruntime` | 节点标题 OCR 识别 |
| `numpy` | 数值计算、布局算法 |
| `opencv-python` | 视觉识别、图像处理 |
| `Pillow` | 截图与图像变换 |
| `pyperclip` | 剪贴板操作 |
| `keyboard` | 键盘注入，用于自动搭图 |

---

## 快速开始

### 1. 克隆仓库

```powershell
git clone <你的仓库地址>
# 例如（上游参考）：
# git clone https://github.com/AyayaXiaowang/Ayaya_Miliastra_Editor.git
```

```powershell
cd <仓库目录>
# 本地文件夹名可以和仓库名不同（例如你把仓库放在 Graph_Generater/ 目录下）
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt -c constraints.txt
```

### 3. 启动 UI 主程序

```powershell
python -X utf8 -m app.cli.run_app
```

也可以使用更短入口：

```powershell
python -X utf8 -m app
```

VSCode 调试（F5）也可以直接运行根目录脚本：

```powershell
python run_app_debug.py
```

启动后会打开 PyQt6 主窗口，可以查看节点图、复合节点、资源配置等。

---

## 常见问题（FAQ）

### 如何告诉 AI 画什么节点？

答：不需要。你只要打开项目，告诉它你要做什么，AI 会自动选择最合适的节点与写法。

### 节点图画好了，怎么执行？

答：首先打开千星沙箱，新建并打开一张空的节点图，确保编辑器上方没有任何窗口遮挡；然后前往本项目的“任务清单”页面，选择你对应的节点图，点击执行即可。

### 目前都有哪些操作能直接全自动同步到千星沙箱里？

答：目前只有**节点图**可以自动操作同步；其他的**信号、结构体**等内容需要自行并提前完成定义。

### 自动运行有风险吗？

答：有。节点图的“执行/同步”是通过模拟键鼠操作《原神》客户端内的千星沙箱编辑器完成的，因此使用该功能必然会操作游戏客户端。请在遵守官方用户协议与相关规则的前提下使用，并自行评估可能的风险与后果。

### 程序有哪些快捷键（重要）？

答：

- `Ctrl+P`：执行过程中随时暂停（全局暂停请求）
- `Ctrl+[`：在任务清单中切到上一个步骤/任务项
- `Ctrl+]`：在任务清单中切到下一个步骤/任务项

### 我看到节点图 UI 里也可以像千星沙箱一样创建节点图，我可以在 UI 里手动创建吗？

答：不可以。现在的**信号、结构体、节点图、复合节点**只支持使用 Python 文件创建。虽然已经完全实现了 UI 内创建/修改的能力，但因存档容易出冲突、损坏文件等问题暂时禁用。如果你有创建或者修改的需求，建议你直接跟 AI 说。

### 这个节点图居然用的是中文，不太习惯

答：项目唯独资源库的内容使用中文命名和编程，目的是为了方便编程新手能稍微看懂一点。

但不建议用户去查看和修改节点图代码：有任何需要修改的地方都应该交给 AI 操作。

如你所见，这个项目的节点图代码的形式不是给人类操作的；人类要做的事情就是使用 UI 预览，即：**用代码写逻辑，用节点图看逻辑**。

### 我还有别的什么问题……

答：项目的文档非常详细，直接问 AI 即可；无法解决可以添加反馈群进行交流：BUG 反馈交流QQ群：`1073774505`。

---

## 常用命令

### 验证节点图

验证所有节点图：

```powershell
python -X utf8 -m tools.validate.validate_graphs --all
```

验证单个节点图：

```powershell
python -X utf8 -m tools.validate.validate_graphs -f assets\资源库\节点图\server\你的图.py
```

### 验证存档（功能包）

```powershell
python -X utf8 -m tools.validate.validate_package
```

### 清理缓存

清理所有缓存：

```powershell
python -X utf8 -m tools.clear_caches --clear
```

清理并重建索引和缓存：

```powershell
python -X utf8 -m tools.clear_caches --clear --rebuild-index --rebuild-graph-caches
```

> 注意：`--rebuild-index/--rebuild-graph-caches` 已接入引擎实现，会执行真实重建；如需避免污染仓库缓存目录，可通过 `tools.clear_caches --root <临时目录>` 在临时工作区验证。

### 运行测试（CI 同源）

```powershell
python -X utf8 -m pytest
```

---

## 目录结构

```text
repo_root/
├── app/             # UI、自动化、CLI 入口
│   ├── cli/
│   │   └── run_app.py       # UI/CLI 入口（请用 python -m app.cli.run_app）
│   └── runtime/
│       └── cache/           # 运行期缓存（默认位置，自动生成）
├── engine/          # 引擎核心（Graph Code 解析、布局、验证、模型）
├── plugins/         # 节点实现及注册表（server/client/shared）
├── assets/          # 资源库（节点图、复合节点、预设、OCR 模板等）
│   └── 资源库/
│       ├── 节点图/      # Graph Code 节点图文件
│       ├── 复合节点库/   # 复合节点定义
│       ├── 管理配置/    # 信号、结构体等配置
│       └── ...
├── tools/           # 工具脚本（验证、生成、清理等）
└── runtime/         # 预留目录（当前通常为空/不使用）
```

---

## 节点图开发流程（Graph Code）

### 1. 编写 Graph Code

在 `assets/资源库/节点图/server/` 目录下创建 `.py` 文件，用类结构 Python 描述节点图逻辑。  
推荐让 AI 先给出草稿，再由人工审阅与补充注释。

### 2. 运行验证（必须）

```powershell
python -X utf8 -m tools.validate.validate_graphs -f assets\资源库\节点图\server\你的图.py
```

验证不通过不得继续，必须根据错误提示修复。  
Graph Code 只能使用节点库中已定义的节点（`plugins/nodes` 与复合节点库）。

### 3. 在 UI 中查看

```powershell
python -X utf8 -m app.cli.run_app
```

打开对应存档，查看自动排版效果、端口连接、变量分层等。

### 4. 自动搭图（可选）

如需在官方编辑器中搭建节点图，可使用自动化脚本控制鼠标批量搭图，减少重复机械劳动。

---

## 常用工具脚本

| 脚本 | 用途 |
| --- | --- |
| `tools.validate.validate_graphs` | 节点图 & 复合节点验证（推荐 `python -m ...` 运行；支持全量 / 单文件 / 严格模式） |
| `tools.validate.validate_package` | 存档级验证，等同 UI 中“验证”按钮（推荐 `python -m ...` 运行） |
| `tools.clear_caches` | 清理运行期缓存（推荐 `python -m ...` 运行；重建开关当前为占位） |
| `app.cli.convert_graph_to_executable` | 将 Graph Code 转成可执行 Python（必须使用 `python -m ...` 运行） |

---

## 注意事项

### UI 仅支持查看，不支持编辑

以下内容在 UI 中 **仅允许查看，不支持修改**：

- **信号（Signal）**
- **结构体（Struct）**
- **复合节点**
- **节点图**

所有修改必须在对应的 Python 源文件中进行，然后运行验证脚本。

### 其他注意事项

- 写完节点图代码后，**必须** 运行 `tools/validate/validate_graphs.py` 验证并根据结果修复
- Graph Code 只能使用节点库中已定义的节点（`plugins/nodes` 与复合节点库）
- 本项目只做静态建模与校验，不在本地执行节点实际业务逻辑
- 运行期缓存缺失时会自动重建，不影响首次启动

---

## 许可

本项目遵循 **GNU General Public License v3.0**。  
完整条款见根目录 `LICENSE`，或访问 [GNU GPLv3](https://www.gnu.org/licenses/gpl-3.0.html)


