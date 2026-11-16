"""The Yunmi (云米) water heater integration."""

from __future__ import annotations

import logging

from miio import Device, DeviceException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
import voluptuous as vol

from .const import DOMAIN, MAX_ONE_SHOT_DURATION, MIN_ONE_SHOT_DURATION, PLATFORMS
from .coordinator import YunmiCommandError, YunmiCoordinator
from .config_flow import _valid_token

_LOGGER = logging.getLogger(__name__)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("method"): str,
        vol.Optional("params", default=[]): [vol.Coerce(str)],
    }
)

ONE_SHOT_SCHEMA = vol.Schema(
    {
        vol.Optional("location", default="floor1"): vol.In(["floor1", "floor2"]),
        vol.Optional("duration"): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_ONE_SHOT_DURATION, max=MAX_ONE_SHOT_DURATION),
        ),
    }
)


def _build_device_meta(entry: ConfigEntry, device: Device) -> tuple[str, DeviceInfo]:
    """Build unique id and DeviceInfo; enrich with miio info() when reachable."""
    mac = (entry.data.get("mac") or "").replace(":", "").lower()
    did = entry.data.get("did")
    model = entry.data.get("model") or "viomi.waterheater"
    fw = None
    try:
        info = device.info()
        model = info.model or model
        if not mac and info.mac_address:
            mac = info.mac_address.replace(":", "").lower()
        fw = info.firmware_version
    except DeviceException:
        pass

    if mac:
        uid = f"viomi-{mac}"
    elif did:
        uid = f"viomi-did{did}"
    else:
        uid = f"viomi-{entry.data[CONF_HOST]}"

    device_info = DeviceInfo(
        identifiers={(DOMAIN, uid)},
        manufacturer="云米 Viomi",
        name=entry.data.get("name"),
        model=model,
        sw_version=fw,
    )
    return uid, device_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Yunmi water heater from a config entry."""
    device = Device(entry.data[CONF_HOST], entry.data[CONF_TOKEN])
    uid, device_info = await hass.async_add_executor_job(_build_device_meta, entry, device)
    coordinator = YunmiCoordinator(hass, entry, device, uid, device_info)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator:
        coordinator.cancel_one_shot()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _get_coordinator(hass: HomeAssistant) -> YunmiCoordinator:
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator:
            return coordinator
    raise HomeAssistantError("no Yunmi water heater is configured")


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "send_command"):
        return

    async def handle_send_command(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass)
        try:
            result = await coordinator.async_send_command(
                call.data["method"], call.data["params"]
            )
        except YunmiCommandError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": result}

    hass.services.async_register(
        DOMAIN,
        "send_command",
        handle_send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle_one_shot_preheat(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        duration = (
            call.data.get("duration")
            or coordinator.one_shot_durations[call.data["location"]]
        )
        try:
            await coordinator.async_start_one_shot(duration)
        except YunmiCommandError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        "one_shot_preheat",
        handle_one_shot_preheat,
        schema=ONE_SHOT_SCHEMA,
    )
