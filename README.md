# Battery Monitor

Battery Monitor 是面向无线鼠标、耳机与手柄的 Windows 电量面板与通知区域程序。使用 Python 标准库、`ctypes` 和 `tkinter`，无需安装第三方库。已在开发机上的四台真实设备上读取验证。

| 设备 | 识别方式 | 电量来源 |
| --- | --- | --- |
| ATK / VXE 鼠标，MAD 8K 接收器 | `373B:1040`，Usage Page `FF02` | ATK V1 查询，校验回复校验和；可读取充电状态和电压 |
| 罗技 MX Master 3S for Business | `046D:C548`，Logi Bolt | HID++ 2.0 `0x1004`，函数 1 获取电池状态；自动查找设备槽位和名称 |
| P9500 蓝牙耳机 | 名称包含 P9500 的蓝牙节点 | Windows 保存的 HFP 电量属性；上报频率由耳机和 Windows 决定 |
| Sony DUALSHOCK 4 | `054C:09CC`，另支持 `05C4` / `0BA0` | USB / 蓝牙输入报告；蓝牙 CRC32 校验，支持 Windows 补齐的 547 字节缓冲区 |

仅上表的本机四台设备做过实际验证。手柄按约 10% 的档位上报，界面显示档位中值，例如 40–49% 显示 45%；满电显示 100%。键盘 ES101T、ERAZER W03、USB VA3 等有线设备不加入电量监测。

## 启动

环境：Windows 10/11，Python 3.10+，需要 tkinter。

```powershell
git clone https://github.com/TECHOTAKU182/Battery-Monitor.git
cd Battery-Monitor
python app.py
```

也可以双击项目目录里的 **Battery Monitor.pyw**（需要关联支持 tkinter 的 Python）。运行 `python install_shortcuts.py --desktop` 后，可通过项目目录或桌面上的 **Battery Monitor** 快捷方式启动。窗口关闭后继续在托盘运行；使用「退出程序」结束程序。

```powershell
python app.py                 # 打开面板
pythonw app.py --tray         # 直接收起到托盘，无控制台窗口
python app.py --once          # 查询一次并打印
python app.py --once --json   # 输出结构化结果
python app.py --inventory     # 查看本机物理 HID 接口及蓝牙电量节点
python app.py --refresh       # 通知运行中的程序刷新
python app.py --quit          # 退出运行中的程序
```

快捷方式使用执行安装脚本的 Python 环境。移动项目或更换 Python 后，可运行 `python install_shortcuts.py --desktop` 重建入口。个人配置 `config.json` 和本机快捷方式 `.lnk` 不提交到仓库，首次运行使用默认设置。

## 使用

界面支持 Light / Dark 两种玻璃色调，配有柔和光晕和圆角悬浮控件，主面板只保留设备图标、简短名称和电量。主题切换会同步更新主面板、标题栏、详情、偏好设置和提示，并自动保存。设备图标与托盘图标共用同一套矢量线条，以超采样生成小尺寸图像。

- 四张卡片显示电量和充电/连接状态，数据来源收进点击详情。电量条绿色 ≥60%，黄色 30–59%，红色 <30%。
- 通知区域仅显示设备轮廓与环形电量：从顶部顺时针环绕，绿色 ≥60%、黄色 30–59%、红色 <30%，旧读数或无数据使用灰色。图标自动适应任务栏明暗与系统小图标尺寸，悬停查看精确电量及取样时间。
- 左键托盘图标打开面板；右键弹出菜单，勾选要显示的设备或直接退出程序。选择立即生效并在重启后保留。面板与托盘自动隐藏已断开的设备，重连后在下次检测时恢复；托盘选择仅影响托盘。没有可显示的设备时保留一个应用图标，方便打开面板或退出。
- 面板按在线数量排版：一台居中放大，两台并排，三台上二下一居中，四台两行网格；零台显示空状态。卡片整体居中，宽高有上限，放大窗口后仍保持适当比例。顶部四个圆形按钮使用缓存的抗锯齿圆周、细内沿与短阴影；鼠标点击不保留高亮外圈，Tab 导航用小圆点提示焦点。
- 右上角依次为刷新、月亮/太阳主题切换、收起到托盘、偏好设置。也可在偏好设置的「外观」中选择 Light / Dark。点击卡片查看协议来源与详细状态；底部时钟调整刷新间隔，电源开关控制自启，信息按钮查看操作说明。F5 刷新，Ctrl+, 打开偏好设置，Tab / Enter 可使用图标控件。
- 卡片圆角使用带透明抗锯齿的九宫格切片，缩放时保持圆角像素与边框粗细。光晕纹理、图标和字体使用缓存；连续缩放按 16 毫秒合并绘制请求，不再等拖动结束才重绘，也不在主线程逐像素计算整张背景。
- 默认每分钟自动刷新，可选 30 秒至 30 分钟。读取在后台进行，窗口不会因等待设备回复而卡住。
- ATK 休眠按在线处理，接收器仍连接时，面板与托盘持续显示本次运行最后一次成功读取的电量，没有两分钟过期限制；标注「休眠 · 上次电量」并保留原取样时间，唤醒后自动更新。暂时读取失败也保留旧电量，详情显示错误。尚未读到电量时保留卡片并显示 `—`；拔掉接收器后才清除缓存并隐藏。罗技暂未回复仍保留两分钟读数宽限。蓝牙耳机以活动连接状态判断，避免 Windows 保留的电量属性使离线设备继续显示。已连接但电量暂不可读的设备保留卡片。
- 开机自启默认关闭。在面板勾选后，在 Windows「启动」文件夹中创建快捷方式，启动到托盘；取消勾选会移除。程序不会擅自创建或修复自启项。
- DualShock 蓝牙读取会启用包含电池状态的完整报告，效果有效位均为 0，不设置震动或灯光。手柄断开后隐藏；被其他软件独占时保留卡片并显示暂不可读。
- P9500 显示的是 Windows 电量属性，可能存在更新延迟，不能把取样时间理解为耳机实际测量时间。

程序单实例运行。重复启动会打开已有窗口。设备读取使用另一把命名互斥锁，避免命令行与面板同时向同一接收器查询。

## 本地文件

只保存刷新间隔、托盘显示设备和主题到 `config.json`，旧版本数字模式设置会自动移除。上次电量仅保存在内存，不跨进程保留。不联网、不上传、不生成日志文件。托盘图标直接在内存中生成，快捷方式指向 Python 和当前目录中的脚本。

## 常驻性能

- 托盘命令和扫描结果通过阻塞等待的事件桥唤醒 Tk，取消原来每 150 ms 的命令检查和每 100 ms 的结果检查。空闲时没有应用层队列轮询，仍按用户选定的间隔检测设备。
- 电量扫描只探测目标 HID 的 VID/PID、能力和报告长度，不读取无关设备的名称或序列号；命令行 `--inventory` 保留完整枚举。
- HID 查询等待报告或超时，不按短间隔唤醒。设备拔出、输入接口不可用或底层读取失败时立即结束当前读取，避免在超时前忙循环。
- 图标只生成系统当前需要的一个尺寸，通过 Win32 内存接口创建 HICON。缓存最多 32 个句柄，淘汰时释放；轮廓不变只更新提示，提示也不变则不通知 Explorer。
- 自启到托盘时不绘制主界面。窗口隐藏或最小化时停止排绘制帧并释放背景、面板中随窗口面积增长的位图；小图标和圆角模板保留，恢复时重新铺设界面。

本机一次对照测量（2026-10-18；Python 3.12 / Windows，数值随设备、窗口大小及系统缓存变化）：

| 项目 | 优化前 | 优化后 |
| --- | --- | --- |
| 应用层固定空闲队列检查 | 约 400 次/分钟 | 0 次/分钟 |
| HID 枚举耗时 | 约 31 ms，34 个接口 | 约 3 ms，18 个目标接口 |
| 新电量图标生成 | 约 190 ms，6 种尺寸及文件写入 | 约 13 ms，当前尺寸、内存生成 |
| 打开主面板再收起后的工作集 | 约 59 MB | 约 45 MB |
| 同一状态的进程私有内存 | 约 35 MB | 约 22 MB |

新版冷启动直接驻留托盘约 37 MB 工作集。旧版 30 秒后台样本消耗约 0.063 秒 CPU；新版两次 30 秒后台样本未测到 CPU 时间增量（系统计时有精度限制，不代表绝对零消耗），覆盖自动刷新周期的 60 秒样本消耗约 0.016 秒 CPU。后台扫描仍有短暂工作，等待设备回复的墙钟耗时也不等于 CPU 时间。

线程投递依据 [Tkinter 线程模型](https://docs.python.org/3/library/tkinter.html#threading-model)；内存图标使用 [CreateIconFromResourceEx](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createiconfromresourceex)。本机 Tcl/Tk 支持线程，原生窗口回调仅入队，保持不直接重入 Tk。

## 代码

| 文件 | 用途 |
| --- | --- |
| `app.py` | 四设备 Tk 面板、后台读取、CLI、单实例入口 |
| `ui_events.py` | 无固定轮询的阻塞等待消息桥，安全投递到 Tk 事件循环 |
| `glass_view.py` | 玻璃视觉、图标控件、悬停提示和偏好设置 |
| `glass_render.py` | Light / Dark 色板、缓存光晕与抗锯齿九宫格面板 |
| `symbols.py` | 卡片与托盘共用的矢量符号、抗锯齿图标与应用徽标 |
| `raster_tools.py` | GDI 高质量背景插值，复用固定光晕纹理 |
| `devices.py` | ATK、罗技、P9500、DualShock 的电量协议和设备清单 |
| `native_tray.py` | Win32 通知区域图标、窗口消息、资源清理 |
| `settings.py` | 设置和用户选择的开机自启 |
| `hid_win.py` | Windows HID 枚举、能力表、独立异步读句柄 |
| `bt_battery.py` | Windows 蓝牙电量属性读取 |
| `win_icon.py` / `win_shell.py` | 环形电量图标、Windows 快捷方式 |
| `tests/test_protocols.py` | 真实回复解析、校验错误、零电量、充电与补齐缓冲区边界测试 |
| `tests/test_runtime.py` | 空闲无队列轮询、隐藏释放缓存、托盘差量更新、句柄上限、读取失败快速结束 |

图标预览：

![鼠标、罗技鼠标、耳机与手柄](assets/device-symbols.png)

环形托盘图标预览（上排放大，下排实际尺寸）：

![环形电量](assets/tray-rings.png)

```powershell
python -m unittest discover -s tests -v
```

## 来源

基于 [yszyszysz233/2.4G-battery-viewer](https://github.com/yszyszysz233/2.4G-battery-viewer) 的思路；复用其中的 `hid_win.py`、`bt_battery.py`、`win_icon.py`、`win_shell.py`。本项目另写了本机设备协议整合、HID++ 请求匹配、四设备面板、托盘和设置管理。

协议交叉核对：[atk-tool-plus](https://github.com/papelblume/atk-tool-plus)、[Solaar HID++](https://github.com/pwr-Solaar/Solaar/blob/master/lib/logitech_receiver/hidpp20.py)、[Linux PlayStation 驱动](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-playstation.c)、[SDL DS4 驱动](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/SDL_hidapi_ps4.c)。
