# Yunmi Water Heater (云米燃气热水器)

[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![HA 版本](https://img.shields.io/badge/HomeAssistant-2026.11%2B-blue)

为云米（Viomi）燃气热水器打造的 Home Assistant 本地集成，基于 LAN miIO 协议直连设备，**不依赖米家云**，支持 UI 配置流、局域网自动发现、全功能实体，以及按用水点划分的「一次性预热」。

> 实测设备：`viomi.waterheater.u10`（云米燃气热水器 U10，固件 2.1.3）。
> 官方 Xiaomi Home 集成虽然能接入该设备，但 MIoT 规格里没有预热接口，无法自动化预热；本集成走局域网 miIO 协议，保留全部功能，两者可共存。

## 功能特性

- **UI 配置流**：装好即配，无需手改 configuration.yaml
- **三种配置方式**：
  - 扫描局域网（输入 Token，自动识别设备 IP）
  - 米家账号登录（自动获取 Token 和 IP，需二次验证时会给链接）
  - 手动填写 IP + Token
- **IP 自动发现**：DHCP 换了设备 IP 也不用改配置；扫描会自动探测网段（含 Docker 桥接网络下的网关探测）
- **全功能实体**：温度/模式调节、一键预热开关、故障/流速/预热时段传感器
- **多用水点一次性预热（v2.1.0）**：每个用水点一个按钮 + 时长，按下后预热指定秒数自动停止，适合「用蓝牙开关把水管里的冷水预热一遍」的场景
- **立即停止预热（v2.2.0）**：一键停止预热并取消倒计时，可手动按或自动化调用
- **状态持久化**：预热时长、一次性预热倒计时在 HA 重启后自动恢复
- **本地服务**：`yunmi.one_shot_preheat`、`yunmi.send_command`（调试任意 miIO 命令）

## 安装

### 方式一：HACS（推荐）

1. HACS → 右上角 ⋮ → **自定义存储库**
2. 仓库地址填本仓库 URL，类别选 **Integration**
3. 点击下载「Yunmi Water Heater (云米燃气热水器)」
4. 重启 Home Assistant

### 方式二：手动

把 `custom_components/yunmi/` 整个文件夹复制到你的 HA 配置目录 `custom_components/` 下，重启 HA：

```
<config_dir>/custom_components/yunmi/
├── manifest.json
├── __init__.py
├── config_flow.py
├── coordinator.py
├── water_heater.py
├── switch.py
├── sensor.py
├── button.py
├── number.py
├── cloud.py
├── diagnostics.py
├── const.py
├── services.yaml
├── strings.json
└── translations/
```

## 配置

重启后进入 **设置 → 设备与服务 → 添加集成**，搜索「云米热水器 / Yunmi Water Heater」：

| 方式 | 需要填写 | 说明 |
|---|---|---|
| 扫描局域网 | Token | 自动扫描网段并用 Token 验证设备，无需知道 IP |
| 米家账号登录 | 米家 App 的账号密码 | 自动获取 Token 和 IP（是米家账号，不是 HA 账号） |
| 手动填写 | IP + Token | 已知设备 IP 时最快 |

**Token 获取方法**（32 位十六进制字符串）：

- 旧插件的 configuration.yaml 里直接复制
- 米家 App 本地数据库提取（网上有很多教程，搜「米家 token 获取」）
- `python-miio` 工具（`miiocli cloud --phone ...`）

## 实体说明

| 实体 | 名称 | 说明 |
|---|---|---|
| `water_heater.*` | 热水器 | 当前水温、目标温度/模式（儿童洗/舒适洗/老人洗/厨房用/自定义）、开关机 |
| `switch.*_yi_jian_yu_re` | 一键预热 | 对应设备的「一键预热」功能，开着就一直预热 |
| `button.*_yi_lou_yu_re` | 一楼预热 | 按下开始一次性预热（默认 45 秒后自动停止） |
| `button.*_er_lou_yu_re` | 二楼预热 | 按下开始一次性预热（默认 55 秒后自动停止） |
| `button.*_li_ji_ting_zhi_yu_re` | 立即停止预热 | 立即停止预热并取消一次性预热倒计时 |
| `number.*_yu_re_shi_chang` | 一楼/二楼预热时长 | 各用水点一次性预热秒数（10-3600） |
| `sensor.*_yi_ci_xing_yu_re_jie_shu` | 一次性预热结束 | 当前倒计时的预计结束时间，空闲时为未知 |
| `sensor.*_gu_zhang_zhuang_tai` | 故障状态 | 0 = 正常 |
| `sensor.*_shui_liu_su_du` | 水流速度 | 用水时变大 |

## 自动化示例

### 蓝牙无线开关按一下 → 一次性预热

在 HA 里把蓝牙开关（如米家无线开关）的「单击」事件作为触发器，动作改成按下对应按钮：

```yaml
automation:
  - alias: 蓝牙开关一键预热一楼
    trigger:
      - platform: state
        entity_id: event.mi_wu_xian_kai_guan_dan_ji   # 换成你的蓝牙开关事件实体
        attribute: event_type
        to: single
    action:
      - action: button.press
        target:
          entity_id: button.re_shui_qi_yi_lou_yu_re   # 一楼按钮
```

二楼同理，把按钮换成 `button.re_shui_qi_er_lou_yu_re`。

### 直接调用服务（可指定秒数）

```yaml
action:
  - action: yunmi.one_shot_preheat
    data:
      location: floor2      # 用水点：floor1 / floor2
      duration: 90          # 可选，不填则用该用水点的预热时长实体值
```

### 一次性预热结束后推送通知

```yaml
trigger:
  - platform: state
    entity_id: sensor.re_shui_qi_yi_ci_xing_yu_re_jie_shu
    from: unknown
action:
  - action: notify.mobile_app_xxx
    data:
      title: 预热完成
      message: 水管预热完成，可以用水了
```

## 常见问题

**扫描不到设备？**
- 确认热水器通电且已联网（米家 App 能看到在线）
- HA 跑在 Docker 桥接网络下也能扫（集成会自动探测网关所在网段），但跨网段/防火墙限制时会失败，可改用「手动填写」
- Token 不对会提示「没有一台能通过 Token 验证」

**预热按钮按下报「热水器已关机」？**
- 一次性预热需要热水器处于开机状态（待机或加热都行），先打开 `water_heater` 实体

**预热进行中又按了另一个用水点的按钮？**
- 不会出错：只会重新计时（后按的时长生效），不会重复下发命令

**状态不更新？**
- 集成默认 30 秒轮询一次，可在集成的「选项」里调（5-600 秒）

**想调试或调用没有暴露的功能？**
- 开发者工具 → 服务 → `yunmi.send_command`，例如设置预热时段：method `set_preheat_time`，params 按设备协议填写
- 打开 `custom_components.yunmi` 和 `miio` 的 debug 日志可以看到收发报文

## 与官方 Xiaomi Home 集成共存

可以同时启用：官方集成通过米家云端接入（走 MIoT），本集成通过局域网直连（走 miIO）。建议自动化只绑其中一个来源的实体，避免重复触发。

## 致谢

- 云端登录模块改编自 [micloud](https://github.com/squachen/micloud)（MIT License, © 2020 Sammy Svensson）
- 协议细节参考了 HA 社区论坛的云米热水器插件

## 许可证

[MIT](LICENSE)
