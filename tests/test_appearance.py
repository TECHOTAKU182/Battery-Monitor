"""主题持久化、缩放帧合并与圆角缓存的回归测试，无窗口或硬件操作。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from glass_render import Panel, panel_pixels
from glass_view import GlassView
import settings


class AppearanceTests(unittest.TestCase):
    def test_theme_survives_restart_without_resetting_devices(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, 'CONFIG', Path(directory) / 'config.json'):
            settings.save({'theme': 'dark', 'interval': 120, 'tray_devices': ['atk', 'p9500']})
            config = settings.load()
            self.assertEqual(config['theme'], 'dark')
            self.assertEqual(config['tray_devices'], ['atk', 'p9500'])
            self.assertEqual(config['interval'], 120)
            settings.save(dict(config, theme='light'))
            self.assertEqual(settings.load()['theme'], 'light')
            self.assertEqual(settings.load()['tray_devices'], config['tray_devices'])

    def test_old_or_invalid_config_defaults_to_light(self):
        self.assertEqual(settings.normalize({})['theme'], 'light')
        self.assertEqual(settings.normalize({'theme': 'broken'})['theme'], 'light')

    def test_continuous_resize_does_not_postpone_the_frame(self):
        view = object.__new__(GlassView)
        view.root, view.pending, view.paint = Mock(), None, Mock()
        view._closed, view._visible = False, True
        view.root.after.return_value = 'frame'
        for _ in range(30):
            view.resize()
        view.root.after.assert_called_once_with(16, view.paint)
        view.root.after_cancel.assert_not_called()

    def test_corners_keep_their_native_pixels_across_sizes(self):
        panel = object.__new__(Panel)
        panel.radius, panel.padding, panel.geometry = 24, 10, None
        panel.parts = [Mock() for _ in range(9)]
        canvas = Mock()
        panel.draw(canvas, 32, 114, 420, 236)
        initial = list(panel.scaled)
        panel.draw(canvas, 32, 114, 720, 400)
        for index in (0, 2, 6, 8):
            self.assertIs(initial[index], panel.scaled[index])
            panel.parts[index].zoom.assert_not_called()
        self.assertEqual(panel.geometry, (672, 352))

    def test_both_glass_surfaces_have_soft_transparent_edges(self):
        for theme in ('light', 'dark'):
            size, pixels = panel_pixels(theme)
            alpha = pixels[3::4]
            self.assertEqual(alpha[0], 0)
            self.assertGreater(alpha[(size // 2) * size + size // 2], 100)
            self.assertGreater(len(set(alpha)), 30)
            self.assertIs(panel_pixels(theme)[1], pixels)


if __name__ == '__main__':
    unittest.main()
