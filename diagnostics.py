"""Diagnostics for the Yunmi water heater."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import async_get

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics, token redacted."""
    coordinator = entry.runtime_data
    data = {
        "entry_data": {
            k: ("**REDACTED**" if k == "token" else v) for k, v in entry.data.items()
        },
        "options": dict(entry.options),
        "coordinator_last_update_success": coordinator.last_update_success,
        "state": {
            "wash_status": coordinator.data.wash_status,
            "velocity": coordinator.data.velocity,
            "water_temp": coordinator.data.water_temp,
            "target_temp": coordinator.data.target_temp,
            "err_status": coordinator.data.err_status,
            "is_preheat_now": coordinator.data.is_preheat_now,
            "preheat_time1": coordinator.data.preheat_time1,
            "preheat_time2": coordinator.data.preheat_time2,
            "preheat_time3": coordinator.data.preheat_time3,
            "extended": coordinator.data.extended,
        },
    }
    device = async_get(hass).async_get_device({(DOMAIN, coordinator.uid)})
    if device:
        data["device"] = {
            "name": device.name,
            "model": device.model,
            "manufacturer": device.manufacturer,
        }
    return data
