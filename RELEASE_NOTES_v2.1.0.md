# v2.1.0

## 新增

- **多用水点一次性预热**：一楼、二楼各一套「预热按钮 + 预热时长」
  - `button.*_yi_lou_yu_re`（一楼预热，默认 45 秒）
  - `button.*_er_lou_yu_re`（二楼预热，默认 55 秒）
  - `number.*_yu_re_shi_chang`（各用水点时长，10-3600 秒，重启后保留）
  - 蓝牙无线开关按一下 → 按钮自动化，即可把水管里的冷水预热固定秒数后自动停止
- 服务 `yunmi.one_shot_preheat` 新增 `location` 参数（floor1/floor2），不填时长时使用所选用水点的时长

## 变更

- 一次性预热最短时长从 60 秒放宽到 10 秒
- 预热进行中按下另一个用水点按钮：只重新计时（后按时长生效），不再重复下发命令避免设备报错

## 迁移说明

v2.0.0 的单按钮 `button.*_yi_ci_xing_yu_re` 和单时长 `number.*_yu_re_shi_chang` 已被上面的双套实体替代，更新后请在自动化里改指新实体。

## 兼容性

- Home Assistant ≥ 2026.11
- 实测设备：viomi.waterheater.u10
