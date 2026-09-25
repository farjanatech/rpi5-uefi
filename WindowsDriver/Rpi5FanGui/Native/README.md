# Raspberry Pi 5 Fan Control — standalone edition

This native C++/Win32 edition sits alongside the original WPF GUI. The WPF project, installer, firmware and kernel drivers are unchanged.

## Run

Copy **Rpi5FanControl-ARM64.exe** anywhere on a Raspberry Pi 5 running Windows 11 ARM64, then double-click. It requests administrator permission to contact the fan driver. No .NET, Python, WebView2, extra GUI DLLs, external images, or Visual C++ Redistributable installation is needed. The C/C++ runtime is statically linked; operating-system DLLs are used normally.

**Existing drivers are still required.** The application uses the same `\\.\Rpi5Fan` exp.6 API v2 interface as the original GUI, plus the existing temperature-provider driver. It does not install a driver, change UEFI, or bypass driver safety policies. An unknown/incompatible/disconnected driver disables control and displays an explicit warning. Check the physical cooler rather than assuming that the animation proves rotation.

Select **Automatic** for driver-managed cooling; choose a value from **30–100%** and press **Apply manual** for a fixed request; use **Force 100%** for the driver's existing fail-safe command. Moving the slider alone sends no command. Closing the GUI leaves the current driver mode in place. Select Automatic before closing when automatic cooling is desired.

## Image and animation

The exact user-supplied 128×128 PNG is retained at `assets/fan-user.png` and embedded in the executable. Its Git blob hash is `4799bfe0ce47fd1ce375630bc83cb2cbfdc5287c`. No substitute fan artwork is used. A high-contrast mint tint is applied to its existing alpha mask. The executable icon contains 16, 24, 32, 48, 64, 128 and 256-pixel variants generated from that same image; upscaling does not invent higher-resolution source detail.

Rotation uses elapsed time, exact exponential acceleration integration, an adjusted hub pivot, anti-aliased rendering and double buffering. Its speed changes without restarting the rotation. The frame timer targets roughly 60 updates per second; this is not a guarantee of 60 FPS on every device. Rotation is **illustrative**, not literal mechanical RPM. Valid tachometer readings are shown separately; otherwise the caption explicitly says RPM is unavailable. A valid 0-RPM reading or an unavailable driver stops the visualization without resetting its angle. Animation is suspended when minimized, when Windows disables client animations, or with **Pause visual**. Pausing the visual never changes the physical fan setting.

Driver communication and CSV writing run on one worker thread, independently of rendering. Log failures do not disable fan control. CSV logs use `%LOCALAPPDATA%\Rpi5Fan\Logs`; recent activity is also displayed in the window.

## Size and packaging

The build rejects executables larger than **20,000,000 bytes (20 MB)** and reports actual bytes, decimal MB and SHA-256 in `BuildInfo.txt`. A native executable can be much smaller than 10 MB; it is deliberately not padded to meet an artificial minimum. The image and icon are compiled-in resources, not files that must be kept beside the executable. No self-extracting wrapper or executable packer is used.

## Build from the repository

Install Visual Studio 2022 C++ tools including ARM64 tools, CMake 3.24+ and the Windows SDK on the build machine. From the repository root:

```powershell
cmake -S WindowsDriver/Rpi5FanGui/Native -B out-native-arm64 -G "Visual Studio 17 2022" -A ARM64
cmake --build out-native-arm64 --config Release
```

Output: `out-native-arm64/Release/Rpi5FanControl-ARM64.exe`.

The **Fan GUI standalone** GitHub Actions workflow builds ARM64 and x64 editions, checks size and PE architecture, inspects DLL dependencies, and runs self-tests and a driver-free UI snapshot. The x64 edition is for development/preview on a normal PC; the ARM64 executable is the Pi build. `--self-test` validates the embedded PNG and animation math. `--preview` displays clearly labeled simulated values without opening a driver or creating logs. `--snapshot` does the same, saves `preview.png` in the working directory and exits.

The GUI is unsigned. Build/preview tests do not establish compatibility with a particular Pi firmware/driver installation. Verify Automatic, Manual and Force 100%, provider failures, actual cooling, DPI scaling, sleep/resume and disconnect behavior on real hardware before treating it as a hardware-verified release. This is a GUI-only candidate, not a newly verified fan-driver release.
