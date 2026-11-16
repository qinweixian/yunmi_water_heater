"""Data update coordinator for the Yunmi water heater."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable

from miio import Device, DeviceException

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_ONE_SHOT_DURATIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EXTENDED_PROPS,
    GET_PROPS,
)

_LOGGER = logging.getLogger(__name__)


class YunmiCommandError(HomeAssistantError):
    """Raised when a miio command fails."""


@dataclass
class YunmiDeviceState:
    """Parsed state of the water heater."""

    wash_status: int = 0
    velocity: int = 0
    water_temp: int | None = None
    target_temp: int | None = None
    err_status: int = 0
    is_preheat_now: int = 0
    preheat_time1: str | None = None
    preheat_time2: str | None = None
    preheat_time3: str | None = None
    extended: dict[str, Any] = field(default_factory=dict)


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YunmiCoordinator(DataUpdateCoordinator[YunmiDeviceState]):
    """Poll the water heater over LAN miio protocol."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        device: Device,
        uid: str,
        device_info: DeviceInfo,
    ) -> None:
        self.device = device
        self.uid = uid
        self.device_info = device_info
        self._extended_checked = False
        self.one_shot_durations: dict[str, int] = dict(DEFAULT_ONE_SHOT_DURATIONS)
        self._one_shot_end_ts: float | None = None
        self._unsub_one_shot: Callable[[], None] | None = None
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> YunmiDeviceState:
        try:
            return await self.hass.async_add_executor_job(self._fetch_state)
        except DeviceException as err:
            raise UpdateFailed(f"water heater not reachable: {err}") from err

    def _fetch_state(self) -> YunmiDeviceState:
        raw = self.device.send("get_prop", GET_PROPS)
        if not isinstance(raw, list) or len(raw) < len(GET_PROPS):
            raise UpdateFailed(f"unexpected get_prop response: {raw}")

        state = YunmiDeviceState(
            wash_status=_to_int(raw[0]) or 0,
            velocity=_to_int(raw[1]) or 0,
            water_temp=_to_int(raw[2]),
            target_temp=_to_int(raw[3]),
            err_status=_to_int(raw[4]) or 0,
            is_preheat_now=_to_int(raw[5]) or 0,
            preheat_time1=str(raw[6]) if raw[6] is not None else None,
            preheat_time2=str(raw[7]) if raw[7] is not None else None,
            preheat_time3=str(raw[8]) if raw[8] is not None else None,
        )

        if not self._extended_checked:
            # Some models expose extra readable props; probe once, ignore failures
            self._extended_checked = True
            try:
                extra = self.device.send("get_prop", EXTENDED_PROPS)
                if isinstance(extra, list):
                    state.extended = {
                        k: v for k, v in zip(EXTENDED_PROPS, extra) if v is not None
                    }
            except DeviceException:
                pass

        return state

    async def async_set_temp(self, value: int) -> None:
        await self._async_send("set_temp", [value])

    async def async_set_power(self, on: bool) -> None:
        await self._async_send("set_power", [1 if on else 0])

    async def async_set_preheat_now(self, on: bool) -> None:
        if not on:
            # Turning preheat off manually also cancels a pending one-shot timer
            self._cancel_one_shot_timer()
            self._one_shot_end_ts = None
        await self._async_send("set_preheat_now", [1 if on else 0])

    async def async_send_command(self, method: str, params: list) -> Any:
        try:
            return await self.hass.async_add_executor_job(
                self.device.send, method, params
            )
        except DeviceException as err:
            raise YunmiCommandError(f"command {method} failed: {err}") from err

    async def _async_send(self, method: str, params: list) -> None:
        try:
            await self.hass.async_add_executor_job(self.device.send, method, params)
        except DeviceException as err:
            raise YunmiCommandError(f"{method} failed: {err}") from err

    @property
    def one_shot_end_ts(self) -> float | None:
        """Unix timestamp when the one-shot preheat will stop, or None."""
        return self._one_shot_end_ts

    async def async_start_one_shot(self, duration: int) -> None:
        """Start preheat and schedule turning it off after duration seconds."""
        if self.data and self.data.wash_status == 0:
            raise YunmiCommandError("热水器已关机，无法开始预热")
        # Re-issuing set_preheat_now while the device is already preheating
        # fails with "Unable to recover failed command", so only send it when
        # preheat is not already running; otherwise just re-arm the timer.
        already_preheating = self._one_shot_end_ts is not None or (
            self.data is not None and self.data.is_preheat_now == 1
        )
        if not already_preheating:
            await self.async_set_preheat_now(True)
        self._cancel_one_shot_timer()
        self._one_shot_end_ts = time.time() + duration
        self._unsub_one_shot = async_call_later(
            self.hass, duration, self._async_one_shot_finished
        )
        self.async_update_listeners()

    def restore_one_shot(self, remaining: float) -> None:
        """Re-arm the one-shot timer after HA restart."""
        self._one_shot_end_ts = time.time() + remaining
        self._unsub_one_shot = async_call_later(
            self.hass, remaining, self._async_one_shot_finished
        )
        self.async_update_listeners()

    def cancel_one_shot(self) -> None:
        """Cancel the pending one-shot timer without touching the device."""
        self._cancel_one_shot_timer()
        self._one_shot_end_ts = None
        self.async_update_listeners()

    def _cancel_one_shot_timer(self) -> None:
        if self._unsub_one_shot:
            self._unsub_one_shot()
            self._unsub_one_shot = None

    async def _async_one_shot_finished(self, _now) -> None:
        self._unsub_one_shot = None
        self._one_shot_end_ts = None
        try:
            await self.async_set_preheat_now(False)
        except YunmiCommandError as err:
            _LOGGER.warning("一次性预热到时停止失败（设备不在线？）：%s", err)
        await self.async_request_refresh()
