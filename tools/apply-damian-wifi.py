#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
r"""
Apply the Damian-edition CYW43455 direct-SDIO compatibility layer to the pinned
Damian edk2-platforms tree.

The transform is intentionally narrow:
  * preserves Damian's ACPI IDs and provider architecture;
  * keeps the existing Wi-Fi ownership switch;
  * adds ACPI\RPI1060 only for direct NDIS mode;
  * configures SDIO2 only when direct mode is selected;
  * preserves Damian's existing RPI1001 _HRV metadata (0=C0/C1, 1=D0);
  * does not replace fan, display, mailbox, RTC, NVRAM, RP1 IRQ or graph ABI.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_one(path: Path, old: str, new: str, reverse: bool) -> None:
    source, target = (new, old) if reverse else (old, new)
    text = path.read_text(encoding="utf-8")
    count = text.count(source)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one {'reverse ' if reverse else ''}"
            f"match, found {count}"
        )
    path.write_text(text.replace(source, target, 1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--reverse", action="store_true")
    ns = ap.parse_args()
    r = ns.root

    varstore = r / "Platform/RaspberryPi/RPi5/Include/RpiPlatformVarStoreData.h"
    replace_one(
        varstore,
        """typedef struct {
  BOOLEAN Value;
} ACPI_SD_LIMIT_UHS_VARSTORE_DATA;

#define ACPI_PCIE_ECAM_COMPAT_MODE_DEN0115""",
        """typedef struct {
  BOOLEAN Value;
} ACPI_SD_LIMIT_UHS_VARSTORE_DATA;

#define ACPI_WIFI_MODE_STANDARD                 0
#define ACPI_WIFI_MODE_DIRECT_NDIS              1
typedef struct {
  UINT8 Value;
} ACPI_WIFI_MODE_VARSTORE_DATA;

#define ACPI_PCIE_ECAM_COMPAT_MODE_DEN0115""",
        ns.reverse,
    )

    cfg_h = r / "Platform/RaspberryPi/RPi5/Drivers/RpiPlatformDxe/ConfigTable.h"
    replace_one(
        cfg_h,
        """#define ACPI_SD_COMPAT_MODE_DEFAULT    ACPI_SD_COMPAT_MODE_BRCMSTB_BAYTRAIL
#define ACPI_SD_LIMIT_UHS_DEFAULT      TRUE
""",
        """#define ACPI_SD_COMPAT_MODE_DEFAULT    ACPI_SD_COMPAT_MODE_BRCMSTB_BAYTRAIL
#define ACPI_SD_LIMIT_UHS_DEFAULT      TRUE
#define ACPI_WIFI_MODE_DEFAULT         ACPI_WIFI_MODE_DIRECT_NDIS
""",
        ns.reverse,
    )
    replace_one(
        cfg_h,
        """VOID
EFIAPI
SetupConfigTableVariables (
  VOID
  );
#endif // VFRCOMPILE
""",
        """VOID
EFIAPI
SetupConfigTableVariables (
  VOID
  );

UINT8
EFIAPI
GetAcpiWifiMode (
  VOID
  );
#endif // VFRCOMPILE
""",
        ns.reverse,
    )

    vfr = r / "Platform/RaspberryPi/RPi5/Drivers/RpiPlatformDxe/RpiPlatformDxeHii.vfr"
    replace_one(
        vfr,
        """    efivarstore ACPI_SD_LIMIT_UHS_VARSTORE_DATA,
      attribute = EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS | EFI_VARIABLE_NON_VOLATILE,
      name  = AcpiSdLimitUhs,
      guid  = RPI_PLATFORM_FORMSET_GUID;

    efivarstore ACPI_PCIE_ECAM_COMPAT_MODE_VARSTORE_DATA,""",
        """    efivarstore ACPI_SD_LIMIT_UHS_VARSTORE_DATA,
      attribute = EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS | EFI_VARIABLE_NON_VOLATILE,
      name  = AcpiSdLimitUhs,
      guid  = RPI_PLATFORM_FORMSET_GUID;

    efivarstore ACPI_WIFI_MODE_VARSTORE_DATA,
      attribute = EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS | EFI_VARIABLE_NON_VOLATILE,
      name  = AcpiWifiMode,
      guid  = RPI_PLATFORM_FORMSET_GUID;

    efivarstore ACPI_PCIE_ECAM_COMPAT_MODE_VARSTORE_DATA,""",
        ns.reverse,
    )
    replace_one(
        vfr,
        """          checkbox varid = AcpiSdLimitUhs.Value,
            prompt      = STRING_TOKEN(STR_ACPI_SD_LIMIT_UHS_PROMPT),
            help        = STRING_TOKEN(STR_ACPI_SD_LIMIT_UHS_HELP),
            flags       = CHECKBOX_DEFAULT | CHECKBOX_DEFAULT_MFG | RESET_REQUIRED,
            default     = ACPI_SD_LIMIT_UHS_DEFAULT,
          endcheckbox;

          subtitle text = STRING_TOKEN(STR_NULL_STRING);
          subtitle text = STRING_TOKEN(STR_ACPI_PCIE_SUBTITLE);
""",
        """          checkbox varid = AcpiSdLimitUhs.Value,
            prompt      = STRING_TOKEN(STR_ACPI_SD_LIMIT_UHS_PROMPT),
            help        = STRING_TOKEN(STR_ACPI_SD_LIMIT_UHS_HELP),
            flags       = CHECKBOX_DEFAULT | CHECKBOX_DEFAULT_MFG | RESET_REQUIRED,
            default     = ACPI_SD_LIMIT_UHS_DEFAULT,
          endcheckbox;

          subtitle text = STRING_TOKEN(STR_NULL_STRING);
          subtitle text = STRING_TOKEN(STR_ACPI_WIFI_SUBTITLE);

          oneof varid = AcpiWifiMode.Value,
            prompt      = STRING_TOKEN(STR_ACPI_WIFI_MODE_PROMPT),
            help        = STRING_TOKEN(STR_ACPI_WIFI_MODE_HELP),
            flags       = NUMERIC_SIZE_1 | INTERACTIVE | RESET_REQUIRED,
            default     = ACPI_WIFI_MODE_DEFAULT,
            option text = STRING_TOKEN(STR_ACPI_WIFI_MODE_STANDARD), value = ACPI_WIFI_MODE_STANDARD, flags = 0;
            option text = STRING_TOKEN(STR_ACPI_WIFI_MODE_DIRECT_NDIS), value = ACPI_WIFI_MODE_DIRECT_NDIS, flags = 0;
          endoneof;

          subtitle text = STRING_TOKEN(STR_NULL_STRING);
          subtitle text = STRING_TOKEN(STR_ACPI_PCIE_SUBTITLE);
""",
        ns.reverse,
    )

    uni = r / "Platform/RaspberryPi/RPi5/Drivers/RpiPlatformDxe/RpiPlatformDxeHii.uni"
    replace_one(
        uni,
        """/*
 * PCI Express configuration
 */""",
        """/*
 * Wi-Fi SDIO configuration
 */
#string STR_ACPI_WIFI_SUBTITLE                              #language en-US "On-board CYW43455 Wi-Fi"
#string STR_ACPI_WIFI_MODE_PROMPT                           #language en-US "Wi-Fi SDIO Mode"
#string STR_ACPI_WIFI_MODE_HELP                             #language en-US "Choose who owns the on-board SDIO2 Wi-Fi host.\\n\\nStandard SD Bus (Damian) preserves the original firmware and OS SD-bus path.\\n\\nWindows Direct NDIS (Farjanatech) hides SDC1 and exposes ACPI\\\\RPI1060 for the matching direct-SDIO NDIS driver. This mode is experimental and requires a driver rebuilt for RPI1060."
#string STR_ACPI_WIFI_MODE_STANDARD                         #language en-US "Standard SD Bus (Damian)"
#string STR_ACPI_WIFI_MODE_DIRECT_NDIS                      #language en-US "Windows Direct NDIS (Farjanatech)"

/*
 * PCI Express configuration
 */""",
        ns.reverse,
    )

    cfg = r / "Platform/RaspberryPi/RPi5/Drivers/RpiPlatformDxe/ConfigTable.c"
    replace_one(
        cfg,
        """STATIC ACPI_SD_COMPAT_MODE_VARSTORE_DATA    AcpiSdCompatMode;
STATIC ACPI_SD_LIMIT_UHS_VARSTORE_DATA      AcpiSdLimitUhs;
""",
        """STATIC ACPI_SD_COMPAT_MODE_VARSTORE_DATA    AcpiSdCompatMode;
STATIC ACPI_SD_LIMIT_UHS_VARSTORE_DATA      AcpiSdLimitUhs;
STATIC ACPI_WIFI_MODE_VARSTORE_DATA         AcpiWifiMode;
""",
        ns.reverse,
    )
    replace_one(
        cfg,
        """  Status = AcpiAmlObjectUpdateInteger (AcpiSdtProtocol, TableHandle,
                "\\\\_SB.SDLU", AcpiSdLimitUhs.Value);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "%a: Failed to patch AcpiSdLimitUhs.\\n", __func__));
  }
}
""",
        """  Status = AcpiAmlObjectUpdateInteger (AcpiSdtProtocol, TableHandle,
                "\\\\_SB.SDLU", AcpiSdLimitUhs.Value);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "%a: Failed to patch AcpiSdLimitUhs.\\n", __func__));
  }

  Status = AcpiAmlObjectUpdateInteger (AcpiSdtProtocol, TableHandle,
                "\\\\_SB.WIFM", AcpiWifiMode.Value);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "%a: Failed to patch AcpiWifiMode.\\n", __func__));
  }
}
""",
        ns.reverse,
    )
    replace_one(
        cfg,
        """  AcpiSdCompatMode.Value = ACPI_SD_COMPAT_MODE_DEFAULT;
  AcpiSdLimitUhs.Value = ACPI_SD_LIMIT_UHS_DEFAULT;
  AcpiPcieEcamCompatMode.Value = ACPI_PCIE_ECAM_COMPAT_MODE_DEFAULT;
""",
        """  AcpiSdCompatMode.Value = ACPI_SD_COMPAT_MODE_DEFAULT;
  AcpiSdLimitUhs.Value = ACPI_SD_LIMIT_UHS_DEFAULT;
  AcpiWifiMode.Value = ACPI_WIFI_MODE_DEFAULT;
  AcpiPcieEcamCompatMode.Value = ACPI_PCIE_ECAM_COMPAT_MODE_DEFAULT;
""",
        ns.reverse,
    )
    replace_one(
        cfg,
        """  Size = sizeof (ACPI_PCIE_ECAM_COMPAT_MODE_VARSTORE_DATA);
  Status = gRT->GetVariable (L"AcpiPcieEcamCompatMode",""",
        """  Size = sizeof (ACPI_WIFI_MODE_VARSTORE_DATA);
  Status = gRT->GetVariable (L"AcpiWifiMode",
                  &gRpiPlatformFormSetGuid,
                  NULL, &Size, &AcpiWifiMode);
  if (EFI_ERROR (Status) || AcpiWifiMode.Value > ACPI_WIFI_MODE_DIRECT_NDIS) {
    AcpiWifiMode.Value = ACPI_WIFI_MODE_DEFAULT;
    Status = gRT->SetVariable (
                    L"AcpiWifiMode",
                    &gRpiPlatformFormSetGuid,
                    EFI_VARIABLE_NON_VOLATILE | EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS,
                    Size,
                    &AcpiWifiMode);
    ASSERT_EFI_ERROR (Status);
  }

  Size = sizeof (ACPI_PCIE_ECAM_COMPAT_MODE_VARSTORE_DATA);
  Status = gRT->GetVariable (L"AcpiPcieEcamCompatMode",""",
        ns.reverse,
    )
    replace_one(
        cfg,
        """VOID
EFIAPI
ApplyConfigTableVariables (
  VOID
  )
{""",
        """UINT8
EFIAPI
GetAcpiWifiMode (
  VOID
  )
{
  // Direct ownership is an ACPI-only contract. Device Tree boots retain
  // Damian's standard SDIO behavior even if the saved setting is Direct NDIS.
  return mIsAcpiEnabled ? AcpiWifiMode.Value : ACPI_WIFI_MODE_STANDARD;
}

VOID
EFIAPI
ApplyConfigTableVariables (
  VOID
  )
{""",
        ns.reverse,
    )

    dsdt = r / "Platform/RaspberryPi/RPi5/AcpiTables/Dsdt.asl"
    replace_one(
        dsdt,
        """    Name (SDCM, 0x0) // Compatibility Mode
    Name (SDLU, 0x0) // Limit UHS-I

    Device (SDC0) {""",
        """    Name (SDCM, 0x0) // Compatibility Mode
    Name (SDLU, 0x0) // Limit UHS-I
    Name (WIFM, ACPI_WIFI_MODE_STANDARD) // Wi-Fi ownership mode

    Device (SDC0) {""",
        ns.reverse,
    )
    replace_one(
        dsdt,
        """      Name (_UID, 0x1)
      Name (_CCA, 0x0)

      Method (_CRS, 0x0, Serialized) {""",
        """      Name (_UID, 0x1)
      Name (_CCA, 0x0)

      Method (_STA, 0, NotSerialized) {
        If (WIFM == ACPI_WIFI_MODE_DIRECT_NDIS) {
          Return (0)
        }
        Return (0x0F)
      }

      Method (_CRS, 0x0, Serialized) {""",
        ns.reverse,
    )
    replace_one(
        dsdt,
        """    } // Device (SDC1)

    Include ("HardwareMetadata.asi")""",
        """    } // Device (SDC1)

    //
    // Optional direct owner for Farjanatech's CYW43455 NDIS miniport.
    // RPI1060 is intentionally outside Damian's revision-1 ACPI ID set.
    // SDC1 and WFD0 are mutually exclusive, so Windows never receives two
    // owners for the SDIO2 MMIO/IRQ resources.
    //
    Device (WFD0) {
      Name (_HID, "RPI1060")
      Name (_UID, 0x0)
      Name (_DDN, "Raspberry Pi 5 CYW43455 Direct SDIO Wi-Fi")
      Name (_CCA, 0x0)

      Method (_STA, 0, NotSerialized) {
        If (WIFM == ACPI_WIFI_MODE_DIRECT_NDIS) {
          Return (0x0F)
        }
        Return (0)
      }

      Method (_CRS, 0x0, Serialized) {
        Name (RBUF, ResourceTemplate () {
          QWORDMEMORY_BUF (00, ResourceConsumer)
          Interrupt (ResourceConsumer, Level, ActiveHigh, Exclusive) { 306 }
        })
        QWORD_SET (00, BCM2712_BRCMSTB_SDIO2_HOST_BASE, BCM2712_BRCMSTB_SDIO_HOST_LENGTH, 0)
        Return (RBUF)
      }

      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "compatible", "raspberrypi,rpi5-cyw43455-direct-sdio" },
          Package () { "raspberrypi,configuration", "\\\\_SB.SDX1" },
          Package () { "raspberrypi,power-provider", "\\\\_SB.BORD" },
          Package () { "startup-delay-us", 150000 },
        }
      })
    }

    Include ("HardwareMetadata.asi")""",
        ns.reverse,
    )

    periph = r / "Platform/RaspberryPi/RPi5/Drivers/RpiPlatformDxe/Peripherals.c"
    replace_one(
        periph,
        """#include <Library/FdtPlatformLib.h>
#include <Library/UefiBootServicesTableLib.h>""",
        """#include <Library/FdtPlatformLib.h>
#include <Library/IoLib.h>
#include <Library/UefiBootServicesTableLib.h>""",
        ns.reverse,
    )
    replace_one(
        periph,
        """BCM2712_PCIE_PLATFORM_PROTOCOL  mPciePlatform = {""",
        """//
// Farjanatech direct-SDIO baseline for the on-board CYW43455.
//
// Damian's normal SD-bus mode never executes this path. In direct mode the
// custom NDIS miniport owns SDHCI itself, so prepare only the host state that
// has been validated for that driver. In particular, leave MAX_50MHZ_MODE at
// its hardware/firmware reset value.
//
#define SDIO2_CFG_CTRL                          0x0
#define SDIO2_CFG_CTRL_SDCD_N_TEST_EN           BIT31
#define SDIO2_CFG_CTRL_SDCD_N_TEST_LEV          BIT30
#define SDIO2_CFG_SD_PIN_SEL                    0x44
#define SDIO2_CFG_SD_PIN_SEL_MASK               (BIT1 | BIT0)
#define SDIO2_CFG_SD_PIN_SEL_SD                 BIT1
#define SDIO2_CFG_CQ_CAPABILITY                 0x4C
#define SDIO2_CFG_CQ_CAPABILITY_FMUL_SHIFT      12
#define SDIO2_BASE_CLOCK_MHZ                    200

STATIC
EFI_STATUS
EFIAPI
InitWifiDirectSdioHost (
  VOID
  )
{
  UINT32 Reg;

  // Route the SDIO2 pads to the SD controller. GPIO30-35 and WL_ON have
  // already been configured by Damian's InitGpioPinctrls().
  Reg = MmioRead32 (BCM2712_BRCMSTB_SDIO2_CFG_BASE + SDIO2_CFG_SD_PIN_SEL);
  Reg &= ~SDIO2_CFG_SD_PIN_SEL_MASK;
  Reg |= SDIO2_CFG_SD_PIN_SEL_SD;
  MmioWrite32 (BCM2712_BRCMSTB_SDIO2_CFG_BASE + SDIO2_CFG_SD_PIN_SEL, Reg);

  // Damian drives WL_ON high in InitGpioPinctrls(). Match the board contract's
  // 150 ms startup delay before touching the SDIO host.
  gBS->Stall (150000);

  // Advertise a 200 MHz base clock (FMUL=3), matching the verified Farjanatech
  // direct-SDIO baseline. Do not apply the old MAX_50MHZ_MODE strap override.
  Reg = (3U << SDIO2_CFG_CQ_CAPABILITY_FMUL_SHIFT) | SDIO2_BASE_CLOCK_MHZ;
  MmioWrite32 (BCM2712_BRCMSTB_SDIO2_CFG_BASE + SDIO2_CFG_CQ_CAPABILITY, Reg);

  // The CYW43455 is soldered down and has no physical card-detect switch.
  Reg = MmioRead32 (BCM2712_BRCMSTB_SDIO2_CFG_BASE + SDIO2_CFG_CTRL);
  Reg &= ~SDIO2_CFG_CTRL_SDCD_N_TEST_LEV;
  Reg |= SDIO2_CFG_CTRL_SDCD_N_TEST_EN;
  MmioWrite32 (BCM2712_BRCMSTB_SDIO2_CFG_BASE + SDIO2_CFG_CTRL, Reg);

  DEBUG ((DEBUG_INFO, "WiFi: prepared SDIO2 for ACPI\\\\RPI1060 direct NDIS ownership\\n"));
  return EFI_SUCCESS;
}

BCM2712_PCIE_PLATFORM_PROTOCOL  mPciePlatform = {""",
        ns.reverse,
    )
    replace_one(
        periph,
        """  Status = RegisterSdControllers ();
  if (EFI_ERROR (Status)) {
    return Status;
  }

  return RegisterPciePlatform ();""",
        """  if (GetAcpiWifiMode () == ACPI_WIFI_MODE_DIRECT_NDIS) {
    Status = InitWifiDirectSdioHost ();
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }

  Status = RegisterSdControllers ();
  if (EFI_ERROR (Status)) {
    return Status;
  }

  return RegisterPciePlatform ();""",
        ns.reverse,
    )


if __name__ == "__main__":
    main()
