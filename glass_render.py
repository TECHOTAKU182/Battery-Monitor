"""缓存光晕和带透明抗锯齿的九宫格玻璃面板，缩放不重新计算圆角。"""
from __future__ import annotations

from functools import lru_cache
import math
import tkinter as tk

import symbols
from raster_tools import scale_rgb


DARK_COLORS = {
    '#25344d': '#eaf0fc', '#7c8aa0': '#9caac1', '#647bd4': '#a4b8ff',
    '#ebf0f8': '#111a29', '#eaf0f8': '#111a29', '#f4f7fc': '#202b3e',
    '#e0e8f8': '#344463', '#f5f8fd': '#29364d', '#ffffff': '#465772',
    '#acb6c7': '#5d6d87', '#bac9e8': '#607aad', '#e8edf4': '#2c3a51',
    '#798ba9': '#b4c4df', '#a6b2c5': '#70809b', '#293d5e': '#edf3ff',
    '#97a4b8': '#7f90ad', '#96a4bb': '#889bb9', '#dde4ef': '#34435c',
    '#d6e0ee': '#0c1422', '#7c8fae': '#a1b2d0', '#d9e1ed': '#3c4b64',
    '#97abe2': '#819bdc', '#d5deec': '#41516b', '#f7f9fd': '#26334a',
    '#e1e8fb': '#384d77', '#d4ddf1': '#627ba7', '#e9edf5': '#35455f',
    '#91a6df': '#859fdf', '#d4ddeb': '#42516a', '#e0e7f1': '#36465e',
    '#bf7380': '#eaa0ad', '#a7606e': '#f2a6b3', '#c7d2e7': '#60759b',
    '#34a77f': '#6ed8af', '#c39035': '#eac273', '#d16a7d': '#ee98aa',
    '#9ba7b7': '#8092ad',
}


def theme_color(color, theme):
    return DARK_COLORS.get(color, color) if theme == 'dark' else color


class ThemedCanvas(tk.Canvas):
    """将现有的语义配色应用于所有 Canvas 图元与弹窗。"""
    def __init__(self, *args, theme='light', **kwargs):
        self.theme = theme
        if 'bg' in kwargs:
            kwargs['bg'] = theme_color(kwargs['bg'], theme)
        super().__init__(*args, **kwargs)

    def _create(self, itemType, args, kw):
        for key in ('fill', 'outline', 'activefill', 'activeoutline'):
            if isinstance(kw.get(key), str):
                kw[key] = theme_color(kw[key], self.theme)
        return super()._create(itemType, args, kw)


@lru_cache(maxsize=2)
def ambient(theme):
    """低频背景仅计算两份固定纹理，后续缩放由 GDI 完成。"""
    w, h = 160, 120
    data = bytearray(w * h * 3)
    dark = theme == 'dark'
    for y in range(h):
        ny = y / h
        for x in range(w):
            nx = x / w
            blue = math.exp(-((nx - .12) ** 2 / .13 + (ny - .34) ** 2 / .18))
            lilac = math.exp(-((nx - .93) ** 2 / .16 + (ny - .16) ** 2 / .17))
            mint = math.exp(-((nx - .63) ** 2 / .15 + (ny - .94) ** 2 / .09))
            rgb = ((16 + 6 * blue + 10 * lilac, 23 + 13 * blue + 9 * mint,
                    36 + 29 * blue + 23 * lilac + 8 * mint) if dark else
                   (235 - 30 * blue + 3 * lilac - 18 * mint,
                    241 - 8 * blue - 24 * lilac + 3 * mint,
                    248 + 5 * blue + 2 * lilac - 13 * mint))
            p = (y * w + x) * 3
            data[p:p + 3] = bytes(max(0, min(255, round(v))) for v in rgb)
    return w, h, bytes(data)


def backdrop(w, h, theme='light'):
    sw, sh, source = ambient(theme)
    rgb = scale_rgb(source, sw, sh, w, h)
    return tk.PhotoImage(data=f'P6\n{w} {h}\n255\n'.encode() + rgb, format='PPM')


def rounded_distance(x, y, size, radius, padding, shift=0):
    center = padding + radius + .5
    qx = abs(x - center) - .5
    qy = abs(y - center - shift) - .5
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - radius


@lru_cache(maxsize=16)
def panel_pixels(theme, radius=24, padding=10, hover=False):
    """每个圆角保持原生像素密度；边缘用距离覆盖与亚像素采样生成。"""
    side = radius + padding
    size = side * 2 + 1
    pixels = bytearray(size * size * 4)
    dark = theme == 'dark'
    base = (38, 51, 73) if dark else (255, 255, 255)
    opacity = (221 if dark else 174) + (8 if hover else 0)
    for y in range(size):
        for x in range(size):
            values = []
            for ox, oy in ((.25, .25), (.75, .25), (.25, .75), (.75, .75)):
                d = rounded_distance(x + ox, y + oy, size, radius, padding)
                shadow_d = rounded_distance(x + ox, y + oy, size, radius, padding, 2)
                shadow = (37 if dark else 21) * math.exp(-max(shadow_d, 0) / 3.1) / 255
                coverage = max(0, min(1, .5 - d))
                fill_a = opacity / 255 * coverage
                # 细内沿，不把低分辨率圆角拉伸到整个窗口。
                rim = max(0, min(1, d + 1.15)) * coverage
                rim *= (.22 if dark else .65) * (1 if y <= side else .45)
                a = fill_a + shadow * (1 - fill_a)
                premult = [component / 255 * fill_a for component in base]
                a2 = rim + a * (1 - rim)
                values.append(([rim + p * (1 - rim) for p in premult], a2))
            alpha = sum(a for _, a in values) / 4
            p = (y * size + x) * 4
            if alpha:
                pixels[p:p + 4] = bytes([min(255, round(sum(rgb[k] for rgb, _ in values) / 4 / alpha * 255))
                                          for k in range(3)] + [round(alpha * 255)])
    return size, bytes(pixels)


class Panel:
    def __init__(self, theme, radius=24, padding=10, hover=False):
        self.radius, self.padding = radius, padding
        size, data = panel_pixels(theme, radius, padding, hover)
        self.source = tk.PhotoImage(data=symbols.png(size, size, data))
        side = radius + padding
        self.parts = []
        for yy, hh in ((0, side), (side, 1), (side + 1, side)):
            for xx, ww in ((0, side), (side, 1), (side + 1, side)):
                image = tk.PhotoImage(width=ww, height=hh)
                image.tk.call(str(image), 'copy', str(self.source), '-from', xx, yy, xx + ww, yy + hh)
                self.parts.append(image)
        self.geometry, self.scaled = None, None

    def draw(self, canvas, x, y, width, height):
        x, y, width, height = map(round, (x, y, width, height))
        middle_w, middle_h = max(1, width - self.radius * 2), max(1, height - self.radius * 2)
        if self.geometry != (middle_w, middle_h):
            self.scaled = [part if i % 3 != 1 and i // 3 != 1 else
                           part.zoom(middle_w if i % 3 == 1 else 1,
                                     middle_h if i // 3 == 1 else 1) for i, part in enumerate(self.parts)]
            self.geometry = middle_w, middle_h
        xs = (x - self.padding, x + self.radius, x + width - self.radius)
        ys = (y - self.padding, y + self.radius, y + height - self.radius)
        for i, image in enumerate(self.scaled):
            canvas.create_image(xs[i % 3], ys[i // 3], image=image, anchor='nw')


@lru_cache(maxsize=4)
def circle_pixels(theme, hover=False):
    """44px 圆形玻璃按钮：亚像素圆周、柔和内沿和向下的短阴影。"""
    size, center, radius = 56, 28, 22
    dark = theme == 'dark'
    pixels = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            samples = []
            for ox, oy in ((.25, .25), (.75, .25), (.25, .75), (.75, .75)):
                dx, dy = x + ox - center, y + oy - center
                d = math.hypot(dx, dy) - radius
                cover = max(0, min(1, .5 - d))
                shadow_d = math.hypot(dx, dy - 1.5) - radius
                shadow_a = (.23 if dark else .08) * math.exp(-max(0, shadow_d) / 1.6)
                fill_a = (.88 if dark else .66) * cover
                glow = max(0, min(1, (radius - dy) / (2 * radius)))
                base = ((43 + 5 * glow, 58 + 6 * glow, 82 + 8 * glow) if dark else
                        (248 + 7 * glow, 251 + 4 * glow, 255))
                if hover:
                    base = tuple(min(255, v + (9 if dark else -6)) for v in base)
                rim = max(0, min(1, d + 1)) * cover * (.11 if dark else .48) * (.35 + .65 * glow)
                a = fill_a + shadow_a * (1 - fill_a)
                rgb = [v / 255 * fill_a for v in base]
                samples.append(([rim + v * (1 - rim) for v in rgb], rim + a * (1 - rim)))
            alpha = sum(a for _, a in samples) / 4
            if alpha:
                p = (y * size + x) * 4
                pixels[p:p + 4] = bytes([min(255, round(sum(rgb[k] for rgb, _ in samples) / 4 / alpha * 255))
                                          for k in range(3)] + [round(alpha * 255)])
    return size, bytes(pixels)


class GlassRenderer:
    def __init__(self, theme='light'):
        self.theme = theme
        self.panels = {}
        self.circles = {}

    def release_surfaces(self):
        for panel in self.panels.values():
            panel.scaled = panel.geometry = None

    def circle(self, canvas, cx, cy, hover=False):
        key = self.theme, hover
        if key not in self.circles:
            size, pixels = circle_pixels(*key)
            self.circles[key] = tk.PhotoImage(data=symbols.png(size, size, pixels))
        canvas.create_image(cx, cy, image=self.circles[key])

    def panel(self, canvas, x, y, width, height, radius=24, hover=False):
        radius = min(radius, max(1, (round(min(width, height)) - 1) // 2))
        key = self.theme, radius, hover
        if key not in self.panels:
            self.panels[key] = Panel(self.theme, radius=radius, hover=hover)
        self.panels[key].draw(canvas, x, y, width, height)
