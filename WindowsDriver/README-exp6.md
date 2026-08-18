# Raspberry Pi 5 Fan Control exp.6

Experimental Windows 11 ARM64 package for the Raspberry Pi 5 Active Cooler using the validated exp.5B split ACPI layout.

## Architecture

- `ACPI\RPI000F` -> `Rpi5Fan.sys`: owns only the four RP1 fan-control MMIO resources.
- `ACPI\RPI0010` -> `Rpi5Temp.sys`: owns only BCM2712 property mailbox `0x107C013880-0x107C0138BF`.
- `Rpi5Fan.sys` queries `Rpi5Temp.sys` through a bounded synchronous KMDF I/O target request.
- `Rpi5FanControl.exe` talks only to `Rpi5Fan.sys`.

The split is required because physical exp.5B testing confirmed that combining the BCM2712 mailbox with the RP1 FAN0 resources causes Windows Code 12, while the split devices allocate successfully.

## Safety policy

- UEFI hands Windows a 100% fan command at ExitBootServices.
- Fan driver D0 entry commands 100% before telemetry is used.
- Missing/unavailable temperature provider -> 100%.
- Invalid/failed temperature read -> 100%.
- Temperature >= 85 C -> 100%.
- Normal fan-driver D0 exit/release -> request 100% before releasing hardware.
- Manual mode is limited to 30-100%.
- No IOCTL or GUI command can request 0%.

An abrupt kernel crash after a lower PWM command cannot execute cleanup; hardware may retain the last commanded non-zero 30-100% value. An independent hardware/firmware watchdog would be required to guarantee automatic 100% after an arbitrary hard crash.

## Install

Use the matching exp.5B/exp.6 UEFI first. Confirm `pnputil /enum-devices /problem 12` does not list `ACPI\RPI000F\0` or `ACPI\RPI0010\0`.

Extract the combo ZIP and run `Install.cmd`. The installer installs the temperature provider first, then the fan driver, verifies both devices reach Code 0 with version `2026.8.18.6`, and creates a Desktop shortcut to the GUI.

These drivers are test-signed experimental builds. If Windows test-signing is disabled, the installer enables it and asks for a reboot before installing either driver.

## GUI

The GUI shows SoC temperature, commanded PWM percentage, automatic/manual mode, split temperature-provider health, fail-safe state, over-temperature state, and CSV logs in `%LOCALAPPDATA%\Rpi5Fan\Logs`.

Actual fan RPM is not reported because tachometer support is not implemented yet.
