"""Preheat duration numbers (one per water outlet) for the Yunmi water heater."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import UnitOfTime
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import MAX_ONE_SHOT_DURATION, MIN_ONE_SHOT_DURATION, ONE_SHOT_SLOTS
from .coordinator import YunmiCoordinator


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up one preheat duration number per water outlet."""
    coordinator: YunmiCoordinator = entry.runtime_data
    async_add_entities(
        [YunmiPreheatDurationNumber(coordinator, slot) for slot in ONE_SHOT_SLOTS]
    )


class YunmiPreheatDurationNumber(CoordinatorEntity[YunmiCoordinator], RestoreNumber):
    """How many seconds that outlet's one-shot preheat runs before stopping."""

    _attr_has_entity_name = True
    _attr_native_min_value = MIN_ONE_SHOT_DURATION
    _attr_native_max_value = MAX_ONE_SHOT_DURATION
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: YunmiCoordinator, slot: str) -> None:
        super().__init__(coordinator)
        self.slot = slot
        self._attr_translation_key = f"preheat_duration_{slot}"
        self._attr_unique_id = f"{coordinator.uid}_preheat_duration_{slot}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float:
        return self.coordinator.one_shot_durations[self.slot]

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.one_shot_durations[self.slot] = int(value)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value:
            self.coordinator.one_shot_durations[self.slot] = int(last.native_value)
