"""连接状态、读数宽限、卡片重排与托盘消失/重连的回归验证。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import devices
import native_tray
import settings
from devices import Reading
from glass_view import GlassView, KEYS, layout
from glass_render import circle_pixels


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        devices._last_readings.clear()

    def tearDown(self):
        devices._last_readings.clear()

    def test_zero_battery_and_connected_without_data_stay_visible(self):
        self.assertTrue(Reading('atk', '', '', 0).visible)
        self.assertTrue(Reading('dualshock', '', '', connected=True).visible)
        self.assertFalse(Reading('p9500', '', '', 50, connected=False).visible)
        self.assertFalse(Reading('atk', '', '').visible)

    def test_confirmed_disconnect_clears_cached_charge(self):
        devices.retain_recent(Reading('atk', '', '', 50, sampled_at=100))
        disconnected = Reading('atk', '', '', status='接收器未连接', connected=False, sampled_at=110)
        self.assertFalse(devices.retain_recent(disconnected).visible)
        self.assertNotIn('atk', devices._last_readings)
        no_reply = Reading('atk', '', '', status='暂未回复', sampled_at=120)
        self.assertFalse(devices.retain_recent(no_reply).visible)

    def test_radio_timeout_grace_expires_without_extending_old_timestamp(self):
        devices.retain_recent(Reading('logitech', '', '', 50, sampled_at=100))
        for stamp in (130, 220):
            cached = devices.retain_recent(Reading('logitech', '', '', status='暂未回复', sampled_at=stamp))
            self.assertTrue(cached.visible)
            self.assertTrue(cached.stale)
            self.assertEqual(cached.sampled_at, 100)
        self.assertFalse(devices.retain_recent(Reading('logitech', '', '', status='暂未回复', sampled_at=221)).visible)

    def test_atk_sleep_keeps_last_charge_without_expiry_and_updates_after_waking(self):
        devices.retain_recent(Reading('atk', '', '', 0, sampled_at=100, connected=True))
        for stamp in (220, 7200, 86400):
            cached = devices.retain_recent(Reading('atk', '', '', status='暂未回复', sampled_at=stamp, connected=True))
            self.assertTrue(cached.visible)
            self.assertTrue(cached.connected)
            self.assertTrue(cached.stale)
            self.assertEqual((cached.level, cached.sampled_at, cached.status), (0, 100, '休眠'))
        awake = devices.retain_recent(Reading('atk', '', '', 50, status='使用中', sampled_at=86500, connected=True))
        self.assertFalse(awake.stale)
        self.assertEqual(awake.level, 50)
        self.assertEqual(devices._last_readings['atk'].sampled_at, 86500)

    def test_atk_receiver_stays_visible_before_first_successful_charge_read(self):
        iface = SimpleNamespace(vid=0x373b, pid=0x1040, usage_page=0xff02, output_len=17, path='receiver')
        with patch.object(devices.hw, 'HidDevice') as hid, \
             patch.object(devices.time, 'monotonic', side_effect=(0, 3, 0, 3)):
            hid.return_value.__enter__.return_value._open_reader.return_value = True
            reading = devices.read_atk([iface])
        self.assertTrue(reading.connected)
        self.assertTrue(reading.visible)
        self.assertIsNone(reading.level)

    def test_atk_read_error_keeps_known_charge_without_claiming_new_measurement(self):
        devices.retain_recent(Reading('atk', '', '', 50, sampled_at=100, connected=True))
        failed = devices.retain_recent(Reading('atk', '', '', status='读取失败', detail='busy', sampled_at=86400, connected=True))
        self.assertTrue(failed.visible)
        self.assertEqual((failed.level, failed.sampled_at, failed.status), (50, 100, '读取失败'))
        self.assertTrue(failed.stale)

    def test_headset_disconnect_does_not_show_retained_windows_property(self):
        with patch.object(devices.bt_battery, 'connected_names', return_value=set()), \
             patch.object(devices.bt_battery, 'list_bluetooth_devices') as properties:
            self.assertFalse(devices.read_headset([]).visible)
            properties.assert_not_called()

    def test_connected_controller_remains_visible_if_another_app_owns_it(self):
        iface = SimpleNamespace(vid=0x054c, pid=0x09cc, input_len=64, usage_page=1, usage=5, path='controller')
        with patch.object(devices.hw, 'HidDevice', side_effect=OSError('busy')):
            reading = devices.read_dualshock([iface])
            self.assertTrue(reading.visible)
            self.assertIsNone(reading.level)
        self.assertFalse(devices.read_dualshock([]).visible)

    def test_every_device_count_fits_without_overlapping(self):
        for w, h in ((800, 680), (940, 720), (1500, 1000)):
            for count in range(5):
                boxes = layout(w, h, count)
                self.assertEqual(len(boxes), count)
                for i, (x, y, cw, ch) in enumerate(boxes):
                    self.assertGreaterEqual(x, 32)
                    self.assertGreaterEqual(y, 108)
                    self.assertLessEqual(x + cw, w - 32)
                    self.assertLessEqual(y + ch, h - 116)
                    for xx, yy, ww, hh in boxes[i + 1:]:
                        self.assertTrue(x + cw <= xx or xx + ww <= x or y + ch <= yy or yy + hh <= y)
                if count in (1, 3):
                    x, _, cw, _ = boxes[-1]
                    self.assertAlmostEqual(x + cw / 2, w / 2)

    def test_view_removes_disconnected_keys_and_restores_stable_order(self):
        view = object.__new__(GlassView)
        view.cards = {key: SimpleNamespace(reading=None) for key in KEYS}
        view.focus = 'dualshock'
        view.clear_tooltip, view.invalidate = Mock(), Mock()
        readings = [Reading('dualshock', '', '', connected=False), Reading('atk', '', '', 0)]
        view.update_readings(readings)
        self.assertEqual(view.visible_keys, ['atk'])
        self.assertIsNone(view.focus)
        view.update_readings([Reading('dualshock', '', '', 100), readings[1]])
        self.assertEqual(view.visible_keys, ['atk', 'dualshock'])

    def test_tray_disconnect_and_reconnect_replace_fallback_with_same_device_id(self):
        tray = object.__new__(native_tray.Tray)
        tray.hwnd, tray.icons, tray.selected = 1, {}, set(settings.DEVICE_LABELS)
        calls = []
        def notify(command, icon):
            calls.append((command, icon._obj.id))
            return True
        with patch.object(native_tray.S, 'Shell_NotifyIconW', notify), \
             patch.object(native_tray.win_icon, 'make_device_hicon', return_value=1):
            tray.update([Reading('dualshock', '', '', 100)])
            self.assertEqual(set(tray.icons), {4})
            tray.update([Reading('dualshock', '', '', 100, connected=False)])
            self.assertEqual(set(tray.icons), {99})
            self.assertIn((2, 4), calls)
            tray.update([Reading('dualshock', '', '', 0)])
            self.assertEqual(set(tray.icons), {4})
            self.assertIn((2, 99), calls)
            self.assertEqual(calls[-1], (0, 4))

    def test_mouse_click_clears_keyboard_highlight_before_action(self):
        view = object.__new__(GlassView)
        view.clear_tooltip, view.close_popup, view.invalidate, view.canvas = Mock(), Mock(), Mock(), Mock()
        view.keyboard_focus = True
        action = Mock(side_effect=lambda: self.assertFalse(view.keyboard_focus))
        view.find = Mock(return_value=('theme', (), action, ''))
        view.click(SimpleNamespace(x=0, y=0))
        action.assert_called_once()

    def test_button_circumference_is_symmetric_and_antialiased(self):
        for theme in ('light', 'dark'):
            size, pixels = circle_pixels(theme)
            alpha = pixels[3::4]
            self.assertGreater(len(set(alpha)), 30)
            for y in range(size):
                for x in range(size // 2):
                    self.assertEqual(alpha[y * size + x], alpha[y * size + size - x - 1])


if __name__ == '__main__':
    unittest.main()
