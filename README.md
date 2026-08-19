# FranklinWH Modbus

A Home Assistant custom integration for FranklinWH battery/aGate
systems, communicating directly over **local Modbus TCP** — no
FranklinWH cloud account, no internet access required. Everything
happens on your local network.

Built on top of the [`franklinwh_local_api`](https://github.com/hAr1x/franklinwh-local-api)
Python library (installed as a dependency).

## Features

- Fully local polling (`local_polling` IoT class), configurable interval
- Full UI-driven setup via Config Flow — no `configuration.yaml`
  editing required
- Device info card populated with the aGate's real manufacturer,
  model, firmware version, and serial number (read once at setup via
  SunSpec Model 1)
- Entities keep displaying their last known value through transient
  network dropouts instead of flipping to `unavailable`/`unknown` — a
  brief Modbus/network outage no longer blanks out your dashboard
- **Sensors**: battery power/SOC/SOH/capacity/energy, grid
  power/import/export/voltage/frequency, solar production, home load
  (high-resolution, ~1W precision), temperatures, TOU dispatch state,
  and diagnostic-only sensors for the raw hardware reserve registers
  and active battery command state — each with a distinct icon
  (battery, transmission tower, solar panel, etc.) rather than a
  generic default
- **Binary sensors**: grid connection status (icon reflects
  connected/disconnected), alarm active (icon reflects
  triggered/clear), battery command active
- **Select**: switches the aGate's native operating mode (Emergency
  Backup / Self-Consumption / TOU)
- **Number**: Self-Consumption reserve %, TOU reserve %, battery
  charge power (W), battery discharge power (W)
- **Switches**: battery charge, battery discharge — directly command
  the battery via the standard SunSpec M704 registers

## Reserve % coordination

The aGate hardware has a firmware defect: register `15509` (TOU
reserve) always mirrors whatever was last written to register `15508`
(Self-Consumption reserve), and vice versa — there is no way to store
two independent reserve values in hardware at the same time.

This integration handles that at the HA layer with a "dirty" flag on
each of the two reserve % Number entities:

- Setting a reserve Number's value in HA always updates its displayed
  value immediately.
  - If the mode that Number governs is the currently active hardware
    mode, the value is also pushed to hardware immediately. On
    success the new value is kept; on failure the display reverts to
    the previous value (hardware is unchanged, so this keeps HA and
    hardware in agreement).
  - If a different mode is active, nothing is written to hardware —
    the value is remembered in HA and marked dirty.
- While a Number's mode is the active mode, its displayed value tracks
  hardware on every poll (so changes made via the official FranklinWH
  app or cloud are picked up automatically). While a different mode is
  active, that Number's register is a firmware-defect mirror of the
  other mode's value and is not meaningful, so polling leaves its
  displayed value untouched.
- When you switch operating mode, the reserve Number for the mode you
  switched into is resolved immediately: a dirty Number's value is
  pushed to hardware; a non-dirty Number's display is set from
  hardware.

## Installation

### Via HACS (custom repository)

1. HACS → Integrations → ⋮ (top right) → Custom repositories
2. Add this repository's URL, category **Integration**
3. Find "FranklinWH Modbus" in HACS and install
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → search "FranklinWH"

### Manual installation

Clone this repository directly into your Home Assistant config
directory. The clone's target directory name matters: Home Assistant
requires the local folder name to exactly match this integration's
domain (`ha_franklinwh_modbus`, underscores), which is unrelated to
this repository's own name on GitHub (which uses hyphens) — so specify
the target directory explicitly rather than letting `git clone` name
it after the repository:

```bash
git clone https://github.com/hAr1x/ha-franklinwh-modbus.git custom_components/ha_franklinwh_modbus
```

Then restart Home Assistant and go to Settings → Devices & Services →
Add Integration → search "FranklinWH".

## Configuration

Initial setup via the UI only asks for the connection basics:

| Field | Description | Default |
|---|---|---|
| Name | Device name (also determines entity_id prefix) | `franklinwh` |
| IP Address | Your aGate's local IP | — |
| Port | Modbus TCP port | `502` |

Click **Configure** on the already-added integration's card (not "Add
Integration" again) to adjust the full set of options, including two
integration-specific tunables not present in the initial setup form:

| Option | Description | Default |
|---|---|---|
| Name / IP Address / Port | Same as initial setup, editable here | — |
| Watchdog (hours) | Auto-release timeout for manual battery charge/discharge commands | `0.5` (30 min) |
| Polling interval (seconds) | How often to poll the aGate | `10` |

## Requirements

- Modbus TCP must be enabled on your aGate (contact your installer or
  FranklinWH support if it isn't).
- The battery charge/discharge switches use standard SunSpec registers
  and work regardless of the "SPAN Modbus" write unlock status.
- Switching operating mode and setting reserve % use FranklinWH's
  proprietary extension registers, which require the installer-level
  "SPAN Modbus" write unlock. Without it, these writes fail with a
  clear error (reads always work regardless).

## Disclaimer

This project has no affiliation with FranklinWH. See
[DISCLAIMER.md](DISCLAIMER.md) for the full disclaimer, including
"use at your own risk" terms.

## License

GNU General Public License v3.0 or later (GPLv3+). See
[LICENSE](LICENSE) for the full text.
