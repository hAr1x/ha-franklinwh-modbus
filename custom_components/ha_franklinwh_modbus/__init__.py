# Copyright (C) 2026 Harry Xue
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""The FranklinWH Modbus integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .cloud import FranklinWHCloudClient
from .const import (
    CONF_CLOUD_EMAIL,
    CONF_CLOUD_ENABLED,
    CONF_CLOUD_PASSWORD,
    CONF_POLLING_SECONDS,
    CONF_WATCHDOG_HOURS,
    DEFAULT_CLOUD_ENABLED,
    DEFAULT_POLLING_SECONDS,
    DEFAULT_WATCHDOG_HOURS,
    DOMAIN,
)
from .coordinator import FranklinWHCoordinator
from franklinwh_local_api import (
    FranklinWHConnectionError,
    FranklinWHDeviceInfo,
    FranklinWHLocalClient,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up FranklinWH Modbus from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    client = FranklinWHLocalClient(host=host, port=port)
    try:
        await client.connect()
    except FranklinWHConnectionError as err:
        raise ConfigEntryNotReady(
            f"Could not connect to aGate at {host}:{port}: {err}"
        ) from err

    try:
        device_info = await client.async_get_device_info()
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Could not read device identification (Model 1) from aGate at "
            "%s:%s - falling back to generic device info", host, port,
            exc_info=True,
        )
        device_info = FranklinWHDeviceInfo(
            manufacturer="FranklinWH",
            model="aGate",
            firmware_version="unknown",
            serial_number="unknown",
        )

    watchdog_hours = entry.options.get(CONF_WATCHDOG_HOURS, DEFAULT_WATCHDOG_HOURS)
    polling_seconds = entry.options.get(CONF_POLLING_SECONDS, DEFAULT_POLLING_SECONDS)

    cloud_client: FranklinWHCloudClient | None = None
    if entry.options.get(CONF_CLOUD_ENABLED, DEFAULT_CLOUD_ENABLED):
        cloud_email = entry.options.get(CONF_CLOUD_EMAIL, "")
        cloud_password = entry.options.get(CONF_CLOUD_PASSWORD, "")
        if cloud_email and cloud_password:
            cloud_client = FranklinWHCloudClient(cloud_email, cloud_password)
        else:
            _LOGGER.warning(
                "Cloud Control is enabled but no email/password is set - "
                "mode-switching and reserve % will use local Modbus only"
            )

    coordinator = FranklinWHCoordinator(
        hass,
        entry,
        client,
        poll_interval_s=polling_seconds,
        watchdog_seconds=watchdog_hours * 3600.0,
        device_info=device_info,
        cloud_client=cloud_client,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change (e.g. watchdog hours,
    polling interval, or host/port edited via the Options flow), so
    changes take effect without requiring a full HA restart."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: FranklinWHCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.close()
        if coordinator.cloud_client is not None:
            await coordinator.cloud_client.async_close()
    return unload_ok
