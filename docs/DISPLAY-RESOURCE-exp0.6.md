# Display-resource candidate exp0.6

Status: **hardware-test candidate; not merged into master and not yet validated on a Pi.**

## Frozen baseline

Parent repository baseline: `838d87df37fe1b27c75a674fca64c1fa067413e3`.

The candidate intentionally keeps these exact submodule pins:

- arm-trusted-firmware: `a5c580fd539929af41cf483b7c1434db261dd51b`
- edk2: `7bbf1f2022f381f48cfb5411df9e5157ee0291a5`
- edk2-platforms: `c4b5d05de1f2ef633bdb4c175b5c118fcb2666ed`
- edk2-non-osi: `66b41e9308a6711cd74e541366a8d9ec7a949d45`

No upstream-behind commit is merged into this experiment. Existing fan/temperature,
microSD, direct-SDIO Wi-Fi, RTC/settings, PCIe/NVMe, USB and HDMI configuration
files are protected byte-for-byte by CI.

## Single functional change

Patch `0006-RPi5-narrow-SOCB-resource-window-for-GPU.patch` changes only the
`SOCB` ACPI `_CRS` producer declaration.

Before:

`SOCB` produces the complete `0x107C000000-0x107FFFFFFF` legacy aperture,
which contains six MMIO ranges consumed by sibling `GPU0`.

Candidate:

`SOCB` produces only its two Windows-stack child MMIO ranges:

- PL011: `0x107D001000-0x107D0011FF`
- TMP0 property-mailbox temperature provider: `0x107C013880-0x107C0138BF`

`SOCB._DMA` is unchanged. `GPU0._CRS`, GPU interrupts, framebuffer setup,
fan resources, Wi-Fi, SD, PCIe, USB and `config.txt` are unchanged.

## Acceptance criteria on hardware

1. Windows boots normally and Microsoft Basic Display remains available as the fallback.
2. Fan and temperature providers remain started and functional.
3. Direct-SDIO Wi-Fi remains started and connected as before.
4. NVMe, microSD and both RP1 USB controllers remain operational.
5. `ACPI\\BCM2712\\0` no longer reports Code 12 / `0xC0000018`.
6. The display driver proceeds beyond resource arbitration into `StartDevice`.
7. If any existing working feature regresses, restore the previous firmware immediately and keep this candidate unmerged.

Passing CI proves only source isolation and build consistency. It does not prove the
resource hypothesis on Windows hardware.
