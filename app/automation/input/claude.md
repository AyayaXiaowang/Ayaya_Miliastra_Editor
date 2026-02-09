## 目录用途
- 提供“低层输入与进程交互”能力：键鼠输入、等待/睡眠工具、前景窗口管理与子进程调用等。
- 与具体的图模型和视觉识别逻辑解耦，专注于与操作系统交互。

## 当前状态
- 主要模块：
  - `common.py`：统一的等待/睡眠、日志输出、前景窗口管理与全局可视化/日志汇聚工具；并提供坐标/阈值类小工具（如基于节点几何基准推导位置容差）。窗口查找直接复用 `window_finder`，避免重复遍历顶层窗口。
  - `win_input_lowlevel.py`：SendInput 封装与绝对坐标/按键原语；提供滚轮事件 `mouse_wheel`（基于 `MOUSEEVENTF_WHEEL`）。
  - `win_input.py`：客户区坐标到屏幕坐标的换算、高层拖拽与文本输入；提供滚轮辅助 `scroll_wheel_notches()`（按“滚轮格数”滚动，内部使用 `WHEEL_DELTA=120`），供 capture/执行步骤复用。
  - `subprocess_runner.py`：用于运行子进程（如外部辅助脚本）的工具。
  - `window_finder.py`：顶层窗口标题匹配与 HWND 查找；Win64 环境下显式声明 WinAPI `argtypes/restype`，避免 HWND 以 32 位默认类型传参导致回调内溢出；并正确处理 `FindWindowW` 返回 NULL 时 `ctypes` 会给出 `None` 的情况，避免 `int(None)` 报错。

## 注意事项
- 鼠标和键盘的具体时序与延时策略应集中在高层输入接口中，低层原语保持不带额外延时。

- 与图执行/识别相关的逻辑不要放在此目录中，避免引入高层依赖。

- 子进程输出解码：默认使用 `encoding="utf-8"` 且 `errors="replace"`，避免外部程序输出非 UTF-8 字节导致后台读线程抛 `UnicodeDecodeError`，从而丢失 stdout/stderr 与排障信息。


