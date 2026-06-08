# Changelog

这个项目使用语义化版本。硬件形态共存在 `main` 分支里，稳定节点通过 Git tag 标记。

## v1.1.0 - WS2812B 灯条支持

- 新增 `firmware/LedStripStatus`，支持 ESP32-C3 + WS2812B 灯条。
- 默认支持 30 颗灯珠，Data 使用 GPIO3。
- 新增三种灯条状态效果：
  - `idle`：青绿色慢呼吸。
  - `busy`：青白头 + 青蓝紫品红渐变尾巴的 comet 跑马灯。
  - `attention`：琥珀色双脉冲。
- README 和文档补充灯条接线、外部 5V 供电、共地、数据线串联电阻和手动测试说明。
- USB watcher 打开串口后设置 DTR/RTS，并增加近期 rollout 写入检测，提升 ESP32-C3 USB CDC 收消息稳定性。

## v1.0.0 - 红绿灯稳定版

- 支持 ESP32-C3 + 红/黄/绿交通灯模块。
- 支持 macOS Codex Desktop rollout 日志监听。
- 支持 USB 串口常驻发送状态。
- 三个可见状态：
  - `idle`：绿灯常亮。
  - `busy`：黄灯常亮。
  - `attention`：红灯慢闪。
- 补充中文 README、硬件接线、macOS 安装、手动测试和排障文档。
