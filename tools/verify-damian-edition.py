#!/usr/bin/env python3
"""Static release-gate checks for the Damian-edition ACPI integration."""
from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("edk2-platforms")
rpi = root / "Platform/RaspberryPi/RPi5"

def read(rel):
    return (root / rel).read_text(encoding="utf-8")

def require(condition, message):
    if not condition:
        raise SystemExit("VERIFY FAILED: " + message)

dsdt = read("Platform/RaspberryPi/RPi5/AcpiTables/Dsdt.asl")
cfg_h = read("Platform/RaspberryPi/RPi5/Drivers/RpiPlatformDxe/ConfigTable.h")
periph = read("Platform/RaspberryPi/RPi5/Drivers/RpiPlatformDxe/Peripherals.c")
rp1_services = read("Platform/RaspberryPi/RPi5/AcpiTables/Rp1Services.asi")
rp1_peripherals = read("Platform/RaspberryPi/RPi5/AcpiTables/Rp1Peripherals.asi")
bcm = read("Platform/RaspberryPi/RPi5/AcpiTables/Bcm2712Peripherals.asi")
platform = read("Platform/RaspberryPi/RPi5/AcpiTables/PlatformServices.asi")
contract = read("Platform/RaspberryPi/RPi5/ACPI-CONTRACT.md")

all_acpi = "\n".join(
    p.read_text(encoding="utf-8")
    for p in (rpi / "AcpiTables").glob("*")
    if p.suffix in (".asl", ".asi")
)

require('#define ACPI_WIFI_MODE_DEFAULT         ACPI_WIFI_MODE_DIRECT_NDIS' in cfg_h,
        "Direct NDIS is not the default Windows Wi-Fi mode")
require(dsdt.count('Name (_HID, "RPI1060")') == 1,
        "RPI1060 must have exactly one ACPI owner")
require("Device (WFD0)" in dsdt, "WFD0 is missing")
require('Interrupt (ResourceConsumer, Level, ActiveHigh, Exclusive) { 306 }' in dsdt,
        "WFD0 IRQ 306 is missing")
require("BCM2712_BRCMSTB_SDIO2_HOST_BASE" in dsdt,
        "WFD0 does not own the SDIO2 host resource")
require("Device (SDC1)" in dsdt and 'Name (_HID, "BRCM5D12")' in dsdt,
        "Damian standard SDC1 fallback was not retained")
require(dsdt.count("WIFM == ACPI_WIFI_MODE_DIRECT_NDIS") >= 2,
        "SDC1/WFD0 mutual exclusion is missing")
require("MAX_50MHZ_MODE" not in periph,
        "Direct path must not reintroduce the old MAX_50MHZ_MODE override")
require("InitWifiDirectSdioHost" in periph and "SDIO2_CFG_CQ_CAPABILITY" in periph,
        "Direct SDIO host preparation is missing")
require("RPI0011" in rp1_services,
        "Damian RP1 IRQ provider RPI0011 was lost")
require('Name (_HID, "RPI0011")' not in dsdt,
        "Wi-Fi must never reuse Damian RPI0011")
require("RPI00F1" in rp1_peripherals,
        "Damian conditional fan compatible ID RPI00F1 was lost")
require("RPI1000" in bcm and "RPI1001" in bcm,
        "Damian V3D/display nodes were lost")
require("RPI1012" in bcm and "RPI1013" in bcm and "RPI1011" in bcm,
        "Damian mailbox/PM/IOMMU nodes were lost")
require("RPI1025" in platform and "RPI1040" in platform,
        "Damian board/graph services were lost")
require("native driver contract, revision 1" in contract,
        "Damian ACPI contract revision changed")

expected = [
    "RPI0001", "RPI0002", "RPI0003", "RPI0004",
    "RPI0050", "RPI0060", "RPI0070", "RPI00F1",
    "RPI0011", "RPI1000", "RPI1001", "RPI1011",
    "RPI1012", "RPI1013", "RPI1014", "RPI1015",
    "RPI1016", "RPI1017", "RPI1020", "RPI1025",
    "RPI1030", "RPI1040",
]
missing = [hid for hid in expected if hid not in all_acpi]
require(not missing, "Damian driver IDs missing: " + ", ".join(missing))

print("Damian-edition static ABI verification passed.")
print("Damian driver IDs preserved:", ", ".join(expected))
print("Farjanatech direct Wi-Fi ID: RPI1060")
