"""本机四台无线设备的电量读取。"""
from __future__ import annotations

import ctypes
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from typing import Optional

import bt_battery
import hid_win as hw

TARGET_IDS = {(0x373B, 0x1040), (0x046D, 0xC548),
              (0x054C, 0x05C4), (0x054C, 0x09CC), (0x054C, 0x0BA0)}


@dataclass
class Reading:
    key: str
    name: str
    connection: str
    level: Optional[int] = None
    status: str = "未读取"
    source: str = ""
    detail: str = ""
    sampled_at: float = field(default_factory=time.time)
    stale: bool = False
    connected: Optional[bool] = None

    @property
    def visible(self):
        # 电量为 0 仍是在线；确认断开优先于任何旧电量。
        return self.connected if self.connected is not None else self.level is not None

    def as_dict(self):
        return asdict(self)


def parse_atk(report: bytes) -> tuple[int, str, str] | None:
    # V1: report 08, opcode 04, sum(payload) == 4D; 电量为下标 6。
    if len(report) != 17 or report[:2] != b"\x08\x04":
        return None
    if sum(report[1:]) & 255 != 0x4D or report[6] > 100:
        return None
    voltage = int.from_bytes(report[8:10], "big")
    return report[6], "充电中" if report[7] == 1 else "使用中", f"电池电压 {voltage / 1000:.2f} V"


def read_atk(interfaces) -> Reading:
    r = Reading("atk", "ATK / VXE 鼠标", "2.4G · MAD 8K", source="ATK V1 电量协议")
    iface = next((d for d in interfaces if (d.vid, d.pid, d.usage_page, d.output_len)
                  == (0x373B, 0x1040, 0xFF02, 17)), None)
    if not iface:
        r.connected = False
        r.status, r.detail = "接收器未连接", "未发现 MAD 8K 接收器（373B:1040）"
        return r
    # ATK 休眠不回复电量查询；按接收器存在视为在线。
    r.connected = True
    try:
        with hw.HidDevice(iface.path, write=True) as dev:
            if not dev._open_reader():
                raise hw.HidError("无法打开接收器读取接口")
            for attempt in range(2):
                dev.drain()
                dev.write_output(bytes([8, 4] + [0] * 14 + [0x49]), use_hidd=attempt == 0)
                end = time.monotonic() + 2.0
                while time.monotonic() < end:
                    report = dev.read_input(max(1, round((end - time.monotonic()) * 1000)))
                    parsed = parse_atk(report or b"")
                    if parsed:
                        r.connected = True
                        r.level, r.status, r.detail = parsed
                        return r
        r.status, r.detail = "暂未回复", "请动一下鼠标，确认已开机并连到这个接收器，再点刷新"
    except Exception as exc:
        r.status, r.detail = "读取失败", str(exc)
    return r


class Hidpp:
    """匹配设备槽位、特性索引、函数和 software ID，忽略其他软件的通知。"""
    def __init__(self, dev):
        self.dev = dev
        self.tag = 9
        if not dev._open_reader():
            raise hw.HidError("无法打开罗技读取接口")

    def call(self, slot, feature, function, params=b"", timeout=0.7):
        self.tag = self.tag % 15 + 1
        header = bytes([0x11, slot, feature, (function << 4) | self.tag])
        packet = (header + bytes(params)).ljust(20, b"\0")
        self.dev.write_output(packet)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            report = self.dev.read_input(max(1, round((end - time.monotonic()) * 1000)))
            if not report:
                continue
            if report[:4] == header:
                return report[4:]
            if len(report) >= 6 and report[0] == 0x11 and report[1] == slot and report[2] == 0xFF:
                if report[3:5] == header[2:4]:
                    return None
        return None

    def feature(self, slot, feature_id, timeout=0.7):
        reply = self.call(slot, 0, 0, feature_id.to_bytes(2, "big"), timeout)
        return reply[0] if reply and reply[0] else None

    def name(self, slot):
        feature = self.feature(slot, 0x0005)
        if not feature:
            return "罗技鼠标"
        reply = self.call(slot, feature, 0)
        length = min(reply[0], 100) if reply else 0
        result = b""
        while len(result) < length:
            chunk = self.call(slot, feature, 1, bytes([len(result)]))
            if not chunk:
                break
            result += chunk[:min(16, length - len(result))]
        return result.decode("utf-8", errors="replace").strip("\0 ") or "罗技鼠标"


_logi_slot = None
_logi_name = None
_last_readings = {}


def parse_unified(payload: bytes):
    # 0x1004 function 1 = getStatus; function 0 是能力表，不是电量。
    if len(payload) < 4 or payload[0] > 100:
        return None
    status = {0: "使用中", 1: "充电中", 2: "充电中", 3: "已充满", 4: "慢速充电"}.get(payload[2], "电池状态异常")
    if payload[0] == 0 and payload[1] != 0:
        return None  # 只上报电量档位时不伪造精确百分比。
    return payload[0], status


def read_logitech(interfaces) -> Reading:
    global _logi_slot, _logi_name
    r = Reading("logitech", _logi_name or "罗技鼠标", "2.4G · Logi Bolt", source="HID++ 2.0 · Unified Battery")
    iface = next((d for d in interfaces if (d.vid, d.pid, d.usage_page, d.output_len)
                  == (0x046D, 0xC548, 0xFF00, 20)), None)
    if not iface:
        r.connected = False
        r.status, r.detail = "接收器未连接", "未发现 Logi Bolt 接收器（046D:C548）"
        return r
    try:
        with hw.HidDevice(iface.path, write=True) as dev:
            link = Hidpp(dev)
            slots = [_logi_slot] if _logi_slot else range(1, 7)
            for slot in slots:
                feature = link.feature(slot, 0x1004, timeout=0.9)
                if not feature:
                    continue
                payload = link.call(slot, feature, 1, timeout=1.2)
                parsed = parse_unified(payload or b"")
                if parsed:
                    r.connected = True
                    _logi_slot = slot
                    if not _logi_name:
                        _logi_name = link.name(slot)
                    r.name, r.level, r.status = _logi_name, parsed[0], parsed[1]
                    r.detail = f"Bolt 设备槽位 {slot} · 设备直接上报"
                    return r
        _logi_slot = None
        r.status, r.detail = "暂未回复", "请唤醒罗技鼠标并确认当前连接的是 Bolt 接收器"
    except Exception as exc:
        r.status, r.detail = "读取失败", str(exc)
    return r


def read_headset(_interfaces) -> Reading:
    r = Reading("p9500", "P9500 蓝牙耳机", "蓝牙 · HFP", source="Windows 蓝牙电量属性")
    connected = bt_battery.connected_names()
    if connected is not None and not any("p9500" in name for name in connected):
        r.connected = False
        r.status, r.detail = "未连接", "P9500 当前没有活动蓝牙连接，请连接耳机后刷新"
        return r
    if connected is not None:
        r.connected = True
    devices = [d for d in bt_battery.list_bluetooth_devices() if "p9500" in d.name.lower()]
    devices.sort(key=lambda d: not d.is_handsfree)
    for dev in devices:
        if dev.has_property and dev.battery is not None:
            r.connected = True
            r.level, r.status = dev.battery, "系统上报"
            r.detail = "耳机通过 HFP 上报；更新频率由耳机和 Windows 决定"
            return r
    r.status = "暂无电量数据"
    r.detail = "请确认耳机已连接；系统保留设备节点不代表当前已连接"
    return r


def parse_dualshock(report: bytes):
    if len(report) == 64 and report[0] == 1:
        value = report[30]
    elif len(report) >= 78 and report[0] == 0x11:
        report = report[:78]  # Windows 按最大 Report 长度（本机 547）补齐。
        if zlib.crc32(b"\xA1" + report[:-4]) != int.from_bytes(report[-4:], "little"):
            return None
        value = report[32]
    else:
        return None
    bucket, plugged = value & 15, bool(value & 16)
    if bucket > 10 and not (plugged and bucket == 11):
        return None
    level = min(100, bucket * 10 + 5)
    status = "已充满" if plugged and bucket == 11 else "充电中" if plugged else "使用中"
    return level, status


def read_dualshock(interfaces) -> Reading:
    r = Reading("dualshock", "DUALSHOCK 4 手柄", "蓝牙 / USB", source="索尼 HID 电池状态")
    iface = next((d for d in interfaces if d.vid == 0x054C and d.pid in (0x05C4, 0x09CC, 0x0BA0)
                  and d.input_len >= 64 and d.usage_page == 1 and d.usage == 5), None)
    if not iface:
        r.connected = False
        r.status, r.detail = "未连接", "按 PS 键连接手柄，或插入 USB 数据线，然后刷新"
        return r
    r.connected = True
    bluetooth = iface.input_len > 64
    r.connection = "蓝牙" if bluetooth else "USB"
    try:
        with hw.HidDevice(iface.path, write=bluetooth) as dev:
            dev._open_reader()
            if bluetooth:
                # 所有效果有效位为 0，仅启用完整输入报告；不设置灯光/震动。
                packet = bytearray(78)
                packet[:2] = b"\x11\xc0"
                packet[-4:] = zlib.crc32(b"\xA2" + packet[:-4]).to_bytes(4, "little")
                dev.write_output(bytes(packet))
            end = time.monotonic() + 1.2
            while time.monotonic() < end:
                parsed = parse_dualshock(dev.read_input(max(1, round((end - time.monotonic()) * 1000))) or b"")
                if parsed:
                    r.level, r.status = parsed
                    r.detail = "约 10% 一档，显示区间中值；100% 表示满电"
                    return r
        r.status, r.detail = "暂无电量数据", "手柄已发现，尚未收到完整电池报告；可能被其他程序独占"
    except Exception as exc:
        r.status, r.detail = "读取失败", str(exc)
    return r


def scan() -> list[Reading]:
    # 将同一电脑上的多份面板/CLI 对硬件的访问串行化。
    kernel = hw.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.ReleaseMutex.restype = ctypes.c_int
    mutex = kernel.CreateMutexW(None, False, "Local\\MyWirelessBatteryHardware")
    try:
        wait = kernel.WaitForSingleObject(mutex, 15000)
        if wait not in (0, 0x80):
            raise RuntimeError("其他实例正在读取设备，请稍后重试")
        try:
            interfaces = hw.enumerate_hid(vendor_products=TARGET_IDS, strings=False)
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(reader, interfaces) for reader in (read_atk, read_logitech, read_headset, read_dualshock)]
                result = [f.result() for f in futures]
                for i, reading in enumerate(result):
                    reading.sampled_at = time.time()
                    result[i] = retain_recent(reading)
                return result
        finally:
            kernel.ReleaseMutex(mutex)
    finally:
        kernel.CloseHandle(mutex)


def retain_recent(reading):
    """ATK 休眠持续保留最后电量；确认接收器断开才清除。"""
    if reading.connected is False:
        _last_readings.pop(reading.key, None)
    elif reading.level is not None:
        _last_readings[reading.key] = replace(reading)
    elif reading.key == 'atk' and reading.key in _last_readings:
        last = _last_readings[reading.key]
        stamp = time.strftime("%H:%M:%S", time.localtime(last.sampled_at))
        sleeping = reading.status == '暂未回复'
        detail = ("鼠标休眠或暂未回复，唤醒后自动更新" if sleeping else
                  f"本轮读取失败：{reading.detail}")
        return replace(last, connected=True, stale=True,
                       status='休眠' if sleeping else reading.status,
                       detail=f"{detail}；显示 {stamp} 的电量")
    elif reading.status == "暂未回复" and reading.key in _last_readings:
        last = _last_readings[reading.key]
        if reading.sampled_at - last.sampled_at <= 120:
            stamp = time.strftime("%H:%M:%S", time.localtime(last.sampled_at))
            return replace(last, stale=True, status="上次读数", detail=f"本轮未回复，显示 {stamp} 的读数；动一下鼠标再刷新")
        _last_readings.pop(reading.key, None)
    return reading


def inventory():
    groups = {}
    for d in hw.enumerate_hid():
        if d.vid == 0x00FF:
            continue
        key = d.vid_pid
        group = groups.setdefault(key, {"usb_id": key, "name": d.product, "manufacturer": d.manufacturer, "interfaces": []})
        group["interfaces"].append({"usage_page": f"{d.usage_page:04X}", "input": d.input_len, "output": d.output_len, "feature": d.feature_len})
    return {"usb_devices": list(groups.values()), "bluetooth": [
        {"name": d.name, "battery": d.battery, "has_battery": d.has_property}
        for d in bt_battery.displayable_devices()
    ]}
