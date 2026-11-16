"""Diagnostic sensors for the Yunmi water heater."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import YunmiCoordinator

ERR_LABELS = {0: "正常"}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Yunmi diagnostic sensors."""
    coordinator: YunmiCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        YunmiOneShotEndSensor(coordinator),
        YunmiErrStatusSensor(coordinator),
        YunmiVelocitySensor(coordinator),
        YunmiPreheatTimeSensor(coordinator, 1),
        YunmiPreheatTimeSensor(coordinator, 2),
        YunmiPreheatTimeSensor(coordinator, 3),
    ]
    extended = coordinator.data.extended
    extended_sensors = {
        "hotWater": "hot_water",
        "needClean": "need_clean",
        "modeType": "mode_type",
        "appointStart": "appoint_start",
        "appointEnd": "appoint_end",
    }
    for prop, key in extended_sensors.items():
        if prop in extended:
            entities.append(YunmiExtendedSensor(coordinator, prop, key))
    async_add_entities(entities)


class YunmiSensorBase(CoordinatorEntity[YunmiCoordinator], SensorEntity):
    """Base class for Yunmi sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: YunmiCoordinator, entity_key: str, translation_key: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.uid}_{entity_key}"
        self._attr_translation_key = translation_key
        self._attr_device_info = coordinator.device_info


class YunmiOneShotEndSensor(CoordinatorEntity[YunmiCoordinator], RestoreSensor):
    """End time of the running one-shot preheat (unknown when idle)."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "one_shot_end"
    _attr_entity_category = None
    _attr_icon = "mdi:clock-end"

    def __init__(self, coordinator: YunmiCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.uid}_one_shot_end"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> datetime | None:
        ts = self.coordinator.one_shot_end_ts
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=UTC)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is None or not isinstance(last.native_value, datetime):
            return
        remaining = (last.native_value - datetime.now(UTC)).total_seconds()
        if remaining > 0:
            self.coordinator.restore_one_shot(remaining)


class YunmiErrStatusSensor(YunmiSensorBase):
    """Fault code of the heater (0 = normal)."""

    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: YunmiCoordinator) -> None:
        super().__init__(coordinator, "err_status", "err_status")

    @property
    def native_value(self) -> int:
        return self.coordinator.data.err_status

    @property
    def extra_state_attributes(self):
        return {
            "状态": ERR_LABELS.get(self.coordinator.data.err_status, "故障")
        }


class YunmiVelocitySensor(YunmiSensorBase):
    """Water flow velocity reported by the heater."""

    _attr_icon = "mdi:water"

    def __init__(self, coordinator: YunmiCoordinator) -> None:
        super().__init__(coordinator, "velocity", "velocity")

    @property
    def native_value(self) -> int:
        return self.coordinator.data.velocity


class YunmiPreheatTimeSensor(YunmiSensorBase):
    """Preheat schedule slot (format like 0-6-0-8-0)."""

    _attr_icon = "mdi:clock-time-eight"

    def __init__(self, coordinator: YunmiCoordinator, slot: int) -> None:
        super().__init__(
            coordinator, f"preheat_time_{slot}", f"preheat_time_{slot}"
        )
        self.slot = slot

    @property
    def native_value(self) -> str | None:
        return getattr(self.coordinator.data, f"preheat_time{self.slot}")


class YunmiExtendedSensor(YunmiSensorBase):
    """Optional extra property reported by some models."""

    def __init__(
        self, coordinator: YunmiCoordinator, prop: str, translation_key: str
    ) -> None:
        super().__init__(coordinator, prop, translation_key)
        self.prop = prop

    @property
    def native_value(self):
        return self.coordinator.data.extended.get(self.prop)
