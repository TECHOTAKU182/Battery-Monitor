# -*- coding: utf-8 -*-
"""win_icon.py —— 用纯 Python 画托盘图标（不依赖 Pillow / 任何第三方库）

共享设备轮廓与环形电量，打包多尺寸 ICO 并按系统小图标尺寸加载。
"""

from __future__ import annotations

import ctypes
import struct
from collections import OrderedDict
from ctypes import wintypes

def build_ico(pngs: list[tuple[int, bytes]]) -> bytes:
    """把多张 RGBA 位图打包成 ICO 文件内容。"""
    entries = []
    blobs = []
    offset = 6 + 16 * len(pngs)
    for size, rgba in pngs:
        # BITMAPINFOHEADER
        bih = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                          size * size * 4, 0, 0, 0, 0)
        # XOR 位图：32bpp BGRA，自下而上
        xor = bytearray()
        for y in range(size - 1, -1, -1):
            row = rgba[y * size * 4:(y + 1) * size * 4]
            for x in range(size):
                r, g, b, a = row[x * 4:x * 4 + 4]
                # 预乘不必要，Windows 直接用 alpha
                xor += bytes((b, g, r, a))
        # AND 掩码：1bpp，每行按 4 字节对齐，全 0（靠 alpha 通道）
        row_bytes = ((size + 31) // 32) * 4
        mask = b"\x00" * (row_bytes * size)
        blob = bih + bytes(xor) + mask
        blobs.append(blob)
        entries.append(struct.pack("<BBBBHHII", size if size < 256 else 0,
                                   size if size < 256 else 0, 0, 0, 1, 32,
                                   len(blob), offset))
        offset += len(blob)
    return (struct.pack("<HHH", 0, 1, len(pngs)) + b"".join(entries)
            + b"".join(blobs))


# ---------------- HICON 缓存 ----------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.DestroyIcon.restype = wintypes.BOOL
user32.DestroyIcon.argtypes = [ctypes.c_void_p]
user32.GetSystemMetrics.argtypes, user32.GetSystemMetrics.restype = [ctypes.c_int], ctypes.c_int
user32.CreateIconFromResourceEx.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL,
                                          wintypes.DWORD, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.CreateIconFromResourceEx.restype = ctypes.c_void_p

MAX_CACHED_ICONS = 32
_icon_cache = OrderedDict()


def taskbar_ink():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            light, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return (47, 61, 83) if light else (229, 237, 249)
    except OSError:
        return (229, 237, 249)


def make_device_hicon(device, level=None, stale=False):
    import symbols
    ink = taskbar_ink()
    if stale or level is None:
        ink = (148, 160, 180)
    target = max(16, user32.GetSystemMetrics(49))
    key = ('device', device, level, stale, ink, target)
    if key in _icon_cache:
        _icon_cache.move_to_end(key)
        return _icon_cache[key]
    # HICON 只需系统当前尺寸；ICO 文件头之后的 DIB 可直接交给 Win32。
    rgba = symbols.raster(device, target, ink, width=2.3,
                          level=level if level is not None else -1, stale=stale)
    resource = build_ico([(target, rgba)])[22:]
    buffer = ctypes.create_string_buffer(resource)
    handle = user32.CreateIconFromResourceEx(buffer, len(resource), True, 0x00030000, target, target, 0)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    _icon_cache[key] = int(handle)
    while len(_icon_cache) > MAX_CACHED_ICONS:
        _, discarded = _icon_cache.popitem(last=False)
        user32.DestroyIcon(ctypes.c_void_p(discarded))
    return _icon_cache[key]


def destroy_all() -> None:
    for h in _icon_cache.values():
        if h:
            try:
                user32.DestroyIcon(ctypes.c_void_p(h))
            except Exception:
                pass
    _icon_cache.clear()
