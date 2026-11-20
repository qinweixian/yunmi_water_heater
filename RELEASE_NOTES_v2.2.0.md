# v2.2.0

## 新增

- **立即停止预热按钮**（`button.*_li_ji_ting_zhi_yu_re`）
  - 按下后设备立即退出预热、恢复待机
  - 同时取消进行中的一次性预热倒计时（结束时间传感器归位）
  - 可手动按压，也可在自动化里用 `button.press` 调用，例如：预热结束但长时间无人用水 → 延时自动停止
- 已在 viomi.waterheater.u10 实机验证：预热中按下秒停，倒计时正确取消

## 兼容性

- Home Assistant ≥ 2026.11
- 实测设备：viomi.waterheater.u10
