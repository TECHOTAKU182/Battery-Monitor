"""创建启动入口，默认仅项目目录；--desktop 同时创建桌面快捷方式。"""
import argparse
from pathlib import Path

import settings
import win_shell


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", action="store_true")
    args = parser.parse_args()
    paths = [settings.BASE / f"{settings.APP_NAME}.lnk"]
    if args.desktop:
        paths.append(Path(win_shell.desktop_dir()) / f"{settings.APP_NAME}.lnk")
    for path in paths:
        ok = win_shell.create_shortcut(str(path), settings.pythonw(), f'"{settings.BASE / "app.py"}"', str(settings.BASE), "查看鼠标、耳机与手柄的电量", str(settings.BASE / 'assets' / 'app.ico'))
        if not ok:
            raise OSError(f"创建快捷方式失败：{path}")
        print(path)


if __name__ == "__main__":
    main()
