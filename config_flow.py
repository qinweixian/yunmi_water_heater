"""Config flow for the Yunmi water heater.

Three setup paths:
- scan: enter token, the LAN is scanned automatically to find the heater
- cloud: login with Mi Home account, token and IP are fetched automatically
- manual: enter host and token
"""

from __future__ import annotations

import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

import homeassistant.helpers.config_validation as cv

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from miio import Device, DeviceException

from .cloud import MiCloud, MiCloudAuthError, MiCloudError, MiCloudTwoFactor
from .const import (
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    GET_PROPS,
    MIIO_PORT,
    CONF_SCAN_INTERVAL,
)
from .coordinator import _to_int

_LOGGER = logging.getLogger(__name__)

MIIO_HELLO = bytes.fromhex(
    "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)


class YunmiCannotConnect(HomeAssistantError):
    """Device unreachable."""


class YunmiInvalidToken(HomeAssistantError):
    """Token rejected by the device."""


def _probe_device_sync(host: str, token: str) -> dict | None:
    """Query the device with get_prop; returns info dict when it is a Viomi heater."""
    try:
        device = Device(host, token)
        raw = device.send("get_prop", GET_PROPS)
    except DeviceException as err:
        _LOGGER.debug("probe %s failed: %s", host, err)
        return None
    if not isinstance(raw, list):
        return None

    info = {"host": host, "token": token}
    try:
        dev_info = device.info()
        info.update(
            model=dev_info.model,
            mac=dev_info.mac_address,
            fw=dev_info.firmware_version,
        )
    except DeviceException as err:
        _LOGGER.debug("info %s failed: %s", host, err)
    return info


def _miio_scan_sync(prefix: str, timeout: float = 4.0) -> list[str]:
    """Send unicast miio hellos to a /24 subnet and collect responders."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", 0))
    s.settimeout(0.5)
    for i in range(1, 255):
        try:
            s.sendto(MIIO_HELLO, (f"{prefix}.{i}", MIIO_PORT))
        except OSError:
            continue
        time.sleep(0.01)

    responders: list[str] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s.settimeout(max(0.1, deadline - time.time()))
            _data, addr = s.recvfrom(1024)
        except socket.timeout:
            break
        except OSError:
            break
        if addr[0] not in responders:
            responders.append(addr[0])
    s.close()
    _LOGGER.debug("miio scan %s.0/24 responders: %s", prefix, responders)
    return responders


def _get_source_ip_sync() -> str:
    """Return the LAN source ip used for outbound traffic (no packets sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 53))
        return s.getsockname()[0]
    finally:
        s.close()


def _gateway_sweep_sync(exclude_prefixes: set[str]) -> list[str]:
    """Detect LAN prefixes behind a NAT'd container.

    HA often runs in a docker bridge network, so the local interfaces only
    show the container subnet. Probe common router gateway addresses across
    192.168.0.0/16 (.1 and .254) on router-ish ports to find the real LAN.
    """
    candidates = [f"192.168.{i}.{h}" for i in range(256) for h in (1, 254)]

    def probe(ip: str) -> None:
        for port in (80, 53):
            s = socket.socket()
            s.settimeout(0.5)
            try:
                s.connect((ip, port))
                found.add(ip)
                return
            except OSError:
                continue
            finally:
                s.close()

    found: set[str] = set()
    with ThreadPoolExecutor(max_workers=64) as pool:
        list(pool.map(probe, candidates))

    prefixes: set[str] = set()
    for ip in found:
        prefix = ".".join(ip.split(".")[:3])
        if prefix not in exclude_prefixes:
            prefixes.add(prefix)
    return sorted(prefixes)[:3]


def _scan_and_probe_sync(prefix: str, token: str) -> tuple[list[dict], bool]:
    responders = _miio_scan_sync(prefix)
    if not responders:
        return [], False
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda ip: _probe_device_sync(ip, token), responders))
    return [info for info in results if info], True


async def async_scan_for_water_heaters(
    hass: HomeAssistant, token: str
) -> tuple[list[dict], bool]:
    """Scan the LAN(s) for Viomi water heaters with the given token.

    Returns (candidates, found_any_miio_device).
    """
    try:
        source_ip = await hass.async_add_executor_job(_get_source_ip_sync)
    except OSError:
        source_ip = None

    prefixes: list[str] = []
    if source_ip:
        prefixes.append(".".join(source_ip.split(".")[:3]))

    extra = await hass.async_add_executor_job(_gateway_sweep_sync, set(prefixes))
    for prefix in extra:
        if prefix not in prefixes:
            prefixes.append(prefix)

    candidates: list[dict] = []
    found_miio = False
    for prefix in prefixes[:4]:
        found, fm = await hass.async_add_executor_job(_scan_and_probe_sync, prefix, token)
        found_miio = found_miio or fm
        for info in found:
            if all(c["host"] != info["host"] for c in candidates):
                candidates.append(info)
    return candidates, found_miio


def _valid_token(token: str) -> bool:
    return bool(token) and len(token) == 32


async def _validate_host_token(hass: HomeAssistant, host: str, token: str) -> dict:
    info = await hass.async_add_executor_job(_probe_device_sync, host, token)
    if info is None:
        raise YunmiCannotConnect
    return info


class YunmiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Yunmi water heater."""

    VERSION = 1

    def __init__(self) -> None:
        self._verify_url: str | None = None
        self._cloud_devices: list[dict] = []
        self._candidates: list[dict] = []
        self._name: str | None = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        return self.async_show_menu(
            step_id="user", menu_options=["scan", "cloud", "manual"]
        )

    async def async_step_scan(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            self._name = user_input.get(CONF_NAME)
            if not _valid_token(token):
                errors[CONF_TOKEN] = "invalid_token_format"
            else:
                try:
                    candidates, found_miio = await async_scan_for_water_heaters(
                        self.hass, token
                    )
                except YunmiCannotConnect:
                    errors["base"] = "cannot_connect"
                else:
                    if not candidates:
                        errors["base"] = (
                            "invalid_token" if found_miio else "no_devices"
                        )
                    elif len(candidates) == 1:
                        return await self._async_create_entry(candidates[0])
                    else:
                        self._candidates = candidates
                        return await self.async_step_scan_pick()

        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_scan_pick(self, user_input=None) -> FlowResult:
        if user_input is not None:
            for info in self._candidates:
                if info["host"] == user_input["device"]:
                    return await self._async_create_entry(info)
        return self.async_show_form(
            step_id="scan_pick",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=info["host"],
                                    label=f"{info.get('name') or '热水器'}"
                                    f" - {info.get('model') or '未知型号'}"
                                    f" ({info['host']})",
                                )
                                for info in self._candidates
                            ]
                        )
                    )
                }
            ),
        )

    async def async_step_cloud(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        placeholders = {"verify_url": self._verify_url or ""}
        if user_input is not None:
            username = user_input["username"].strip()
            password = user_input["password"].strip()
            session = async_get_clientsession(self.hass)
            cloud = MiCloud(session)
            try:
                await cloud.login(username, password)
                devices = await cloud.get_devices()
            except MiCloudTwoFactor as err:
                self._verify_url = err.verify_url
                placeholders = {"verify_url": err.verify_url}
                errors["base"] = "two_factor_required"
            except MiCloudAuthError:
                errors["base"] = "invalid_auth"
            except MiCloudError:
                errors["base"] = "cloud_error"
            else:
                heaters = [
                    {
                        "host": d.get("localip"),
                        "token": d.get("token"),
                        "name": d.get("name") or DEFAULT_NAME,
                        "model": d.get("model"),
                        "did": str(d.get("did")),
                        "mac": d.get("mac"),
                    }
                    for d in devices
                    if "waterheater" in (d.get("model") or "")
                ]
                if not heaters:
                    errors["base"] = "cloud_no_waterheater"
                elif len(heaters) == 1:
                    return await self._async_create_entry(heaters[0])
                else:
                    self._cloud_devices = heaters
                    return await self.async_step_cloud_pick()

        schema = {
            vol.Required("username"): cv.string,
            vol.Required("password"): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_cloud_pick(self, user_input=None) -> FlowResult:
        if user_input is not None:
            for info in self._cloud_devices:
                if info["did"] == user_input["device"]:
                    return await self._async_create_entry(info)
        return self.async_show_form(
            step_id="cloud_pick",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=info["did"],
                                    label=f"{info['name']}"
                                    f" - {info.get('model') or '未知型号'}"
                                    f" ({info['host']})",
                                )
                                for info in self._cloud_devices
                            ]
                        )
                    )
                }
            ),
        )

    async def async_step_manual(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            token = user_input[CONF_TOKEN].strip()
            self._name = user_input.get(CONF_NAME)
            if not _valid_token(token):
                errors[CONF_TOKEN] = "invalid_token_format"
            else:
                try:
                    info = await _validate_host_token(self.hass, host, token)
                except YunmiCannotConnect:
                    errors["base"] = "cannot_connect"
                else:
                    return await self._async_create_entry(info)

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): cv.string,
                    vol.Required(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                }
            ),
            errors=errors,
        )

    async def _async_create_entry(self, info: dict) -> FlowResult:
        mac = (info.get("mac") or "").replace(":", "").lower()
        did = info.get("did")
        if mac:
            unique_id = f"viomi-{mac}"
        elif did:
            unique_id = f"viomi-did{did}"
        else:
            unique_id = f"viomi-{info['host']}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        name = self._name or info.get("name") or DEFAULT_NAME
        data = {
            CONF_HOST: info["host"],
            CONF_TOKEN: info["token"],
            CONF_NAME: name,
        }
        for key in ("model", "mac", "did"):
            if info.get(key):
                data[key] = info[key]

        return self.async_create_entry(
            title=name,
            data=data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return YunmiOptionsFlow()


class YunmiOptionsFlow(config_entries.OptionsFlow):
    """Handle options for the Yunmi water heater."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(min=5, max=600, step=1, mode=NumberSelectorMode.BOX)
                    ),
                }
            ),
        )
