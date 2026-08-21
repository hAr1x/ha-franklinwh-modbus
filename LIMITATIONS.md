# Known Limitations

Technical details for the limitations mentioned in [README.md](README.md).

## Mode switching and reserve % may not work over local Modbus

FranklinWH's aGate exposes operating mode (register `15507`) and
reserve % (registers `15508`/`15509`) through a proprietary extension
block that sits outside the standard SunSpec register map. Writing to
this block requires an installer-level "SPAN Modbus" write unlock -
without it, the aGate accepts the write at the protocol level (it
echoes success) but silently discards it internally. The register
never actually changes, and there is no error returned to distinguish
this from a real write.

This is not a bug in this integration or in the underlying
`franklinwh_local_api` library - it's how the hardware behaves for
the vast majority of installations, which do not have a physical SPAN
smart panel provisioned by FranklinWH.

### Independent verification

A third-party report against the `franklinwh-modbus` reference
project, from a user with a physical SPAN Main 32 panel and confirmed
correct SPAN/SunSpec Modbus configuration (verified directly by
FranklinWH support), found the extension register block
(`15507`-`15509`, and its `16000`+ high-resolution mirrors) uniformly
rejects writes across every Modbus function code tested - FC06 (write
single register), FC16 (write multiple registers), FC22 (mask write),
and FC23 (read/write multiple) - even on a correctly configured SPAN
installation. See:
[david2069/franklinwh-modbus#5](https://github.com/david2069/franklinwh-modbus/issues/5).

The same report separately confirmed that the SunSpec Model 704
battery control registers (which this integration's battery
charge/discharge switches use) accept writes normally and are not
affected by this limitation.

FranklinWH support has also stated directly that third-party Modbus
polling (including tools like Home Assistant) is not an officially
supported interface, and that no register behavior - including
`15507`-`15509` - is documented or guaranteed for general/homeowner
use.

### What this means in practice

- **Battery charge/discharge (the two switches and their power
  Number entities)** use SunSpec Model 704, which is unaffected by
  this limitation and should work regardless of SPAN unlock status.
- **Operating mode (the select entity) and reserve % (the two
  Number entities)** use the proprietary extension block. If your
  aGate does not have a genuine SPAN panel with a granted write
  unlock, these writes will silently fail over local Modbus.
- This integration's local write attempts include a read-back
  verification step specifically to detect this failure mode and
  surface a clear error, rather than reporting false success.
- If this affects you, enable the optional **Cloud Control** fallback
  described below.

## Cloud Control fallback

When local Modbus writes for mode/reserve % aren't accepted, this
integration can optionally switch mode and update reserve % through
the FranklinWH Cloud API instead, using your FranklinWH account
credentials. This is implemented in `cloud.py` as a small,
purpose-built client - not a general Cloud API library.

- **Disabled by default.** Nothing about this integration's default
  behavior changes unless you explicitly enable it in the Options
  Flow and provide account credentials.
- **Only used for mode-switching and reserve %.** No other data or
  functionality goes through the cloud.
- **All readback stays local.** The displayed operating mode and
  displayed reserve % on every entity always come from the next local
  Modbus poll - never from the Cloud API - even when Cloud Control is
  enabled and used to perform the write. This keeps the integration's
  `local_polling` classification accurate: it describes how state is
  read, and state is always read locally.
- **Reserve % updates address each mode independently.** Unlike the
  local Modbus registers (which only reflect whichever mode is
  currently active, due to the mirroring behavior described below),
  the Cloud API's `updateSocV2` endpoint takes an explicit mode
  parameter and updates that mode's reserve % directly, regardless of
  which mode is currently active. This means the "dirty flag"
  mechanism described below (needed to work around the local Modbus
  hardware limitation) does not apply when Cloud Control is enabled -
  changes to either reserve % Number take effect immediately.

## Reserve % dirty-flag behavior (local Modbus only)

This section only applies when Cloud Control is **not** enabled (the
default). It does not apply to the Cloud Control path described
above.

The aGate hardware has a firmware defect: register `15509` (TOU
reserve) always mirrors whatever was last written to register `15508`
(Self-Consumption reserve), and vice versa - there is no way to store
two independent reserve values in hardware at the same time. Only one
of the two reserve % Number entities' underlying register is
meaningful at any given time: whichever one matches the aGate's
currently active operating mode.

This integration works around that with a "dirty" flag on each of the
two reserve % Number entities:

- Setting a reserve Number's value in HA always updates its displayed
  value immediately.
  - If the mode that Number governs is the currently active hardware
    mode, the value is also pushed to hardware immediately. On
    success the new value is kept; on failure the display reverts to
    the previous value (hardware is unchanged, so this keeps HA and
    hardware in agreement).
  - If a different mode is active, nothing is written to hardware -
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

The value and dirty flag persist across Home Assistant restarts.

## Other notes

- Home load is read from an undocumented FranklinWH extension
  register that provides ~1W resolution, in preference to the
  documented register which only updates in ~100W steps.
- A brief Modbus/network dropout does not blank out the dashboard -
  entities keep displaying their last known value until the next
  successful poll.
