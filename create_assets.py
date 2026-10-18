"""从共享矢量图形生成发布资源；仅开发时使用。"""
from pathlib import Path

import symbols
from win_icon import build_ico


def main():
    destination = Path(__file__).resolve().parent / 'assets'
    destination.mkdir(exist_ok=True)
    frames = [(size, symbols.application_icon(size)) for size in (16, 20, 24, 32, 40, 48, 64, 128)]
    (destination / 'app.ico').write_bytes(build_ico(frames))
    w, h = 512, 128
    preview = bytearray(bytes((237, 243, 251, 255)) * (w * h))
    for i, key in enumerate(('atk', 'logitech', 'p9500', 'dualshock')):
        data = symbols.raster(key, 80, (97, 119, 157), width=1.35)
        for y in range(80):
            for x in range(80):
                p, q = (y * 80 + x) * 4, ((y + 24) * w + x + 24 + i * 128) * 4
                alpha = data[p + 3] / 255
                preview[q:q + 3] = bytes(round(preview[q + c] * (1 - alpha) + data[p + c] * alpha) for c in range(3))
    (destination / 'device-symbols.png').write_bytes(symbols.png(w, h, bytes(preview)))
    # 环绕电量预览：上排放大展示，下排保留真实 16 / 20 / 24 / 32 像素尺寸。
    w, h = 512, 160
    preview = bytearray(bytes((25, 30, 40, 255)) * (w * h))
    for i, (key, level) in enumerate(zip(('atk', 'logitech', 'p9500', 'dualshock'), (50, 60, 25, 100))):
        for size, top in ((64, 17), ((16, 20, 24, 32)[i], 111)):
            data = symbols.raster(key, size, (229, 237, 249), width=2.3, level=level)
            left = i * 128 + (128 - size) // 2
            for y in range(size):
                for x in range(size):
                    p, q = (y * size + x) * 4, ((y + top) * w + left + x) * 4
                    alpha = data[p + 3] / 255
                    preview[q:q + 3] = bytes(round(preview[q + c] * (1 - alpha) + data[p + c] * alpha) for c in range(3))
    (destination / 'tray-rings.png').write_bytes(symbols.png(w, h, bytes(preview)))


if __name__ == '__main__':
    main()
