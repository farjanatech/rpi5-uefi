/**
 * Raspberry Pi 5 BCM2712 property-mailbox temperature provider.
 *
 * This driver binds only to ACPI\RPI0010 (TMP0) from the exp.5B+ UEFI
 * layout. It owns the 0x107C013880-0x107C0138BF mailbox resource and exposes
 * validated SoC temperature to the separate Rpi5Fan driver.
 *
 * SPDX-License-Identifier: BSD-2-Clause-Patent
 */

#include "Rpi5Temp.h"

#define BCM2712_MAILBOX_PHYSICAL          0x000000107c013880ll
#define BCM2712_MAILBOX_LENGTH            0x40u

#define MBOX_READ                         0x00
#define MBOX_STATUS                       0x18
#define MBOX_WRITE                        0x20
#define MBOX_STATUS_FULL                  (1u << 31)
#define MBOX_STATUS_EMPTY                 (1u << 30)
#define MBOX_PROPERTY_CHANNEL             8u
#define MBOX_BUS_ALIAS                    0xc0000000u
#define MBOX_GET_TEMPERATURE              0x00030006u
#define MBOX_RESPONSE_SUCCESS             0x80000000u
#define MBOX_TAG_RESPONSE                 0x80000000u
#define MBOX_POLL_COUNT                   1000u
#define MBOX_POLL_DELAY_US                10u
#define TEMP_MIN_MILLIC                   5000u
#define TEMP_MAX_MILLIC                   150000u

const GUID GUID_DEVINTERFACE_RPI5TEMP =
    { 0xdeea6ba8, 0x318b, 0x465d,
      { 0xbe, 0xc8, 0x94, 0x41, 0xc4, 0x6e, 0x4d, 0xc3 } };

static __forceinline ULONG
TempRead32(_In_ PUCHAR Base, _In_ ULONG Offset)
{
    return READ_REGISTER_ULONG((PULONG)(Base + Offset));
}

static __forceinline VOID
TempWrite32(_In_ PUCHAR Base, _In_ ULONG Offset, _In_ ULONG Value)
{
    WRITE_REGISTER_ULONG((PULONG)(Base + Offset), Value);
}

static VOID
TempReleaseMemory(_Inout_ PTEMP_DEVICE_CONTEXT Context)
{
    if (Context->Message != NULL) {
        MmFreeContiguousMemory(Context->Message);
        Context->Message = NULL;
        Context->MessagePhysical.QuadPart = 0;
    }

    if (Context->Mailbox != NULL) {
        MmUnmapIoSpace(Context->Mailbox, Context->MailboxLength);
        Context->Mailbox = NULL;
        Context->MailboxLength = 0;
    }
}

_Success_(return != FALSE)
static BOOLEAN
TempReadTemperatureLocked(_Inout_ PTEMP_DEVICE_CONTEXT Context,
                          _Out_ PULONG MilliCelsius)
{
    volatile ULONG *message;
    ULONG request;
    ULONG value;
    ULONG i;

    if (!Context->HardwareReady || Context->Mailbox == NULL ||
        Context->Message == NULL || Context->MessagePhysical.HighPart != 0 ||
        Context->MessagePhysical.LowPart > 0x3fffffffu) {
        return FALSE;
    }

    message = (volatile ULONG *)Context->Message;
    RtlZeroMemory(Context->Message, PAGE_SIZE);
    message[0] = 8u * sizeof(ULONG);
    message[1] = 0;
    message[2] = MBOX_GET_TEMPERATURE;
    message[3] = 2u * sizeof(ULONG);
    message[4] = 0;
    message[5] = 0;
    message[6] = 0;
    message[7] = 0;

    request = (Context->MessagePhysical.LowPart + MBOX_BUS_ALIAS) |
              MBOX_PROPERTY_CHANNEL;
    KeMemoryBarrier();

    /* Drain stale responses, but never wait forever. */
    for (i = 0; i < MBOX_POLL_COUNT; ++i) {
        if ((TempRead32(Context->Mailbox, MBOX_STATUS) & MBOX_STATUS_EMPTY) != 0) {
            break;
        }
        (void)TempRead32(Context->Mailbox, MBOX_READ);
    }
    if (i == MBOX_POLL_COUNT) {
        return FALSE;
    }

    for (i = 0; i < MBOX_POLL_COUNT; ++i) {
        if ((TempRead32(Context->Mailbox, MBOX_STATUS) & MBOX_STATUS_FULL) == 0) {
            TempWrite32(Context->Mailbox, MBOX_WRITE, request);
            break;
        }
        KeStallExecutionProcessor(MBOX_POLL_DELAY_US);
    }
    if (i == MBOX_POLL_COUNT) {
        return FALSE;
    }

    for (i = 0; i < MBOX_POLL_COUNT; ++i) {
        if ((TempRead32(Context->Mailbox, MBOX_STATUS) & MBOX_STATUS_EMPTY) == 0) {
            value = TempRead32(Context->Mailbox, MBOX_READ);
            if (value == request) {
                KeMemoryBarrier();
                if (message[1] != MBOX_RESPONSE_SUCCESS ||
                    (message[4] & MBOX_TAG_RESPONSE) == 0 ||
                    message[6] < TEMP_MIN_MILLIC ||
                    message[6] > TEMP_MAX_MILLIC) {
                    return FALSE;
                }
                *MilliCelsius = message[6];
                return TRUE;
            }
        }
        KeStallExecutionProcessor(MBOX_POLL_DELAY_US);
    }

    return FALSE;
}

NTSTATUS
TempEvtPrepareHardware(_In_ WDFDEVICE Device,
                       _In_ WDFCMRESLIST ResourcesRaw,
                       _In_ WDFCMRESLIST ResourcesTranslated)
{
    PTEMP_DEVICE_CONTEXT context = TempGetContext(Device);
    PHYSICAL_ADDRESS mailboxStart = { 0 };
    ULONG mailboxLength = 0;
    ULONG memoryCount = 0;
    ULONG count;
    ULONG i;
    PHYSICAL_ADDRESS low = { 0 };
    PHYSICAL_ADDRESS high;
    PHYSICAL_ADDRESS boundary = { 0 };

    UNREFERENCED_PARAMETER(ResourcesRaw);

    count = WdfCmResourceListGetCount(ResourcesTranslated);
    for (i = 0; i < count; ++i) {
        PCM_PARTIAL_RESOURCE_DESCRIPTOR descriptor =
            WdfCmResourceListGetDescriptor(ResourcesTranslated, i);
        if (descriptor != NULL && descriptor->Type == CmResourceTypeMemory) {
            mailboxStart = descriptor->u.Memory.Start;
            mailboxLength = descriptor->u.Memory.Length;
            ++memoryCount;
        }
    }

    if (memoryCount != 1 || mailboxLength != BCM2712_MAILBOX_LENGTH ||
        mailboxStart.QuadPart != BCM2712_MAILBOX_PHYSICAL) {
        return STATUS_DEVICE_CONFIGURATION_ERROR;
    }

    context->MailboxLength = mailboxLength;
    context->Mailbox = MmMapIoSpaceEx(
        mailboxStart, mailboxLength, PAGE_READWRITE | PAGE_NOCACHE);
    if (context->Mailbox == NULL) {
        context->MailboxLength = 0;
        return STATUS_INSUFFICIENT_RESOURCES;
    }

    high.QuadPart = 0x3fffffff;
    context->Message = MmAllocateContiguousMemorySpecifyCache(
        PAGE_SIZE, low, high, boundary, MmNonCached);
    if (context->Message == NULL) {
        TempReleaseMemory(context);
        return STATUS_INSUFFICIENT_RESOURCES;
    }

    context->MessagePhysical = MmGetPhysicalAddress(context->Message);
    context->LastTemperatureMilliCelsius = 0;
    context->ConsecutiveFailures = 0;
    context->TemperatureValid = FALSE;
    context->HardwareReady = FALSE;
    return STATUS_SUCCESS;
}

NTSTATUS
TempEvtReleaseHardware(_In_ WDFDEVICE Device,
                       _In_ WDFCMRESLIST ResourcesTranslated)
{
    PTEMP_DEVICE_CONTEXT context = TempGetContext(Device);
    UNREFERENCED_PARAMETER(ResourcesTranslated);

    WdfWaitLockAcquire(context->Lock, NULL);
    context->HardwareReady = FALSE;
    context->TemperatureValid = FALSE;
    TempReleaseMemory(context);
    WdfWaitLockRelease(context->Lock);
    return STATUS_SUCCESS;
}

NTSTATUS
TempEvtD0Entry(_In_ WDFDEVICE Device,
               _In_ WDF_POWER_DEVICE_STATE PreviousState)
{
    PTEMP_DEVICE_CONTEXT context = TempGetContext(Device);
    ULONG temperature;
    UNREFERENCED_PARAMETER(PreviousState);

    WdfWaitLockAcquire(context->Lock, NULL);
    context->HardwareReady = (context->Mailbox != NULL && context->Message != NULL);
    if (context->HardwareReady && TempReadTemperatureLocked(context, &temperature)) {
        context->LastTemperatureMilliCelsius = temperature;
        context->TemperatureValid = TRUE;
        context->ConsecutiveFailures = 0;
    } else {
        context->TemperatureValid = FALSE;
        if (context->ConsecutiveFailures != MAXULONG) {
            ++context->ConsecutiveFailures;
        }
    }
    WdfWaitLockRelease(context->Lock);
    return context->HardwareReady ? STATUS_SUCCESS : STATUS_DEVICE_NOT_READY;
}

NTSTATUS
TempEvtD0Exit(_In_ WDFDEVICE Device,
              _In_ WDF_POWER_DEVICE_STATE TargetState)
{
    PTEMP_DEVICE_CONTEXT context = TempGetContext(Device);
    UNREFERENCED_PARAMETER(TargetState);

    WdfWaitLockAcquire(context->Lock, NULL);
    context->HardwareReady = FALSE;
    context->TemperatureValid = FALSE;
    WdfWaitLockRelease(context->Lock);
    return STATUS_SUCCESS;
}

VOID
TempEvtIoDeviceControl(_In_ WDFQUEUE Queue,
                       _In_ WDFREQUEST Request,
                       _In_ size_t OutputBufferLength,
                       _In_ size_t InputBufferLength,
                       _In_ ULONG IoControlCode)
{
    WDFDEVICE device = WdfIoQueueGetDevice(Queue);
    PTEMP_DEVICE_CONTEXT context = TempGetContext(device);
    PRPI5TEMP_STATUS output;
    ULONG temperature = 0;
    NTSTATUS status = STATUS_INVALID_DEVICE_REQUEST;
    size_t information = 0;

    UNREFERENCED_PARAMETER(OutputBufferLength);
    UNREFERENCED_PARAMETER(InputBufferLength);

    if (IoControlCode == IOCTL_RPI5TEMP_GET_TEMPERATURE) {
        status = WdfRequestRetrieveOutputBuffer(
            Request, sizeof(*output), (PVOID *)&output, NULL);
        if (NT_SUCCESS(status)) {
            WdfWaitLockAcquire(context->Lock, NULL);
            if (TempReadTemperatureLocked(context, &temperature)) {
                context->LastTemperatureMilliCelsius = temperature;
                context->TemperatureValid = TRUE;
                context->ConsecutiveFailures = 0;
            } else {
                context->TemperatureValid = FALSE;
                if (context->ConsecutiveFailures != MAXULONG) {
                    ++context->ConsecutiveFailures;
                }
            }

            RtlZeroMemory(output, sizeof(*output));
            output->Size = sizeof(*output);
            output->ApiVersion = RPI5TEMP_API_VERSION;
            output->TemperatureMilliCelsius = context->LastTemperatureMilliCelsius;
            output->TemperatureValid = context->TemperatureValid ? 1u : 0u;
            output->HardwareReady = context->HardwareReady ? 1u : 0u;
            output->ConsecutiveFailures = context->ConsecutiveFailures;
            WdfWaitLockRelease(context->Lock);
            information = sizeof(*output);
            status = STATUS_SUCCESS;
        }
    }

    WdfRequestCompleteWithInformation(Request, status, information);
}

NTSTATUS
TempEvtDeviceAdd(_In_ WDFDRIVER Driver,
                 _Inout_ PWDFDEVICE_INIT DeviceInit)
{
    WDF_PNPPOWER_EVENT_CALLBACKS pnp;
    WDF_OBJECT_ATTRIBUTES attributes;
    WDF_IO_QUEUE_CONFIG queueConfig;
    WDFDEVICE device;
    PTEMP_DEVICE_CONTEXT context;
    UNICODE_STRING symbolicLink = RTL_CONSTANT_STRING(L"\\DosDevices\\Rpi5Temp");
    NTSTATUS status;

    UNREFERENCED_PARAMETER(Driver);

    WDF_PNPPOWER_EVENT_CALLBACKS_INIT(&pnp);
    pnp.EvtDevicePrepareHardware = TempEvtPrepareHardware;
    pnp.EvtDeviceReleaseHardware = TempEvtReleaseHardware;
    pnp.EvtDeviceD0Entry = TempEvtD0Entry;
    pnp.EvtDeviceD0Exit = TempEvtD0Exit;
    WdfDeviceInitSetPnpPowerEventCallbacks(DeviceInit, &pnp);

    WDF_OBJECT_ATTRIBUTES_INIT_CONTEXT_TYPE(&attributes, TEMP_DEVICE_CONTEXT);
    attributes.ExecutionLevel = WdfExecutionLevelPassive;
    status = WdfDeviceCreate(&DeviceInit, &attributes, &device);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    context = TempGetContext(device);
    RtlZeroMemory(context, sizeof(*context));
    status = WdfWaitLockCreate(WDF_NO_OBJECT_ATTRIBUTES, &context->Lock);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    status = WdfDeviceCreateDeviceInterface(
        device, &GUID_DEVINTERFACE_RPI5TEMP, NULL);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    status = WdfDeviceCreateSymbolicLink(device, &symbolicLink);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(
        &queueConfig, WdfIoQueueDispatchSequential);
    queueConfig.EvtIoDeviceControl = TempEvtIoDeviceControl;
    return WdfIoQueueCreate(
        device, &queueConfig, WDF_NO_OBJECT_ATTRIBUTES, WDF_NO_HANDLE);
}

NTSTATUS
DriverEntry(_In_ PDRIVER_OBJECT DriverObject,
            _In_ PUNICODE_STRING RegistryPath)
{
    WDF_DRIVER_CONFIG config;
    WDF_DRIVER_CONFIG_INIT(&config, TempEvtDeviceAdd);
    return WdfDriverCreate(
        DriverObject, RegistryPath, WDF_NO_OBJECT_ATTRIBUTES, &config,
        WDF_NO_HANDLE);
}
