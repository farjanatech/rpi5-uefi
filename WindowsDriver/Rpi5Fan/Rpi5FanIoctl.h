/**
 * Shared control API for the Raspberry Pi 5 Active Cooler driver.
 *
 * The driver never exposes a stop/0% command. Manual control is limited to
 * 30-100%, and telemetry failure or over-temperature conditions force 100%.
 * Include this file after the Windows/WDK headers that define GUID, ULONG,
 * CTL_CODE, METHOD_BUFFERED, FILE_READ_ACCESS, and FILE_WRITE_ACCESS.
 *
 * SPDX-License-Identifier: BSD-2-Clause-Patent
 */

#pragma once

#define RPI5FAN_API_VERSION 1u
#define RPI5FAN_MINIMUM_PERCENT 30u
#define RPI5FAN_MAXIMUM_PERCENT 100u

#define RPI5FAN_DEVICE_TYPE 0x8337u

#define IOCTL_RPI5FAN_GET_STATUS \
    CTL_CODE(RPI5FAN_DEVICE_TYPE, 0x800, METHOD_BUFFERED, FILE_READ_ACCESS)
#define IOCTL_RPI5FAN_SET_AUTO \
    CTL_CODE(RPI5FAN_DEVICE_TYPE, 0x801, METHOD_BUFFERED, FILE_WRITE_ACCESS)
#define IOCTL_RPI5FAN_SET_MANUAL \
    CTL_CODE(RPI5FAN_DEVICE_TYPE, 0x802, METHOD_BUFFERED, FILE_WRITE_ACCESS)
#define IOCTL_RPI5FAN_SET_FAILSAFE \
    CTL_CODE(RPI5FAN_DEVICE_TYPE, 0x803, METHOD_BUFFERED, FILE_WRITE_ACCESS)

typedef enum _RPI5FAN_CONTROL_MODE {
    Rpi5FanControlAutomatic = 0,
    Rpi5FanControlManual = 1
} RPI5FAN_CONTROL_MODE;

typedef struct _RPI5FAN_STATUS {
    ULONG Size;
    ULONG ApiVersion;
    ULONG ControlMode;
    ULONG CurrentPercent;
    ULONG RequestedPercent;
    ULONG TemperatureMilliCelsius;
    ULONG TemperatureValid;
    ULONG HardwareReady;
    ULONG FailSafeActive;
    ULONG OverTemperatureOverride;
    ULONG ConsecutiveTemperatureFailures;
    ULONG FanRpm;
    ULONG FanRpmValid;
} RPI5FAN_STATUS, *PRPI5FAN_STATUS;

typedef struct _RPI5FAN_MANUAL_REQUEST {
    ULONG Size;
    ULONG Percent;
} RPI5FAN_MANUAL_REQUEST, *PRPI5FAN_MANUAL_REQUEST;

/* {5AD47920-26FC-4EE8-AE95-1B27AD8D663B} */
extern const GUID GUID_DEVINTERFACE_RPI5FAN;
