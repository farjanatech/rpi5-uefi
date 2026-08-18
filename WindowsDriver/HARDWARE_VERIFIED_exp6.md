# Raspberry Pi 5 Fan Control exp.6 — Hardware Verified

Physical Raspberry Pi 5 / Windows 11 ARM64 verification was reported successful on 2026-08-19.

Verified release: `rpi5fan-v0.1.1-exp.6`

- Combined `Rpi5Temp` + `Rpi5Fan` driver installation is working on the target hardware.
- The Windows ARM64 GUI is working with the installed drivers.
- The validated exp.5B split-resource UEFI/ACPI layout remains the required firmware layout.
- Driver version is `2026.8.18.6`.

This verification does not change the documented limitations: actual tachometer RPM is not implemented, and an arbitrary hard kernel crash cannot guarantee a software transition back to 100% PWM without an independent watchdog.
