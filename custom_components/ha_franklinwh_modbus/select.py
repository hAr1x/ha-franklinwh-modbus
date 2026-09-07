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

"""Select entity for the FranklinWH Modbus integration.

Also contains the mode-switch reconciliation step for the two reserve %
Number entities in number.py: after switching operating mode, the
reserve Number corresponding to the newly active mode is resolved
against hardware immediately, rather than waiting for the next
coordinator poll.
"""
from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

from franklinwh_local_api import OperatingMode
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    MODE_LABEL_EMERGENCY_BACKUP,
    MODE_LABEL_SELF_CONSUMPTION,
    MODE_LABEL_TOU,
)
from .coordinator import FranklinWHCoordinator
from .entity import FranklinWHBaseEntity

_LOGGER = logging.getLogger(__name__)

_MODE_TO_LABEL: dict[OperatingMode, str] = {
    OperatingMode.EMERGENCY_BACKUP: MODE_LABEL_EMERGENCY_BACKUP,
    OperatingMode.SELF_CONSUMPTION: MODE_LABEL_SELF_CONSUMPTION,
    OperatingMode.TOU: MODE_LABEL_TOU,
}
_LABEL_TO_MODE: dict[str, OperatingMode] = {v: k for k, v in _MODE_TO_LABEL.items()}

# Delay after writing the mode register before reading it back for
# reserve reconciliation, giving the aGate time to apply the change.
_RECONCILE_SETTLE_S = 0.5


class FranklinOperatingModeSelect(FranklinWHBaseEntity, SelectEntity):
    """Selects the aGate's native operating mode: Emergency Backup,
    Self-Consumption, or TOU."""

    _attr_translation_key = "operating_mode"
    _attr_icon = "mdi:tune"
    _attr_options: ClassVar[list[str]] = list(_MODE_TO_LABEL.values())

    def __init__(self, coordinator: FranklinWHCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_operating_mode"

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return _MODE_TO_LABEL.get(self.coordinator.data.operating_mode)

    async def async_select_option(self, option: str) -> None:
        target_mode = _LABEL_TO_MODE[option]

        if self.coordinator.cloud_client is not None:
            # Cloud Control path: switches mode via the FranklinWH
            # Cloud API instead of a local Modbus write. This does not
            # touch the two reserve % Number entities' dirty-flag logic
            # at all - that mechanism exists only to work around a
            # local Modbus hardware limitation (registers 15508/15509
            # mirroring each other) that does not apply to the Cloud
            # API's independently-addressed workMode parameter. See
            # LIMITATIONS.md.
            await self.coordinator.cloud_client.async_set_mode_cloud(target_mode)
        else:
            await self.coordinator.client.async_set_operating_mode(target_mode)

            await asyncio.sleep(_RECONCILE_SETTLE_S)
            status = await self.coordinator.client.async_get_status()
            await self._async_reconcile_reserve(target_mode, status)

        # Readback (current_option) always comes from the next local
        # Modbus poll, regardless of which path was used above - this
        # keeps the integration's iot_class of local_polling accurate.
        await self.coordinator.async_request_refresh()

    async def _async_reconcile_reserve(self, new_mode: OperatingMode, status) -> None:
        """Resolve the reserve % Number entity for new_mode against
        the hardware value in status.

        If the Number is dirty, its value is pushed to hardware. If
        not dirty, the Number's displayed value is set from hardware.
        Emergency Backup has no corresponding reserve Number.
        """
        if new_mode == OperatingMode.SELF_CONSUMPTION:
            number_entity = self.coordinator.self_reserve_number
            hw_value = status.self_reserve_pct
        elif new_mode == OperatingMode.TOU:
            number_entity = self.coordinator.tou_reserve_number
            hw_value = status.tou_reserve_pct
        else:
            return

        if number_entity is None:
            return

        if number_entity.is_dirty:
            try:
                await number_entity.async_push_to_hardware()
            except Exception:
                _LOGGER.warning(
                    "Failed to push %s reserve to hardware after mode switch",
                    new_mode.value, exc_info=True,
                )
        else:
            number_entity.sync_from_hardware(hw_value)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FranklinWHCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FranklinOperatingModeSelect(coordinator)])
