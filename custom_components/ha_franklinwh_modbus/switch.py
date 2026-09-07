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

"""Switch entities for the FranklinWH Modbus integration.

Two switches control the battery's manual charge/discharge command
(M704):
  - battery_charge: turning on reads the "Battery Charge Power" Number
    and calls async_start_battery_charge(). Turning off calls
    async_stop_battery_command().
  - battery_discharge: mirrors battery_charge for the discharge
    direction, reading the "Battery Discharge Power" Number.

On turn-on, the auto-release duration is resolved per direction from
the corresponding duration Number (minutes; 0 = unset) with the
watchdog_hours option as fallback, and the resulting deadline is
persisted (coordinator.async_set_deadline) so it survives HA restarts.
Turning off clears the record.

is_on reflects the live hardware state
(coordinator.data.battery_command_charge_w /
battery_command_discharge_w). M704 has a single active setpoint
register, so the two switches are mutually exclusive - turning one on
drives the other's power to 0.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DEFAULT_BATTERY_POWER_W, DOMAIN
from .coordinator import FranklinWHCoordinator
from .entity import FranklinWHBaseEntity

_LOGGER = logging.getLogger(__name__)


class FranklinBatteryChargeSwitch(FranklinWHBaseEntity, SwitchEntity):
    _attr_translation_key = "battery_charge"
    _attr_icon = "mdi:battery-arrow-up"

    def __init__(self, coordinator: FranklinWHCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_battery_charge"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.battery_command_charge_w > 0

    async def async_turn_on(self, **kwargs) -> None:
        number = self.coordinator.charge_power_number
        power_w = number.native_value if number is not None else DEFAULT_BATTERY_POWER_W
        duration_s = self.coordinator.resolved_duration_s_for("charge")
        await self.coordinator.client.async_start_battery_charge(
            power_w=power_w, duration_s=duration_s
        )
        if duration_s is not None:
            await self.coordinator.async_set_deadline(
                "charge", dt_util.utcnow() + timedelta(seconds=duration_s)
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.async_stop_battery_command()
        await self.coordinator.async_clear_deadline()
        await self.coordinator.async_request_refresh()


class FranklinBatteryDischargeSwitch(FranklinWHBaseEntity, SwitchEntity):
    _attr_translation_key = "battery_discharge"
    _attr_icon = "mdi:battery-arrow-down"

    def __init__(self, coordinator: FranklinWHCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_battery_discharge"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.battery_command_discharge_w > 0

    async def async_turn_on(self, **kwargs) -> None:
        number = self.coordinator.discharge_power_number
        power_w = number.native_value if number is not None else DEFAULT_BATTERY_POWER_W
        duration_s = self.coordinator.resolved_duration_s_for("discharge")
        await self.coordinator.client.async_start_battery_discharge(
            power_w=power_w, duration_s=duration_s
        )
        if duration_s is not None:
            await self.coordinator.async_set_deadline(
                "discharge", dt_util.utcnow() + timedelta(seconds=duration_s)
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.async_stop_battery_command()
        await self.coordinator.async_clear_deadline()
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FranklinWHCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            FranklinBatteryChargeSwitch(coordinator),
            FranklinBatteryDischargeSwitch(coordinator),
        ]
    )
