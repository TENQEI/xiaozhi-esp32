# Flower S3：闲聊花花无屏终端

适用硬件：**Seeed Studio XIAO ESP32-S3 普通版（8 MB Flash + 8 MB Octal PSRAM）**、
外置 INMP441 I²S 麦克风、MAX98357A I²S 功放，以及接在功放上的单个扬声器。
复用面包板版本的麦克风和功放，不需要 OLED、摄像头或 Sense 扩展板。
板型及固件变体标识均为 `flower-s3`，不会改变原有面包板和 ReSpeaker 板型。

## 接线

**D 编号与 GPIO 编号不同。** 下表和 `config.h` 对应；不要继续使用大开发板的 GPIO15/16。
麦克风和功放使用两组独立时钟，不要把它们的 BCLK 或 WS/LRC 短接在一起。

| 模块 | 模块引脚 | XIAO 引脚 | ESP32-S3 GPIO |
| --- | --- | --- | --- |
| INMP441 | VDD | 3V3 | — |
| INMP441 | GND | GND | — |
| INMP441 | L/R | GND（选择左声道，不悬空） | — |
| INMP441 | WS | D3 | 4 |
| INMP441 | SCK | D4 | 5 |
| INMP441 | SD（麦克风数据输出） | D5 | 6 |
| MAX98357A | VIN | 3V3（首次低音量测试） | — |
| MAX98357A | GND | GND | — |
| MAX98357A | BCLK | D8 | 7 |
| MAX98357A | LRC / LRCLK | D9 | 8 |
| MAX98357A | DIN | D10 | 9 |
| MAX98357A | SD / EN | 保持模块默认使能；不要接 GND | — |
| MAX98357A | GAIN | 悬空，使用模块默认增益 | — |
| MAX98357A | SPK+ / SPK− | 仅连接扬声器两端 | — |

INMP441 的 `SD` 是音频数据，MAX98357A 的 `SD` 是关断/声道选择，两者不是同一种信号。
功放按常见默认左声道或双声道混合模式使用；若模块没有默认使能电阻，应按该模块原理图设置
SD/MODE，选择左声道或混合输出。本固件沿用上游驱动的左声道 I²S 输出。

所有模块必须共地。INMP441 只用 3.3 V；扬声器不能接 GPIO、3V3 或 GND，
MAX98357A 的 SPK− 也不能接 GND。原花花扬声器的额定功率仍未实测确认，先用低音量测试。
新设备默认音量设为 20/100；已有音量设置仍会从 NVS 恢复，不会在每次重启时强制重置。
3V3 方案受 XIAO 稳压器余量限制，大音量可能造成压降、重启或失真。
需要更大音量时可在 USB 供电下将功放 VIN 改接 XIAO 5V（麦克风仍接 3V3），
并确认扬声器功率和供电余量；电池供电时 5V 引脚不会自动升压输出 5 V。
本配置不包含电池电量检测、自动关机或外部功放电源控制。

D0（GPIO1）用于外接主按键：常开、自复位触点的一端接 D0，另一端接 GND。
按键使用内部上拉、低电平有效；原花花导电橡胶按钮的两组电极需先与原主控断开，再按上述方式接入。
不要接按钮电源，也不要将扬声器 SPK− 当作 GND。
保留 D1/D2、D6/D7 供后续扩展。GPIO0 保留板载 BOOT 键，GPIO21 用板载低电平点亮的用户 LED；
不占用 USB GPIO19/20，也不使用 GPIO3 启动绑带引脚。
请接好 XIAO 配套天线。

## 编译

使用 ESP-IDF **release/v6.1**（最低 v6.0.1，不能使用旧教程中的 IDF 5.x）。
先激活 ESP-IDF 环境，在仓库根目录运行：

```bash
python scripts/build.py --list-boards
python scripts/build.py flower-s3 --name flower-s3 --language zh-CN --zip
```

该命令自动选择 ESP32-S3、`BOARD_TYPE_FLOWER_S3`、8 MB Flash 和
`partitions/v2/8m.csv`，继承 ESP32-S3 的 8 线 PSRAM/80 MHz 配置。
输入采样率 16 kHz，输出采样率 24 kHz；复用 `NoAudioCodecSimplex` 的两个 I²S 控制器。
中文构建默认使用“你好小智”唤醒词；不需要外接按键即可使用语音唤醒。
无屏界面由公共 `NoDisplay` 实现，状态通过板载灯、语音提示和 USB 串口日志查看。

输出：`build/merged-binary.bin` 和 `releases/v<版本>_flower-s3.zip`。
仓库的 **Build Flower S3** Actions 工作流也会编译中文固件，并提供上述产物下载。
语言和唤醒词保留为用户构建选项，没有写死在板级 `config.json` 中。

使用 `idf.py menuconfig` 手动配置时，除选择 `Flower S3` 板型外，还必须设置 8 MB Flash、
上述 8 MB 分区表、USB Serial/JTAG 控制台，并明确选择语言、唤醒引擎和模型。
首次构建优先使用上面的构建脚本，避免继承其他板卡的配置。

## 烧录与首次启动

1. 用支持数据传输的 USB-C 线连接 XIAO。若未出现串口，按住 BOOT，短按 RESET，
   再松开 BOOT，进入 ROM 下载模式。
2. 下载并解压对应的 `flower-s3` 固件，使用小智烧录工具或 esptool。
   **合并固件 `merged-binary.bin` 从地址 `0x0` 烧录**，不是 `0x10000`。
   例如（将 `COM7` 换成实际端口，Linux/macOS 使用对应 `/dev/...`）：

   ```bash
   python -m esptool --chip esp32s3 --port COM7 --baud 460800 write-flash 0x0 merged-binary.bin
   ```

   已在本机完成构建时也可直接运行 `idf.py -p COM7 flash monitor`。
3. 烧录后松开 BOOT 并短按 RESET。首次无 Wi-Fi 凭据会进入配网模式，
   按语音提示连接热点并完成配网；日志可用 `idf.py -p COM7 monitor` 查看。
4. 如使用官方服务，按语音播报的激活码完成设备绑定；如连接自建 NAS 服务，
   在构建前通过项目配置设置对应的 OTA/服务地址，避免误连默认官方服务。

运行中，板载 BOOT（GPIO0）与外接主按键（D0/GPIO1）使用相同功能：
短按切换对话；双击随机播放一条定型文；
长按约 3 秒请求重新配网（沿用上游可进入配网的状态限制）。
只有板载 BOOT 同时是下载绑带键，正常启动时不要一直按住；D0 外接按键不具备 ROM 下载功能。
用户 LED 的亮灭/闪烁沿用上游 `GpioLed` 状态逻辑，充电灯不受固件控制。

## 验收与后续扩展

编译成功不等于实物验证。上板后依次确认：

- 串口正确识别 8 MB Flash 和 PSRAM，固件不循环重启。
- 配网、无屏激活码播报、断网重连正常。
- “你好小智”唤醒与 BOOT 对话可用，采音没有恒定噪声或全静音。
- 扬声器低音量播放清晰，逐步加大音量无失真或电源重启。
- 对话切换、打断以及长按重新配网正常。

## 花花独立音频资源

所有项目音频统一放在 `main/assets/flower/`，由 `audio_manifest.json` 管理。
原生 `locales`、`common`、`gen_lang.py` 和 `Lang::Sounds` 不变。

| 用途 | 文件名 | 数量 |
| --- | --- | --- |
| 十二小时整点报时 | `clock_01.ogg` 至 `clock_12.ogg` | 12 |
| 早安、晚安 | `greeting_morning.ogg`、`greeting_night.ogg` | 2 |
| 上午定型文（06:00–12:00） | `phrase_morning_01.ogg` 至 `04` | 4 |
| 下午定型文（12:00–18:00） | `phrase_afternoon_01.ogg` 至 `04` | 4 |
| 晚间定型文（18:00–次日06:00） | `phrase_evening_01.ogg` 至 `04` | 4 |
| 全天定型文 | `phrase_anytime_01.ogg` 至 `10` | 10 |
| 连续会话开始 | `session_start_01.ogg` 至 `03` | 3 |
| 连续会话结束 | `session_end_01.ogg` 至 `03` | 3 |

合计 42 个文件，全部使用 Ogg Opus、单声道、输入采样率 16 kHz、16 kbps。
Opus 的容器时间轴采用 48 kHz，这是正常格式行为。
当前提交的是约 0.4 秒的测试音，不是正式角色语音。每个文件使用不同音高。
清单记录类别、名称、启用标记、占位标记和预计正式时长；预计时长不是占位音的实测时长。

生成缺失占位文件（需要 ffmpeg，不覆盖任何现有文件）：

```bash
python scripts/generate_flower_placeholders.py
```

正式录音按同名替换，清单中的 `placeholder` 改为 `false`，然后重新编译。
`enabled: false` 可以停用某条音频；停用仍保留资源嵌入和清单完整性。
`automatic_enabled: false` 关闭自动报时及早晚安，不影响手动定型文和会话音。
录音不支持网页上传或运行时替换。旧板级 `chimes/`、`greetings/`、`phrases/` 路径及
`FLOWER_CHIME_SOURCE_DIR` 等打包选项已由新资源体系替代。

`gen_flower_audio.py` 独立生成构建目录内的 `flower_audio_assets.h`，提供
`Flower::Sounds::CLOCK_01` 等常量和分组表。CMake 校验清单、收集 OGG 并加入
`EMBED_FILES`；修改文件内容、清单或文件集合都会触发检查，缺失、额外文件会报错。
它们直接进入 app 镜像，原有 assets 分区继续服务于原生模型等资源，分区表不变。

## 播放规则

- 报时采用十二小时制：00:00、12:00 对应 `clock_12.ogg`；13:00 对应 `clock_01.ogg`。
- 默认早安 08:00、晚安 20:00；晚安至次日早安为免打扰时段，不播整点音。
  边界优先播早安或晚安，不再叠加整点音。
- 双击 BOOT 或外接主按键：从当前时段与全天音频的合并池中等概率随机选择一条。
  有多个候选时避免连续重复；设备时间未校准时只使用全天池。
- 会话连接成功后，随机播放一条开始音，再开始监听或发送唤醒音频。
  同一次连续会话中的监听、回答往返不重复播放开始音。
- 在监听状态短按 BOOT 或外接主按键主动结束连续会话，正常关闭后随机播放一条结束音。
  说话状态短按仍为打断回答；断网、错误、升级、重启或重新配网不播放结束音。
- 本地音频复用异步 NotifyPlayer/AudioService，不阻塞主事件循环。
  自动播放遇到忙碌即跳过，不补播；唤醒或按键可打断普通本地播放。
  开始音播放期间再次短按可取消会话。
- 其他板型的默认会话接口为空，继续沿用原生提示。

## 网页修改早晚安时间

设备接入 Wi-Fi 后，浏览器访问 `http://设备IP:8080/`。
分别设置工作日（周一至周五）和双休（周六、周日）的早晚安时间。
如果希望每天相同，将两套时间设为相同值即可。
不接入中国法定节假日及调休数据。设置保存到 NVS 后即时生效，重启保留，沿用已有 NVS 键和迁移。
修改时间不需要重新编译、打包或替换音频。免打扰只控制自动播报，手动双击仍可播放。
网页仅提供时间配置，不提供音频修改。

## 音量调节

当前可在联网对话中请求“把音量调到 30”或“音量小一点”，由支持设备工具调用的服务端
使用原生 `self.audio_speaker.set_volume` 设置 0–100 的全局音量；对话、本地定型文、报时和提示音共用。
新设备默认 20/100，非零设置保存到 NVS，重启恢复。沿用原生行为：设为 0 可在当前运行中静音，
但重启时会回到 10。是否成功调节需以实际工具调用为准，只有语音回复不代表设备音量已改变。
当前没有独立音量按键，早晚安网页也不提供音量调节；GPIO0 和 GPIO1 都保留原有对话操作。

## 构建与验收

```bash
python -m unittest discover -s scripts/tests -p 'test_flower_*.py' -v
python scripts/build.py flower-s3 --name flower-s3 --language zh-CN --zip
python scripts/verify_flower_firmware.py
```

最后一个命令检查实际 ELF 中全部 42 对资源符号及长度，读取实际分区表验证 8 MB 范围和两套 OTA 槽，
输出 `build/flower-audio-report.json`，含 app.bin 实际字节数与最小 OTA 槽剩余空间。
Actions 另外用预计正式时长的独立测试素材重新构建，报告容量；正式下载产物在该测试前上传。
不能把主机链接测试或占位文件总大小当作 ESP32 固件大小。

上板还需验证录音音量、长音频流式播放、唤醒与按键打断、断网重连、报时边界、
周五至周六及周日至周一切换、网页保存重启，以及会话提示结束前不采集麦克风。
此版本不增加电池检测或电源管理功能。

## 本次构建验证记录

固件源码提交 `27a6282` 在 ESP-IDF release/v6.1 下完成中文构建、全部 42 对嵌入符号校验，
以及 19 个代表板型/变体的构建。构建日志与产物：

- [Flower 中文固件与容量报告](https://github.com/TENQEI/xiaozhi-esp32/actions/runs/41587954729)
- [19 个代表板型构建](https://github.com/TENQEI/xiaozhi-esp32/actions/runs/41587960067)

| 测试素材 | OGG 合计字节 | app 字节 | 最小 OTA 槽字节 | 剩余字节 |
| --- | ---: | ---: | ---: | ---: |
| 42 个约 0.4 秒测试音 | 42,462 | 2,049,792 | 3,080,192 | 1,030,400 |
| 报时各 10 秒、其余各 5 秒的独立测试包 | 560,448 | 2,567,760 | 3,080,192 | 512,432 |

本地主机测试运行 171 项，通过，另有一个 MCP 测试组因开发依赖缺失跳过；
本地 Flower 专项 20 项全部通过。云端主机测试共 175 项，其中 172 项通过、3 项因环境依赖跳过
（CMake 重建测试及两项资源打包依赖测试）；云端 Flower 专项共 20 项，其中 19 项通过、1 项因 CMake 环境跳过。
CMake 重建检查已在本地实际执行。以上尺寸只对应这些素材；替换正式录音后需重新检查容量。
尚未完成实物验收，也未部署或烧录。
