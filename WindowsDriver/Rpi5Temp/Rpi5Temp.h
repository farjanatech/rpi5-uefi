/**
 * Experimental Raspberry Pi 5 BCM2712 temperature provider KMDF driver.
 *
 * SPDX-License-Identifier: BSD-2-Clause-Patent
 */
#pragma once

#include <ntddk.h>
#include <wdf.h>
#include "Rpi5TempIoctl.h"

typedef struct _TEMP_DEVICE_CONTEXT {
    PUCHAR Mailbox;
    ULONG MailboxLength;
    PVOID Message;
    PHYSICAL_ADDRESS MessagePhysical;
    WDFWAITLOCK Lock;
    ULONG LastTemperatureMilliCelsius;
    ULONG ConsecutiveFailures;
    BOOLEAN TemperatureValid;
    BOOLEAN HardwareReady;
} TEMP_DEVICE_CONTEXT, *PTEMP_DEVICE_CONTEXT;

WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(TEMP_DEVICE_CONTEXT, TempGetContext)

DRIVER_INITIALIZE DriverEntry;
EVT_WDF_DRIVER_DEVICE_ADD TempEvtDeviceAdd;
EVT_WDF_DEVICE_PREPARE_HARDWARE TempEvtPrepareHardware;
EVT_WDF_DEVICE_RELEASE_HARDWARE TempEvtReleaseHardware;
EVT_WDF_DEVICE_D0_ENTRY TempEvtD0Entry;
EVT_WDF_DEVICE_D0_EXIT TempEvtD0Exit;
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL TempEvtIoDeviceControl;
