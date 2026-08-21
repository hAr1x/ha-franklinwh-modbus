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

"""DataUpdateCoordinator for the FranklinWH Modbus integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from franklinwh_local_api import (
    FranklinWHConnectionError,
    FranklinWHDeviceInfo,
    FranklinWHLocalClient,
    FranklinWHStatus,
)

if TYPE_CHECKING:
    from .cloud import FranklinWHCloudClient
    from .number import FranklinBatteryPowerNumber, FranklinReserveNumber

_LOGGER = logging.getLogger(__name__)


class FranklinWHCoordinator(DataUpdateCoordinator[FranklinWHStatus]):
    """Polls the aGate via FranklinWHLocalClient on a fixed interval and
    exposes the latest FranklinWHStatus snapshot to all platforms.

    Also holds a couple of cross-platform references that don't fit
    neatly into the coordinator.data model:
      - watchdog_seconds: passed to async_start_battery_charge/discharge()
        as duration_s, configurable via the Options Flow.
      - self_reserve_number / tou_reserve_number: populated by
        number.py's async_setup_entry() so that select.py's mode-switch
        handler can reach these two Number entities directly (for the
        dirty-flag reconciliation logic - see number.py's module
        docstring for the full explanation).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: FranklinWHLocalClient,
        poll_interval_s: float,
        watchdog_seconds: float,
        device_info: FranklinWHDeviceInfo,
        cloud_client: "FranklinWHCloudClient | None" = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{entry.title} coordinator",
            update_interval=timedelta(seconds=poll_interval_s),
        )
        self.entry = entry
        self.client = client
        self.watchdog_seconds = watchdog_seconds
        self.device_info = device_info

        # None unless the user has explicitly enabled Cloud Control in
        # the Options Flow (disabled by default). When set, select.py
        # and number.py use it instead of local Modbus writes for
        # mode-switching and reserve % updates only - all readback
        # (displayed values on every entity) always comes from local
        # Modbus polling regardless of this being set. See cloud.py's
        # module docstring and LIMITATIONS.md.
        self.cloud_client = cloud_client

        self.self_reserve_number: "FranklinReserveNumber | None" = None
        self.tou_reserve_number: "FranklinReserveNumber | None" = None
        self.charge_power_number: "FranklinBatteryPowerNumber | None" = None
        self.discharge_power_number: "FranklinBatteryPowerNumber | None" = None

    async def _async_update_data(self) -> FranklinWHStatus:
        try:
            return await self.client.async_get_status()
        except FranklinWHConnectionError as err:
            raise UpdateFailed(f"Error communicating with aGate: {err}") from err
