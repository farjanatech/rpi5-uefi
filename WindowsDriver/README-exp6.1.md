# Raspberry Pi 5 Fan Control exp.6.1

exp.6.1 is a visual and packaging refresh of the hardware-verified exp.6 Windows 11 ARM64 fan-control stack.

## Backend status

The UEFI ACPI split, `Rpi5Temp.sys`, `Rpi5Fan.sys`, fan curve, fail-safe policy, and driver API remain unchanged from the verified exp.6 backend. The driver continues to control temperature automatically even when the GUI is closed.

## GUI refresh

- New dark dashboard with color-coded temperature, fan output, mode, driver, provider, and safety cards.
- Animated fan visual whose rotation speed follows the commanded PWM percentage. The animation is decorative telemetry and does not claim measured RPM.
- Custom fan artwork used for the window icon and embedded executable icon.
- Removed the previous tachometer/RPM explanatory footer.
- Existing automatic/manual/force-100 controls and CSV logging are retained.

## Safety

- UEFI hands Windows a 100% fan command at ExitBootServices.
- Fan driver enters D0 at 100%.
- Missing/failed/invalid temperature telemetry forces 100%.
- Temperature >=85 C forces 100%.
- Manual commands remain limited to 30-100%.
- Normal D0 exit/release requests 100%.
- An arbitrary hard kernel crash cannot execute driver cleanup; an independent watchdog would still be required to guarantee 100% after every possible crash.
