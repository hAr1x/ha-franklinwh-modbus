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

"""Minimal FranklinWH Cloud API client for the two write operations
this integration needs as a fallback: switching operating mode and
updating reserve %.

This is NOT a general-purpose FranklinWH Cloud API library - it is a
small, internal-use-only client scoped to exactly what this
integration needs. For a complete Cloud API client (TOU schedules,
storm settings, smart circuits, etc.), see the franklinwh-cloud
project (https://github.com/hAr1x/franklinwh-cloud).

This client is only ever used for the "write" side of mode-switching
and reserve % updates, and only when the user has explicitly enabled
Cloud Control in this integration's options (disabled by default). All
read-side data - every sensor, binary_sensor, and the displayed value
of every select/number entity - continues to come exclusively from
local Modbus polling, regardless of whether Cloud Control is enabled.
See LIMITATIONS.md for the full rationale.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx
from franklinwh_local_api import OperatingMode

_LOGGER = logging.getLogger(__name__)

_URL_BASE = "https://energy.franklinwh.com/"
_LOGIN_URL = _URL_BASE + "hes-gateway/terminal/initialize/appUserOrInstallerLogin"
_HOME_GATEWAY_LIST_URL = _URL_BASE + "hes-gateway/terminal/getHomeGatewayList"
_TOU_LIST_URL = _URL_BASE + "hes-gateway/terminal/tou/getGatewayTouListV2"
_UPDATE_MODE_URL = _URL_BASE + "hes-gateway/terminal/tou/updateTouModeV2"
_UPDATE_SOC_URL = _URL_BASE + "hes-gateway/terminal/tou/updateSocV2"

# Emulates a known-working FranklinWH mobile app version string in the
# outbound request header - some endpoints reject requests missing
# this header entirely.
_EMULATE_APP_VERSION = "APP2.4.1"

_LOGIN_TYPE_USER = 0  # homeowner/app user (not installer)

_TOKEN_EXPIRED_CODES = (401, 10009)
_SUCCESS_CODES = (200, 176)  # 176 = queued for offline sync, still a success

_MODE_TO_WORKMODE: dict[OperatingMode, int] = {
    OperatingMode.TOU: 1,
    OperatingMode.SELF_CONSUMPTION: 2,
    OperatingMode.EMERGENCY_BACKUP: 3,
}
# Fallback only - used if a profile entry is somehow missing its own
# oldIndex field. The gateway's own returned value is always preferred;
# see async_set_mode_cloud()'s docstring for why this must not be
# treated as a universal constant.
_MODE_TO_OLDINDEX_FALLBACK: dict[OperatingMode, int] = {
    OperatingMode.TOU: 3,
    OperatingMode.SELF_CONSUMPTION: 2,
    OperatingMode.EMERGENCY_BACKUP: 1,
}


class FranklinWHCloudError(Exception):
    """Raised for any FranklinWH Cloud API failure (network error, or
    a response the API itself reports as unsuccessful)."""


class FranklinWHCloudAuthError(FranklinWHCloudError):
    """Raised when login fails (bad credentials, locked account)."""


class FranklinWHCloudClient:
    """Minimal, internal-use-only FranklinWH Cloud API client.

    Usage:
        cloud = FranklinWHCloudClient(email, password)
        await cloud.async_set_mode_cloud(OperatingMode.TOU)
        await cloud.async_update_soc_cloud(OperatingMode.SELF_CONSUMPTION, 30)
        await cloud.async_close()
    """

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._token: str | None = None
        self._gateway_id: str | None = None
        self._session = httpx.AsyncClient(http2=True)

    async def async_close(self) -> None:
        await self._session.aclose()

    # ------------------------------------------------------------------
    # Auth / gateway discovery
    # ------------------------------------------------------------------

    async def _async_login(self) -> None:
        form = {
            "account": self._email,
            "password": hashlib.md5(self._password.encode("utf-8")).hexdigest(),
            "lang": "en_US",
            "type": _LOGIN_TYPE_USER,
        }
        resp = await self._session.post(
            _LOGIN_URL,
            data=form,
            headers={"softwareversion": _EMULATE_APP_VERSION},
            timeout=30,
        )
        js = resp.json()
        if js.get("code") != 200:
            raise FranklinWHCloudAuthError(
                f"FranklinWH Cloud login failed: {js.get('message', 'unknown error')}"
            )
        self._token = js["result"]["token"]

    async def _async_discover_gateway(self) -> None:
        resp = await self._async_request("GET", _HOME_GATEWAY_LIST_URL, {})
        gw_list = resp.get("result") or []
        if not gw_list:
            raise FranklinWHCloudError(
                "No FranklinWH gateways found on this account"
            )
        # Most homes have exactly one aGate - use the first one found.
        self._gateway_id = gw_list[0]["id"]

    async def _async_ensure_ready(self) -> None:
        if self._token is None:
            await self._async_login()
        if self._gateway_id is None:
            await self._async_discover_gateway()

    # ------------------------------------------------------------------
    # Low-level HTTP helper (with automatic re-login retry on expired token)
    # ------------------------------------------------------------------

    async def _async_request(
        self, method: str, url: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        params = {**params, "lang": "en_US"}

        async def _do() -> dict[str, Any]:
            resp = await self._session.request(
                method, url, params=params,
                headers={"loginToken": self._token or ""}, timeout=30,
            )
            return resp.json()

        js = await _do()
        if js.get("code") in _TOKEN_EXPIRED_CODES:
            _LOGGER.debug("FranklinWH Cloud token expired - re-logging in")
            await self._async_login()
            js = await _do()
        return js

    # ------------------------------------------------------------------
    # Public write operations
    # ------------------------------------------------------------------

    async def async_set_mode_cloud(
        self, mode: OperatingMode, soc: int | None = None
    ) -> None:
        """Switch the aGate's operating mode via the FranklinWH Cloud API.

        Used as a fallback when local Modbus writes to register 15507
        are not accepted by the hardware (no physical SPAN panel write
        unlock granted - see LIMITATIONS.md).

        If soc is None, the target mode's currently-saved reserve % is
        read fresh from the gateway's own TOU list and passed back
        unchanged - this call does not modify the reserve in that case,
        it only avoids omitting a field the API requires.

        Storm Hedge (stromEn) and oldIndex are read fresh from the
        gateway's own TOU list response and passed back verbatim.
        """
        await self._async_ensure_ready()
        work_mode = _MODE_TO_WORKMODE[mode]

        # This endpoint only accepts POST.
        tou_res = await self._async_request(
            "POST", _TOU_LIST_URL, {"gatewayId": self._gateway_id, "showType": "1"}
        )
        result = tou_res.get("result") or {}
        entries = [e for e in result.get("list", []) if e.get("workMode") == work_mode]
        if not entries:
            raise FranklinWHCloudError(
                f"Mode {mode.value} (workMode={work_mode}) not found in this "
                f"aGate's TOU list"
            )
        entry = entries[0]

        params: dict[str, Any] = {
            "gatewayId": self._gateway_id,
            "currendId": entry.get("id"),
            "oldIndex": entry.get("oldIndex", _MODE_TO_OLDINDEX_FALLBACK[mode]),
            "workMode": work_mode,
            "soc": soc if soc is not None else entry.get("soc"),
            "electricityType": entry.get("electricityType", 1),
            "stromEn": result.get("stromEn", 1),
        }
        if mode == OperatingMode.EMERGENCY_BACKUP:
            # Indefinite backup by default - this integration does not
            # expose a UI for scheduled/timed backup duration.
            params["backupForeverFlag"] = 1

        resp = await self._async_request("POST", _UPDATE_MODE_URL, params)
        if resp.get("code") not in _SUCCESS_CODES:
            raise FranklinWHCloudError(
                f"Mode switch to {mode.value} failed: "
                f"{resp.get('message', resp.get('code'))}"
            )

    async def async_update_soc_cloud(self, mode: OperatingMode, soc: int) -> None:
        """Update the reserve % for a specific operating mode via the
        FranklinWH Cloud API, without switching to that mode.

        Unlike the local Modbus registers (15508/15509, which mirror
        each other and only reflect whichever mode is currently
        active), the Cloud API's workMode parameter addresses each
        mode's reserve independently - this mode does not need to be
        the currently active one for this call to take effect.
        """
        await self._async_ensure_ready()
        work_mode = _MODE_TO_WORKMODE[mode]
        params = {
            "gatewayId": self._gateway_id,
            "workMode": work_mode, "electricityType": 1, "soc": soc,
        }
        resp = await self._async_request("POST", _UPDATE_SOC_URL, params)
        if resp.get("code") not in _SUCCESS_CODES:
            raise FranklinWHCloudError(
                f"Reserve % update for {mode.value} failed: "
                f"{resp.get('message', resp.get('code'))}"
            )