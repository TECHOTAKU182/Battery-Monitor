"""仅保存用户设置；自启使用启动文件夹快捷方式。"""
import json
import os
import sys
from pathlib import Path

import win_shell

BASE = Path(__file__).resolve().parent
APP_NAME = "Battery Monitor"
CONFIG = BASE / "config.json"
INTERVALS = {"30 秒": 30, "1 分钟": 60, "2 分钟": 120, "5 分钟": 300, "10 分钟": 600, "30 分钟": 1800}
DEVICE_LABELS = {"atk": "ATK 鼠标", "logitech": "罗技 MX Master 3S", "p9500": "P9500 耳机", "dualshock": "DualShock 4 手柄"}


def normalize(config):
    if not isinstance(config, dict):
        config = {}
    value = config.get("interval", 60)
    selected = config.get("tray_devices", list(DEVICE_LABELS))
    if not isinstance(selected, list):
        selected = list(DEVICE_LABELS)
    selected = [key for key in DEVICE_LABELS if key in selected]
    theme = config.get('theme', 'light')
    return {"interval": value if type(value) is int and value in INTERVALS.values() else 60,
            "tray_devices": selected or list(DEVICE_LABELS),
            "theme": theme if theme in ('light', 'dark') else 'light'}


def load():
    try:
        return normalize(json.loads(CONFIG.read_text(encoding="utf-8")))
    except (OSError, ValueError, AttributeError):
        return normalize({})


def save(config):
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(normalize(config), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CONFIG)


def pythonw():
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate if candidate.exists() else Path(sys.executable))


def shortcut():
    return Path(win_shell.startup_dir()) / f"{APP_NAME}.lnk"


def autostart_enabled():
    if not shortcut().exists():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder") as key:
            data, _ = winreg.QueryValueEx(key, shortcut().name)
            if isinstance(data, bytes) and data and data[0] in (3, 7):
                return False
    except OSError:
        pass
    return True


def set_autostart(enabled):
    if enabled:
        ok = win_shell.create_shortcut(str(shortcut()), pythonw(), f'"{BASE / "app.py"}" --tray', str(BASE), "监测鼠标、耳机与手柄的电量")
        if not ok:
            raise OSError("无法创建启动快捷方式")
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder") as key:
            winreg.SetValueEx(key, shortcut().name, 0, winreg.REG_BINARY, b"\x02" + b"\0" * 11)
    elif shortcut().exists():
        shortcut().unlink()
