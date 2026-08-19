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

"""Binary sensor entities for the FranklinWH Modbus integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FranklinWHCoordinator
from .entity import FranklinWHBaseEntity
from franklinwh_local_api import FranklinWHStatus


@dataclass(frozen=True, kw_only=True)
class FranklinBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[FranklinWHStatus], bool]
    extra_attrs_fn: Callable[[FranklinWHStatus], dict] | None = None
    icon_on: str | None = None
    icon_off: str | None = None


BINARY_SENSORS: tuple[FranklinBinarySensorDescription, ...] = (
    FranklinBinarySensorDescription(
        key="grid_connected",
        translation_key="grid_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda s: s.grid_connected,
        icon_on="mdi:transmission-tower",
        icon_off="mdi:transmission-tower-off",
    ),
    FranklinBinarySensorDescription(
        key="alarm_active",
        translation_key="alarm_active",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: s.alarm_active,
        extra_attrs_fn=lambda s: {"alarms": s.alarms},
        icon_on="mdi:alert",
        icon_off="mdi:check-circle",
    ),
    FranklinBinarySensorDescription(
        key="battery_command_active",
        translation_key="battery_command_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.battery_command_active,
    ),
)


class FranklinBinarySensor(FranklinWHBaseEntity, BinarySensorEntity):
    entity_description: FranklinBinarySensorDescription

    def __init__(
        self,
        coordinator: FranklinWHCoordinator,
        description: FranklinBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def icon(self) -> str | None:
        is_on = self.is_on
        if is_on is None:
            return None
        return self.entity_description.icon_on if is_on else self.entity_description.icon_off

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.coordinator.data is None or self.entity_description.extra_attrs_fn is None:
            return None
        return self.entity_description.extra_attrs_fn(self.coordinator.data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FranklinWHCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        FranklinBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )
