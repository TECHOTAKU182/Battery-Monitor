"""Win32 通知区域：与 Tk 共用主线程消息循环。"""
import ctypes as c
from ctypes import wintypes as w
import time

import win_icon
import settings
from hid_win import GUID

U = c.WinDLL("user32", use_last_error=True)
K = c.WinDLL("kernel32", use_last_error=True)
S = c.WinDLL("shell32", use_last_error=True)
CLASS = "MyWirelessBatteryTrayWindow"
WM_TRAY, WM_SHOW, WM_REFRESH, WM_QUIT = 0x8001, 0x8002, 0x8003, 0x8004
CALLBACK = c.WINFUNCTYPE(c.c_ssize_t, c.c_void_p, w.UINT, c.c_size_t, c.c_ssize_t)


class WindowClass(c.Structure):
    _fields_ = [("style", w.UINT), ("proc", CALLBACK), ("extra", c.c_int), ("window_extra", c.c_int),
                ("instance", c.c_void_p), ("icon", c.c_void_p), ("cursor", c.c_void_p),
                ("background", c.c_void_p), ("menu", w.LPCWSTR), ("name", w.LPCWSTR)]


class NotifyIcon(c.Structure):
    _fields_ = [("size", w.DWORD), ("hwnd", c.c_void_p), ("id", w.UINT), ("flags", w.UINT),
                ("message", w.UINT), ("icon", c.c_void_p), ("tip", c.c_wchar * 128),
                ("state", w.DWORD), ("state_mask", w.DWORD), ("info", c.c_wchar * 256),
                ("version", w.UINT), ("info_title", c.c_wchar * 64), ("info_flags", w.DWORD),
                ("guid", GUID), ("balloon_icon", c.c_void_p)]


class Point(c.Structure):
    _fields_ = [("x", w.LONG), ("y", w.LONG)]


U.RegisterClassW.argtypes, U.RegisterClassW.restype = [c.POINTER(WindowClass)], w.WORD
U.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int, c.c_int, c.c_int, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p]
U.CreateWindowExW.restype = c.c_void_p
U.DefWindowProcW.argtypes, U.DefWindowProcW.restype = [c.c_void_p, w.UINT, c.c_size_t, c.c_ssize_t], c.c_ssize_t
U.DestroyWindow.argtypes = [c.c_void_p]
U.FindWindowW.argtypes, U.FindWindowW.restype = [w.LPCWSTR, w.LPCWSTR], c.c_void_p
U.PostMessageW.argtypes, U.PostMessageW.restype = [c.c_void_p, w.UINT, c.c_size_t, c.c_ssize_t], w.BOOL
U.RegisterWindowMessageW.argtypes, U.RegisterWindowMessageW.restype = [w.LPCWSTR], w.UINT
K.GetModuleHandleW.argtypes, K.GetModuleHandleW.restype = [w.LPCWSTR], c.c_void_p
K.CreateMutexW.argtypes, K.CreateMutexW.restype = [c.c_void_p, w.BOOL, w.LPCWSTR], c.c_void_p
K.CloseHandle.argtypes = [c.c_void_p]
S.Shell_NotifyIconW.argtypes, S.Shell_NotifyIconW.restype = [w.DWORD, c.POINTER(NotifyIcon)], w.BOOL
U.CreatePopupMenu.argtypes, U.CreatePopupMenu.restype = [], c.c_void_p
U.AppendMenuW.argtypes, U.AppendMenuW.restype = [c.c_void_p, w.UINT, c.c_size_t, w.LPCWSTR], w.BOOL
U.TrackPopupMenuEx.argtypes, U.TrackPopupMenuEx.restype = [c.c_void_p, w.UINT, c.c_int, c.c_int, c.c_void_p, c.c_void_p], w.UINT
U.GetCursorPos.argtypes, U.GetCursorPos.restype = [c.POINTER(Point)], w.BOOL
U.SetForegroundWindow.argtypes, U.SetForegroundWindow.restype = [c.c_void_p], w.BOOL
U.DestroyMenu.argtypes, U.DestroyMenu.restype = [c.c_void_p], w.BOOL


def notify_running(message):
    hwnd = U.FindWindowW(CLASS, None)
    return bool(hwnd and U.PostMessageW(hwnd, message, 0, 0))


class Tray:
    def __init__(self, show, open_menu, quit_app, toggle_device, refresh, selected=None):
        self.show, self.open_menu, self.quit_app = show, open_menu, quit_app
        self.toggle_device, self.refresh = toggle_device, refresh
        self.selected = set(selected if selected else settings.DEVICE_LABELS)
        self.icons = {}
        self.readings = []
        self.restarted = U.RegisterWindowMessageW("TaskbarCreated")
        self.callback = CALLBACK(self._message)
        self.instance = K.GetModuleHandleW(None)
        wc = WindowClass()
        wc.proc, wc.instance, wc.name = self.callback, self.instance, CLASS
        if not U.RegisterClassW(c.byref(wc)):
            raise c.WinError(c.get_last_error())
        self.hwnd = U.CreateWindowExW(0, CLASS, settings.APP_NAME, 0, 0, 0, 0, 0, None, None, self.instance, None)
        if not self.hwnd:
            raise c.WinError(c.get_last_error())

    def _message(self, hwnd, message, wp, lp):
        if message == WM_TRAY:
            if lp & 0xFFFF in (0x0202, 0x0203):
                self.show()
            elif lp & 0xFFFF in (0x0205, 0x007B):
                self.open_menu()
            return 0
        if message == WM_SHOW:
            self.show()
            return 0
        if message == WM_REFRESH:
            self.refresh()
            return 0
        if message == WM_QUIT:
            self.quit_app()
            return 0
        if message == self.restarted:
            self.icons.clear()
            self.update(self.readings)
            return 0
        return U.DefWindowProcW(hwnd, message, wp, lp)

    def popup_menu(self):
        """在 Tk 主线程调度中打开原生菜单，WndProc 只负责将请求排队。"""
        menu = U.CreatePopupMenu()
        if not menu:
            return
        try:
            U.AppendMenuW(menu, 1, 0, "托盘显示设备")
            U.AppendMenuW(menu, 0x800, 0, None)
            for index, (key, label) in enumerate(settings.DEVICE_LABELS.items(), 100):
                checked = key in self.selected
                flags = 8 if checked else 0
                if checked and len(self.selected) == 1:
                    flags |= 1
                U.AppendMenuW(menu, flags, index, label)
            if len(self.selected) == 1:
                U.AppendMenuW(menu, 1, 0, "至少保留一个托盘入口")
            U.AppendMenuW(menu, 0x800, 0, None)
            U.AppendMenuW(menu, 0, 200, "退出程序")
            point = Point()
            U.GetCursorPos(c.byref(point))
            U.SetForegroundWindow(self.hwnd)
            command = U.TrackPopupMenuEx(menu, 0x100 | 0x80 | 2, point.x, point.y, self.hwnd, None)
            U.PostMessageW(self.hwnd, 0, 0, 0)
            if 100 <= command < 100 + len(settings.DEVICE_LABELS):
                self.toggle_device(list(settings.DEVICE_LABELS)[command - 100])
            elif command == 200:
                self.quit_app()
        finally:
            U.DestroyMenu(menu)

    def set_selected(self, selected):
        self.selected = set(selected)
        self.update(self.readings)

    def publish(self, icon):
        previous = self.icons.get(icon.id)
        if previous and previous.icon == icon.icon:
            if previous.tip == icon.tip:
                return
            icon.flags = 4  # 电量轮廓不变时只更新提示文字，避免 Explorer 重绘。
        command = 1 if previous else 0
        if not S.Shell_NotifyIconW(command, c.byref(icon)):
            icon.flags = 7
            S.Shell_NotifyIconW(0, c.byref(icon))
        self.icons[icon.id] = icon

    def update(self, readings):
        self.readings = readings
        device_ids = {key: i for i, key in enumerate(settings.DEVICE_LABELS, 1)}
        visible = [r for r in readings if r.key in self.selected and r.visible]
        desired = {device_ids[r.key] for r in visible} or {99}
        for uid in list(self.icons):
            if uid not in desired:
                S.Shell_NotifyIconW(2, c.byref(self.icons.pop(uid)))
        if not visible:
            icon = NotifyIcon()
            icon.size, icon.hwnd, icon.id = c.sizeof(icon), self.hwnd, 99
            icon.flags, icon.message = 7, WM_TRAY
            icon.icon = win_icon.make_device_hicon('battery')
            icon.tip = f'{settings.APP_NAME} · 暂无可显示的设备\n左键打开 / 右键选择设备或退出'
            self.publish(icon)
        for r in visible:
            uid = device_ids[r.key]
            icon = NotifyIcon()
            icon.size, icon.hwnd, icon.id = c.sizeof(icon), self.hwnd, uid
            icon.flags, icon.message = 7, WM_TRAY
            text = str(r.level) if r.level is not None else "--"
            icon.icon = win_icon.make_device_hicon(r.key, r.level, r.stale)
            stamp = time.strftime("%H:%M:%S", time.localtime(r.sampled_at))
            icon.tip = f"{r.name}：{text}{'%' if r.level is not None else ''} · {r.status}\n更新 {stamp} · 左键打开 / 右键菜单"[:127]
            self.publish(icon)

    def close(self):
        for icon in self.icons.values():
            S.Shell_NotifyIconW(2, c.byref(icon))
        self.icons.clear()
        U.DestroyWindow(self.hwnd)
        win_icon.destroy_all()
