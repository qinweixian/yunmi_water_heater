"""Preheat switch for the Yunmi water heater (一键预热)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import YunmiCoordinator


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the preheat switch."""
    coordinator: YunmiCoordinator = entry.runtime_data
    async_add_entities([YunmiPreheatSwitch(coordinator)])


class YunmiPreheatSwitch(CoordinatorEntity[YunmiCoordinator], SwitchEntity):
    """Toggle the one-key preheat (set_preheat_now) of the heater."""

    _attr_has_entity_name = True
    _attr_translation_key = "preheat"
    _attr_icon = "mdi:progress-clock"

    def __init__(self, coordinator: YunmiCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.uid}_preheat"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.is_preheat_now == 1

    async def async_turn_on(self, **kwargs) -> None:
        if self.coordinator.data.wash_status == 0:
            raise HomeAssistantError("热水器已关机，请先开机再预热")
        await self.coordinator.async_set_preheat_now(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_preheat_now(False)
