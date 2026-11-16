"""Yunmi water heater main entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import STATE_OFF, STATE_ON, UnitOfTemperature, PRECISION_WHOLE
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    WASH_MODE_CODES,
    WASH_STATUS_LABELS,
)
from .coordinator import YunmiCoordinator, YunmiDeviceState


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Yunmi water heater entity."""
    coordinator: YunmiCoordinator = entry.runtime_data
    async_add_entities([YunmiWaterHeater(coordinator)])


def _wash_label(state: YunmiDeviceState) -> str:
    if state.wash_status == 0:
        return WASH_STATUS_LABELS[0]
    if state.is_preheat_now == 1:
        return WASH_STATUS_LABELS[3]
    if state.velocity > 0:
        return WASH_STATUS_LABELS[2]
    return WASH_STATUS_LABELS.get(state.wash_status, str(state.wash_status))


class YunmiWaterHeater(CoordinatorEntity[YunmiCoordinator], WaterHeaterEntity):
    """Viomi water heater controlled over LAN miio protocol."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 1
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: YunmiCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.uid}_water_heater"
        self._attr_device_info = coordinator.device_info
        self._attr_supported_features = (
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE
            | WaterHeaterEntityFeature.AWAY_MODE
            | WaterHeaterEntityFeature.ON_OFF
        )

    @property
    def state(self) -> str | None:
        state = self.coordinator.data
        if state.wash_status == 0:
            return STATE_OFF
        if self.current_operation:
            return self.current_operation
        return STATE_ON

    @property
    def current_operation(self) -> str | None:
        state = self.coordinator.data
        if state.wash_status == 0:
            return None
        if state.target_temp in WASH_MODE_CODES:
            return WASH_MODE_CODES[state.target_temp]
        return "自定义温度"

    @property
    def operation_list(self) -> list[str]:
        return ["自定义温度", *WASH_MODE_CODES.values()]

    @property
    def native_current_temperature(self) -> float | None:
        return self.coordinator.data.water_temp

    @property
    def native_target_temperature(self) -> float | None:
        state = self.coordinator.data
        if state.target_temp is None or state.target_temp in WASH_MODE_CODES:
            return None
        return state.target_temp

    @property
    def is_away_mode_on(self) -> bool | None:
        return self.coordinator.data.is_preheat_now == 1

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        return {
            "washStatus": state.wash_status,
            "velocity": state.velocity,
            "waterTemp": state.water_temp,
            "targetTemp": state.target_temp,
            "errStatus": state.err_status,
            "isPreHeatNow": state.is_preheat_now,
            "preHeatTime1": state.preheat_time1,
            "preHeatTime2": state.preheat_time2,
            "preHeatTime3": state.preheat_time3,
            "加热状态": _wash_label(state),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        temperature = int(temperature)
        if not MIN_TEMP <= temperature <= MAX_TEMP:
            raise ValueError(f"temperature must be {MIN_TEMP}-{MAX_TEMP}")
        await self.coordinator.async_set_temp(temperature)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        codes = {"自定义温度": None, **WASH_MODE_CODES}
        code = codes.get(operation_mode)
        if code is None:
            raise ValueError(f"unsupported mode: {operation_mode}")
        await self.coordinator.async_set_temp(code)

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_power(False)

    async def async_turn_away_mode_on(self) -> None:
        await self.coordinator.async_set_preheat_now(True)

    async def async_turn_away_mode_off(self) -> None:
        await self.coordinator.async_set_preheat_now(False)
