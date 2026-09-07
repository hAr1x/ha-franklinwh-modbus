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

"""Sensor entities for the FranklinWH Modbus integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from franklinwh_local_api import FranklinWHStatus
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import FranklinWHCoordinator
from .entity import FranklinWHBaseEntity


def _watts_to_kw(value: float) -> float:
    """Convert a raw Watts value (as stored on FranklinWHStatus) to kW,
    rounded to 3 decimal places (i.e. 1W precision)."""
    return round(value / 1000.0, 3)


def _wh_to_kwh(value: float) -> float:
    """Convert a raw Wh value to kWh, rounded to 3 decimal places."""
    return round(value / 1000.0, 3)


@dataclass(frozen=True, kw_only=True)
class FranklinSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value_fn to extract and
    convert the right field from a FranklinWHStatus snapshot."""

    value_fn: Callable[[FranklinWHStatus], float | int | str | None]


POWER_SENSORS: tuple[FranklinSensorDescription, ...] = (
    FranklinSensorDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:battery-charging",
        value_fn=lambda s: _watts_to_kw(s.battery_power_w),
    ),
    FranklinSensorDescription(
        key="battery_charging_power",
        translation_key="battery_charging_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        icon="mdi:battery-plus",
        value_fn=lambda s: _watts_to_kw(s.battery_charging_w),
    ),
    FranklinSensorDescription(
        key="battery_discharging_power",
        translation_key="battery_discharging_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        icon="mdi:battery-minus",
        value_fn=lambda s: _watts_to_kw(s.battery_discharging_w),
    ),
    FranklinSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:meter-electric",
        value_fn=lambda s: _watts_to_kw(s.grid_power_w),
    ),
    FranklinSensorDescription(
        key="grid_import_power",
        translation_key="grid_import_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        icon="mdi:transmission-tower-import",
        value_fn=lambda s: _watts_to_kw(s.grid_import_w),
    ),
    FranklinSensorDescription(
        key="grid_export_power",
        translation_key="grid_export_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        icon="mdi:transmission-tower-export",
        value_fn=lambda s: _watts_to_kw(s.grid_export_w),
    ),
    FranklinSensorDescription(
        key="solar_power",
        translation_key="solar_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:solar-power-variant",
        value_fn=lambda s: _watts_to_kw(s.solar_power_w),
    ),
    FranklinSensorDescription(
        key="home_load_power",
        translation_key="home_load_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:home-lightning-bolt",
        value_fn=lambda s: _watts_to_kw(s.home_load_w),
    ),
    FranklinSensorDescription(
        key="battery_command_charge_power",
        translation_key="battery_command_charge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        icon="mdi:battery-arrow-up",
        value_fn=lambda s: _watts_to_kw(s.battery_command_charge_w),
    ),
    FranklinSensorDescription(
        key="battery_command_discharge_power",
        translation_key="battery_command_discharge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        icon="mdi:battery-arrow-down",
        value_fn=lambda s: _watts_to_kw(s.battery_command_discharge_w),
    ),
)

ENERGY_SENSORS: tuple[FranklinSensorDescription, ...] = (
    FranklinSensorDescription(
        key="battery_capacity",
        translation_key="battery_capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:battery-sync",
        value_fn=lambda s: _wh_to_kwh(s.battery_capacity_wh),
    ),
    FranklinSensorDescription(
        key="battery_energy_available",
        translation_key="battery_energy_available",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:battery-unknown",
        value_fn=lambda s: _wh_to_kwh(s.battery_energy_wh),
    ),
)

PERCENTAGE_SENSORS: tuple[FranklinSensorDescription, ...] = (
    FranklinSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.battery_soc_pct,
    ),
    FranklinSensorDescription(
        key="battery_soc_rounded",
        translation_key="battery_soc_rounded",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.battery_soc_pct_rounded,
    ),
    FranklinSensorDescription(
        key="battery_soh",
        translation_key="battery_soh",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-variant",
        value_fn=lambda s: s.battery_soh_pct,
    ),
    FranklinSensorDescription(
        key="hw_self_reserve_pct",
        translation_key="hw_self_reserve_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        icon="mdi:percent-box",
        value_fn=lambda s: s.self_reserve_pct,
    ),
    FranklinSensorDescription(
        key="hw_tou_reserve_pct",
        translation_key="hw_tou_reserve_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        icon="mdi:percent-box",
        value_fn=lambda s: s.tou_reserve_pct,
    ),
)

VOLTAGE_SENSORS: tuple[FranklinSensorDescription, ...] = (
    FranklinSensorDescription(
        key="grid_voltage_ln",
        translation_key="grid_voltage_ln",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        icon="mdi:current-ac",
        value_fn=lambda s: s.grid_voltage_ln_v,
    ),
    FranklinSensorDescription(
        key="grid_voltage_ll",
        translation_key="grid_voltage_ll",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        icon="mdi:current-ac",
        value_fn=lambda s: s.grid_voltage_ll_v,
    ),
)

MISC_SENSORS: tuple[FranklinSensorDescription, ...] = (
    FranklinSensorDescription(
        key="grid_frequency",
        translation_key="grid_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sine-wave",
        value_fn=lambda s: s.grid_frequency_hz,
    ),
    FranklinSensorDescription(
        key="ambient_temperature",
        translation_key="ambient_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda s: s.ambient_temp_c,
    ),
    FranklinSensorDescription(
        key="cabinet_temperature",
        translation_key="cabinet_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        value_fn=lambda s: s.cabinet_temp_c,
    ),
    FranklinSensorDescription(
        key="tou_dispatch_state",
        translation_key="tou_dispatch_state",
        icon="mdi:calendar-clock",
        value_fn=lambda s: s.tou_dispatch_state,
    ),
    FranklinSensorDescription(
        key="battery_command_pct_raw",
        translation_key="battery_command_pct_raw",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        icon="mdi:percent",
        value_fn=lambda s: s.battery_command_pct_raw,
    ),
)

ALL_SENSORS: tuple[FranklinSensorDescription, ...] = (
    POWER_SENSORS + ENERGY_SENSORS + PERCENTAGE_SENSORS + VOLTAGE_SENSORS + MISC_SENSORS
)


class FranklinSensor(FranklinWHBaseEntity, SensorEntity):
    """A single read-only sensor backed by a FranklinSensorDescription."""

    entity_description: FranklinSensorDescription

    def __init__(
        self,
        coordinator: FranklinWHCoordinator,
        description: FranklinSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> float | int | str | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class FranklinBatteryMaxPowerSensor(FranklinWHBaseEntity, SensorEntity):
    """Nameplate max power (kW) for one battery command direction, from
    the M702 init read - set once at setup, never polled."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: FranklinWHCoordinator, direction: str) -> None:
        super().__init__(coordinator)
        self._direction = direction
        self._attr_translation_key = f"battery_{direction}_max_power"
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_battery_{direction}_max_power"
        )
        self._attr_icon = (
            "mdi:battery-charging"
            if direction == "charge"
            else "mdi:battery-arrow-down"
        )

    @property
    def native_value(self) -> float | None:
        return _watts_to_kw(self.coordinator.max_power_for(self._direction))


class FranklinBatteryCommandTimeRemainingSensor(FranklinWHBaseEntity, SensorEntity):
    """Time remaining (seconds) until the active battery command is
    automatically released.

    Computed locally as (persisted deadline - now) and refreshed on
    every coordinator poll - no extra aGate traffic. unknown when no
    command is active or no deadline is tracked.
    """

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: FranklinWHCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = "battery_command_time_remaining"
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_battery_command_time_remaining"
        )

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        if data.battery_command_charge_w > 0:
            active = "charge"
        elif data.battery_command_discharge_w > 0:
            active = "discharge"
        else:
            return None
        deadline = self.coordinator.deadline
        if deadline is None or self.coordinator.deadline_direction != active:
            return None
        return max(0.0, (deadline - dt_util.utcnow()).total_seconds())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FranklinWHCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        FranklinSensor(coordinator, description) for description in ALL_SENSORS
    ]
    entities.append(FranklinBatteryMaxPowerSensor(coordinator, "charge"))
    entities.append(FranklinBatteryMaxPowerSensor(coordinator, "discharge"))
    entities.append(FranklinBatteryCommandTimeRemainingSensor(coordinator))
    async_add_entities(entities)
