# Damian-edition integration notes

## Invariants

This branch must continue to build against Damian's exact pinned submodules.
Do not replace Damian's ACPI provider model with Farjanatech's older experimental
fan/display/Wi-Fi IDs.

Reserved collision that motivated the new Wi-Fi ID:

- Damian: RPI0011 = RP1B.IRQ0 shared interrupt provider.
- Historical Farjanatech Wi-Fi: RPI0011 = direct SDIO NDIS adapter.
- Damian edition: RPI1060 = direct SDIO NDIS adapter.

## Resource contract for WFD0 / RPI1060

The current Farjanatech miniport validates its first memory resource as:

- physical base: 0x1001100000
- length: 0x100..0x1000

and consumes the first interrupt resource. Damian SDC1 already describes the
same SDIO2 host base and IRQ 306. WFD0 deliberately mirrors that _CRS while SDC1
is hidden, so ownership is exclusive.

## Standard mode

Standard mode is the default. No direct-SDIO register programming is performed
and Damian's original SDC1/WLAN namespace remains visible.

## Direct mode

Direct mode:

1. Damian still configures GPIO30-35 and asserts WL_ON GPIO28.
2. Firmware waits 150 ms for the radio.
3. SDIO2 SD-pin selection is asserted.
4. CQ_CAPABILITY is programmed with FMUL=3 and 200 MHz base clock.
5. Card-present is forced active-low for the soldered-down device.
6. MAX_50MHZ_MODE is intentionally untouched.
7. SDC1 reports _STA=0.
8. WFD0/RPI1060 reports _STA=0x0F.

No fan, display, mailbox, RTC, NVRAM, RP1 IRQ, GPIO, graph, PCIe or other
Damian ACPI ABI is changed.
