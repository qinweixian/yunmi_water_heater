# 云米燃气热水器在ha中使用米家miio控制的自定义插件

## 使用方法

1. 把项目文件夹重命名为yunmi,复制到ha中的/config/custom_components文件夹中
2. 修改/confg/configuration.yaml，添加如下代码

```yaml
water_heater:
  - platform: yunmi
    host: 192.168.*.*
    token: *************************
    name: Yunmi water heater
```

* host：热水器的局域网ip
* token：小米iot的设备token，可以通过工具获取

3. 自定义开关实现控制一键预热
4. 可以接入nodered中，实现无线开关联动，按无线开关一键预热50秒
