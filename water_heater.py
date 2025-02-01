'''
v1.0
'''

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.water_heater import (
    UnitOfTemperature,
    PRECISION_WHOLE,
    ATTR_TEMPERATURE,
    ATTR_OPERATION_MODE,
    STATE_ON,
    STATE_OFF,
    _LOGGER,
    WaterHeaterEntity,
    PLATFORM_SCHEMA
)
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_TOKEN
from homeassistant.exceptions import PlatformNotReady
from miio import Device, DeviceException

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME): cv.string
    }
)

_LOGGER = logging.getLogger(__name__)

STATE_WARM = "warm"
YUNMI_STATE = [STATE_OFF, STATE_ON, STATE_WARM]
YUNMI_OPERATION = {99: '自定义温度', 101: '开启预热', 102: '关闭预热', 103: '开机', 104: '关机', 39: '儿童洗',
                   40: '舒适洗', 42: '老人洗', 36: '厨房用'}
YUNMI_OPERATION_KEY = {v: k for k, v in YUNMI_OPERATION.items()}


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    host = config.get(CONF_HOST)
    name = config.get(CONF_NAME)
    token = config.get(CONF_TOKEN)

    _LOGGER.info("Initializing Yunmi Water Heater with host %s (token %s...)", host, token[:5])
    try:
        device = Device(host, token)
        yumiWaterHeate = YunmiWaterHeater(device, name)

    except DeviceException:
        _LOGGER.exception('Fail to setup Yunmi Water Heater')
        raise PlatformNotReady

    async_add_devices([yumiWaterHeate])


class YunmiWaterHeater(WaterHeaterEntity):
    def __init__(self, device, name):
        self._max_temp = 65
        self._min_temp = 30
        # self._supported_features = SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE | SUPPORT_AWAY_MODE
        self._supported_features = (1, 2, 4, 8)

        self._device = device
        self._name = name
        self._current_operation = None
        self._state_attrs = {'washStatus': 0, 'velocity': 0, 'waterTemp': None, 'targetTemp': None, 'errStatus': None,
                             'isPreHeatNow': 0, 'preHeatTime1': None, 'preHeatTime2': None, 'preHeatTime3': None}

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._max_temp

    @property
    def state(self):
        """Return the current state."""
        if self._state_attrs['isPreHeatNow'] == 1:
            return '预热中'
        if self._state_attrs['velocity'] > 0:
            return '工作中'
        if self._state_attrs['washStatus'] == 1:
            return '待机中'
        if self._state_attrs['washStatus'] == 0:
            return '已关机'

            # return YUNMI_STATE[self._state_attrs['washStatus']]

    @property
    def current_operation(self):
        """Return the current operating mode (Auto, On, or Off)."""
        return self._current_operation

    @property
    def operation_list(self):
        """Return the list of available operations."""
        return [v for k, v in YUNMI_OPERATION.items()]

    @property
    def temperature_unit(self):
        """Return the unit of measurement of this entity, if any."""
        return UnitOfTemperature.CELSIUS

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def target_temp_step(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def device_state_attributes(self):
        return self._state_attrs

    async def async_update(self):
        # 返回按照请求字段排序
        # Params Demo
        # {"method":"get_prop","did":"213213213","id":"1","params":["washStatus","velocity","waterTemp","targetTemp","errStatus","isPreHeatNow","preHeatTime1","preHeatTime2","preHeatTime3"]}
        # Response Demo
        # {"code":0,"message":"ok","result":[1,0,20,47,0,0,"0-6-0-8-0","0-19-0-21-0","0-0-0-0-0"]}
        try:
            state = self._device.send('get_prop',
                                      ["washStatus", "velocity", "waterTemp", "targetTemp", "errStatus", "isPreHeatNow",
                                       "preHeatTime1", "preHeatTime2", "preHeatTime3"])
            # 状态 开机为 1 关机为 0 当启动预热时变为流速数字
            self._state_attrs['washStatus'] = state[0]
            # 流速
            self._state_attrs['velocity'] = state[1]
            # 当前温度
            self._state_attrs['waterTemp'] = state[2]
            # 目标温度
            self._state_attrs['targetTemp'] = state[3]
            # 是否处于错误状态
            self._state_attrs['errStatus'] = state[4]
            # 是否处于预热模式
            self._state_attrs['isPreHeatNow'] = state[5]
            # 预约时间
            self._state_attrs['preHeatTime1'] = state[6]
            self._state_attrs['preHeatTime2'] = state[7]
            self._state_attrs['preHeatTime3'] = state[8]

            if state[3] in YUNMI_OPERATION:
                self._current_operation = YUNMI_OPERATION[state[3]]
            else:
                self._current_operation = YUNMI_OPERATION[99]

            _LOGGER.debug('update yunmi Water Heater status: %s', state[0])
        except DeviceException:
            _LOGGER.exception('Fail to get_prop from Yunmi Water Heater')
            raise PlatformNotReady

    @property
    def name(self):
        """Return the name of the water heater."""
        return self._name

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._state_attrs['waterTemp']

    @property
    def is_preheat_now(self):
        """Return the current temperature."""
        return self._state_attrs['isPreHeatNow']

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._state_attrs['targetTemp']

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if self._state_attrs['washStatus'] == 1:
            target_temp = int(kwargs.get(ATTR_TEMPERATURE))
            _LOGGER.info("set_operation_mode operation %s", target_temp)
            self._device.send('set_temp', [target_temp])
        self.async_schedule_update_ha_state()

    async def async_set_operation_mode(self, **kwargs):
        """Set new target operation mode."""
        current_operation = kwargs.get(ATTR_OPERATION_MODE)
        mode_code = int(YUNMI_OPERATION_KEY[current_operation])

        if mode_code < 99:
            if self._state_attrs['washStatus'] == 1:
                self._device.send('set_temp', [mode_code])
        elif mode_code == 101:
            if self._state_attrs['washStatus'] == 1:
                self._device.send('set_preheat_now', [1])
        elif mode_code == 102:
            if self._state_attrs['washStatus'] >= 1:
                self._device.send('set_preheat_now', [0])
        elif mode_code == 103:
            if self._state_attrs['washStatus'] == 0:
                self._device.send('set_power', [1])
        elif mode_code == 104:
            if self._state_attrs['washStatus'] != 0:
                self._device.send('set_power', [0])

        _LOGGER.info("set_operation_mode operation %s", current_operation)

        self.async_schedule_update_ha_state()

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._supported_features

    @property
    def error_status(self):
        """Return the list of supported features."""
        return self._state_attrs['error_status']

    @property
    def target_temperature_high(self):
        """Return the highbound target temperature we try to reach."""
        return None

    @property
    def target_temperature_low(self):
        """Return the lowbound target temperature we try to reach."""
        return None

    async def async_turn_on(self):
        if self._state_attrs['washStatus'] == 0:
            self._device.send('set_power', [1])
            self.async_schedule_update_ha_state()

    async def async_turn_off(self):
        if self._state_attrs['washStatus'] == 1:
            self._device.send('set_power', [0])
            self.async_schedule_update_ha_state()

    async def async_turn_away_mode_on(self):
        _LOGGER.error("on预热状态 %s", self._state_attrs['isPreHeatNow'])
        if self._state_attrs['isPreHeatNow'] == 0:
            self._device.send('set_preheat_now', [1])
            self.async_schedule_update_ha_state()

    async def async_turn_away_mode_off(self):
        _LOGGER.error("off预热状态 %s", self._state_attrs['isPreHeatNow'])
        # if self._state_attrs['isPreHeatNow'] == 1:
        self._device.send('set_preheat_now', [0])
        self.async_schedule_update_ha_state()
