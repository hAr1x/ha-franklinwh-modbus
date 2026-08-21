# FranklinWH Modbus

Monitor and control your FranklinWH battery system directly from Home
Assistant - no cloud account needed for day-to-day monitoring.

This integration talks to your FranklinWH aGate over your local
network (Modbus TCP), so your data stays fast and private. An optional
cloud fallback is available for a couple of controls that some
installations can't do locally - see [Cloud Control](#cloud-control-optional)
below.

## What you get

- **Battery**: charge level, power flowing in/out, capacity, health
- **Grid**: import/export power, voltage, frequency, connection status
- **Solar**: current production
- **Home**: how much power your house is using right now
- **Temperatures**: ambient and cabinet
- **Alarms**: a sensor that lights up if the aGate reports a fault
- **Operating mode**: switch between Emergency Backup,
  Self-Consumption, and Time-of-Use right from Home Assistant
- **Reserve %**: set the battery reserve level for Self-Consumption
  and Time-of-Use modes
- **Manual battery control**: force the battery to charge or discharge
  at a specific power level, with an automatic safety timeout so it
  never gets left running by accident

Everything keeps showing its last known value during a brief network
hiccup instead of going blank, so your dashboard stays useful.

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations** → menu (⋮) → **Custom repositories**
2. Add this repository's URL and choose category **Integration**
3. Find **FranklinWH Modbus** in HACS and install it
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration**, search
   for "FranklinWH", and follow the setup steps

### Manual

Copy this repository into your Home Assistant `config/custom_components`
folder as `ha_franklinwh_modbus` (the folder name matters - it must be
exactly this, regardless of what this repository is named on GitHub),
then restart Home Assistant and add the integration as above.

## Setup

You'll need your aGate's IP address on your local network. You can
usually find this in your router's device list, or in the FranklinWH
app under your gateway's network settings.

| Field | What to enter |
|---|---|
| Name | Whatever you'd like to call this device |
| IP Address | Your aGate's local IP address |
| Port | Leave as `502` unless you know it's different |

Once added, click **Configure** on the integration's card at any time
to adjust the polling speed, the battery command safety timeout, or to
turn on the optional Cloud Control fallback described below.

## Cloud Control (optional)

Switching operating mode and setting reserve % require your aGate to
have a specific write permission unlocked ("SPAN Modbus"), which most
installations don't have - only homes with a genuine SPAN smart panel
provisioned by FranklinWH. If you try to switch modes or set a reserve
% and it doesn't take effect, this is almost certainly why.

If that's the case, you can enable **Cloud Control** in the
integration's options and enter your FranklinWH account email and
password. This lets those two controls fall back to going through
your FranklinWH account instead of the local connection. It's off by
default, and turning it on doesn't change anything else - all your
sensor data always comes from the local connection, with or without
Cloud Control enabled.

Battery charge/discharge control is not affected either way - it
always works locally, regardless of the SPAN permission above.

For the technical details behind all of this, see
[LIMITATIONS.md](LIMITATIONS.md).

## Disclaimer

This project has no affiliation with FranklinWH. See
[DISCLAIMER.md](DISCLAIMER.md) for the full disclaimer, including
"use at your own risk" terms.

## License

GNU General Public License v3.0 or later (GPLv3+). See
[LICENSE](LICENSE) for the full text.