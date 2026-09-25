# Raspberry Pi 5 Fan Control One-Shot Setup beta.3

## Device-detection correction

Beta.2 incorrectly reported the temperature device missing on a Pi whose Windows CIM inventory showed BOTH `ACPI\RPI000F\0` and `ACPI\RPI0010\0`, Present=True, Code 28 and empty names. That diagnostic establishes an installer detection failure, not an absent firmware device. The exact cause of the earlier PnpDevice-cmdlet lookup failure has not been established on that Pi.

Beta.3 replaces that lookup with direct `Win32_PnPEntity` CIM discovery, the same query family that succeeded on the user's machine. It matches exact approved ACPI hardware IDs, uses the discovered instance ID, and accepts a nameless Code-28 device as present and awaiting a driver. Driver metadata is not required for this fresh-install state. Once a driver is selected, its properties are read through CIM GetDeviceProperties with a Win32_PnPSignedDriver fallback. Enumeration failures, ambiguous matches, unknown presence and missing selected-driver metadata are reported separately, not silently converted into a firmware-missing message. Code 12, disabled-device, newer-driver and unknown-provider protections remain.

No UEFI update or reinstallation of Windows is part of this fix. The original exp.6 drivers and standalone GUI are unchanged.

## Install

Run `Rpi5FanControl-OneShot-ARM64-Setup.exe` on Windows 11 ARM64 on the Pi. Confirm the wizard says **0.2.0-beta.3**, approve administrator access and the driver/test-signing consent page. The offline package includes the original Rpi5Temp and Rpi5Fan driver version 2026.8.18.6 and the updated standalone GUI.

When test signing is already configured AND active, the BCD change is skipped. Otherwise setup requests the required restart before loading test-signed drivers. Sign in to the same installing administrator after restarting; the named continuation task resumes installation. Healthy correctly selected bundled-version drivers and already-present certificate entries are skipped. Temperature is installed first, then fan control. Existing driver control mode is preserved.

Open **Raspberry Pi 5 Fan Control - Standalone** on the desktop and select Automatic for temperature-managed cooling. Check the physical cooler. Setup verifies driver health and live API v2 readiness before reporting installation complete; the animation alone does not prove physical rotation.

The setup EXE and GUI are unsigned; the original kernel packages are test-signed. Test signing is a persistent system-wide boot setting permitting test-signed drivers, not normal production signing. Setup does not disable Secure Boot or Memory Integrity, suspend encryption, or flash firmware. A blocking security or resource-conflict condition is reported rather than bypassed. Uninstall removes the GUI/setup and continuation task, but leaves drivers, certificate and test signing in place; logs can remain.

Installation folder: `%ProgramFiles%\RPi5FanControl-OneShot`. Post-install logs: `Setup\Logs`; last result: `Setup\LastResult.txt`. Preflight results are in the Inno Setup log in the Windows temporary folder. The continuation task keeps its legacy name `RPi5Fan-OneShot-beta2-Resume` so updates clean up existing pending tasks.

## Tests and limitations

CI runs policy tests, regression tests using the user's exact nameless Code-28 diagnostic-record shape, absent/ambiguous/failed-query cases, healthy-driver skip and driver-property fallback cases. The tests also exercise real read-only Windows CIM driver-property retrieval. The compiled installer is tested on Windows ARM64 for refusal when Pi devices are genuinely absent.

These automated and simulated tests are not a physical-Pi fresh installation or reboot-continuation test. This remains an experimental prerelease pending verification on the target Pi.
