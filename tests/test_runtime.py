"""后台消息唤醒、隐藏窗口、托盘差量更新及原生资源上限。"""
from collections import OrderedDict
from dataclasses import replace
import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import Application
from devices import Reading
from glass_render import GlassRenderer
from glass_view import GlassView
from ui_events import UiEvents
import hid_win
import native_tray
import symbols
import win_icon


class RuntimeTests(unittest.TestCase):
    def test_queue_waits_for_messages_without_calling_tk_from_native_callback(self):
        root = Mock()
        events = UiEvents(root, Mock())
        # 原生 WndProc 在主线程只执行 put，不允许重入 Tk。
        events.put('show')
        root.event_generate.assert_not_called()
        notified = threading.Event()
        root.event_generate.side_effect = lambda *a, **kw: notified.set()
        events.start()
        self.assertTrue(notified.wait(1))
        self.assertEqual(events.get_nowait(), 'show')
        events.close()
        events.thread.join(1)
        self.assertFalse(events.thread.is_alive())
        root.after.assert_not_called()
        root.after_idle.assert_called_once()
        events.put('late')
        with self.assertRaises(queue.Empty):
            events.get_nowait()

    def test_burst_of_commands_is_delivered_in_order(self):
        events = UiEvents(Mock(), Mock())
        for index in range(1000):
            events.put(index)
        self.assertEqual([events.get_nowait() for _ in range(1000)], list(range(1000)))
        events.close()

    def test_commands_and_scan_results_do_not_schedule_polling_timers(self):
        app = object.__new__(Application)
        app.closed, app.commands, app.root, app.pump = False, queue.SimpleQueue(), Mock(), Mock()
        app.commands.put(('scan_done', [], None))
        app.poll_commands()
        app.pump.assert_called_once_with([], None)
        app.root.after.assert_not_called()

    def test_worker_signals_completion_without_result_polling(self):
        app = object.__new__(Application)
        app.closed = app.busy = False
        app.timer, app.commands, app.root = None, queue.Queue(), Mock()
        app.refresh_button, app.updated = Mock(), Mock()
        with patch('devices.scan', return_value=[]):
            app.refresh()
            self.assertEqual(app.commands.get(timeout=1), ('scan_done', [], None))
        app.root.after.assert_not_called()

    def test_hidden_view_schedules_no_frames_and_releases_large_surfaces(self):
        view = object.__new__(GlassView)
        view.root, view.canvas, view.renderer = Mock(), Mock(), Mock()
        view.clear_tooltip, view.close_popup = Mock(), Mock()
        view._closed, view._visible, view.pending = False, True, 'frame'
        view.background, view.background_size = object(), (1600, 1000)
        view.suspend()
        view.root.after_cancel.assert_called_once_with('frame')
        self.assertIsNone(view.background)
        self.assertIsNone(view.background_size)
        view.renderer.release_surfaces.assert_called_once()
        view.invalidate()
        view.resize()
        view.root.after.assert_not_called()
        view.root.after_idle.assert_not_called()
        view.mapped(SimpleNamespace(widget=view.root))
        view.root.after_idle.assert_called_once_with(view.paint)

    def test_large_panel_images_are_released_but_small_corner_cache_survives(self):
        renderer = GlassRenderer()
        small = [object() for _ in range(9)]
        panel = SimpleNamespace(parts=small, scaled=[object()], geometry=(500, 300))
        renderer.panels['test'] = panel
        renderer.release_surfaces()
        self.assertIsNone(panel.scaled)
        self.assertIsNone(panel.geometry)
        self.assertIs(panel.parts, small)

    def test_unchanged_tray_icons_do_not_redraw_and_new_timestamp_updates_only_tip(self):
        tray = object.__new__(native_tray.Tray)
        tray.hwnd, tray.icons, tray.selected = 1, {}, {'logitech'}
        reading = Reading('logitech', 'MX Master', '', 60, sampled_at=100)
        calls = []
        def notify(command, pointer):
            calls.append((command, pointer._obj.flags))
            return True
        with patch.object(native_tray.S, 'Shell_NotifyIconW', notify), \
             patch.object(win_icon, 'make_device_hicon', return_value=10):
            tray.update([reading])
            tray.update([reading])
            self.assertEqual(calls, [(0, 7)])
            tray.update([replace(reading, sampled_at=101)])
            self.assertEqual(calls[-1], (1, 4))

    def test_icon_cache_is_bounded_releases_evicted_handles_and_never_writes_files(self):
        with patch.object(win_icon, '_icon_cache', OrderedDict()), \
             patch.object(win_icon, 'MAX_CACHED_ICONS', 3), \
             patch.object(win_icon, 'taskbar_ink', return_value=(255, 255, 255)), \
             patch.object(win_icon.user32, 'GetSystemMetrics', return_value=20), \
             patch.object(win_icon.user32, 'CreateIconFromResourceEx', side_effect=(10, 11, 12, 13)), \
             patch.object(win_icon.user32, 'DestroyIcon') as destroy, \
             patch.object(symbols, 'raster', return_value=bytes(20 * 20 * 4)) as raster, \
             patch('builtins.open', side_effect=AssertionError('Unexpected disk I/O')):
            for level in (50, 51, 52, 50, 53):
                win_icon.make_device_hicon('atk', level)
            self.assertEqual(len(win_icon._icon_cache), 3)
            self.assertEqual(raster.call_count, 4)
            destroy.assert_called_once()
            self.assertEqual(destroy.call_args.args[0].value, 11)
            win_icon.destroy_all()
            self.assertFalse(win_icon._icon_cache)
            self.assertEqual(destroy.call_count, 4)

    def test_normal_hid_wait_uses_deadline_instead_of_short_polling(self):
        device = object.__new__(hid_win.HidDevice)
        device._caps = SimpleNamespace(InputReportByteLength=17)
        device._open_reader = Mock(return_value=True)
        device._read_event, device._read_handle = 7, 8
        with patch.object(hid_win.kernel32, 'ReadFile', return_value=False), \
             patch.object(hid_win.kernel32, 'ResetEvent'), \
             patch.object(hid_win.kernel32, 'WaitForSingleObject', return_value=0) as wait, \
             patch.object(hid_win.kernel32, 'GetOverlappedResult', return_value=True), \
             patch.object(hid_win.ctypes, 'get_last_error', return_value=997), \
             patch.object(hid_win.time, 'monotonic', return_value=100):
            device.read_input(timeout_ms=2000)
            wait.assert_called_once_with(7, 2000)

    def test_failed_hid_read_stops_immediately_instead_of_spinning_until_timeout(self):
        device = object.__new__(hid_win.HidDevice)
        device._caps = SimpleNamespace(InputReportByteLength=17)
        device._open_reader = Mock(return_value=True)
        device._read_event, device._read_handle = 7, 8
        with patch.object(hid_win.kernel32, 'ReadFile', return_value=False), \
             patch.object(hid_win.kernel32, 'ResetEvent'), \
             patch.object(hid_win.kernel32, 'WaitForSingleObject') as wait, \
             patch.object(hid_win.ctypes, 'get_last_error', return_value=1167):
            with self.assertRaises(hid_win.HidError):
                device.read_input(timeout_ms=2000)
            wait.assert_not_called()

    def test_hid_battery_scan_skips_name_and_serial_queries(self):
        with patch.object(hid_win.kernel32, 'CreateFileW', return_value=1), \
             patch.object(hid_win.kernel32, 'CloseHandle'), \
             patch.object(hid_win.hid, 'HidD_GetAttributes', return_value=False), \
             patch.object(hid_win.hid, 'HidD_GetPreparsedData', return_value=False), \
             patch.object(hid_win, '_wide_string') as strings:
            interface = hid_win._probe_interface('hid#vid_373b&pid_1040', strings=False)
            strings.assert_not_called()
            self.assertEqual((interface.vid, interface.pid), (0x373b, 0x1040))


if __name__ == '__main__':
    unittest.main()
