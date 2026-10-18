"""托盘选择的持久化、稳定标识、左右键消息与环形电量边界。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import settings
import symbols
import native_tray
from devices import Reading


class TrayTests(unittest.TestCase):
    def test_settings_migrate_and_validate(self):
        old = settings.normalize({'interval': 120, 'tray_style': 'numbers'})
        self.assertNotIn('tray_style', old)
        self.assertEqual(old['tray_devices'], list(settings.DEVICE_LABELS))
        self.assertEqual(settings.normalize({'tray_devices': ['p9500', 'bogus', 'p9500']})['tray_devices'], ['p9500'])
        self.assertTrue(settings.normalize({'tray_devices': []})['tray_devices'])

    def test_selection_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(settings, 'CONFIG', Path(folder) / 'config.json'):
            settings.save({'interval': 60, 'tray_devices': ['logitech', 'p9500'], 'tray_style': 'numbers'})
            self.assertEqual(settings.load()['tray_devices'], ['logitech', 'p9500'])
            self.assertNotIn('tray_style', json.loads(settings.CONFIG.read_text(encoding='utf-8')))

    def test_clicks_are_dispatched_without_ui_reentry(self):
        tray = object.__new__(native_tray.Tray)
        tray.show, tray.open_menu, tray.refresh = Mock(), Mock(), Mock()
        tray._message(0, native_tray.WM_TRAY, 1, 0x0202)
        tray.show.assert_called_once()
        tray.refresh.assert_not_called()
        tray._message(0, native_tray.WM_TRAY, 1, 0x0205)
        tray.open_menu.assert_called_once()

    def test_hiding_device_deletes_icon_without_renumbering(self):
        tray = object.__new__(native_tray.Tray)
        tray.hwnd, tray.icons = 1, {}
        tray.selected = set(settings.DEVICE_LABELS)
        readings = [Reading(key, name, '', 50) for key, name in settings.DEVICE_LABELS.items()]
        calls = []
        def notify(command, icon):
            calls.append((command, icon._obj.id))
            return True
        with patch.object(native_tray.S, 'Shell_NotifyIconW', notify), patch.object(native_tray.win_icon, 'make_device_hicon', return_value=1):
            tray.update(readings)
            tray.set_selected(['logitech', 'p9500'])
            self.assertEqual(set(tray.icons), {2, 3})
            self.assertIn((2, 1), calls)
            self.assertIn((2, 4), calls)
            tray.set_selected(['atk', 'logitech', 'p9500'])
            self.assertEqual(set(tray.icons), {1, 2, 3})
            self.assertEqual(calls[-1], (0, 1))

    def test_ring_progress_uses_circumference(self):
        data = symbols.raster('atk', 32, (230, 237, 249), level=25)
        def pixel(x, y):
            p = (y * 32 + x) * 4
            return data[p:p + 4]
        # 25% 从顶部顺时针到右侧；底部仍是淡色轨道。
        self.assertGreater(pixel(29, 16)[3], pixel(16, 29)[3])
        self.assertNotEqual(data, symbols.raster('atk', 32, (230, 237, 249), level=100))
        self.assertEqual(len(symbols.raster('dualshock', 16, level=-1)), 16 * 16 * 4)


if __name__ == '__main__':
    unittest.main()
