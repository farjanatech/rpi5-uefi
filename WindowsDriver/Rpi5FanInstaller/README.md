# Raspberry Pi 5 Fan Control One-Shot Setup beta.2

Run `Rpi5FanControl-OneShot-ARM64-Setup.exe` on Windows 11 ARM64 on the Pi and approve the wizard. This offline package contains the standalone GUI plus the original exp.6 Rpi5Temp and Rpi5Fan driver packages, version 2026.8.18.6. The original driver binaries and signatures are preserved.

Setup requires both firmware ACPI devices (`ACPI\RPI0010\0` and `ACPI\RPI000F\0`) to be present without Code 12. It is a Windows installer, not a firmware updater.

The consent page explains the persistent Windows test-signing change and installation of the original project test certificate. When test signing is already configured and active, that change is skipped. A correctly selected, healthy driver of the bundled version is also skipped. The temperature driver is processed before the fan driver.

A configured but not yet active test-signing setting requires a restart before driver installation. Setup offers a restart and resumes when the same installing administrator next signs in. Save your work first. Windows may request an additional driver restart. Automatic continuation is bounded; failures are logged rather than retried indefinitely.

Installed directory: `%ProgramFiles%\RPi5FanControl-OneShot`.
Logs: `Setup\Logs` inside that directory.
Latest result: `Setup\LastResult.txt`.
Continuation task: `RPi5Fan-OneShot-beta2-Resume`.

Setup reports completion only after the required drivers are healthy and live API v2 reports hardware readiness and valid temperature telemetry. Check the physical cooler too. Select Automatic in the GUI for temperature-based cooling; the GUI need not remain open. Setup preserves the driver's existing control mode.

Uninstall removes the GUI and the named continuation task. It leaves the drivers, certificate and test-signing setting in place; logs can remain. This avoids disrupting other devices that may depend on the current boot policy. Review those separately when retiring the installation.

The installer and GUI are unsigned, while the original kernel packages are test-signed. This is an experimental prerelease. Automated checks do not replace fresh-install, reboot and cooling tests on a physical Raspberry Pi.
