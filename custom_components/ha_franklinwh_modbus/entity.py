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

"""Common base entity for the FranklinWH Modbus integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DEFAULT_NAME, DOMAIN
from .coordinator import FranklinWHCoordinator


class FranklinWHBaseEntity(CoordinatorEntity[FranklinWHCoordinator]):
    """Base class for all FranklinWH Modbus entities.

    Provides a shared DeviceInfo so every entity groups under a single
    device in HA's UI, named after the "Name" field the user chose (or
    the default "franklinwh") during config flow - this name is also
    what determines the entity_id prefix (e.g. sensor.franklinwh_...).
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: FranklinWHCoordinator) -> None:
        super().__init__(coordinator)
        device_name = coordinator.entry.data.get(CONF_NAME, DEFAULT_NAME)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=device_name,
            manufacturer=coordinator.device_info.manufacturer,
            model=coordinator.device_info.model,
            sw_version=coordinator.device_info.firmware_version,
            serial_number=coordinator.device_info.serial_number,
        )

    @property
    def available(self) -> bool:
        """Consider the entity available as long as we have ever
        successfully polled at least one status snapshot, even if the
        most recent poll failed (e.g. a transient network dropout).

        CoordinatorEntity's default `available` ties directly to
        `coordinator.last_update_success`, which flips every entity to
        "unavailable" on any single failed poll - even though
        `coordinator.data` still holds the last known-good snapshot
        (DataUpdateCoordinator does not clear `.data` on a failed
        refresh). That default causes every sensor/select/switch to
        briefly show "unavailable"/"unknown" during a short outage
        instead of retaining the last known value, which is the
        behavior we want here.

        Overriding to check `coordinator.data is not None` instead
        means entities keep displaying their last known values through
        transient failures, and only become genuinely unavailable
        before the very first successful poll (when there is truly no
        data to show yet).
        """
        return self.coordinator.data is not None
