"""统一的简约线条图标。32×32 坐标，界面与托盘共用，无第三方依赖。"""
from __future__ import annotations

import math
import struct
import zlib


def arc(cx, cy, rx, ry, start, end, steps=24):
    return [(cx + rx * math.cos(math.radians(start + (end - start) * i / steps)),
             cy + ry * math.sin(math.radians(start + (end - start) * i / steps))) for i in range(steps + 1)]


def smooth_closed(points, steps=7):
    points = points[:-1] if points[0] == points[-1] else points
    result = []
    for i in range(len(points)):
        p0, p1, p2, p3 = (points[(i + j) % len(points)] for j in (-1, 0, 1, 2))
        for s in range(steps):
            t = s / steps
            result.append(tuple(.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t
                               + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
                               + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t ** 3) for k in (0, 1)))
    return result + [result[0]]


PATHS = {
    "atk": [arc(16, 16, 8, 11, 180, 360) + arc(16, 18, 8, 9, 0, 180)[1:] + [(8, 16)],
            [(16, 5), (16, 12)], [(8.4, 15), (23.6, 15)], [(16, 9), (16, 11)]],
    "logitech": [[(9, 27), (6, 24), (5, 19), (7, 9), (10, 5), (16, 4), (21, 6), (24, 12),
                  (25, 21), (23, 26), (19, 28), (9, 27)],
                 [(16, 5), (16, 12)], [(7, 15), (12, 16), (17, 15), (23, 13)],
                 [(16, 8), (16, 11)], [(8, 19), (8, 22)]],
    "p9500": [arc(16, 17, 11, 12, 180, 360), [(5, 16), (5, 24)], [(27, 16), (27, 24)],
              [(9, 16), (6, 16), (5, 18), (5, 23), (6, 25), (9, 25), (9, 16)],
              [(23, 16), (26, 16), (27, 18), (27, 23), (26, 25), (23, 25), (23, 16)]],
    "dualshock": [[(8, 10), (12, 9), (14, 11), (18, 11), (20, 9), (24, 10),
                   (27, 13), (30, 24), (28, 27), (25, 26), (21, 22), (11, 22),
                   (7, 26), (4, 27), (2, 24), (5, 13), (8, 10)],
                  [(7, 16), (13, 16)], [(10, 13), (10, 19)],
                  [(23, 13), (23, 14)], [(26, 16), (26, 17)],
                  [(20, 16), (20, 17)], [(23, 19), (23, 20)], [(14, 16), (18, 16)]],
    "refresh": [arc(16, 16, 9, 9, 40, 325), [(24, 6), (24, 12), (18, 12)]],
    "tray": [[(6, 21), (6, 26), (26, 26), (26, 21)], [(16, 5), (16, 20)], [(10, 14), (16, 20), (22, 14)]],
    "settings": [arc(16, 16, 4.5, 4.5, 0, 360),
                 [(16 + (11.5 if i % 4 in (1, 2) else 9) * math.cos(i * math.pi / 16),
                   16 + (11.5 if i % 4 in (1, 2) else 9) * math.sin(i * math.pi / 16)) for i in range(33)]],
    "clock": [arc(16, 16, 11, 11, 0, 360), [(16, 9), (16, 16), (21, 19)]],
    "sun": [arc(16, 16, 5, 5, 0, 360)] + [[(16 + 9 * math.cos(t), 16 + 9 * math.sin(t)),
               (16 + 12 * math.cos(t), 16 + 12 * math.sin(t))] for t in [i * math.pi / 4 for i in range(8)]],
    "moon": [[(24, 22), (21, 25), (16, 27), (10, 25), (6, 21), (5, 16), (7, 11), (11, 7),
              (15, 5), (13, 10), (13, 15), (15, 20), (19, 22), (24, 22)]],
    "power": [arc(16, 17, 10, 10, -55, 235), [(16, 3), (16, 16)]],
    "chevron": [[(10, 13), (16, 19), (22, 13)]],
    "bluetooth": [[(11, 9), (23, 21), (16, 27), (16, 5), (23, 11), (11, 23)]],
    "wireless": [arc(16, 23, 15, 15, 226, 314), arc(16, 23, 10, 10, 226, 314),
                 arc(16, 23, 5, 5, 226, 314), [(16, 25), (16, 25.2)]],
    "usb": [[(12, 5), (12, 11)], [(20, 5), (20, 11)], [(8, 11), (24, 11), (24, 19),
             (21, 23), (11, 23), (8, 19), (8, 11)], [(16, 23), (16, 29)]],
    "bolt": [[(18, 3), (8, 18), (15, 18), (13, 29), (24, 13), (17, 13), (18, 3)]],
    "info": [arc(16, 16, 11, 11, 0, 360), [(16, 14), (16, 23)], [(16, 9), (16, 9.2)]],
    "check": [[(7, 16), (13, 22), (25, 9)]],
    "close": [[(9, 9), (23, 23)], [(23, 9), (9, 23)]],
    "battery": [[(6, 9), (25, 9), (26, 10), (26, 23), (25, 24), (6, 24), (5, 23), (5, 10), (6, 9)],
                [(28, 14), (28, 19)], [(10, 14), (10, 19)], [(15, 14), (15, 19)], [(20, 14), (20, 19)]],
}

PATHS['logitech'][0] = smooth_closed(PATHS['logitech'][0])
PATHS['dualshock'][0] = smooth_closed(PATHS['dualshock'][0])
PATHS['moon'][0] = smooth_closed(PATHS['moon'][0])


def png(width, height, rgba):
    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data))
    rows = b''.join(b'\0' + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 6)) + chunk(b'IEND', b''))


def raster(key, size, color=(36, 55, 83), width=1.8, level=None, stale=False):
    """3× 超采样；托盘以顺时针外环表示电量，设备轮廓保留在中央。"""
    aa = 3
    n = size * aa
    pixels = bytearray(n * n * 4)
    scale = n / 32
    glyph_scale = 0.69 if level is not None else 1.0
    offset_x = offset_y = 32 * (1 - glyph_scale) / 2

    def stroke(a, b, rgba, thickness):
        x1, y1 = a[0] * scale, a[1] * scale
        x2, y2 = b[0] * scale, b[1] * scale
        radius = thickness * scale / 2
        lo_x, hi_x = max(0, int(min(x1, x2) - radius - 1)), min(n, int(max(x1, x2) + radius + 2))
        lo_y, hi_y = max(0, int(min(y1, y2) - radius - 1)), min(n, int(max(y1, y2) + radius + 2))
        dx, dy = x2 - x1, y2 - y1
        norm = dx * dx + dy * dy
        for y in range(lo_y, hi_y):
            for x in range(lo_x, hi_x):
                t = max(0, min(1, ((x + .5 - x1) * dx + (y + .5 - y1) * dy) / norm)) if norm else 0
                distance = math.hypot(x + .5 - x1 - t * dx, y + .5 - y1 - t * dy)
                coverage = max(0, min(1, radius + .5 - distance))
                if coverage:
                    p = (y * n + x) * 4
                    alpha = round(coverage * rgba[3])
                    if alpha > pixels[p + 3]:
                        pixels[p:p + 4] = bytes((*rgba[:3], alpha))

    for path in PATHS[key]:
        points = [(x * glyph_scale + offset_x, y * glyph_scale + offset_y) for x, y in path]
        for a, b in zip(points, points[1:]):
            stroke(a, b, (*color, 255), width)
    if level is not None:
        track = arc(16, 16, 14, 14, -90, 270, 100)
        for a, b in zip(track, track[1:]):
            stroke(a, b, (*color, 85), 2.8)
        if level >= 0:
            tint = (146, 156, 176) if stale else (75, 204, 156) if level >= 60 else (238, 183, 77) if level >= 30 else (244, 105, 126)
            sweep = max(0, min(100, level)) * 3.6
            progress = arc(16, 16, 14, 14, -90, -90 + sweep, max(1, round(sweep / 3.6)))
            for a, b in zip(progress, progress[1:]):
                stroke(a, b, (*tint, 255), 2.8)
    output = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            samples = [(yy * n + xx) * 4 for yy in range(y * aa, y * aa + aa) for xx in range(x * aa, x * aa + aa)]
            alpha_sum = sum(pixels[p + 3] for p in samples)
            p = (y * size + x) * 4
            if alpha_sum:
                output[p:p + 4] = bytes([round(sum(pixels[q + c] * pixels[q + 3] for q in samples) / alpha_sum) for c in range(3)] + [round(alpha_sum / (aa * aa))])
    return bytes(output)


def application_icon(size):
    """用于窗口与桌面入口的玻璃电池徽标。"""
    foreground = raster('battery', size, (250, 253, 255), width=1.6)
    output = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            nx, ny = (x + .5) / size, (y + .5) / size
            qx, qy = abs(nx - .5) - .31, abs(ny - .5) - .31
            distance = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - .16
            alpha = max(0, min(1, .5 - distance * size))
            p = (y * size + x) * 4
            if not alpha:
                continue
            shine = 22 * math.exp(-((nx - .27) ** 2 + (ny - .15) ** 2) / .09)
            base = (105 - 18 * ny + shine, 139 + 9 * ny + shine, 205 + 18 * ny + shine)
            opacity = foreground[p + 3] / 255
            output[p:p + 4] = bytes([min(255, round(a * (1 - opacity) + foreground[p + i] * opacity))
                                      for i, a in enumerate(base)] + [round(alpha * 255)])
    return bytes(output)
