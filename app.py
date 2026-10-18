"""Battery Monitor：面板、通知区域与命令行。Python 标准库即可运行。"""
from __future__ import annotations

import argparse
import ctypes
import json
import queue
import sys
import threading
import time

import devices
import settings

class Application:
    def __init__(self, tray_only=False):
        import tkinter as tk
        from native_tray import Tray
        from glass_view import GlassView
        from ui_events import UiEvents
        self.tk = tk
        self.config = settings.load()
        self.root = tk.Tk()
        if tray_only:
            self.root.withdraw()
        self.root.title(settings.APP_NAME)
        self.root.configure(bg="#111a29" if self.config['theme'] == 'dark' else "#ebf0f8")
        self.root.geometry("940x720")
        self.root.minsize(800, 680)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.commands = UiEvents(self.root, self.poll_commands)
        self.busy = self.closed = False
        self.timer, self.readings = None, []
        current_label = next(k for k, v in settings.INTERVALS.items() if v == self.config["interval"])
        self.interval = tk.StringVar(value=current_label)
        self.autostart = tk.BooleanVar(value=settings.autostart_enabled())
        actions = dict(refresh=self.refresh, hide=self.hide, quit=self.quit,
                       interval=self.change_interval, autostart=self.change_autostart,
                       devices=self.toggle_tray_device, theme=self.change_theme)
        self.view = GlassView(self.root, actions, self.interval, self.autostart,
                              self.config['tray_devices'], theme=self.config['theme'])
        self.cards, self.summary, self.updated = self.view.cards, self.view.summary, self.view.updated
        self.refresh_button, self.hide_button = self.view.refresh_button, self.view.hide_button
        self.tray = None
        try:
            self.tray = Tray(lambda: self.commands.put("show"),
                             lambda: self.commands.put("tray_menu"),
                             lambda: self.commands.put("quit"),
                             lambda key: self.commands.put(("toggle_device", key)),
                             lambda: self.commands.put("refresh"), selected=self.config['tray_devices'])
            self.tray.update([])
        except OSError:
            self.root.deiconify()
            self.updated.configure(text="托盘暂不可用")
            self.hide_button.configure(state="disabled")
        icon = settings.BASE / "assets" / "app.ico"
        if icon.exists():
            self.root.iconbitmap(str(icon))
        self.root.bind("<FocusIn>", self.sync_autostart, add="+")
        self.root.after_idle(self.view.update_native_theme)
        if tray_only and self.tray:
            self.root.withdraw()
        self.root.after(150, self.refresh)

    def show(self):
        if self.closed:
            return
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.sync_autostart()

    def poll_commands(self):
        if self.closed:
            return
        while True:
            try:
                command = self.commands.get_nowait()
            except queue.Empty:
                break
            if command == "show":
                self.show()
            elif command == "refresh":
                self.refresh()
            elif command == "tray_menu" and self.tray:
                self.tray.popup_menu()
            elif isinstance(command, tuple) and command[0] == "toggle_device":
                self.toggle_tray_device(command[1])
            elif isinstance(command, tuple) and command[0] == "scan_done":
                self.pump(command[1], command[2])
            elif command == "quit":
                self.quit()
                return

    def hide(self):
        self.view.clear_tooltip()
        self.view.close_popup()
        if self.tray:
            self.view.suspend()
            self.root.withdraw()
        else:
            self.quit()

    def sync_autostart(self, _event=None):
        self.autostart.set(settings.autostart_enabled())
        self.view.invalidate()

    def change_interval(self, _event=None):
        self.config["interval"] = settings.INTERVALS[self.interval.get()]
        try:
            settings.save(self.config)
        except OSError as exc:
            from tkinter import messagebox
            messagebox.showerror("设置未保存", str(exc), parent=self.root)
        self.schedule()

    def change_theme(self, theme):
        if theme not in ('light', 'dark'):
            return
        candidate = dict(self.config, theme=theme)
        try:
            settings.save(candidate)
        except OSError as exc:
            from tkinter import messagebox
            messagebox.showerror('设置未保存', str(exc), parent=self.root)
            return
        self.config = candidate
        self.view.set_theme(theme)

    def toggle_tray_device(self, key):
        selected = self.config['tray_devices']
        if key not in settings.DEVICE_LABELS or (key in selected and len(selected) == 1):
            return
        updated = [item for item in selected if item != key] if key in selected else selected + [key]
        candidate = dict(self.config, tray_devices=updated)
        try:
            settings.save(candidate)
        except OSError as exc:
            from tkinter import messagebox
            messagebox.showerror("设置未保存", str(exc), parent=self.root)
            return
        self.config = settings.normalize(candidate)
        self.view.tray_devices = self.config['tray_devices']
        if self.tray:
            self.tray.set_selected(self.config['tray_devices'])
        self.view.invalidate()

    def change_autostart(self):
        try:
            settings.set_autostart(self.autostart.get())
        except OSError as exc:
            from tkinter import messagebox
            messagebox.showerror("无法修改开机自启", str(exc), parent=self.root)
        self.sync_autostart()

    def schedule(self):
        if self.timer:
            self.root.after_cancel(self.timer)
        self.timer = self.root.after(self.config["interval"] * 1000, self.refresh)

    def refresh(self):
        if self.closed or self.busy:
            return
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.busy = True
        self.refresh_button.configure(state="disabled", text="读取中…")
        self.updated.configure(text="正在刷新…")

        def worker():
            try:
                self.commands.put(('scan_done', devices.scan(), None))
            except Exception as exc:
                self.commands.put(('scan_done', None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def pump(self, readings, error):
        if self.closed:
            return
        self.busy = False
        self.refresh_button.configure(state="normal", text="立即刷新")
        if error:
            self.updated.configure(text="刷新失败 · 稍后重试")
        else:
            self.readings = readings
            self.view.update_readings(readings)
            if self.tray:
                self.tray.update(readings)
            count = sum(r.visible for r in readings)
            summary = f"{count} 台设备"
            self.summary.configure(text=summary)
            stamp = time.strftime("%H:%M:%S")
            self.updated.configure(text=f"{stamp} 更新")
        self.schedule()

    def quit(self):
        if self.closed:
            return
        self.closed = True
        self.commands.close()
        self.view.close()
        if self.tray:
            self.tray.close()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=f"{settings.APP_NAME}：无线设备电量面板与托盘")
    parser.add_argument("--once", action="store_true", help="查询一次并退出")
    parser.add_argument("--json", action="store_true", help="输出 JSON（配合 --once）")
    parser.add_argument("--inventory", action="store_true", help="列出本机物理 HID 设备与蓝牙电量节点")
    parser.add_argument("--tray", action="store_true", help="启动后直接收起到托盘")
    parser.add_argument("--quit", action="store_true", help="退出正在运行的面板/托盘")
    parser.add_argument("--refresh", action="store_true", help="通知运行中的面板立即刷新")
    parser.add_argument("--quit-after", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inventory:
        print(json.dumps(devices.inventory(), ensure_ascii=False, indent=2))
        return 0
    if args.once:
        readings = devices.scan()
        if args.json:
            print(json.dumps([r.as_dict() for r in readings], ensure_ascii=False, indent=2))
        else:
            for r in readings:
                level = f"{r.level}%" if r.level is not None else "--"
                print(f"{r.name}: {level} · {r.status} · {r.detail}")
        return 0
    from native_tray import K, WM_SHOW, WM_QUIT, WM_REFRESH, notify_running
    if args.quit or args.refresh:
        return 0 if notify_running(WM_QUIT if args.quit else WM_REFRESH) else 1
    mutex = K.CreateMutexW(None, False, "Local\\MyWirelessBatteryApplication")
    already_running = ctypes.get_last_error() == 183
    if already_running:
        for _ in range(10):
            if notify_running(WM_SHOW):
                K.CloseHandle(mutex)
                return 0
            time.sleep(0.2)
        K.CloseHandle(mutex)
        return 1
    try:
        try:
            ctypes.WinDLL("user32").SetProcessDPIAware()
        except OSError:
            pass
        app = Application(args.tray)
        if args.quit_after:
            app.root.after(args.quit_after * 1000, app.quit)
        app.root.mainloop()
        return 0
    finally:
        K.CloseHandle(mutex)


if __name__ == "__main__":
    sys.exit(main())
