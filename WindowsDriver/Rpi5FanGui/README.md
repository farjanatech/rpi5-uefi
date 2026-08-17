# Raspberry Pi 5 Fan Control GUI (Windows 11 ARM64)

This WPF utility is the user-mode companion for the experimental `Rpi5Fan`
KMDF driver. It targets native Windows ARM64 and talks to the driver through
`\\.\Rpi5Fan` IOCTLs.

## Safety policy

- The GUI has no fan-stop command.
- Manual fan control is restricted to 30-100%.
- Selecting Automatic or Manual first asks the driver to hold 100% until the
  next valid temperature sample is available.
- If temperature telemetry fails, the driver commands 100%.
- At or above 85 C, the driver overrides manual mode and commands 100%.
- Driver D0 exit and hardware release request 100% before resources are
  released.
- Actual RPM is intentionally shown as unavailable until a tachometer input is
  implemented. The displayed fan percentage is the commanded PWM duty.

## Dashboard

The GUI shows:

- BCM2712 SoC temperature
- commanded PWM percentage
- Automatic/Manual control mode
- driver/hardware-ready state
- fail-safe and over-temperature override state
- consecutive temperature-read failures
- recent events and telemetry samples

CSV logs are written to:

`%LOCALAPPDATA%\Rpi5Fan\Logs\rpi5fan-YYYY-MM-DD.csv`

## Build on Windows

Requirements:

- Windows 11
- .NET 8 SDK with ARM64 support

From this directory:

```powershell
dotnet restore
dotnet build -c Release -r win-arm64
```

To create a self-contained ARM64 build:

```powershell
dotnet publish -c Release -r win-arm64 --self-contained true
```

The application requests administrator elevation because it can change kernel
fan-control state.

## Driver API

The matching driver API is version 1 and is defined by
`../Rpi5Fan/Rpi5FanIoctl.h`. Driver package version for this experiment is
`2026.8.17.4`.
