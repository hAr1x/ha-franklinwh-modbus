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

"""Number entities for the FranklinWH Modbus integration.

Four Number entities:

1. FranklinReserveNumber (self-consumption, TOU) - each tracks a
   "dirty" flag and a "hw_baseline" value to manage register
   15508/15509, which mirror each other's value on the aGate (writing
   one changes what the other reads back).

   Behavior when this Number's mode IS the currently active hardware
   mode:
     - Setting the value pushes it to hardware immediately.
       - On success, the displayed value is the new value, dirty
         clears.
       - On failure, the displayed value is reset back to what it was
         before the change, dirty clears (the hardware value is
         unchanged, so this keeps HA and hardware in agreement).
     - On every coordinator poll, the displayed value is set from the
       hardware register (this register is reliable while its mode is
       active, so external changes made via the FranklinWH app or
       cloud are picked up automatically).

   Behavior when this Number's mode is NOT the currently active mode:
     - Setting the value only updates the display; nothing is written
       to hardware. Dirty is set.
     - On every coordinator poll, the displayed value is left
       unchanged (this register mirrors the other mode's register
       while inactive, so its readback is not meaningful here).

   select.py's mode-switch handler resolves this Number once its mode
   becomes active: if dirty, its value is pushed to hardware; if not
   dirty, its displayed value is set from hardware.

   The value and dirty flag persist across HA restarts via
   RestoreEntity.

2. FranklinBatteryPowerNumber (charge, discharge) - a local value with
   no hardware interaction. Read by the corresponding battery
   charge/discharge switch in switch.py when the switch is turned on.
"""
from __future__ import annotations

import logging
from typing import Any

from franklinwh_local_api import OperatingMode
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    BATTERY_POWER_MAX_W,
    BATTERY_POWER_MIN_W,
    BATTERY_POWER_STEP_W,
    DEFAULT_BATTERY_POWER_W,
    DOMAIN,
    RESERVE_PCT_MAX,
    RESERVE_PCT_MIN,
    RESERVE_PCT_STEP,
)
from .coordinator import FranklinWHCoordinator
from .entity import FranklinWHBaseEntity

_LOGGER = logging.getLogger(__name__)


class FranklinReserveNumber(FranklinWHBaseEntity, RestoreEntity, NumberEntity):
    """Reserve % Number for one operating mode (self-consumption or
    TOU). See module docstring for the dirty-flag behavior."""

    _attr_native_min_value = RESERVE_PCT_MIN
    _attr_native_max_value = RESERVE_PCT_MAX
    _attr_native_step = RESERVE_PCT_STEP
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = "%"

    def __init__(
        self,
        coordinator: FranklinWHCoordinator,
        mode: OperatingMode,
    ) -> None:
        super().__init__(coordinator)
        self._mode = mode
        self._is_dirty: bool = False
        self._attr_native_value: float | None = None

        if mode == OperatingMode.SELF_CONSUMPTION:
            self._attr_translation_key = "self_consumption_reserve"
            self._attr_unique_id = f"{coordinator.entry.entry_id}_self_consumption_reserve"
            self._hw_field = "self_reserve_pct"
        else:
            self._attr_translation_key = "tou_reserve"
            self._attr_unique_id = f"{coordinator.entry.entry_id}_tou_reserve"
            self._hw_field = "tou_reserve_pct"

    async def _async_setter(self, pct: int) -> None:
        if self._mode == OperatingMode.SELF_CONSUMPTION:
            await self.coordinator.client.async_set_self_reserve_pct(pct)
        else:
            await self.coordinator.client.async_set_tou_reserve_pct(pct)

    @property
    def is_dirty(self) -> bool:
        return self._is_dirty

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"is_dirty": self._is_dirty}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in (
            None, "unknown", "unavailable"
        ):
            self._attr_native_value = float(last_state.state)
            self._is_dirty = bool(last_state.attributes.get("is_dirty", False))
        elif self.coordinator.data is not None:
            self._attr_native_value = float(
                getattr(self.coordinator.data, self._hw_field)
            )
            self._is_dirty = False

    async def async_set_native_value(self, value: float) -> None:
        if self.coordinator.cloud_client is not None:
            # Cloud Control path: the Cloud API's workMode parameter
            # addresses each mode's reserve independently, so this
            # value can always be pushed immediately regardless of
            # which mode is currently active - the dirty-flag/mode-
            # matching logic below exists only to work around the
            # local Modbus hardware limitation where registers
            # 15508/15509 mirror each other. See LIMITATIONS.md.
            previous_value = self._attr_native_value
            self._attr_native_value = value
            try:
                await self.coordinator.cloud_client.async_update_soc_cloud(
                    self._mode, int(value)
                )
            except Exception:
                _LOGGER.warning(
                    "Failed to push %s reserve via Cloud Control - reverting "
                    "to previous value", self._mode.value, exc_info=True,
                )
                self._attr_native_value = previous_value
            self._is_dirty = False
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
            return

        current_mode = (
            self.coordinator.data.operating_mode
            if self.coordinator.data is not None
            else None
        )

        if current_mode == self._mode:
            previous_value = self._attr_native_value
            self._attr_native_value = value
            try:
                await self._async_setter(int(value))
            except Exception:
                _LOGGER.warning(
                    "Failed to push %s reserve to hardware - reverting to "
                    "previous value", self._mode.value, exc_info=True,
                )
                self._attr_native_value = previous_value
            self._is_dirty = False
        else:
            self._attr_native_value = value
            self._is_dirty = True

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data is not None:
            current_mode = self.coordinator.data.operating_mode
            if current_mode == self._mode:
                # This Number's register is only meaningful while its
                # mode is active - track it. External changes (cloud,
                # official app) are picked up here automatically.
                hw_value = getattr(self.coordinator.data, self._hw_field)
                self._attr_native_value = float(hw_value)
                self._is_dirty = False
            # else: a different mode is active, so this register just
            # mirrors that mode's value - leave the displayed value
            # and dirty flag untouched.

        super()._handle_coordinator_update()

    @callback
    def sync_from_hardware(self, hw_value: int) -> None:
        """Set the displayed value from a hardware read without
        writing to hardware."""
        self._attr_native_value = float(hw_value)
        self._is_dirty = False
        self.async_write_ha_state()

    async def async_push_to_hardware(self) -> None:
        """Write the current displayed value to hardware and clear
        dirty."""
        if self._attr_native_value is None:
            return
        await self._async_setter(int(self._attr_native_value))
        self._is_dirty = False
        self.async_write_ha_state()


class FranklinBatteryPowerNumber(FranklinWHBaseEntity, RestoreEntity, NumberEntity):
    """A local power value with no hardware interaction. Read by the
    corresponding battery charge/discharge switch in switch.py when
    the switch is turned on."""

    _attr_native_min_value = BATTERY_POWER_MIN_W
    _attr_native_max_value = BATTERY_POWER_MAX_W
    _attr_native_step = BATTERY_POWER_STEP_W
    _attr_native_unit_of_measurement = "W"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: FranklinWHCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_native_value: float = float(DEFAULT_BATTERY_POWER_W)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in (
            None, "unknown", "unavailable"
        ):
            self._attr_native_value = float(last_state.state)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FranklinWHCoordinator = hass.data[DOMAIN][entry.entry_id]

    self_reserve_number = FranklinReserveNumber(coordinator, OperatingMode.SELF_CONSUMPTION)
    tou_reserve_number = FranklinReserveNumber(coordinator, OperatingMode.TOU)
    charge_power_number = FranklinBatteryPowerNumber(coordinator, "battery_charge_power")
    discharge_power_number = FranklinBatteryPowerNumber(coordinator, "battery_discharge_power")

    coordinator.self_reserve_number = self_reserve_number
    coordinator.tou_reserve_number = tou_reserve_number
    coordinator.charge_power_number = charge_power_number
    coordinator.discharge_power_number = discharge_power_number

    async_add_entities(
        [
            self_reserve_number,
            tou_reserve_number,
            charge_power_number,
            discharge_power_number,
        ]
    )
