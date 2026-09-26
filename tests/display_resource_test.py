#!/usr/bin/env python3
"""Regression checks for the isolated RPi5 SOCB/GPU ACPI resource candidate."""
from __future__ import annotations
import pathlib
import re
import sys

GPU_NAMES = [
    "BCM2712_V3D_HUB", "BCM2712_V3D_CORE0", "BCM2712_V3D_SMS",
    "BCM2712_HVS", "BCM2712_HVS_IOMMU", "BCM2712_PIXELVALVE0",
    "BCM2712_PIXELVALVE1", "BCM2712_MOP", "BCM2712_MOPLET",
    "BCM2712_DISP_INTR",
]


def block(text: str, marker: str) -> str:
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise AssertionError(f"unterminated block: {marker}")


def macro(header: str, name: str) -> int:
    m = re.search(rf"^#define\s+{re.escape(name)}\s+(0x[0-9A-Fa-f]+|[0-9]+)\s*$", header, re.M)
    if not m:
        raise AssertionError(f"missing macro {name}")
    return int(m.group(1), 0)


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: display_resource_test.py <edk2-platforms>")
    root = pathlib.Path(sys.argv[1])
    dsdt_path = root / "Platform/RaspberryPi/RPi5/AcpiTables/Dsdt.asl"
    bcm_path = root / "Silicon/Broadcom/Bcm27xx/Include/IndustryStandard/Bcm2712.h"
    rp1_path = root / "Silicon/RaspberryPi/RpiSiliconPkg/Include/Rp1.asi"
    dsdt = dsdt_path.read_text()
    header = bcm_path.read_text()
    rp1 = rp1_path.read_text()

    socb = block(dsdt, "Device (SOCB)")
    gpu = block(dsdt, "Device (GPU0)")
    crs = block(socb, "Method (_CRS")

    assert "BCM2712_LEGACY_BUS_BASE" not in crs
    assert "BCM2712_LEGACY_BUS_LENGTH" not in crs
    assert "QWORD_SET (00, PL011_DEBUG_BASE_ADDRESS, PL011_DEBUG_LENGTH, 0)" in crs
    assert "QWORD_SET (01, 0x000000107C013880, 0x40, 0)" in crs
    assert crs.count("ResourceProducer") == 2
    assert "Device (URT0)" in socb
    assert 'Name (_HID, "RPI0010")' in socb  # existing TMP0 provider
    assert 'Name (_HID, "RPI0011")' in dsdt  # existing direct-SDIO Wi-Fi
    assert 'Name (_HID, "RPI000F")' in rp1   # existing fan device
    assert dsdt.index("Device (GPU0)") > dsdt.index("} // Device (SOCB)")

    for name in GPU_NAMES:
        assert f"{name}_BASE" in gpu and f"{name}_LENGTH" in gpu

    uart = (
        macro(header, "BCM2712_PL011_UART0_BASE"),
        macro(header, "BCM2712_PL011_UART0_BASE") + macro(header, "BCM2712_PL011_LENGTH") - 1,
    )
    temp = (0x107C013880, 0x107C0138BF)
    producers = [uart, temp]

    gpu_ranges = []
    for name in GPU_NAMES:
        base = macro(header, f"{name}_BASE")
        length = macro(header, f"{name}_LENGTH")
        gpu_ranges.append((name, (base, base + length - 1)))

    for producer in producers:
        for name, rng in gpu_ranges:
            assert not overlaps(producer, rng), (
                f"SOCB producer {producer[0]:#x}-{producer[1]:#x} overlaps {name} "
                f"{rng[0]:#x}-{rng[1]:#x}"
            )

    # The experiment is intentionally narrow: retain the DMA translation.
    assert "Name (_DMA, ResourceTemplate ()" in socb
    assert "0x00000000C0000000" in socb
    assert "0xFFFFFFFF40000000" in socb
    assert "0x0000000040000000" in socb

    print("PASS display-resource: SOCB produces only UART/TMP0; GPU sibling MMIO is disjoint")
    print("PASS preserved: TMP0, direct-SDIO RPI0011, FAN0 and SOCB DMA translation remain present")


if __name__ == "__main__":
    main()
