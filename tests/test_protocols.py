"""协议边界测试：不连接硬件。"""
import unittest
import zlib

from devices import parse_atk, parse_unified, parse_dualshock


class ProtocolTests(unittest.TestCase):
    def test_real_atk_reply(self):
        reply = bytes.fromhex("08 04 00 00 00 02 32 00 0f 12 00 00 00 00 00 00 f4")
        self.assertEqual(parse_atk(reply), (50, "使用中", "电池电压 3.86 V"))

    def test_atk_rejects_corruption(self):
        reply = bytearray.fromhex("08 04 00 00 00 02 32 00 0f 12 00 00 00 00 00 00 f4")
        reply[6] = 99
        self.assertIsNone(parse_atk(bytes(reply)))
        self.assertIsNone(parse_atk(b"\x08\x04"))

    def test_real_logitech_status_not_capability(self):
        self.assertEqual(parse_unified(bytes.fromhex("3c 08 00 00")), (60, "使用中"))
        self.assertEqual(parse_unified(bytes.fromhex("00 00 00 00")), (0, "使用中"))
        self.assertIsNone(parse_unified(bytes.fromhex("00 08 00 00")))
        self.assertEqual(parse_unified(bytes.fromhex("19 02 01 00")), (25, "充电中"))
        self.assertIsNone(parse_unified(bytes.fromhex("ff 00 00 00")))

    def test_usb_ds4_buckets(self):
        report = bytearray(64)
        report[0], report[30] = 1, 4
        self.assertEqual(parse_dualshock(bytes(report)), (45, "使用中"))
        report[30] = 0x14
        self.assertEqual(parse_dualshock(bytes(report)), (45, "充电中"))
        report[30] = 0x1B
        self.assertEqual(parse_dualshock(bytes(report)), (100, "已充满"))
        report[30] = 0x1F
        self.assertIsNone(parse_dualshock(bytes(report)))

    def test_padded_bluetooth_ds4_and_crc(self):
        report = bytearray(78)
        report[0], report[1], report[32] = 0x11, 0xC0, 10
        report[-4:] = zlib.crc32(b"\xA1" + report[:-4]).to_bytes(4, "little")
        self.assertEqual(parse_dualshock(bytes(report).ljust(547, b"\0")), (100, "使用中"))
        report[32] = 4
        self.assertIsNone(parse_dualshock(bytes(report)))
        self.assertIsNone(parse_dualshock(b"\x01" + bytes(9)))


if __name__ == "__main__":
    unittest.main()
