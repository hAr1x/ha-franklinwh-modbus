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

"""Config flow for the FranklinWH Modbus integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_NAME,
    CONF_POLLING_SECONDS,
    CONF_WATCHDOG_HOURS,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_POLLING_SECONDS,
    DEFAULT_WATCHDOG_HOURS,
    DOMAIN,
)
from franklinwh_local_api import FranklinWHConnectionError, FranklinWHLocalClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
    }
)


async def _async_validate_connection(host: str, port: int) -> None:
    """Attempt a connection + one status read to verify the aGate is
    reachable before allowing the config entry to be created.

    Raises FranklinWHConnectionError on failure.
    """
    client = FranklinWHLocalClient(host=host, port=port)
    try:
        await client.connect()
        await client.async_get_status()
    finally:
        await client.close()


class FranklinWHModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow (UI-driven, no YAML required)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            name = user_input[CONF_NAME]

            try:
                await _async_validate_connection(host, port)
            except FranklinWHConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during setup validation")
                errors["base"] = "unknown"

            if not errors:
                self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_HOST: host,
                        CONF_PORT: port,
                    },
                    options={
                        CONF_WATCHDOG_HOURS: DEFAULT_WATCHDOG_HOURS,
                        CONF_POLLING_SECONDS: DEFAULT_POLLING_SECONDS,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "FranklinWHModbusOptionsFlow":
        return FranklinWHModbusOptionsFlow()


class FranklinWHModbusOptionsFlow(config_entries.OptionsFlow):
    """Options flow, reachable via the integration's 'CONFIGURE' button
    in HA's Devices & Services UI. Lets the user edit host/port/name
    plus the two integration-specific tunables (watchdog hours, polling
    interval) without needing to remove and re-add the integration.

    self.config_entry is provided by the OptionsFlow base class.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            try:
                await _async_validate_connection(host, port)
            except FranklinWHConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during options validation")
                errors["base"] = "unknown"

            if not errors:
                # data (name/host/port) and options (watchdog/polling)
                # are stored separately in a ConfigEntry - update both.
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        **self.config_entry.data,
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_HOST: host,
                        CONF_PORT: port,
                    },
                )
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_WATCHDOG_HOURS: user_input[CONF_WATCHDOG_HOURS],
                        CONF_POLLING_SECONDS: user_input[CONF_POLLING_SECONDS],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=current.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Required(CONF_HOST, default=current.get(CONF_HOST)): str,
                vol.Required(
                    CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)
                ): vol.Coerce(int),
                vol.Required(
                    CONF_WATCHDOG_HOURS,
                    default=current.get(CONF_WATCHDOG_HOURS, DEFAULT_WATCHDOG_HOURS),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_POLLING_SECONDS,
                    default=current.get(CONF_POLLING_SECONDS, DEFAULT_POLLING_SECONDS),
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
