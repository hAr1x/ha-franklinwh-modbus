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

"""Constants for the FranklinWH Modbus integration."""

DOMAIN = "ha_franklinwh_modbus"

# --- Config Flow / Options Flow keys ---
CONF_NAME = "name"
CONF_WATCHDOG_HOURS = "watchdog_hours"
CONF_POLLING_SECONDS = "polling_seconds"

# --- Defaults ---
DEFAULT_NAME = "franklinwh"
DEFAULT_PORT = 502
DEFAULT_WATCHDOG_HOURS = 0.5      # 30 minutes
DEFAULT_POLLING_SECONDS = 10

# --- Battery command power ranges (Watts) ---
BATTERY_POWER_MIN_W = 0
BATTERY_POWER_MAX_W = 5000
BATTERY_POWER_STEP_W = 50
DEFAULT_BATTERY_POWER_W = 1000

# --- Reserve % range ---
RESERVE_PCT_MIN = 5
RESERVE_PCT_MAX = 100
RESERVE_PCT_STEP = 1

# --- Operating mode select options ---
# Maps the UI-facing option label to the OperatingMode enum. Only the
# three "real" user-selectable modes are exposed (Standby and Manual
# are hardware-internal states, not valid write targets - see
# franklinwh_local_api's OperatingMode docstring).
MODE_LABEL_EMERGENCY_BACKUP = "Emergency Backup"
MODE_LABEL_SELF_CONSUMPTION = "Self-Consumption"
MODE_LABEL_TOU = "TOU"
