"""One-shot preheat buttons (one per water outlet) for the Yunmi water heater."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ONE_SHOT_SLOTS
from .coordinator import YunmiCoordinator, YunmiCommandError


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up one one-shot preheat button per water outlet."""
    coordinator: YunmiCoordinator = entry.runtime_data
    async_add_entities(
        [YunmiOneShotButton(coordinator, slot) for slot in ONE_SHOT_SLOTS]
    )


class YunmiOneShotButton(CoordinatorEntity[YunmiCoordinator], ButtonEntity):
    """Start a timed preheat that stops automatically after the configured duration."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-fast"

    def __init__(self, coordinator: YunmiCoordinator, slot: str) -> None:
        super().__init__(coordinator)
        self.slot = slot
        self._attr_translation_key = f"one_shot_preheat_{slot}"
        self._attr_unique_id = f"{coordinator.uid}_one_shot_preheat_{slot}"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_start_one_shot(
                self.coordinator.one_shot_durations[self.slot]
            )
        except YunmiCommandError as err:
            raise HomeAssistantError(str(err)) from err
