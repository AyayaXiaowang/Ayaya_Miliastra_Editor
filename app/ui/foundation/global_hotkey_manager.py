"""全局热键管理器 - Windows API 实现（仅适用于 Windows 平台）。

本模块使用 ctypes 调用 Windows API 实现系统级全局热键，无需额外依赖，
支持在程序失去焦点时仍能响应热键。非 Windows 平台请勿导入或调用本模块，
也不要尝试在此基础上做跨平台抽象，以免引入隐性失败分支。
"""

import ctypes
from ctypes import wintypes
from PyQt6 import QtCore, QtWidgets
from typing import Optional


# Windows API 常量
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
VK_OEM_4 = 0xDB  # [ 键
VK_OEM_6 = 0xDD  # ] 键
VK_P = 0x50      # P 键

# 热键ID
HOTKEY_PREV = 1
HOTKEY_NEXT = 2
HOTKEY_CTRL_P = 3


class HotkeyWidget(QtWidgets.QWidget):
    """隐藏窗口用于接收热键消息"""
    
    # 信号
    hotkey_pressed = QtCore.pyqtSignal(int)  # 热键ID
    
    def nativeEvent(self, eventType, message):
        """处理原生Windows事件"""
        # 在Windows上，eventType是b'windows_generic_MSG'
        if eventType == b'windows_generic_MSG' or eventType == b'windows_dispatcher_MSG':
            # 解析消息
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                # 触发信号
                self.hotkey_pressed.emit(int(msg.wParam))
                return True, 0
        return False, 0


class GlobalHotkeyManager(QtCore.QObject):
    """全局热键管理器
    
    功能：
    - 注册系统级全局热键（Ctrl+[ 和 Ctrl+]）
    - 接收 Windows 消息并转换为 Qt 信号
    - 支持注册/注销热键
    
    使用方法：
        manager = GlobalHotkeyManager()
        manager.prev_hotkey_triggered.connect(on_prev)
        manager.next_hotkey_triggered.connect(on_next)
        manager.register_hotkeys()
        # ... 使用完毕后 ...
        manager.unregister_hotkeys()
    """
    
    # 信号
    prev_hotkey_triggered = QtCore.pyqtSignal()   # Ctrl+[ 触发
    next_hotkey_triggered = QtCore.pyqtSignal()   # Ctrl+] 触发
    ctrl_p_hotkey_triggered = QtCore.pyqtSignal() # Ctrl+P 触发（全局）
    
    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        
        # Windows API 函数
        self.user32 = ctypes.windll.user32
        # ctypes 默认会把参数按 32 位 int 处理；在 64 位进程中 hwnd 会溢出，
        # 必须显式声明 argtypes/restype。
        self.user32.RegisterHotKey.argtypes = [
            wintypes.HWND,  # hWnd
            wintypes.INT,   # id
            wintypes.UINT,  # fsModifiers
            wintypes.UINT,  # vk
        ]
        self.user32.RegisterHotKey.restype = wintypes.BOOL
        self.user32.UnregisterHotKey.argtypes = [
            wintypes.HWND,  # hWnd
            wintypes.INT,   # id
        ]
        self.user32.UnregisterHotKey.restype = wintypes.BOOL
        
        # 隐藏窗口用于接收消息
        self._hidden_widget: Optional[HotkeyWidget] = None
        
        # 热键注册状态
        self._hotkeys_registered = False
        self._registered_hotkey_ids: set[int] = set()
    
    def _on_hotkey_pressed(self, hotkey_id: int) -> None:
        """处理热键按下事件"""
        if hotkey_id == HOTKEY_PREV:
            self.prev_hotkey_triggered.emit()
        elif hotkey_id == HOTKEY_NEXT:
            self.next_hotkey_triggered.emit()
        elif hotkey_id == HOTKEY_CTRL_P:
            self.ctrl_p_hotkey_triggered.emit()
    
    def register_hotkeys(self) -> bool:
        """注册全局热键"""
        if self._hotkeys_registered:
            return True
        
        # 创建隐藏窗口用于接收消息
        if self._hidden_widget is None:
            self._hidden_widget = HotkeyWidget()
            self._hidden_widget.setWindowFlags(QtCore.Qt.WindowType.Tool)
            self._hidden_widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
            self._hidden_widget.resize(1, 1)
            # 连接信号
            self._hidden_widget.hotkey_pressed.connect(self._on_hotkey_pressed)
        
        # 获取窗口句柄
        hwnd = wintypes.HWND(int(self._hidden_widget.winId()))
        self._registered_hotkey_ids.clear()
        
        # 注册 Ctrl+[
        success1 = bool(self.user32.RegisterHotKey(
            hwnd,
            HOTKEY_PREV,
            MOD_CONTROL,
            VK_OEM_4
        ))
        if success1:
            self._registered_hotkey_ids.add(int(HOTKEY_PREV))
        
        # 注册 Ctrl+]
        success2 = bool(self.user32.RegisterHotKey(
            hwnd,
            HOTKEY_NEXT,
            MOD_CONTROL,
            VK_OEM_6
        ))
        if success2:
            self._registered_hotkey_ids.add(int(HOTKEY_NEXT))
        
        # 注册 Ctrl+P（全局暂停）
        success3 = bool(self.user32.RegisterHotKey(
            hwnd,
            HOTKEY_CTRL_P,
            MOD_CONTROL,
            VK_P
        ))
        if success3:
            self._registered_hotkey_ids.add(int(HOTKEY_CTRL_P))
        
        if success1 and success2 and success3:
            self._hotkeys_registered = True
            print(f"[全局热键] 注册成功: Ctrl+[ (ID={HOTKEY_PREV}), Ctrl+] (ID={HOTKEY_NEXT}), Ctrl+P (ID={HOTKEY_CTRL_P})")
            return True
        else:
            # 部分注册失败，清理已注册的热键
            print(f"[全局热键] 注册失败: Ctrl+[ = {success1}, Ctrl+] = {success2}, Ctrl+P = {success3}")
            for hotkey_id in list(self._registered_hotkey_ids):
                self.user32.UnregisterHotKey(hwnd, int(hotkey_id))
            self._registered_hotkey_ids.clear()
            self._hotkeys_registered = False
            return False
    
    def unregister_hotkeys(self) -> None:
        """注销全局热键"""
        if (not self._hotkeys_registered) and (len(self._registered_hotkey_ids) == 0):
            return
        
        if self._hidden_widget:
            hwnd = wintypes.HWND(int(self._hidden_widget.winId()))
            if self._registered_hotkey_ids:
                for hotkey_id in list(self._registered_hotkey_ids):
                    self.user32.UnregisterHotKey(hwnd, int(hotkey_id))
                self._registered_hotkey_ids.clear()
            else:
                self.user32.UnregisterHotKey(hwnd, int(HOTKEY_PREV))
                self.user32.UnregisterHotKey(hwnd, int(HOTKEY_NEXT))
                self.user32.UnregisterHotKey(hwnd, int(HOTKEY_CTRL_P))
        
        self._hotkeys_registered = False
        print(f"[全局热键] 注销成功")
    
    def __del__(self):
        """析构函数 - 确保注销热键"""
        self.unregister_hotkeys()

