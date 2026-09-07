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
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from franklinwh_local_api import (
    FranklinWHConnectionError,
    FranklinWHDeviceInfo,
    FranklinWHLocalClient,
    FranklinWHStatus,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import storage
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FALLBACK_BATTERY_POWER_MAX_W

if TYPE_CHECKING:
    from .cloud import FranklinWHCloudClient
    from .number import (
        FranklinBatteryDurationNumber,
        FranklinBatteryPowerNumber,
        FranklinReserveNumber,
    )

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
      - battery power limits (M702): nameplate charge/discharge max
        power in Watts, read once at setup and never polled.
      - battery command deadline: the absolute UTC moment the active
        M704 command should be released. Tracked in memory, persisted
        in a storage.Store so it survives HA restarts, and kept
        consistent with the client's in-process watchdog by
        _async_reconcile_deadline() on every successful poll.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: FranklinWHLocalClient,
        poll_interval_s: float,
        watchdog_seconds: float,
        device_info: FranklinWHDeviceInfo,
        cloud_client: FranklinWHCloudClient | None = None,
        charge_power_max_w: float | None = None,
        discharge_power_max_w: float | None = None,
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

        self.self_reserve_number: FranklinReserveNumber | None = None
        self.tou_reserve_number: FranklinReserveNumber | None = None
        self.charge_power_number: FranklinBatteryPowerNumber | None = None
        self.discharge_power_number: FranklinBatteryPowerNumber | None = None
        self.charge_duration_number: FranklinBatteryDurationNumber | None = None
        self.discharge_duration_number: FranklinBatteryDurationNumber | None = None

        # Battery nameplate power limits (Watts), read once from SunSpec
        # M702 at setup time - never polled (a nameplate value does not
        # change). max_power_for() falls back to
        # FALLBACK_BATTERY_POWER_MAX_W while this is None.
        self.charge_power_max_w: float | None = charge_power_max_w
        self.discharge_power_max_w: float | None = discharge_power_max_w

        # Battery command deadline tracking - see
        # _async_reconcile_deadline() for the full state machine.
        self.deadline_direction: str | None = None  # "charge" | "discharge"
        self.deadline: datetime | None = None  # UTC
        self._watchdog_armed = False
        self._store: storage.Store[dict] = storage.Store(
            hass, version=1, key=f"{DOMAIN}_{entry.entry_id}"
        )

    async def _async_update_data(self) -> FranklinWHStatus:
        try:
            status = await self.client.async_get_status()
        except FranklinWHConnectionError as err:
            raise UpdateFailed(f"Error communicating with aGate: {err}") from err
        await self._async_reconcile_deadline(status)
        return status

    def max_power_for(self, direction: str) -> float:
        """Nameplate max power (W) for 'charge' or 'discharge', falling
        back to FALLBACK_BATTERY_POWER_MAX_W until/when the M702 init
        read has not succeeded."""
        value = getattr(self, f"{direction}_power_max_w")
        return float(value) if value is not None else FALLBACK_BATTERY_POWER_MAX_W

    def resolved_duration_s_for(self, direction: str) -> float | None:
        """Auto-release duration (seconds) for a battery command in the
        given direction, resolved in order of precedence:
          1. the per-direction duration Number (minutes; 0 = unset)
          2. the watchdog_hours option (the pre-0.1.4 behavior)
        Returns None when no auto-release is configured at all (both 0)
        - the command then runs until stopped manually (or until the
        reserve % is hit)."""
        number = (
            self.charge_duration_number
            if direction == "charge"
            else self.discharge_duration_number
        )
        if (
            number is not None
            and number.native_value is not None
            and number.native_value > 0
        ):
            return number.native_value * 60.0
        if self.watchdog_seconds > 0:
            return self.watchdog_seconds
        return None

    async def async_load_deadline(self) -> None:
        """Load a persisted battery-command deadline (if any) before the
        first refresh. The actual re-arm / immediate-release happens
        during the first successful poll (_async_reconcile_deadline),
        which is the only point where the live M704 state is known.
        """
        data = await self._store.async_load()
        if (
            isinstance(data, dict)
            and data.get("direction") in ("charge", "discharge")
            and isinstance(data.get("deadline_epoch"), (int, float))
        ):
            self.deadline_direction = data["direction"]
            self.deadline = dt_util.utc_from_timestamp(data["deadline_epoch"])

    async def async_set_deadline(self, direction: str, deadline: datetime) -> None:
        """Track a battery command that should be released at `deadline`
        (UTC). Arms nothing directly - the client's in-process watchdog
        is armed by the start command (or by _async_reconcile_deadline
        after a restart)."""
        self.deadline_direction = direction
        self.deadline = deadline
        self._watchdog_armed = True
        await self._store.async_save(
            {"direction": direction, "deadline_epoch": deadline.timestamp()}
        )

    async def async_clear_deadline(self) -> None:
        """Forget the tracked deadline (the command was released)."""
        if self.deadline is None:
            self._watchdog_armed = False
            return
        self.deadline_direction = None
        self.deadline = None
        self._watchdog_armed = False
        await self._store.async_remove()

    async def _async_reconcile_deadline(self, status: FranklinWHStatus) -> None:
        """Keep the tracked deadline, the persisted store, and the
        client's in-process watchdog consistent with the live M704
        state from the latest snapshot. Runs after every successful
        poll, including the first one after an HA restart.

        no command active:
          - a deadline is tracked -> the command was released (client
            watchdog or externally): clear the record.
        command active:
          - tracked for this direction:
              - deadline passed -> release it ourselves; the client
                watchdog has already had its chance (this covers a
                failed auto-release and HA being down past the
                deadline). A failed release retries on the next poll.
              - deadline in the future but the client watchdog is not
                armed (HA just restarted) -> re-arm it with the
                remaining seconds, so the original stop time holds.
          - not tracked (or a different direction) -> the command was
            started outside this integration (official app, or the
            record was lost): adopt it - arm a watchdog for the fully
            resolved duration and persist a new record, so it cannot
            run away to the reserve %.
        """
        if status.battery_command_charge_w > 0:
            active = "charge"
        elif status.battery_command_discharge_w > 0:
            active = "discharge"
        else:
            active = None

        if active is None:
            if self.deadline is not None:
                await self.async_clear_deadline()
            return

        if self.deadline is not None and self.deadline_direction == active:
            remaining = (self.deadline - dt_util.utcnow()).total_seconds()
            if remaining <= 0:
                _LOGGER.warning(
                    "Battery %s command has passed its deadline but is still "
                    "active on the aGate - releasing it now",
                    active
                )
                try:
                    await self.client.async_stop_battery_command()
                except FranklinWHConnectionError:
                    _LOGGER.warning(
                        "Deadline release of the battery %s command failed - "
                        "will retry on the next poll",
                        active,
                        exc_info=True
                    )
                    return
                await self.async_clear_deadline()
            elif not self._watchdog_armed:
                self.client.arm_watchdog(remaining)
                self._watchdog_armed = True
            return

        duration_s = self.resolved_duration_s_for(active)
        if duration_s is None or duration_s <= 0:
            # No auto-release configured anywhere - nothing to track.
            return
        self.client.arm_watchdog(duration_s)
        await self.async_set_deadline(
            active, dt_util.utcnow() + timedelta(seconds=duration_s)
        )
        _LOGGER.warning(
            "A battery %s command is active on the aGate but was not started "
            "by this integration (or its record was lost) - armed a %.0f-second "
            "auto-release watchdog as a safeguard",
            active,
            duration_s
        )
