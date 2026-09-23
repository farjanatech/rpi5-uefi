# RPi5 UEFI exp.0.4: clock and settings persistence candidate

Based on the hardware-used direct-SDIO exp.0.3 source `bda4c47`. This is a
firmware maintenance candidate, not a new Wi-Fi driver or a speed update.
GitHub software checks do not establish Raspberry Pi hardware success.

## Changes

- RTC boot initialization starts with initialized, unspecified timezone metadata.
  A valid clock is not reset to the firmware build date. An unprogrammed zero
  counter is seeded with build time as a placeholder, not as accurate local time.
- PC-style calendar-clock storage: preserve the time written by the OS, without
  a second timezone/DST adjustment in the mailbox library. This avoids a time
  jump if file-backed timezone metadata cannot persist after ExitBootServices.
  Dhaka UTC+06:00 is supported without a Bangladesh-specific firmware offset;
  other zones, fractional offsets and DST metadata work the same way. The OS
  owns timezone selection and DST transitions; firmware does not infer location.
- Reject dates outside the 32-bit RTC counter range rather than wrapping them.
- Submit menu changes with F10/Save. A boot-only two-second timer retries dirty
  settings, in addition to the existing boot/reset save hooks. Unsaved edits in
  the browser are not committed by this timer. Runtime Windows resets never
  call filesystem boot services.
- Check write length, flush result, read-back contents and close result. A
  failed save remains dirty for retry and produces a visible warning if the
  console is available. A changed store during saving is not marked clean.
- Reject wrong-size firmware files, different firmware code, and variable
  stores that do not match the image loaded at startup, before choosing a save
  target. Discovery itself no longer writes candidate files.
- Fan patches 0001-0003, direct-SDIO patch 0004, ACPI/PCIe configuration defaults,
  device trees, boot configuration and all pinned submodules remain unchanged.

## Safe update from exp.0.3

1. Keep your current working Wi-Fi driver installed. Shut down the Pi normally
   and disconnect power before removing its firmware boot medium.
2. On another PC, back up the **entire firmware boot partition** to a separate
   folder. Keep the old `RPI_EFI.fd` outside the boot root so you can restore it.
   Record your important UEFI settings and boot order before updating.
3. On the **actual medium from which the Pi loads UEFI**, replace only
   `RPI_EFI.fd` with the file from this package. Do not overwrite your customized
   `config.txt`, format any disk, update EEPROM, or change Windows boot files.
   The shipped FD has default variables: custom UEFI settings may need re-entry.
4. Safely eject the medium, reconnect it and power on. Confirm the fan still
   spins and Windows boots. Keep recovery media/the old firmware available.
5. In Windows choose `(UTC+06:00) Dhaka`, enable automatic time, and synchronize
   once after the update. An administrator can select this zone using
   `tzutil /s "Bangladesh Standard Time"`. Do not apply this command on the
   development PC unless you want to change that PC's zone too.
6. Restart normally while power remains connected. Confirm the date/time stays
   correct before network synchronization; separately confirm the UEFI clock.
7. Save one safe UEFI setting, wait at least three seconds, reboot, change it
   back, save and reboot again. **Do not disable the PCIe controller used by your
   boot/Windows disk** merely to perform this test. A test must not strand boot.

If boot fails, power off and restore the backed-up FD from another PC. Do not
reset all UEFI settings blindly or reinstall Windows.

## Limits and compatibility

- A battery is still required to retain the hardware clock when all main power
  is removed. An ordinary powered restart should not require an RTC battery.
- Firmware does not change Windows registry, timezone, Secure Boot, test
  signing, drivers, or network configuration. A bad Windows timezone or failed
  network synchronization remains an independent possible cause.
- Dual-boot systems must agree on local-clock vs UTC-clock policy. This package
  does not change another OS's policy or automatically convert an existing RTC.
  Synchronize once in the intended OS after updating. A later OS that writes a
  differently interpreted clock can still cause an offset on the next boot.
- File-backed variables still cannot be saved after ExitBootServices. This is
  not EEPROM-backed runtime NVRAM. Menu settings are persisted before OS entry;
  the clock no longer depends on persisted timezone offsets for its calendar.
- Boot media must remain writable and accessible to UEFI. Keep only one active
  root-level `RPI_EFI.fd` boot copy connected during testing. Byte-identical
  cloned boot media cannot be distinguished by content checks alone. Custom
  firmware filenames/paths are not supported by this inherited backend.
- Existing direct-SDIO driver and connector binaries do not require replacement.
  Older Wi-Fi **installers** explicitly require revision `bda4c47`; they may
  refuse a reinstall on this new revision. Do not bypass that check or modify
  their signed/hash-checked packages. A future driver installer must explicitly
  allow this tested firmware revision. Already-installed drivers keep working
  against the unchanged ACPI/device interface, subject to Pi validation.

## Evidence

GitHub compiles the real patched RTC library with the pinned EDK2 TimeBaseLib
and mocked mailbox. Tests cover all 2,881 minute offsets plus unspecified,
valid DST flags, metadata loss at reboot, leap dates, range limits and errors.
The real file save functions are tested with short writes, flush/read/close
failures, read-back mismatch, wrong target files, retry, generation changes and
the runtime guard. The packaged C0/D0 pinctrl tests still run unchanged. The
complete ARM64 firmware build must pass before publication.

Relevant design references:
- https://uefi.org/specs/UEFI/2.10/08_Services_Runtime_Services.html
- https://github.com/tianocore/edk2/blob/master/PcAtChipsetPkg/PcatRealTimeClockRuntimeDxe/PcRtc.c
- https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#real-time-clock-rtc
