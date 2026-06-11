# Wi-Fi 灯条通信设计

## 目标

给 WS2812B + ESP32-C3 灯条增加 Wi-Fi 通信能力，让灯条不再需要一直插在
Mac 上。Mac 仍然运行 Codex 状态监听器，继续负责判断当前状态，但状态发送从
USB 串口改为通过家庭局域网发送。

可见状态模型保持不变：

```text
idle
busy
attention
```

## 范围

本次包含：

- 保留现有 USB 串口通信能力。
- 给 Python 监听器增加 UDP 广播发送能力。
- 给 `LedStripStatus` 固件增加 Wi-Fi 连接和 UDP 接收能力。
- 继续复用现有状态解析和超时兜底逻辑。
- 补充 Wi-Fi 配置、上传、手动测试和排障文档。

本次不包含：

- 企业 Wi-Fi、访客网网页登录、Portal 登录等复杂网络认证。
- 云中转、手机 App 配网、家庭局域网之外的远程访问。
- 改造现有 Codex 日志读取和状态判断逻辑。
- 大范围改动交通灯固件；除非共享逻辑需要极小兼容调整。

## 推荐方案

采用 Mac 到 ESP32-C3 的 UDP 广播。

监听器把当前可见状态编码成带换行的 UTF-8 文本，例如 `busy\n`，发到
`255.255.255.255` 的固定 UDP 端口。ESP32-C3 接入家里的 2.4GHz Wi-Fi 后监听
这个端口，收到数据后继续用现有 `parseStatus()` 解析，然后切换灯条效果。

这个方案不需要固定灯条 IP，也不依赖路由器 DHCP 分配结果。UDP 可能偶发丢包，
但现有监听器本来就会定时重发当前状态，所以这个风险可接受。

## 架构

### 固件

`firmware/LedStripStatus/LedStripStatus.ino` 增加可选 Wi-Fi 输入路径：

- 从本地 secrets 头文件读取 Wi-Fi 名称和密码，真实密码文件不提交到 git。
- 启用 Wi-Fi 模式时，开机连接家里的 2.4GHz Wi-Fi。
- 启动 `WiFiUDP` 监听固定端口。
- 主循环里继续读取 USB 串口，同时在 Wi-Fi 已连接时读取 UDP 包。
- UDP 收到的有效状态继续走现有状态解析函数。
- Wi-Fi 断开后自动重连，不阻塞灯效动画。

USB 仍然保留，因为固件上传、现场排障和手动测试都还会用到。

### Python 监听器

`tools/codex_desktop_usb_light.py` 增加通信方式参数：

```text
--transport usb
--transport udp
```

`usb` 继续作为默认值，避免破坏当前已经安装的后台服务。`udp` 模式新增一个发送器，
负责校验状态是否属于 `VISIBLE_STATES`，把 `state + "\n"` 编码后发到可配置地址和端口：

```text
--udp-host 255.255.255.255
--udp-port 37650
```

现有重发机制继续保留，用来处理 UDP 丢包、ESP32 重启、Wi-Fi 短暂断开后的恢复。

## 数据流

```text
Codex Desktop 日志
  -> Python 监听器状态机
  -> UDP 广播："busy\n"
  -> ESP32-C3 Wi-Fi UDP 监听器
  -> parseStatus("busy")
  -> WS2812B busy 灯效
```

## 配置

固件里的 Wi-Fi 配置放在本地文件，例如：

```cpp
// firmware/LedStripStatus/WifiSecrets.h
#pragma once

#define WIFI_STATUS_LIGHT_ENABLED 1
#define WIFI_STATUS_LIGHT_SSID "your-ssid"
#define WIFI_STATUS_LIGHT_PASSWORD "your-password"
#define WIFI_STATUS_LIGHT_UDP_PORT 37650
```

仓库提交一个示例文件，真实 `WifiSecrets.h` 放进 `.gitignore`，避免把家里 Wi-Fi
密码提交进仓库。

LaunchAgent 从 USB 改成 Wi-Fi 时，只需要调整监听器启动参数：

```text
--transport udp
--udp-host 255.255.255.255
--udp-port 37650
```

## 异常处理

- 如果没有启用 Wi-Fi，固件表现与现在的 USB-only 版本一致。
- 如果启用了 Wi-Fi 但缺少 Wi-Fi 配置，编译时给出明确错误。
- 如果运行时 Wi-Fi 断开，固件自动重连，不阻塞灯效动画。
- 如果超过现有主机命令超时时间没有收到有效状态，显示回落到 `idle`。
- 如果监听器 UDP 发送失败，记录错误，并在下次轮询或重发周期继续尝试。

## 测试

自动化测试：

- 增加 Python UDP 发送器测试，覆盖状态校验和数据包内容。
- 增加 CLI 通信方式选择测试，不触碰真实 socket。
- 保持现有状态机和串口相关测试通过。

手动测试：

- 用本地 Wi-Fi 配置编译 Wi-Fi 固件。
- 先通过 USB 上传固件，然后把 ESP32-C3 改接到墙插或其他电源。
- 运行 UDP 模式监听器，验证 `idle`、`busy`、`attention` 三种状态。
- 用 Python 手动发 UDP 包，确认不依赖 Codex Desktop 时灯条也能切换。
- 断开并恢复 ESP32 电源，确认它能重新连上 Wi-Fi，并在下一次重发后恢复状态。

## 兼容性

现有 USB 用户不需要改任何东西。当前 LaunchAgent 配置继续可用，因为 USB 仍然是默认
通信方式。Wi-Fi 支持在固件和监听器两侧都是显式启用，不会影响已有安装。
