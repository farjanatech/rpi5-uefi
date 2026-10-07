# Raspberry Pi 5 UEFI — Damian Edition v0.1.0-rc1

This release candidate is a **Damian-first compatibility build**. Damian's UEFI
architecture and Windows-driver ACPI contract remain authoritative; the only
functional extension is an isolated direct-SDIO Wi-Fi owner at
`ACPI\RPI1060`.

## Release gates

- Damian `edk2-platforms` pinned to `313a8915...`.
- Damian ACPI contract revision 1 retained.
- Damian driver-facing ACPI IDs are statically checked during CI.
- `RPI0011` remains Damian's RP1 IRQ provider and is never reused for Wi-Fi.
- `SDC1` and `WFD0/RPI1060` are mutually exclusive owners of SDIO2.
- Damian fan, display, mailbox, RTC, GPIO, board, NVRAM, RP1 and graph code are
  not replaced by older Farjanatech implementations.
- Release build enables Damian-compatible file-backed NVRAM and ships fresh
  redundant `RPI_NV0.bin` / `RPI_NV1.bin` stores.
- Raspberry Pi board DTB and D0 overlay are downloaded from Damian's pinned
  upstream revisions and SHA-256 verified.
- Full EDK2 Release build and ACPI compilation must pass before packaging.

## Wi-Fi status

The **firmware side is ready** for the later Farjanatech Wi-Fi conversion to
`ACPI\RPI1060`.

The current public Farjanatech Wi-Fi 0.7.1.20 package still matches
`ACPI\RPI0011` and must **not** be installed unchanged with this firmware.
We will rebuild that driver for `RPI1060` separately.

## Validation status

This is a prerelease/RC because CI/source verification cannot replace physical
hardware validation of every driver combination. The intended final profile is:

**Damian 0.1a Windows driver set + Farjanatech RPI1060 Wi-Fi driver**
