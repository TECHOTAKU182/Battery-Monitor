"""轻量 Liquid Glass 风格视图：同一套符号用于卡片、操作和托盘。"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import font as tkfont

import settings
import symbols
from glass_render import GlassRenderer, ThemedCanvas, backdrop, theme_color

INK, MUTED, ACCENT = '#25344d', '#7c8aa0', '#647bd4'
FONT = 'Microsoft YaHei UI'
TITLES = {'atk': 'ATK', 'logitech': 'MX Master 3S', 'p9500': 'P9500', 'dualshock': 'DualShock 4'}
KEYS = tuple(TITLES)


def rounded(canvas, box, radius=20, **kwargs):
    x, y, r, b = box
    radius = min(radius, (r - x) / 2, (b - y) / 2)
    return canvas.create_polygon(x + radius, y, r - radius, y, r, y, r, y + radius,
                                 r, b - radius, r, b, r - radius, b, x + radius, b,
                                 x, b, x, b - radius, x, y + radius, x, y,
                                 smooth=True, splinesteps=28, **kwargs)


def layout(w, h, count=4):
    """卡片等宽、整体居中；奇数行也保持视觉重心。"""
    count = max(0, min(4, count))
    if not count:
        return []
    gap, top, available_h = 18, 108, h - 224
    if count == 1:
        cw, ch = min(620, w - 96), min(350, available_h)
        return [((w - cw) / 2, top + (available_h - ch) / 2, cw, ch)]
    grid_w = min(1040, w - 64)
    cw = (grid_w - gap) / 2
    rows = 1 if count == 2 else 2
    ch = min(330 if rows == 1 else 300, (available_h - gap * (rows - 1)) / rows)
    y = top + (available_h - ch * rows - gap * (rows - 1)) / 2
    left = (w - grid_w) / 2
    return [((w - cw) / 2 if count == 3 and i == 2 else left + (i % 2) * (cw + gap),
             y + (i // 2) * (ch + gap), cw, ch) for i in range(count)]


class Value:
    def __init__(self, view, text='', command=None):
        self.view, self.text, self.command, self.state = view, text, command, 'normal'

    def configure(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.view.invalidate()


class Card:
    def __init__(self, view, key):
        self.view, self.key, self.reading = view, key, None

    def update(self, reading):
        self.reading = reading
        self.view.invalidate()


class GlassView:
    def __init__(self, root, actions, interval, autostart, tray_devices, theme="light"):
        self.root, self.actions = root, actions
        self.theme = theme
        self.renderer = GlassRenderer(theme)
        self.fonts = {}
        self.interval, self.autostart, self.tray_devices = interval, autostart, tray_devices
        self.canvas = ThemedCanvas(root, theme=theme, bg='#ebf0f8', highlightthickness=0, takefocus=True)
        self.canvas.pack(fill='both', expand=True)
        self.cards = {key: Card(self, key) for key in KEYS}
        self.visible_keys = []
        self.scanned = False
        self.summary, self.updated = Value(self, '…'), Value(self, '正在连接设备')
        self.refresh_button = Value(self, command=actions['refresh'])
        self.hide_button = Value(self, command=actions['hide'])
        self.hover, self.focus, self.hits = None, None, []
        self.keyboard_focus = False
        self.background, self.background_size, self.images = None, None, {}
        self.pending, self.tooltip_job, self.tooltip, self.popup = None, None, None, None
        self.canvas.bind('<Configure>', self.resize)
        self.canvas.bind('<Motion>', self.motion)
        self.canvas.bind('<Leave>', self.leave)
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.bind('<Tab>', self.tab)
        self.canvas.bind('<Shift-Tab>', lambda e: self.tab(e, -1))
        self.canvas.bind('<Return>', self.activate)
        self.canvas.bind('<space>', self.activate)
        root.bind('<F5>', lambda _: actions['refresh']())
        root.bind('<Escape>', lambda _: self.close_popup() if self.popup else actions['hide']())
        root.bind('<Control-comma>', lambda _: self.preferences())
        self._closed = False
        self._visible = root.state() not in ('withdrawn', 'iconic')
        root.bind('<Map>', self.mapped, add='+')
        root.bind('<Unmap>', self.unmapped, add='+')

    def mapped(self, event):
        if event.widget == self.root:
            self._visible = True
            self.invalidate()

    def unmapped(self, event):
        if event.widget == self.root:
            self.suspend()

    def suspend(self):
        """收起时释放随窗口面积增长的位图，保留小图标以便快速再打开。"""
        self._visible = False
        self.clear_tooltip()
        self.close_popup()
        if self.pending is not None:
            self.root.after_cancel(self.pending)
            self.pending = None
        self.canvas.delete('all')
        self.background, self.background_size = None, None
        self.renderer.release_surfaces()

    def update_readings(self, readings):
        self.scanned = True
        for reading in readings:
            if reading.key in self.cards:
                self.cards[reading.key].reading = reading
        visible = {r.key for r in readings if r.visible}
        self.visible_keys = [key for key in KEYS if key in visible]
        if self.focus in KEYS and self.focus not in visible:
            self.focus = None
        self.clear_tooltip()
        self.invalidate()

    def invalidate(self):
        if not self._closed and self._visible and self.pending is None:
            self.pending = self.root.after_idle(self.paint)

    def resize(self, _event=None):
        if not self._closed and self._visible and self.pending is None:
            self.pending = self.root.after(16, self.paint)

    def update_native_theme(self):
        background = theme_color('#eaf0f8', self.theme)
        self.root.configure(bg=background)
        native_material(self.root, background, dark=self.theme == 'dark')

    def set_theme(self, theme):
        if theme == self.theme:
            return
        self.clear_tooltip()
        self.close_popup()
        self.theme = theme
        self.renderer.theme = theme
        self.canvas.theme = theme
        self.canvas.configure(bg=theme_color('#ebf0f8', theme))
        self.background_size = None
        self.update_native_theme()
        self.invalidate()

    def toggle_theme(self):
        self.actions['theme']('dark' if self.theme == 'light' else 'light')

    def select_theme(self, theme):
        self.actions['theme'](theme)
        self.preferences()

    def image(self, key, size, color=INK, width=1.8):
        size = max(8, round(size))
        color = theme_color(color, self.theme)
        token = key, size, color, width
        if token not in self.images:
            rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
            self.images[token] = tk.PhotoImage(data=symbols.png(size, size, symbols.raster(key, size, rgb, width)))
        return self.images[token]

    def icon(self, key, cx, cy, size=24, color=INK, canvas=None, width=1.8):
        (canvas or self.canvas).create_image(cx, cy, image=self.image(key, size, color, width))

    def text(self, x, y, text, size=13, color=INK, anchor='w', bold=False, canvas=None, **kwargs):
        return (canvas or self.canvas).create_text(x, y, text=text, anchor=anchor, fill=color,
                       font=(FONT, -round(size), 'bold' if bold else 'normal'), **kwargs)

    def hit(self, key, box, action, tooltip):
        self.hits.append((key, box, action, tooltip))

    def circle_button(self, key, cx, cy, icon, action, tooltip, disabled=False):
        box = cx - 22, cy - 22, cx + 22, cy + 22
        self.renderer.circle(self.canvas, cx, cy, hover=self.hover == key and not disabled)
        self.icon(icon, cx, cy, 22, '#acb6c7' if disabled else INK, width=1.65)
        if self.keyboard_focus and self.focus == key:
            self.canvas.create_oval(cx - 1.5, cy + 27, cx + 1.5, cy + 30, fill=ACCENT, outline='')
        if not disabled:
            self.hit(key, box, action, tooltip)

    def paint(self):
        self.pending = None
        if self._closed or not self._visible:
            return
        c = self.canvas
        w, h = max(760, c.winfo_width()), max(620, c.winfo_height())
        if self.background_size != (w, h):
            self.background = backdrop(w, h, self.theme)
            self.background_size = w, h
        c.delete('all')
        c.create_image(0, 0, image=self.background, anchor='nw')
        self.hits = []
        self.icon('battery', 47, 52, 28, ACCENT)
        self.text(72, 51, '电量', 25, bold=True)
        self.text(146, 54, self.summary.text, 12, MUTED)
        self.circle_button('refresh', w - 222, 53, 'refresh', self.actions['refresh'], '刷新电量 · F5', self.refresh_button.state == 'disabled')
        self.circle_button('theme', w - 166, 53, 'moon' if self.theme == 'light' else 'sun', self.toggle_theme, '切换到深色' if self.theme == 'light' else '切换到浅色')
        self.circle_button('hide', w - 110, 53, 'tray', self.actions['hide'], '收起到托盘', self.hide_button.state == 'disabled')
        self.circle_button('settings', w - 54, 53, 'settings', self.preferences, '偏好设置 · Ctrl + ,')
        for key, box in zip(self.visible_keys, layout(w, h, len(self.visible_keys))):
            self.draw_card(key, box)
        if not self.visible_keys:
            cy = 108 + (h - 224) / 2
            self.icon('wireless', w / 2, cy - 40, 64, MUTED, width=1.1)
            self.text(w / 2, cy + 20, '暂无已连接设备' if self.scanned else '正在发现设备', 18, anchor='center')
            self.text(w / 2, cy + 53, '连接后将自动显示' if self.scanned else '读取无线设备电量…', 12, MUTED, anchor='center')
        self.draw_dock(w, h)

    def draw_card(self, key, box):
        c = self.canvas
        x, y, w, h = box
        r = self.cards[key].reading
        active = r is not None and r.level is not None and not r.stale
        self.renderer.panel(c, x, y, w, h, hover=self.hover == key or (self.keyboard_focus and self.focus == key))
        tint = '#34a77f' if active and r.level >= 60 else '#c39035' if active and r.level >= 30 else '#d16a7d' if active else '#9ba7b7'
        self.text(x + 26, y + 29, TITLES[key], 15, bold=True)
        connection = ('usb' if key == 'dualshock' and r and r.connection == 'USB' else
                      'bluetooth' if key in ('p9500', 'dualshock') else 'wireless')
        self.icon(connection, x + 33, y + 58, 16, MUTED)
        self.text(x + 48, y + 59, {'wireless': '2.4G', 'bluetooth': 'Bluetooth', 'usb': 'USB'}[connection], 11, MUTED)
        if r and r.stale:
            rounded(c, (x + w - 65, y + 18, x + w - 21, y + 39), 10, fill='#e8edf4', outline='')
            self.text(x + w - 43, y + 28, '上次', 10, MUTED, anchor='center')
        else:
            c.create_oval(x + w - 32, y + 25, x + w - 26, y + 31, fill=tint, outline='')
        # 大尺寸设备轮廓，识别设备时不依赖长说明。
        hero = len(self.visible_keys) == 1
        self.icon(key, x + w - (112 if hero else 81), y + h * .51, 144 if hero else 96,
                  '#798ba9' if active else '#a6b2c5', width=1.25)
        number = str(r.level) if r and r.level is not None else '—'
        cy = y + h * .50
        number_color = '#293d5e' if active else '#97a4b8'
        number_size = min(84 if hero else 59, round(h * .26))
        if number_size not in self.fonts:
            self.fonts[number_size] = tkfont.Font(family='Segoe UI Variable Display', size=-number_size)
        f = self.fonts[number_size]
        c.create_text(x + 24, cy, text=number, anchor='w', fill=number_color, font=f)
        if r and r.level is not None:
            percent_x = x + 28 + f.measure(number)
            self.text(percent_x, cy + 12, '%', 21, '#96a4bb')
        status = ('等待连接' if r is None else '休眠 · 上次电量' if r.stale and r.status == '休眠' else
                  '上次读数' if r.stale else
                  '待唤醒' if r.level is None and r.status == '暂未回复' else
                  '暂无数据' if r.level is None and r.status == '暂无电量数据' else
                  '暂不可读' if r.level is None else '充电中' if '充电' in r.status else
                  '已充满' if '满' in r.status else '')
        if status:
            self.text(x + 27, y + h - 69, status, 11, MUTED)
        if r and r.level is not None and '充电' in r.status:
            self.icon('bolt', x + 87, y + h - 70, 15, tint)
        if r and r.stale:
            stamp = time.strftime('%H:%M', time.localtime(r.sampled_at))
            self.text(x + w - 27, y + h - 69, stamp, 11, MUTED, anchor='e')
        # 细圆角电量轨道，电量色只占一小部分视觉面积。
        left, right, by = x + 27, x + w - 27, y + h - 37
        c.create_line(left, by, right, by, fill='#dde4ef', width=4, capstyle='round')
        if r and r.level is not None:
            end = left + (right - left) * r.level / 100
            if end > left:
                c.create_line(left, by, end, by, fill=tint, width=4, capstyle='round')
        tooltip = TITLES[key] + (' · 点击查看详情' if r is None else f" · {r.level if r.level is not None else '—'}{'%' if r.level is not None else ''}\n{r.status} · 点击查看详情")
        self.hit(key, (x, y, x + w, y + h), lambda k=key: self.details(k), tooltip)

    def draw_dock(self, w, h):
        c = self.canvas
        dw, dh = 286, 52
        x, y = (w - dw) / 2, h - 91
        self.renderer.panel(c, x, y, dw, dh, radius=26)
        self.icon('clock', x + 29, y + 26, 21, '#7c8fae')
        self.text(x + 49, y + 27, self.interval.get(), 12)
        self.icon('chevron', x + 111, y + 27, 14, MUTED)
        c.create_line(x + 135, y + 15, x + 135, y + 37, fill='#d9e1ed', width=1)
        self.icon('power', x + 163, y + 26, 20, ACCENT if self.autostart.get() else MUTED)
        sx = x + 188
        enabled = self.autostart.get()
        rounded(c, (sx, y + 16, sx + 33, y + 36), 10, fill='#97abe2' if enabled else '#d5deec', outline='')
        knob = sx + (23 if enabled else 10)
        c.create_oval(knob - 7, y + 19, knob + 7, y + 33, fill='white', outline='')
        c.create_line(x + 237, y + 15, x + 237, y + 37, fill='#d9e1ed', width=1)
        self.icon('info', x + 261, y + 26, 19, MUTED)
        self.hit('interval', (x + 9, y + 6, x + 128, y + 46), self.preferences, '自动刷新间隔')
        self.hit('autostart', (x + 144, y + 6, x + 228, y + 46), self.toggle_autostart, '开机自启：' + ('已开启' if enabled else '已关闭'))
        self.hit('about', (x + 245, y + 6, x + 280, y + 46), self.about, '使用说明')
        self.text(w / 2, h - 19, self.updated.text, 10, MUTED, anchor='center')

    def find(self, x, y):
        return next((hit for hit in self.hits if hit[1][0] <= x <= hit[1][2] and hit[1][1] <= y <= hit[1][3]), None)

    def motion(self, event):
        hit = self.find(event.x, event.y)
        key = hit[0] if hit else None
        if key != self.hover:
            self.clear_tooltip()
            self.hover = key
            self.canvas.configure(cursor='hand2' if hit else '')
            self.invalidate()
            if hit:
                text, px, py = hit[3], event.x_root, event.y_root
                self.tooltip_job = self.root.after(650, lambda: self.show_tooltip(text, px, py))

    def leave(self, _event):
        self.hover = None
        self.clear_tooltip()
        self.invalidate()

    def click(self, event):
        self.clear_tooltip()
        self.close_popup()
        self.canvas.focus_set()
        self.keyboard_focus = False
        self.invalidate()
        hit = self.find(event.x, event.y)
        if hit:
            self.focus = hit[0]
            hit[2]()

    def tab(self, _event, direction=1):
        self.keyboard_focus = True
        keys = [hit[0] for hit in self.hits]
        if keys:
            i = keys.index(self.focus) if self.focus in keys else -1
            self.focus = keys[(i + direction) % len(keys)]
            self.invalidate()
        return 'break'

    def activate(self, _event):
        hit = next((hit for hit in self.hits if hit[0] == self.focus), None)
        if hit:
            hit[2]()
        return 'break'

    def clear_tooltip(self):
        if self.tooltip_job:
            self.root.after_cancel(self.tooltip_job)
            self.tooltip_job = None
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def show_tooltip(self, text, x, y):
        if self._closed:
            return
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)
        self.tooltip.attributes('-topmost', True)
        label = tk.Label(self.tooltip, text=text, bg=theme_color('#f7f9fd', self.theme), fg=theme_color(INK, self.theme), font=(FONT, -11), padx=11, pady=7,
                         justify='left', relief='solid', borderwidth=1)
        label.pack()
        self.tooltip.update_idletasks()
        x = min(x + 12, self.root.winfo_screenwidth() - self.tooltip.winfo_reqwidth() - 8)
        y = min(y + 19, self.root.winfo_screenheight() - self.tooltip.winfo_reqheight() - 8)
        self.tooltip.geometry(f'+{max(0, x)}+{max(0, y)}')

    def open_popup(self, width, height, title):
        self.clear_tooltip()
        self.close_popup()
        pop = self.popup = tk.Toplevel(self.root)
        pop.title(title)
        pop.transient(self.root)
        pop.resizable(False, False)
        pop.configure(bg=theme_color('#f4f7fc', self.theme))
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        pop.geometry(f'{width}x{height}+{x}+{y}')
        pop.bind('<Escape>', lambda _: self.close_popup())
        c = ThemedCanvas(pop, theme=self.theme, bg='#f4f7fc', highlightthickness=0)
        c.pack(fill='both', expand=True)
        pop.after_idle(lambda: native_material(pop, theme_color('#f4f7fc', self.theme), backdrop=2, dark=self.theme == 'dark'))
        return c

    def close_popup(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def toggle_autostart(self):
        self.autostart.set(not self.autostart.get())
        self.actions['autostart']()
        self.invalidate()

    def preferences(self):
        c = self.open_popup(356, 406, '偏好设置')
        self.icon('settings', 32, 35, 23, ACCENT, c)
        self.text(56, 35, '偏好设置', 16, bold=True, canvas=c)
        self.text(25, 78, '刷新间隔', 11, MUTED, canvas=c)
        buttons = []
        labels = ('30 秒', '1 分钟', '2 分钟', '5 分钟', '10 分钟', '30 分钟')
        for i, label in enumerate(labels):
            x, y = 24 + i % 3 * 105, 96 + i // 3 * 39
            chosen = self.interval.get() == label
            rounded(c, (x, y, x + 96, y + 31), 14, fill='#e1e8fb' if chosen else '#ffffff', outline='#d4ddf1' if chosen else '#e9edf5')
            self.text(x + 48, y + 16, label, 11, ACCENT if chosen else INK, anchor='center', canvas=c)
            buttons.append(((x, y, x + 96, y + 31), lambda v=label: self.set_interval(v)))
        self.text(25, 195, '外观', 11, MUTED, canvas=c)
        for i, (value, label, symbol) in enumerate((('light', 'Light', 'sun'), ('dark', 'Dark', 'moon'))):
            x = 137 + i * 98
            chosen = self.theme == value
            rounded(c, (x, 181, x + 92, 213), 14, fill='#e1e8fb' if chosen else '#ffffff', outline='')
            self.icon(symbol, x + 19, 197, 17, ACCENT if chosen else MUTED, c)
            self.text(x + 35, 197, label, 11, ACCENT if chosen else INK, canvas=c)
            buttons.append(((x, 181, x + 92, 213), lambda t=value: self.select_theme(t)))
        self.text(25, 247, '托盘显示', 11, MUTED, canvas=c)
        rounded(c, (208, 233, 328, 264), 14, fill='#e1e8fb', outline='')
        self.text(268, 249, f'{len(self.tray_devices)} 个设备', 11, ACCENT, anchor='center', canvas=c)
        buttons.append(((208, 233, 328, 264), self.tray_preferences))
        self.text(25, 298, '开机启动', 12, canvas=c)
        enabled = self.autostart.get()
        rounded(c, (282, 287, 328, 311), 12, fill='#91a6df' if enabled else '#d4ddeb', outline='')
        knob = 315 if enabled else 295
        c.create_oval(knob - 8, 291, knob + 8, 307, fill='white', outline='')
        buttons.append(((265, 278, 334, 319), self.popup_autostart))
        c.create_line(25, 334, 331, 334, fill='#e0e7f1')
        self.icon('power', 36, 367, 20, '#bf7380', c)
        self.text(58, 367, '退出程序', 12, '#a7606e', canvas=c)
        buttons.append(((22, 345, 331, 389), self.actions['quit']))
        self.bind_popup(c, buttons)

    def bind_popup(self, c, buttons):
        def clicked(event):
            for (x1, y1, x2, y2), action in buttons:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    action()
                    return
        c.bind('<Button-1>', clicked)
        c.configure(cursor='hand2')

    def popup_autostart(self):
        self.toggle_autostart()
        self.preferences()

    def set_interval(self, label):
        self.interval.set(label)
        self.actions['interval']()
        self.preferences()

    def tray_preferences(self):
        c = self.open_popup(356, 316, '托盘显示设备')
        self.text(25, 32, '托盘显示设备', 16, bold=True, canvas=c)
        buttons = []
        for index, (key, label) in enumerate(settings.DEVICE_LABELS.items()):
            y = 78 + index * 53
            self.icon(key, 42, y, 27, ACCENT, c)
            self.text(69, y, label, 12, canvas=c)
            selected = key in self.tray_devices
            rounded(c, (298, y - 10, 318, y + 10), 5, fill=ACCENT if selected else '#ffffff', outline='#c7d2e7')
            if selected:
                self.icon('check', 308, y, 16, '#f9fcff', c)
            if not selected or len(self.tray_devices) > 1:
                buttons.append(((24, y - 23, 331, y + 23), lambda k=key: self.toggle_device(k)))
        self.text(25, 290, '至少保留一个托盘入口', 10, MUTED, canvas=c)
        self.bind_popup(c, buttons)

    def toggle_device(self, key):
        self.actions['devices'](key)
        self.tray_preferences()

    def details(self, key):
        r = self.cards[key].reading
        c = self.open_popup(392, 244, TITLES[key])
        self.icon(key, 45, 48, 42, ACCENT, c, width=1.4)
        self.text(82, 39, TITLES[key], 16, bold=True, canvas=c)
        self.text(82, 65, r.status if r else '等待连接', 11, MUTED, canvas=c)
        if r:
            self.text(27, 112, r.source, 12, canvas=c)
            self.text(27, 148, r.detail, 11, MUTED, canvas=c, width=338)
            self.text(27, 211, time.strftime('读取于 %H:%M:%S', time.localtime(r.sampled_at)), 10, MUTED, canvas=c)

    def about(self):
        c = self.open_popup(356, 236, '使用说明')
        self.icon('battery', 42, 43, 34, ACCENT, c)
        self.text(72, 43, settings.APP_NAME, 17, bold=True, canvas=c)
        for y, key, text in ((96, 'refresh', '点击刷新 · F5'), (132, 'tray', '关闭窗口后，仍在托盘运行'),
                             (168, 'info', '悬停看状态，点击卡片看详情')):
            self.icon(key, 39, y, 20, MUTED, c)
            self.text(62, y, text, 12, canvas=c)
        self.text(29, 211, '托盘左键打开 · 右键选择设备或退出', 10, MUTED, canvas=c)

    def close(self):
        self._closed = True
        self.clear_tooltip()
        self.close_popup()
        if self.pending:
            self.root.after_cancel(self.pending)


def native_material(root, background='#eaf0f8', backdrop=2, dark=False):
    """Windows 11 原生圆角及主题标题栏；不支持时保留 Canvas 外观。"""
    import ctypes as c
    try:
        user = c.WinDLL('user32')
        user.GetParent.argtypes, user.GetParent.restype = [c.c_void_p], c.c_void_p
        hwnd = user.GetParent(root.winfo_id())
        dwm = c.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [c.c_void_p, c.c_uint, c.c_void_p, c.c_uint]
        for attribute, value in ((20, int(dark)), (33, 2), (38, backdrop),
                                 (35, int(background[5:7] + background[3:5] + background[1:3], 16))):
            data = c.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attribute, c.byref(data), c.sizeof(data))
    except (OSError, AttributeError, tk.TclError):
        pass
