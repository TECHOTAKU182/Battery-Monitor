# Battery Monitor

A Windows battery dashboard and system tray app for wireless mice, headphones, and controllers. Battery Monitor brings device battery levels into one panel, with light and dark glass themes and compact tray icons that show charge at a glance.

Built with Python's standard library, `ctypes`, and `tkinter`. No third-party Python packages are required. Battery readings have been verified on the four physical devices listed below.

## Supported devices

| Device | Identification | Battery source |
| --- | --- | --- |
| ATK / VXE mouse with a MAD 8K receiver | `373B:1040`, Usage Page `FF02` | ATK V1 queries with response checksum validation; also reads charging state and voltage |
| Logitech MX Master 3S for Business | `046D:C548`, Logi Bolt | HID++ 2.0 feature `0x1004`, function 1; automatically discovers the device slot and name |
| P9500 Bluetooth headphones | Bluetooth nodes whose names contain P9500 | HFP battery property cached by Windows; reporting frequency depends on the headphones and Windows |
| Sony DUALSHOCK 4 | `054C:09CC`; also recognizes product IDs `05C4` / `0BA0` | USB and Bluetooth input reports, with Bluetooth CRC32 validation and support for Windows-padded 547-byte buffers |

Only the four devices tested on the development machine have been verified. Support for these protocols does not imply compatibility with every model from the same brand.

The controller reports battery levels in roughly 10% steps. The app displays the midpoint of each range: for example, 40–49% appears as 45%, while a full battery appears as 100%. Wired devices such as the ES101T keyboard, ERAZER W03, and USB VA3 are excluded from battery monitoring.

## Getting started

### Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer, with `tkinter` available
- A supported device connected to the computer

### Run the app

```powershell
git clone https://github.com/TECHOTAKU182/Battery-Monitor.git
cd Battery-Monitor
python app.py
```

You can also double-click **Battery Monitor.pyw** if `.pyw` files are associated with a Python installation that includes `tkinter`.

To create shortcuts in the project folder and on your desktop:

```powershell
python install_shortcuts.py --desktop
```

Run the installer without `--desktop` to create only the shortcut in the project folder. Shortcuts use the Python environment that runs the installer. If you move the project or change Python installations, run the installer again to rebuild them.

Closing the window keeps the app running in the system tray. Choose **Exit** from the app or tray menu to stop it. The current interface uses Chinese labels; the Exit command is labeled `退出程序`.

### Command-line options

```powershell
python app.py                 # Open the dashboard
pythonw app.py --tray         # Start in the tray without a console window
python app.py --once          # Read battery levels once and print the results
python app.py --once --json   # Print structured JSON results
python app.py --inventory     # List physical HID interfaces and Bluetooth battery nodes
python app.py --refresh       # Ask the running instance to refresh
python app.py --quit          # Stop the running instance
```

Personal settings in `config.json` and machine-specific `.lnk` shortcuts are excluded from the repository. A fresh checkout uses the default settings.

## Using Battery Monitor

### Dashboard and themes

The dashboard uses device icons, short names, and battery levels, with charging and connection status on each card. Click a card to see its protocol source and detailed status.

- **Light and dark themes:** Soft glows, rounded cards, and floating controls. Changing the theme updates the dashboard, title bar, details, preferences, and tooltips, and saves your choice.
- **Battery colors:** Green at 60% or above, yellow at 30–59%, and red below 30%.
- **Adaptive layout:** One device is enlarged and centered; two sit side by side; three use two cards above one centered card; four form a two-row grid. With no visible devices, the panel shows an empty state. Cards stay centered and have size limits so they remain proportionate in larger windows.
- **Automatic refresh:** Once per minute by default, with intervals from 30 seconds to 30 minutes. Device reads run in the background so the window remains responsive while waiting for replies.

The four buttons at the upper right are Refresh, Theme, Hide to tray, and Preferences. You can also choose Light or Dark in the appearance section of Preferences. At the bottom, the clock changes the refresh interval, the power control toggles startup at sign-in, and the information button opens the usage guide.

| Shortcut | Action |
| --- | --- |
| `F5` | Refresh battery readings |
| `Ctrl+,` | Open Preferences |
| `Tab` / `Enter` | Navigate and activate icon controls |

The circular controls use cached antialiased outlines, fine inner edges, and short shadows. Mouse clicks do not leave a highlighted focus ring; keyboard navigation uses a small focus dot.

### System tray

Tray icons combine a device outline with a battery ring that fills clockwise from the top. The ring uses the same green, yellow, and red thresholds as the dashboard; stale or unavailable readings appear gray. Icons adapt to the taskbar's light or dark appearance and the system's small-icon size. Hover over an icon for the numeric battery level and sample time.

- **Left-click** an icon to open the dashboard.
- **Right-click** to choose which devices appear in the tray or to exit.
- Tray selections take effect immediately and survive restarts. They affect only the tray, not the dashboard.
- Disconnected devices disappear from both the dashboard and tray, then return after the next scan detects reconnection.
- If no devices can be shown, one app icon remains so you can still open the dashboard or exit.

Dashboard and tray icons share the same vector outlines, rendered with supersampling for small sizes.

### Device behavior and reading limits

- **ATK sleep and temporary read failures:** While the receiver remains connected, the app keeps the last successful reading from the current session without a two-minute expiry. Sleeping devices are marked as asleep with the previous battery level, and the original sample time is retained. Readings update after the mouse wakes. Temporary read errors also retain the previous level, with the error available in Details. Before the first successful read, the card stays visible with `—`. Unplugging the receiver clears the cached reading and hides the device.
- **Logitech timeouts:** Previously received readings have a two-minute grace period when the device temporarily stops replying.
- **Bluetooth headphones:** Visibility follows the active connection state so a battery property retained by Windows does not keep disconnected headphones on screen. P9500 readings can be delayed; the displayed sample time is when the app read the Windows property, not necessarily when the headphones measured their battery.
- **DUALSHOCK 4:** Bluetooth reads enable the full reports that include battery status. Effect-valid flags remain zero, so the app does not set rumble or lighting. Disconnected controllers are hidden. If another app has exclusive access, the card remains visible and indicates that the reading is temporarily unavailable.
- **Connected devices without a readable battery level:** Their cards remain visible rather than disappearing.

### Startup and single-instance behavior

Startup at sign-in is disabled by default. Enabling it creates a shortcut in the Windows Startup folder and starts the app in the tray. Disabling it removes that shortcut. The app does not create or repair startup entries without your choice.

Only one app instance runs at a time. Launching it again opens the existing window. A separate named mutex protects hardware reads so the command line and dashboard do not query the same receiver simultaneously.

## Local storage and privacy

The app saves only the refresh interval, selected tray devices, and theme to `config.json`. Obsolete numeric-icon settings from earlier versions are removed automatically.

Previous battery readings are kept only in memory and do not survive process restarts. The app makes no network requests, uploads no data, and creates no log files. Tray icons are generated directly in memory. Shortcuts point to Python and the scripts in the current project folder.

## Performance and rendering

- **Event-driven idle behavior:** Tray commands and scan results wake Tk through a blocking event bridge. This replaces the earlier 150 ms command checks and 100 ms result checks. There is no fixed application-level queue polling while idle; device scans still follow the selected refresh interval.
- **Targeted HID enumeration:** Battery scans inspect only the target devices' VID/PID, capabilities, and report lengths. They do not request unrelated device names or serial numbers. The `--inventory` command retains full enumeration.
- **Blocking HID waits:** Queries wait for a report or a timeout rather than waking at short intervals. Device removal, unavailable input interfaces, and underlying read failures end the current read immediately instead of spinning until the deadline.
- **Bounded icon cache:** Only the icon size currently needed by Windows is generated. HICONs are created through Win32 memory APIs, with at most 32 cached handles; evicted handles are released. If the icon is unchanged, only its tooltip is updated. If both are unchanged, Explorer receives no update.
- **Lower hidden-window overhead:** Starting in the tray skips dashboard rendering. Hiding or minimizing the window stops scheduling drawing frames and releases background and panel bitmaps whose memory use grows with window size. Small icons and corner templates remain cached, and the dashboard is rebuilt when restored.
- **Cached glass rendering:** Cards use transparent, antialiased nine-slice images so corner pixels and border thickness remain consistent during resizing. Glow textures, icons, and fonts are cached. Continuous resize requests are coalesced over 16 ms instead of waiting until dragging ends, and the main thread does not recalculate every background pixel.

The following measurements compare an earlier version with the optimized implementation on the development machine on **October 18, 2026**, using Python 3.12 on Windows. Results vary with connected devices, window size, and system caches.

| Measurement | Before optimization | After optimization |
| --- | --- | --- |
| Fixed application-level idle queue checks | About 400/min | 0/min |
| HID enumeration | About 31 ms, 34 interfaces | About 3 ms, 18 target interfaces |
| Generation of a new battery icon | About 190 ms, six sizes and file writes | About 13 ms, current size generated in memory |
| Working set after opening and hiding the dashboard | About 59 MB | About 45 MB |
| Process private memory in the same state | About 35 MB | About 22 MB |

A cold start directly into the tray used approximately 37 MB of working-set memory. A 30-second background sample of the earlier version consumed about 0.063 seconds of CPU time. Two 30-second samples of the optimized version showed no measurable CPU-time increase; this reflects timer precision, not a claim of zero CPU use. A 60-second sample covering an automatic refresh consumed about 0.016 seconds of CPU time. Background scans still perform brief work, and wall-clock time spent waiting for device replies is not equivalent to CPU time.

Thread delivery follows the [Tkinter threading model](https://docs.python.org/3/library/tkinter.html#threading-model). The local Tcl/Tk build supports threads, and native window callbacks only enqueue commands rather than directly reentering Tk. In-memory icon creation uses [CreateIconFromResourceEx](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createiconfromresourceex).

## Project structure

| File | Purpose |
| --- | --- |
| `app.py` | Four-device Tk dashboard, background reads, CLI, and single-instance entry point |
| `Battery Monitor.pyw` | Double-click launcher without a console window |
| `ui_events.py` | Blocking message bridge that safely delivers work to Tk without fixed polling |
| `glass_view.py` | Glass-style interface, icon controls, tooltips, and preferences |
| `glass_render.py` | Light/dark palettes, cached glows, and antialiased nine-slice panels |
| `symbols.py` | Shared vector symbols, antialiased device icons, and app logo |
| `raster_tools.py` | High-quality GDI background interpolation with reusable glow textures |
| `devices.py` | ATK, Logitech, P9500, and DUALSHOCK battery protocols and device definitions |
| `native_tray.py` | Win32 tray icons, window messages, and resource cleanup |
| `settings.py` | Settings persistence and user-controlled startup at sign-in |
| `install_shortcuts.py` | Project-folder and optional desktop shortcut creation |
| `hid_win.py` | Windows HID enumeration, capability structures, and separate asynchronous read handles |
| `bt_battery.py` | Windows Bluetooth battery-property reads |
| `win_icon.py` / `win_shell.py` | Battery-ring icons and Windows shortcuts |
| `tests/test_protocols.py` | Recorded response parsing, checksum failures, zero battery, charging, and padded-buffer boundaries |
| `tests/test_runtime.py` | Idle behavior, hidden-window cache release, incremental tray updates, handle limits, and early read failure |
| `tests/test_appearance.py` | Theme persistence, resize scheduling, and cached panel corners |
| `tests/test_tray.py` | Tray selection persistence, stable device IDs, click dispatch, and battery rings |
| `tests/test_visibility.py` | Device visibility, sleep caching, reconnection, adaptive layout, and control focus |

## Icon previews

Device icons for the ATK mouse, Logitech mouse, headphones, and controller:

![ATK mouse, Logitech mouse, headphones, and controller icons](assets/device-symbols.png)

Battery-ring tray icons, enlarged on the top row and at actual size on the bottom row:

![Battery-ring system tray icons](assets/tray-rings.png)

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Acknowledgments

Inspired by [yszyszysz233/2.4G-battery-viewer](https://github.com/yszyszysz233/2.4G-battery-viewer), reusing its `hid_win.py`, `bt_battery.py`, `win_icon.py`, and `win_shell.py` modules. This project adds device-protocol integration for the tested hardware, HID++ response matching, the four-device dashboard, system tray behavior, and settings management.

Protocol implementations were cross-checked against [atk-tool-plus](https://github.com/papelblume/atk-tool-plus), [Solaar HID++](https://github.com/pwr-Solaar/Solaar/blob/master/lib/logitech_receiver/hidpp20.py), the [Linux PlayStation driver](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-playstation.c), and the [SDL DS4 driver](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/SDL_hidapi_ps4.c).
