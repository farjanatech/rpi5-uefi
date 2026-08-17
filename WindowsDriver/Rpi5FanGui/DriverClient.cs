using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Rpi5FanControl;

internal enum FanControlMode : uint
{
    Automatic = 0,
    Manual = 1
}

[StructLayout(LayoutKind.Sequential)]
internal struct DriverStatus
{
    public uint Size;
    public uint ApiVersion;
    public uint ControlMode;
    public uint CurrentPercent;
    public uint RequestedPercent;
    public uint TemperatureMilliCelsius;
    public uint TemperatureValid;
    public uint HardwareReady;
    public uint FailSafeActive;
    public uint OverTemperatureOverride;
    public uint ConsecutiveTemperatureFailures;
    public uint FanRpm;
    public uint FanRpmValid;
}

[StructLayout(LayoutKind.Sequential)]
internal struct ManualRequest
{
    public uint Size;
    public uint Percent;
}

internal sealed class DriverClient : IDisposable
{
    private const string DevicePath = @"\\.\Rpi5Fan";
    private const uint GenericRead = 0x80000000;
    private const uint GenericWrite = 0x40000000;
    private const uint FileShareRead = 0x00000001;
    private const uint FileShareWrite = 0x00000002;
    private const uint OpenExisting = 3;

    private const uint DeviceType = 0x8337;
    private const uint MethodBuffered = 0;
    private const uint FileReadAccess = 0x0001;
    private const uint FileWriteAccess = 0x0002;

    private static readonly uint IoctlGetStatus = CtlCode(0x800, FileReadAccess);
    private static readonly uint IoctlSetAuto = CtlCode(0x801, FileWriteAccess);
    private static readonly uint IoctlSetManual = CtlCode(0x802, FileWriteAccess);
    private static readonly uint IoctlSetFailSafe = CtlCode(0x803, FileWriteAccess);

    private SafeFileHandle? _handle;

    public bool IsConnected => _handle is { IsInvalid: false, IsClosed: false };

    public void Connect()
    {
        if (IsConnected)
        {
            return;
        }

        _handle?.Dispose();
        _handle = CreateFileW(
            DevicePath,
            GenericRead | GenericWrite,
            FileShareRead | FileShareWrite,
            IntPtr.Zero,
            OpenExisting,
            0,
            IntPtr.Zero);

        if (_handle.IsInvalid)
        {
            int error = Marshal.GetLastWin32Error();
            _handle.Dispose();
            _handle = null;
            throw new Win32Exception(error, "Unable to open the RPi5 fan driver.");
        }
    }

    public DriverStatus GetStatus()
    {
        EnsureConnected();
        int size = Marshal.SizeOf<DriverStatus>();
        IntPtr output = Marshal.AllocHGlobal(size);
        try
        {
            if (!DeviceIoControl(
                    _handle!, IoctlGetStatus,
                    IntPtr.Zero, 0,
                    output, (uint)size,
                    out uint returned, IntPtr.Zero))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Fan status request failed.");
            }

            if (returned < size)
            {
                throw new InvalidOperationException("The fan driver returned a short status record.");
            }

            DriverStatus status = Marshal.PtrToStructure<DriverStatus>(output);
            if (status.Size < size || status.ApiVersion != 1)
            {
                throw new InvalidOperationException(
                    $"Unsupported fan driver API (size={status.Size}, version={status.ApiVersion}).");
            }
            return status;
        }
        finally
        {
            Marshal.FreeHGlobal(output);
        }
    }

    public void SetAutomatic()
    {
        SendNoInput(IoctlSetAuto, "Unable to enable automatic fan control.");
    }

    public void SetFailSafe100()
    {
        SendNoInput(IoctlSetFailSafe, "Unable to force the fan to 100%.");
    }

    public void SetManual(uint percent)
    {
        if (percent is < 30 or > 100)
        {
            throw new ArgumentOutOfRangeException(nameof(percent), "Manual fan speed must be 30-100%.");
        }

        EnsureConnected();
        ManualRequest request = new()
        {
            Size = (uint)Marshal.SizeOf<ManualRequest>(),
            Percent = percent
        };

        IntPtr input = Marshal.AllocHGlobal(Marshal.SizeOf<ManualRequest>());
        try
        {
            Marshal.StructureToPtr(request, input, false);
            if (!DeviceIoControl(
                    _handle!, IoctlSetManual,
                    input, request.Size,
                    IntPtr.Zero, 0,
                    out _, IntPtr.Zero))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to set manual fan speed.");
            }
        }
        finally
        {
            Marshal.FreeHGlobal(input);
        }
    }

    private void SendNoInput(uint ioctl, string failureMessage)
    {
        EnsureConnected();
        if (!DeviceIoControl(
                _handle!, ioctl,
                IntPtr.Zero, 0,
                IntPtr.Zero, 0,
                out _, IntPtr.Zero))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), failureMessage);
        }
    }

    private void EnsureConnected()
    {
        if (!IsConnected)
        {
            Connect();
        }
    }

    private static uint CtlCode(uint function, uint access) =>
        (DeviceType << 16) | (access << 14) | (function << 2) | MethodBuffered;

    public void Dispose()
    {
        _handle?.Dispose();
        _handle = null;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFileW(
        string lpFileName,
        uint dwDesiredAccess,
        uint dwShareMode,
        IntPtr lpSecurityAttributes,
        uint dwCreationDisposition,
        uint dwFlagsAndAttributes,
        IntPtr hTemplateFile);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeviceIoControl(
        SafeFileHandle hDevice,
        uint dwIoControlCode,
        IntPtr lpInBuffer,
        uint nInBufferSize,
        IntPtr lpOutBuffer,
        uint nOutBufferSize,
        out uint lpBytesReturned,
        IntPtr lpOverlapped);
}
