"""用 Windows GDI 高质量插值缩放 RGB 背景，避免逐像素 Python 放大。"""
import ctypes as c
from ctypes import wintypes as w


class Header(c.Structure):
    _fields_ = [('size', w.DWORD), ('width', w.LONG), ('height', w.LONG),
                ('planes', w.WORD), ('bits', w.WORD), ('compression', w.DWORD),
                ('image_size', w.DWORD), ('xppm', w.LONG), ('yppm', w.LONG),
                ('used', w.DWORD), ('important', w.DWORD)]


class Info(c.Structure):
    _fields_ = [('header', Header), ('colors', w.DWORD * 3)]


def scale_rgb(rgb, sw, sh, dw, dh):
    gdi = c.WinDLL('gdi32', use_last_error=True)
    gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [c.c_void_p], c.c_void_p
    gdi.CreateDIBSection.argtypes = [c.c_void_p, c.POINTER(Info), w.UINT, c.POINTER(c.c_void_p), c.c_void_p, w.DWORD]
    gdi.CreateDIBSection.restype = c.c_void_p
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [c.c_void_p, c.c_void_p], c.c_void_p
    gdi.SetStretchBltMode.argtypes = [c.c_void_p, c.c_int]
    gdi.SetBrushOrgEx.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_void_p]
    gdi.StretchDIBits.argtypes = [c.c_void_p] + [c.c_int] * 8 + [c.c_void_p, c.POINTER(Info), w.UINT, w.DWORD]
    gdi.DeleteObject.argtypes = [c.c_void_p]
    gdi.DeleteDC.argtypes = [c.c_void_p]
    stride = (sw * 3 + 3) & ~3
    packed = bytearray(len(rgb))
    packed[0::3], packed[1::3], packed[2::3] = rgb[2::3], rgb[1::3], rgb[0::3]
    source = b''.join(packed[y * sw * 3:(y + 1) * sw * 3] + bytes(stride - sw * 3) for y in range(sh))
    source_buffer = c.create_string_buffer(source)
    source_info, target_info = Info(), Info()
    for info, width, height, bits in ((source_info, sw, sh, 24), (target_info, dw, dh, 32)):
        info.header.size, info.header.width, info.header.height = c.sizeof(Header), width, -height
        info.header.planes, info.header.bits = 1, bits
    dc = gdi.CreateCompatibleDC(None)
    bitmap, old = None, None
    try:
        data = c.c_void_p()
        bitmap = gdi.CreateDIBSection(dc, c.byref(target_info), 0, c.byref(data), None, 0)
        if not bitmap:
            raise c.WinError(c.get_last_error())
        old = gdi.SelectObject(dc, bitmap)
        gdi.SetStretchBltMode(dc, 4)  # HALFTONE
        gdi.SetBrushOrgEx(dc, 0, 0, None)
        result = gdi.StretchDIBits(dc, 0, 0, dw, dh, 0, 0, sw, sh, source_buffer, c.byref(source_info), 0, 0x00CC0020)
        if result in (0, -1):
            raise OSError('背景缩放失败')
        bgra = c.string_at(data, dw * dh * 4)
        output = bytearray(dw * dh * 3)
        output[0::3], output[1::3], output[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
        return output
    finally:
        if old:
            gdi.SelectObject(dc, old)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if dc:
            gdi.DeleteDC(dc)
