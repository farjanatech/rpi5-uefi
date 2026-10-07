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

## Windows all-drivers mode (default)

Direct NDIS mode is the default for this branch so the complete Damian Windows driver set and Farjanatech Wi-Fi can operate in the same boot. Only SDC1 ownership changes; Damian's other ACPI nodes remain enabled.

## Standard mode

Standard mode is the recovery/compatibility fallback. No direct-SDIO register programming is performed
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


## Coexistence with Damian drivers

Direct NDIS mode does not disable any Damian source-driver package. It hides only
the standard SDC1 SD-bus owner and exposes WFD0/RPI1060 over the same SDIO2 host.

- Pi5Board.sys / RPI1025 remains active and holds the Wi-Fi enable signal in its
  operating state; it does not implement Wi-Fi networking.
- Pi5Bluetooth.sys / RPI1017 remains active over its H4 UART transport.
- RP1 IRQ service / RPI0011 remains untouched and cannot be matched by Wi-Fi.
- Graphics, fan, mailbox, RTC, GPIO, DMA, clocks, NVRAM and RPIGRAPH are unchanged.

The intended Windows profile is therefore:

Damian driver package + Farjanatech RPI1060 Wi-Fi driver, concurrently.


## BCM2712 C1 / D0 graphics revision ABI

Damian already detects the BCM2712 pinctrl generation from the boot firmware
device tree and patches `\_SB.SREV`:

- `0` = C0/C1 register generation
- `1` = D0 register generation
- any other value = unknown / fail closed

Damian Edition also exposes the same value as `_HRV` on `RPI1001` (DISP).
This does not alter the display MMIO or IRQ resources. It gives the matching
Windows graphics driver an explicit, firmware-authoritative way to select its
C1 or D0 handoff parser while retaining one ACPI HID and one driver package.
