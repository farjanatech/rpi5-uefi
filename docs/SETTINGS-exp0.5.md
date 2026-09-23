# RPi5 UEFI exp.0.5: fix settings-save target rejection

This is a focused correction to exp.0.4, not a Wi-Fi driver or speed update.
GitHub software checks do not establish Raspberry Pi hardware success.

## Identified failure and correction

The exp.0.4 firmware returned from the user's NVMe was byte-for-byte identical
to the published FD, with an empty variable store. Its target check compared
the entire loaded outer firmware volume with the on-disk file. The SEC boot
code executes in place in RAM and changes its mailbox buffer and globals.
Those legitimate startup changes made the correct file fail the comparison.

The corrected check validates the pinned FV/FFS layout, compares the FV and SEC
headers, then compares everything after the SEC payload, including the complete
immutable compressed DXE image and trailing padding. It excludes the SEC
payload, whose live contents cannot serve as an on-disk identity. It fails closed
on malformed lengths, unexpected file types and unsupported extended layouts.
The original boot variable-store snapshot must still match the candidate file.
This is an accidental-wrong-target filter, not cryptographic authentication of
the whole firmware: SEC payload changes are deliberately not compared.

Only the existing variable region is written. Full-length write, flush,
read-back and close checks, dirty retry, boot-only timer and runtime guards
remain. Candidate-file close errors are also rejected.

The tests now model mutable SEC data and check malformed layouts, immutable
content mismatches, NV mismatches, write/flush/read/close failures and Gen 3 ->
Gen 2 -> Gen 3 persistence across simulated reloads. A second test compiles the
actual validation code against the built FD. It locates the real SEC mailbox
request, models its boot response, proves the old whole-FV comparison rejects
it, and requires the corrected comparison to accept it without any writes.
All executable tests and the ARM64 build run on GitHub, not the development PC.

## Safe update from exp.0.4

1. Keep the existing Windows/Wi-Fi driver installed. Shut down the Pi normally,
   disconnect its power, and access its actual NVMe firmware boot partition.
2. Back up that partition, especially the current `RPI_EFI.fd` and `config.txt`,
   outside its boot root. Keep recovery media available.
3. Replace **only `RPI_EFI.fd`** with this package's file. Preserve your existing
   `config.txt`, device trees, Windows files and drivers. Do not format anything,
   update EEPROM or reflash Windows. The new FD starts with default settings.
4. Safely eject, reconnect and boot. Confirm the firmware revision matches
   `direct_sdio_branch_commit` in `SOURCE_REVISIONS.txt`, and the fan operates.
5. Select PCIe link speed Gen 3, press F10/Save and confirm, wait at least three
   seconds, then restart and revisit the menu. Confirm the selection remains.
   Repeat once with Gen 2 to verify saving works in both directions. Do not
   disable the controller that hosts your boot/Windows NVMe drive.
6. If the menu retains Gen 3 but the device runs at Gen 2, that is a separate
   link-training/compatibility question. Raspberry Pi does not certify Gen 3;
   retaining a menu selection is not a guarantee of stable Gen 3 operation.

If boot fails, power off and restore your backed-up FD from another computer.
If settings still revert, keep the post-reboot FD and photograph any
`WARNING: UEFI settings are not saved` message. Do not repeatedly reflash.

## Unchanged behaviour and limits

- Fan patches 0001-0003, Wi-Fi/SDIO patch 0004, PCIe defaults, ACPI, device trees,
  submodule pins and boot configuration are unchanged from exp.0.4. The RTC
  changes from exp.0.4 are retained without new clock changes.
- In Windows select `(UTC+06:00) Dhaka` for Bangladesh, or the actual local zone
  elsewhere. No timezone is hardcoded in firmware. A before/after restart time
  within the same minute alone is not evidence of a clock failure. A backup
  battery is needed for RTC retention when main power is fully disconnected.
- Runtime variable writes after ExitBootServices are still not persisted to
  disk. This is a boot-time file backend, not EEPROM-backed runtime NVRAM.
- The boot partition must remain accessible and writable in UEFI. The backend
  expects root-level `RPI_EFI.fd`; custom paths/names are not supported. Keep one
  active boot copy connected. Byte-identical cloned boot media cannot be
  distinguished by these content checks alone.
- Already-installed Wi-Fi/connector binaries use the unchanged ACPI interface.
  Older driver installers may reject the new firmware revision. Do not bypass
  their checks, edit signed packages or reinstall a working driver for this fix.

Sources:
- Pinned early-boot mutable buffer: https://github.com/eotics-com/edk2-platforms/blob/c4b5d05de1f2ef633bdb4c175b5c118fcb2666ed/Platform/RaspberryPi/RPi5/Library/PlatformLib/AArch64/RaspberryPiHelper.S
- Pinned firmware layout: https://github.com/eotics-com/edk2-platforms/blob/c4b5d05de1f2ef633bdb4c175b5c118fcb2666ed/Platform/RaspberryPi/RPi5/RPi5.fdf
