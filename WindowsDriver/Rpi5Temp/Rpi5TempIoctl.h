/**
 * Kernel control API for the Raspberry Pi 5 BCM2712 temperature provider.
 *
 * SPDX-License-Identifier: BSD-2-Clause-Patent
 */
#pragma once

#define RPI5TEMP_API_VERSION 1u
#define RPI5TEMP_DEVICE_TYPE 0x8338u

#define IOCTL_RPI5TEMP_GET_TEMPERATURE \
    CTL_CODE(RPI5TEMP_DEVICE_TYPE, 0x800, METHOD_BUFFERED, FILE_READ_ACCESS)

typedef struct _RPI5TEMP_STATUS {
    ULONG Size;
    ULONG ApiVersion;
    ULONG TemperatureMilliCelsius;
    ULONG TemperatureValid;
    ULONG HardwareReady;
    ULONG ConsecutiveFailures;
} RPI5TEMP_STATUS, *PRPI5TEMP_STATUS;

/* {DEEA6BA8-318B-465D-BEC8-9441C46E4DC3} */
extern const GUID GUID_DEVINTERFACE_RPI5TEMP;
