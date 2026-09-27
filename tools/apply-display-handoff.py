#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Apply/reverse the isolated RPi5 display timing+EDID handoff experiment."""
from pathlib import Path
import argparse

def replace_one(path: Path, old: str, new: str, reverse: bool) -> None:
    # Git's Raspberry Pi sources use CRLF in several files.  Work on a
    # normalized in-memory view, but restore the file's original newline
    # convention exactly so applying/reversing this experiment is byte-clean.
    raw = path.read_bytes()
    text_raw = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text_raw else "\n"
    text = text_raw.replace("\r\n", "\n")
    src, dst = (new, old) if reverse else (old, new)
    if text.count(src) != 1:
        raise SystemExit(f"{path}: expected exactly one handoff anchor, found {text.count(src)}")
    result = text.replace(src, dst, 1)
    if newline == "\r\n":
        result = result.replace("\n", "\r\n")
    path.write_bytes(result.encode("utf-8"))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--reverse", action="store_true")
    ns = ap.parse_args()
    r = ns.root

    mbox = r / "Platform/RaspberryPi/Include/IndustryStandard/RpiMbox.h"
    replace_one(mbox,
        "#define RPI_MBOX_GET_CUSTOMER_OTP                             0x00030021\n",
        "#define RPI_MBOX_GET_CUSTOMER_OTP                             0x00030021\n#define RPI_MBOX_GET_EDID_BLOCK_DISPLAY                       0x00030023\n",
        ns.reverse)
    replace_one(mbox,
        "#define RPI_MBOX_GET_FB_GPIOVIRTBUF                           0x00040010\n",
        "#define RPI_MBOX_GET_FB_GPIOVIRTBUF                           0x00040010\n#define RPI_MBOX_GET_FB_NUM_DISPLAYS                         0x00040013\n#define RPI_MBOX_GET_FB_DISPLAY_ID                            0x00040016\n#define RPI_MBOX_GET_DISPLAY_TIMING                           0x00040017\n",
        ns.reverse)

    proto = r / "Platform/RaspberryPi/Include/Protocol/RpiFirmware.h"
    replace_one(proto,
        "#define RASPBERRY_PI_FIRMWARE_PROTOL_GUID \\\n  { 0x0ACA9535, 0x7AD0, 0x4286, { 0xB0, 0x2E, 0x87, 0xFA, 0x7E, 0x2A, 0x57, 0x11 } }\n",
        "#define RASPBERRY_PI_FIRMWARE_PROTOL_GUID \\\n  { 0x0ACA9535, 0x7AD0, 0x4286, { 0xB0, 0x2E, 0x87, 0xFA, 0x7E, 0x2A, 0x57, 0x11 } }\n\n#define RASPBERRY_PI_EDID_BLOCK_SIZE  128\n",
        ns.reverse)
    timing = """\
#pragma pack(1)
typedef struct {
  UINT8   Display;
  UINT8   Padding;
  UINT16  VideoIdCode;
  UINT32  Clock;
  UINT16  HDisplay;
  UINT16  HSyncStart;
  UINT16  HSyncEnd;
  UINT16  HTotal;
  UINT16  HSkew;
  UINT16  VDisplay;
  UINT16  VSyncStart;
  UINT16  VSyncEnd;
  UINT16  VTotal;
  UINT16  VScan;
  UINT16  VRefresh;
  UINT16  Padding2;
  UINT32  Flags;
} RASPBERRY_PI_DISPLAY_TIMING;
#pragma pack()

"""
    replace_one(proto,
        "} RASPBERRY_PI_RTC_REGISTER;\n\n",
        "} RASPBERRY_PI_RTC_REGISTER;\n\n" + timing,
        ns.reverse)
    api = """\
typedef
EFI_STATUS
(EFIAPI *GET_FB_NUM_DISPLAYS) (
  OUT UINT32  *DisplayCount
  );

typedef
EFI_STATUS
(EFIAPI *GET_FB_DISPLAY_ID) (
  IN  UINT32  DisplayIndex,
  OUT UINT32  *DisplayId
  );

typedef
EFI_STATUS
(EFIAPI *GET_DISPLAY_TIMING) (
  IN  UINT32                       DisplayNumber,
  OUT RASPBERRY_PI_DISPLAY_TIMING  *Timing
  );

typedef
EFI_STATUS
(EFIAPI *GET_EDID_BLOCK_DISPLAY) (
  IN  UINT32  DisplayNumber,
  IN  UINT32  BlockNumber,
  OUT UINT8   Edid[RASPBERRY_PI_EDID_BLOCK_SIZE]
  );

"""
    replace_one(proto, "typedef struct {\n  SET_POWER_STATE",
        api + "typedef struct {\n  SET_POWER_STATE", ns.reverse)
    replace_one(proto,
        "  GET_TEMPERATURE        GetTemperature;\n} RASPBERRY_PI_FIRMWARE_PROTOCOL;",
        "  GET_TEMPERATURE        GetTemperature;\n  GET_FB_NUM_DISPLAYS    GetFbNumDisplays;\n  GET_FB_DISPLAY_ID      GetFbDisplayId;\n  GET_DISPLAY_TIMING     GetDisplayTiming;\n  GET_EDID_BLOCK_DISPLAY GetEdidBlockDisplay;\n} RASPBERRY_PI_FIRMWARE_PROTOCOL;",
        ns.reverse)

    fw = r / "Platform/RaspberryPi/Drivers/RpiFirmwareDxe/RpiFirmwareDxe.c"
    structs = """\
#pragma pack(push, 1)
typedef struct {
  RPI_FW_BUFFER_HEAD  BufferHead;
  RPI_FW_TAG_HEAD     TagHead;
  UINT32              TagBody;
  UINT32              EndTag;
} RPI_FW_GET_FB_DISPLAY_ID_CMD;

typedef RPI_FW_GET_FB_DISPLAY_ID_CMD RPI_FW_GET_FB_NUM_DISPLAYS_CMD;

typedef struct {
  RPI_FW_BUFFER_HEAD            BufferHead;
  RPI_FW_TAG_HEAD               TagHead;
  RASPBERRY_PI_DISPLAY_TIMING   TagBody;
  UINT32                        EndTag;
} RPI_FW_GET_DISPLAY_TIMING_CMD;

typedef struct {
  UINT32  BlockNumber;
  UINT32  DisplayNumber;
  UINT8   Edid[RASPBERRY_PI_EDID_BLOCK_SIZE];
} RPI_FW_EDID_BLOCK_DISPLAY_TAG;

typedef struct {
  RPI_FW_BUFFER_HEAD             BufferHead;
  RPI_FW_TAG_HEAD                TagHead;
  RPI_FW_EDID_BLOCK_DISPLAY_TAG  TagBody;
  UINT32                         EndTag;
} RPI_FW_GET_EDID_BLOCK_DISPLAY_CMD;
#pragma pack(pop)

"""
    replace_one(fw,
        "STATIC UINTN mMboxBaseAddress;",
        structs + "STATIC UINTN mMboxBaseAddress;",
        ns.reverse)
    funcs = """\
STATIC
EFI_STATUS
EFIAPI
RpiFirmwareGetFbNumDisplays (
  OUT UINT32  *DisplayCount
  )
{
  RPI_FW_GET_FB_NUM_DISPLAYS_CMD *Cmd;
  EFI_STATUS                     Status;
  UINT32                         Result;

  if (DisplayCount == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  if (!AcquireSpinLockOrFail (&mMailboxLock)) {
    return EFI_DEVICE_ERROR;
  }

  Cmd = mDmaBuffer;
  ZeroMem (Cmd, sizeof (*Cmd));
  Cmd->BufferHead.BufferSize = sizeof (*Cmd);
  Cmd->TagHead.TagId = RPI_MBOX_GET_FB_NUM_DISPLAYS;
  Cmd->TagHead.TagSize = sizeof (Cmd->TagBody);
  Cmd->TagBody = 0;
  Cmd->EndTag = 0;

  Status = MailboxTransaction (Cmd->BufferHead.BufferSize, RPI_MBOX_VC_CHANNEL, &Result);
  if (EFI_ERROR (Status) ||
      Cmd->BufferHead.Response != RPI_MBOX_RESP_SUCCESS ||
      (Cmd->TagHead.TagValueSize & RPI_MBOX_VALUE_SIZE_RESPONSE_MASK) == 0 ||
      (Cmd->TagHead.TagValueSize & ~RPI_MBOX_VALUE_SIZE_RESPONSE_MASK) < sizeof (Cmd->TagBody) ||
      Cmd->TagBody == 0) {
    Status = EFI_NOT_FOUND;
  } else {
    *DisplayCount = Cmd->TagBody;
  }
  ReleaseSpinLock (&mMailboxLock);
  return Status;
}

STATIC
EFI_STATUS
EFIAPI
RpiFirmwareGetFbDisplayId (
  IN  UINT32  DisplayIndex,
  OUT UINT32  *DisplayId
  )
{
  RPI_FW_GET_FB_DISPLAY_ID_CMD *Cmd;
  EFI_STATUS                   Status;
  UINT32                       Result;

  if (DisplayId == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  if (!AcquireSpinLockOrFail (&mMailboxLock)) {
    return EFI_DEVICE_ERROR;
  }

  Cmd = mDmaBuffer;
  ZeroMem (Cmd, sizeof (*Cmd));
  Cmd->BufferHead.BufferSize = sizeof (*Cmd);
  Cmd->TagHead.TagId = RPI_MBOX_GET_FB_DISPLAY_ID;
  Cmd->TagHead.TagSize = sizeof (Cmd->TagBody);
  Cmd->TagBody = DisplayIndex;
  Cmd->EndTag = 0;

  Status = MailboxTransaction (Cmd->BufferHead.BufferSize, RPI_MBOX_VC_CHANNEL, &Result);
  if (EFI_ERROR (Status) ||
      Cmd->BufferHead.Response != RPI_MBOX_RESP_SUCCESS ||
      (Cmd->TagHead.TagValueSize & RPI_MBOX_VALUE_SIZE_RESPONSE_MASK) == 0 ||
      (Cmd->TagHead.TagValueSize & ~RPI_MBOX_VALUE_SIZE_RESPONSE_MASK) < sizeof (Cmd->TagBody)) {
    Status = EFI_NOT_FOUND;
  } else {
    *DisplayId = Cmd->TagBody;
  }
  ReleaseSpinLock (&mMailboxLock);
  return Status;
}

STATIC
EFI_STATUS
EFIAPI
RpiFirmwareGetDisplayTiming (
  IN  UINT32                       DisplayNumber,
  OUT RASPBERRY_PI_DISPLAY_TIMING  *Timing
  )
{
  RPI_FW_GET_DISPLAY_TIMING_CMD *Cmd;
  EFI_STATUS                    Status;
  UINT32                        Result;

  if (Timing == NULL || DisplayNumber > 0xFFU) {
    return EFI_INVALID_PARAMETER;
  }
  if (!AcquireSpinLockOrFail (&mMailboxLock)) {
    return EFI_DEVICE_ERROR;
  }

  Cmd = mDmaBuffer;
  ZeroMem (Cmd, sizeof (*Cmd));
  Cmd->BufferHead.BufferSize = sizeof (*Cmd);
  Cmd->TagHead.TagId = RPI_MBOX_GET_DISPLAY_TIMING;
  Cmd->TagHead.TagSize = sizeof (Cmd->TagBody);
  Cmd->TagBody.Display = (UINT8)DisplayNumber;
  Cmd->EndTag = 0;

  Status = MailboxTransaction (Cmd->BufferHead.BufferSize, RPI_MBOX_VC_CHANNEL, &Result);
  if (EFI_ERROR (Status) ||
      Cmd->BufferHead.Response != RPI_MBOX_RESP_SUCCESS ||
      (Cmd->TagHead.TagValueSize & RPI_MBOX_VALUE_SIZE_RESPONSE_MASK) == 0 ||
      (Cmd->TagHead.TagValueSize & ~RPI_MBOX_VALUE_SIZE_RESPONSE_MASK) < sizeof (Cmd->TagBody) ||
      Cmd->TagBody.Clock == 0) {
    Status = EFI_NOT_FOUND;
  } else {
    CopyMem (Timing, &Cmd->TagBody, sizeof (*Timing));
  }
  ReleaseSpinLock (&mMailboxLock);
  return Status;
}

STATIC
EFI_STATUS
EFIAPI
RpiFirmwareGetEdidBlockDisplay (
  IN  UINT32  DisplayNumber,
  IN  UINT32  BlockNumber,
  OUT UINT8   Edid[RASPBERRY_PI_EDID_BLOCK_SIZE]
  )
{
  RPI_FW_GET_EDID_BLOCK_DISPLAY_CMD *Cmd;
  EFI_STATUS                        Status;
  UINT32                            Result;

  if (Edid == NULL || DisplayNumber > 0xFFU || BlockNumber > 255) {
    return EFI_INVALID_PARAMETER;
  }
  if (!AcquireSpinLockOrFail (&mMailboxLock)) {
    return EFI_DEVICE_ERROR;
  }

  Cmd = mDmaBuffer;
  ZeroMem (Cmd, sizeof (*Cmd));
  Cmd->BufferHead.BufferSize = sizeof (*Cmd);
  Cmd->TagHead.TagId = RPI_MBOX_GET_EDID_BLOCK_DISPLAY;
  Cmd->TagHead.TagSize = sizeof (Cmd->TagBody);
  Cmd->TagBody.BlockNumber = BlockNumber;
  Cmd->TagBody.DisplayNumber = DisplayNumber;
  Cmd->EndTag = 0;

  Status = MailboxTransaction (Cmd->BufferHead.BufferSize, RPI_MBOX_VC_CHANNEL, &Result);
  if (EFI_ERROR (Status) ||
      Cmd->BufferHead.Response != RPI_MBOX_RESP_SUCCESS ||
      (Cmd->TagHead.TagValueSize & RPI_MBOX_VALUE_SIZE_RESPONSE_MASK) == 0 ||
      (Cmd->TagHead.TagValueSize & ~RPI_MBOX_VALUE_SIZE_RESPONSE_MASK) < sizeof (Cmd->TagBody)) {
    Status = EFI_NOT_FOUND;
  } else {
    CopyMem (Edid, Cmd->TagBody.Edid, RASPBERRY_PI_EDID_BLOCK_SIZE);
  }
  ReleaseSpinLock (&mMailboxLock);
  return Status;
}

"""
    replace_one(fw,
        "STATIC RASPBERRY_PI_FIRMWARE_PROTOCOL mRpiFirmwareProtocol = {",
        funcs + "STATIC RASPBERRY_PI_FIRMWARE_PROTOCOL mRpiFirmwareProtocol = {",
        ns.reverse)
    replace_one(fw,
        "  RpiFirmwareGetTemperature,\n};",
        "  RpiFirmwareGetTemperature,\n  RpiFirmwareGetFbNumDisplays,\n  RpiFirmwareGetFbDisplayId,\n  RpiFirmwareGetDisplayTiming,\n  RpiFirmwareGetEdidBlockDisplay,\n};",
        ns.reverse)
    replace_one(fw,
        "  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetTemperature);\n",
        "  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetTemperature);\n  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetFbNumDisplays);\n  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetFbDisplayId);\n  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetDisplayTiming);\n  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetEdidBlockDisplay);\n",
        ns.reverse)

    display_h = r / "Platform/RaspberryPi/Drivers/DisplayDxe/DisplayDxe.h"
    replace_one(display_h,
        "#include <Protocol/DevicePath.h>\n#include <Protocol/RpiFirmware.h>\n",
        "#include <Protocol/DevicePath.h>\n#include <Protocol/AcpiTable.h>\n#include <IndustryStandard/Acpi.h>\n#include <Protocol/RpiFirmware.h>\n",
        ns.reverse)

    display_inf = r / "Platform/RaspberryPi/Drivers/DisplayDxe/DisplayDxe.inf"
    replace_one(display_inf,
        "  gEfiCpuArchProtocolGuid\n  gEfiSimpleFileSystemProtocolGuid\n",
        "  gEfiCpuArchProtocolGuid\n  gEfiVariableArchProtocolGuid\n  gEfiVariableWriteArchProtocolGuid\n  gEfiAcpiTableProtocolGuid\n  gEfiSimpleFileSystemProtocolGuid\n",
        ns.reverse)
    replace_one(display_inf,
        "  gEfiCpuArchProtocolGuid AND gRaspberryPiFirmwareProtocolGuid\n",
        "  gEfiCpuArchProtocolGuid AND gRaspberryPiFirmwareProtocolGuid AND gEfiVariableArchProtocolGuid AND gEfiVariableWriteArchProtocolGuid\n",
        ns.reverse)

    disp = r / "Platform/RaspberryPi/Drivers/DisplayDxe/DisplayDxe.c"
    defs = """\
#define RPI5_DISPLAY_HANDOFF_SIGNATURE  0x48443552U
#define RPI5_DISPLAY_HANDOFF_VERSION    1
#define RPI5_DISPLAY_HANDOFF_MAX_EDID_BLOCKS  4
#define RPI5_DISPLAY_HANDOFF_MAX_PROBE_DISPLAYS  4
#define RPI5_DISPLAY_HANDOFF_TIMING_VALID  BIT0
#define RPI5_DISPLAY_HANDOFF_EDID_VALID    BIT1
#define RPI5_DISPLAY_TIMING_FLAG_INTERLACE  BIT2

STATIC EFI_GUID mRpi5DisplayHandoffGuid =
  { 0x941ce3d8, 0x8c4f, 0x4b9e, { 0xa5, 0x77, 0x1c, 0xc9, 0x82, 0x74, 0x55, 0x31 } };

STATIC EFI_EVENT mRpi5DisplayReadyToBootEvent;

STATIC
VOID
EFIAPI
Rpi5DisplayReadyToBoot (
  IN EFI_EVENT Event,
  IN VOID *Context
  );

#pragma pack(1)
typedef struct {
  UINT32                       Signature;
  UINT16                       Version;
  UINT16                       Size;
  UINT32                       DisplayNumber;
  UINT32                       Flags;
  RASPBERRY_PI_DISPLAY_TIMING  Timing;
  UINT32                       EdidBlockCount;
  UINT8                        Edid[RPI5_DISPLAY_HANDOFF_MAX_EDID_BLOCKS * RASPBERRY_PI_EDID_BLOCK_SIZE];
} RPI5_DISPLAY_HANDOFF;
#pragma pack()

#define RPI5_DISPLAY_ACPI_REVISION  1
#define RPI5_DISPLAY_DIAG_ACPI_REVISION  1

#define RPI5_DISPLAY_TIMING_SOURCE_NONE        0U
#define RPI5_DISPLAY_TIMING_SOURCE_FIRMWARE    1U
#define RPI5_DISPLAY_TIMING_SOURCE_EDID        2U
#define RPI5_DISPLAY_TIMING_SOURCE_PIXELVALVE  3U

#define RPI5_DISPLAY_DIAG_READY_TO_BOOT        BIT0
#define RPI5_DISPLAY_DIAG_PV0_SCANNING         BIT1
#define RPI5_DISPLAY_DIAG_PV1_SCANNING         BIT2
#define RPI5_DISPLAY_DIAG_FW_TIMING_VALID      BIT3
#define RPI5_DISPLAY_DIAG_EDID_TIMING_VALID    BIT4
#define RPI5_DISPLAY_DIAG_PV_TIMING_VALID      BIT5
#define RPI5_DISPLAY_DIAG_VBLANK_MEASURED      BIT6
#define RPI5_DISPLAY_DIAG_R5DH_INSTALLED       BIT7
#define RPI5_DISPLAY_DIAG_VARIABLE_PUBLISHED   BIT8
#define RPI5_DISPLAY_DIAG_EDID_COMPLETE        BIT9

#define RPI5_PV0_BASE  0x107C410000ULL
#define RPI5_PV1_BASE  0x107C411000ULL
#define RPI5_PV_CONTROL     0x00U
#define RPI5_PV_V_CONTROL   0x04U
#define RPI5_PV_HORZA       0x0CU
#define RPI5_PV_HORZB       0x10U
#define RPI5_PV_VERTA       0x14U
#define RPI5_PV_VERTB       0x18U
#define RPI5_PV_INTSTAT     0x28U
#define RPI5_PV_CONTROL_EN       BIT0
#define RPI5_PV_VCONTROL_VIDEN   BIT0
#define RPI5_PV_VCONTROL_INTERLACE BIT4
#define RPI5_PV_INT_VFP_START    BIT7
#define RPI5_PV_MEASURE_FRAMES   4U
#define RPI5_PV_EDGE_WAIT_LOOPS  5000U
#define RPI5_PV_EDGE_WAIT_US     50U

#pragma pack(1)
typedef struct {
  EFI_ACPI_DESCRIPTION_HEADER Header;
  RPI5_DISPLAY_HANDOFF        Handoff;
} RPI5_DISPLAY_HANDOFF_ACPI_TABLE;

typedef struct {
  UINT64 Base;
  UINT32 Control;
  UINT32 VControl;
  UINT32 Horza;
  UINT32 Horzb;
  UINT32 Verta;
  UINT32 Vertb;
  UINT32 Intstat;
} RPI5_DISPLAY_PV_DIAG;

typedef struct {
  UINT32 Version;
  UINT32 StatusFlags;
  UINT32 TimingSource;
  UINT32 SelectedPixelValve;
  UINT64 LastStatus;
  UINT64 FramePeriodNs;
  UINT32 DerivedClockKHz;
  UINT32 ActiveWidth;
  UINT32 ActiveHeight;
  UINT32 HTotal;
  UINT32 VTotal;
  RPI5_DISPLAY_PV_DIAG PixelValve[2];
} RPI5_DISPLAY_DIAG_PAYLOAD;

typedef struct {
  EFI_ACPI_DESCRIPTION_HEADER Header;
  RPI5_DISPLAY_DIAG_PAYLOAD   Diag;
} RPI5_DISPLAY_DIAG_ACPI_TABLE;
#pragma pack()

STATIC UINTN mRpi5DisplayAcpiTableKey;
STATIC UINTN mRpi5DisplayDiagTableKey;
STATIC RPI5_DISPLAY_DIAG_PAYLOAD mRpi5DisplayDiag;

"""
    replace_one(disp,
        "} GOP_MODE_DATA;\n\n",
        "} GOP_MODE_DATA;\n\n" + defs,
        ns.reverse)
    handoff = """\
STATIC
BOOLEAN
ValidateEdidBlock (
  IN CONST UINT8 *Block,
  IN BOOLEAN BaseBlock
  )
{
  UINTN Index;
  UINT8 Sum = 0;
  STATIC CONST UINT8 Header[8] = { 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00 };

  if (BaseBlock && CompareMem (Block, Header, sizeof (Header)) != 0) {
    return FALSE;
  }
  for (Index = 0; Index < RASPBERRY_PI_EDID_BLOCK_SIZE; Index++) {
    Sum = (UINT8)(Sum + Block[Index]);
  }
  return Sum == 0;
}

STATIC
BOOLEAN
ValidateDisplayTiming (
  IN CONST RASPBERRY_PI_DISPLAY_TIMING *Timing,
  IN UINT32 Width,
  IN UINT32 Height
  )
{
  return Timing != NULL &&
         Timing->Clock != 0 && Timing->Clock <= 4000000U &&
         Timing->HDisplay == Width && Timing->VDisplay == Height &&
         Timing->HTotal >= Timing->HDisplay && Timing->VTotal >= Timing->VDisplay &&
         Timing->HSyncStart >= Timing->HDisplay &&
         Timing->HSyncEnd >= Timing->HSyncStart && Timing->HSyncEnd <= Timing->HTotal &&
         Timing->VSyncStart >= Timing->VDisplay &&
         Timing->VSyncEnd >= Timing->VSyncStart && Timing->VSyncEnd <= Timing->VTotal &&
         (Timing->Flags & RPI5_DISPLAY_TIMING_FLAG_INTERLACE) == 0;
}

STATIC
BOOLEAN
ParseEdidDetailedTiming (
  IN CONST UINT8 *Dtd,
  IN UINT32 Width,
  IN UINT32 Height,
  IN UINT32 Display,
  OUT RASPBERRY_PI_DISPLAY_TIMING *Timing
  )
{
  UINT32 PixelClock10KHz;
  UINT32 HActive;
  UINT32 HBlank;
  UINT32 VActive;
  UINT32 VBlank;
  UINT32 HSyncOffset;
  UINT32 HSyncWidth;
  UINT32 VSyncOffset;
  UINT32 VSyncWidth;
  UINT64 FramePixels;
  UINT64 Refresh;

  if (Dtd == NULL || Timing == NULL) {
    return FALSE;
  }

  PixelClock10KHz = (UINT32)Dtd[0] | ((UINT32)Dtd[1] << 8);
  if (PixelClock10KHz == 0) {
    return FALSE;
  }

  HActive = (UINT32)Dtd[2] | (((UINT32)Dtd[4] & 0xF0U) << 4);
  HBlank = (UINT32)Dtd[3] | (((UINT32)Dtd[4] & 0x0FU) << 8);
  VActive = (UINT32)Dtd[5] | (((UINT32)Dtd[7] & 0xF0U) << 4);
  VBlank = (UINT32)Dtd[6] | (((UINT32)Dtd[7] & 0x0FU) << 8);

  if (HActive != Width || VActive != Height || HBlank == 0 || VBlank == 0) {
    return FALSE;
  }

  HSyncOffset = (UINT32)Dtd[8] | (((UINT32)Dtd[11] & 0xC0U) << 2);
  HSyncWidth = (UINT32)Dtd[9] | (((UINT32)Dtd[11] & 0x30U) << 4);
  VSyncOffset = ((UINT32)Dtd[10] >> 4) | (((UINT32)Dtd[11] & 0x0CU) << 2);
  VSyncWidth = ((UINT32)Dtd[10] & 0x0FU) | (((UINT32)Dtd[11] & 0x03U) << 4);

  ZeroMem (Timing, sizeof (*Timing));
  Timing->Display = (UINT8)Display;
  Timing->Clock = PixelClock10KHz * 10U;
  Timing->HDisplay = (UINT16)HActive;
  Timing->HSyncStart = (UINT16)(HActive + HSyncOffset);
  Timing->HSyncEnd = (UINT16)(HActive + HSyncOffset + HSyncWidth);
  Timing->HTotal = (UINT16)(HActive + HBlank);
  Timing->VDisplay = (UINT16)VActive;
  Timing->VSyncStart = (UINT16)(VActive + VSyncOffset);
  Timing->VSyncEnd = (UINT16)(VActive + VSyncOffset + VSyncWidth);
  Timing->VTotal = (UINT16)(VActive + VBlank);

  if ((Dtd[17] & 0x80U) != 0) {
    Timing->Flags |= RPI5_DISPLAY_TIMING_FLAG_INTERLACE;
  }

  /* EDID separate digital sync: bit 1 is H polarity, bit 2 is V polarity. */
  if ((Dtd[17] & 0x18U) == 0x18U) {
    if ((Dtd[17] & 0x02U) != 0) {
      Timing->Flags |= BIT0;
    }
    if ((Dtd[17] & 0x04U) != 0) {
      Timing->Flags |= BIT1;
    }
  }

  FramePixels = (UINT64)Timing->HTotal * (UINT64)Timing->VTotal;
  if (FramePixels != 0) {
    Refresh = ((UINT64)Timing->Clock * 1000ULL + (FramePixels / 2ULL)) / FramePixels;
    if (Refresh <= MAX_UINT16) {
      Timing->VRefresh = (UINT16)Refresh;
    }
  }

  return ValidateDisplayTiming (Timing, Width, Height);
}

STATIC
BOOLEAN
FindEdidDetailedTiming (
  IN CONST UINT8 *Edid,
  IN UINT32 BlocksRead,
  IN UINT32 Width,
  IN UINT32 Height,
  IN UINT32 Display,
  OUT RASPBERRY_PI_DISPLAY_TIMING *Timing
  )
{
  UINT32 Descriptor;
  UINT32 Block;
  UINT32 Offset;
  CONST UINT8 *Extension;

  if (Edid == NULL || Timing == NULL || BlocksRead == 0) {
    return FALSE;
  }

  /* Base EDID has four 18-byte detailed descriptors starting at byte 54. */
  for (Descriptor = 0; Descriptor < 4; Descriptor++) {
    Offset = 54U + (Descriptor * 18U);
    if (ParseEdidDetailedTiming (&Edid[Offset], Width, Height, Display, Timing)) {
      return TRUE;
    }
  }

  /*
   * CTA-861 extension detailed timings start at byte 2's DTD offset and end
   * before the checksum at byte 127. Other extension formats are ignored.
   */
  for (Block = 1; Block < BlocksRead; Block++) {
    Extension = &Edid[Block * RASPBERRY_PI_EDID_BLOCK_SIZE];
    if (Extension[0] != 0x02U || Extension[2] < 4U || Extension[2] >= 127U) {
      continue;
    }

    for (Offset = Extension[2]; Offset + 18U <= 127U; Offset += 18U) {
      if (ParseEdidDetailedTiming (&Extension[Offset], Width, Height, Display, Timing)) {
        return TRUE;
      }
    }
  }

  return FALSE;
}

STATIC
EFI_STATUS
ReadDisplayEdid (
  IN UINT32 Display,
  OUT UINT8 Edid[RPI5_DISPLAY_HANDOFF_MAX_EDID_BLOCKS * RASPBERRY_PI_EDID_BLOCK_SIZE],
  OUT UINT32 *BlocksRead,
  OUT BOOLEAN *Complete
  )
{
  EFI_STATUS Status;
  UINT32 Block;
  UINT32 WantedBlocks;
  UINT32 ReadLimit;

  if (Edid == NULL || BlocksRead == NULL || Complete == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  ZeroMem (Edid,
    RPI5_DISPLAY_HANDOFF_MAX_EDID_BLOCKS * RASPBERRY_PI_EDID_BLOCK_SIZE);
  *BlocksRead = 0;
  *Complete = FALSE;

  Status = mFwProtocol->GetEdidBlockDisplay (Display, 0, &Edid[0]);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  if (!ValidateEdidBlock (&Edid[0], TRUE)) {
    return EFI_COMPROMISED_DATA;
  }

  *BlocksRead = 1;
  WantedBlocks = 1U + Edid[126];
  ReadLimit = WantedBlocks;
  if (ReadLimit > RPI5_DISPLAY_HANDOFF_MAX_EDID_BLOCKS) {
    ReadLimit = RPI5_DISPLAY_HANDOFF_MAX_EDID_BLOCKS;
  }

  for (Block = 1; Block < ReadLimit; Block++) {
    Status = mFwProtocol->GetEdidBlockDisplay (
                            Display,
                            Block,
                            &Edid[Block * RASPBERRY_PI_EDID_BLOCK_SIZE]);
    if (EFI_ERROR (Status) ||
        !ValidateEdidBlock (&Edid[Block * RASPBERRY_PI_EDID_BLOCK_SIZE], FALSE)) {
      return EFI_SUCCESS;
    }
    (*BlocksRead)++;
  }

  if (WantedBlocks <= RPI5_DISPLAY_HANDOFF_MAX_EDID_BLOCKS &&
      *BlocksRead == WantedBlocks) {
    *Complete = TRUE;
  }

  return EFI_SUCCESS;
}

STATIC
VOID
CapturePixelValveRegisters (
  IN UINT32 PixelValve
  )
{
  RPI5_DISPLAY_PV_DIAG *Diag;
  UINT64 Base;

  if (PixelValve > 1) {
    return;
  }

  Base = PixelValve == 0 ? RPI5_PV0_BASE : RPI5_PV1_BASE;
  Diag = &mRpi5DisplayDiag.PixelValve[PixelValve];
  Diag->Base = Base;
  Diag->Control = MmioRead32 ((UINTN)(Base + RPI5_PV_CONTROL));
  Diag->VControl = MmioRead32 ((UINTN)(Base + RPI5_PV_V_CONTROL));
  Diag->Horza = MmioRead32 ((UINTN)(Base + RPI5_PV_HORZA));
  Diag->Horzb = MmioRead32 ((UINTN)(Base + RPI5_PV_HORZB));
  Diag->Verta = MmioRead32 ((UINTN)(Base + RPI5_PV_VERTA));
  Diag->Vertb = MmioRead32 ((UINTN)(Base + RPI5_PV_VERTB));
  Diag->Intstat = MmioRead32 ((UINTN)(Base + RPI5_PV_INTSTAT));

  if ((Diag->Control & RPI5_PV_CONTROL_EN) != 0 &&
      (Diag->VControl & RPI5_PV_VCONTROL_VIDEN) != 0) {
    mRpi5DisplayDiag.StatusFlags |=
      PixelValve == 0 ? RPI5_DISPLAY_DIAG_PV0_SCANNING
                      : RPI5_DISPLAY_DIAG_PV1_SCANNING;
  }
}

STATIC
BOOLEAN
WaitPixelValveVfpStart (
  IN UINT64 Base,
  OUT UINT64 *TimestampNs
  )
{
  UINT32 Attempt;

  if (TimestampNs == NULL) {
    return FALSE;
  }

  MmioWrite32 ((UINTN)(Base + RPI5_PV_INTSTAT), RPI5_PV_INT_VFP_START);
  for (Attempt = 0; Attempt < RPI5_PV_EDGE_WAIT_LOOPS; Attempt++) {
    if ((MmioRead32 ((UINTN)(Base + RPI5_PV_INTSTAT)) &
         RPI5_PV_INT_VFP_START) != 0) {
      *TimestampNs = GetTimeInNanoSecond (GetPerformanceCounter ());
      MmioWrite32 ((UINTN)(Base + RPI5_PV_INTSTAT), RPI5_PV_INT_VFP_START);
      return TRUE;
    }
    MicroSecondDelay (RPI5_PV_EDGE_WAIT_US);
  }

  return FALSE;
}

STATIC
BOOLEAN
MeasurePixelValveFramePeriod (
  IN UINT64 Base,
  OUT UINT64 *FramePeriodNs
  )
{
  UINT64 First;
  UINT64 Last;
  UINT64 Stamp;
  UINT32 Frame;

  if (FramePeriodNs == NULL ||
      !WaitPixelValveVfpStart (Base, &First)) {
    return FALSE;
  }

  Last = First;
  for (Frame = 0; Frame < RPI5_PV_MEASURE_FRAMES; Frame++) {
    if (!WaitPixelValveVfpStart (Base, &Stamp)) {
      return FALSE;
    }
    Last = Stamp;
  }

  if (Last <= First) {
    return FALSE;
  }

  *FramePeriodNs = (Last - First) / RPI5_PV_MEASURE_FRAMES;
  return *FramePeriodNs != 0;
}

STATIC
BOOLEAN
ReadPixelValveTiming (
  IN UINT32 Width,
  IN UINT32 Height,
  OUT UINT32 *Display,
  OUT RASPBERRY_PI_DISPLAY_TIMING *Timing
  )
{
  UINT32 PixelValve;
  UINT64 Base;
  RPI5_DISPLAY_PV_DIAG *Diag;
  UINT32 HSync;
  UINT32 HBackPorch;
  UINT32 HActive;
  UINT32 HFrontPorch;
  UINT32 VSync;
  UINT32 VBackPorch;
  UINT32 VActive;
  UINT32 VFrontPorch;
  UINT32 HTotal;
  UINT32 VTotal;
  UINT64 FramePeriodNs;
  UINT64 FramePixels;
  UINT64 PixelClockHz;
  UINT64 Refresh;

  if (Display == NULL || Timing == NULL) {
    return FALSE;
  }

  CapturePixelValveRegisters (0);
  CapturePixelValveRegisters (1);

  for (PixelValve = 0; PixelValve < 2; PixelValve++) {
    Diag = &mRpi5DisplayDiag.PixelValve[PixelValve];
    Base = Diag->Base;

    if ((Diag->Control & RPI5_PV_CONTROL_EN) == 0 ||
        (Diag->VControl & RPI5_PV_VCONTROL_VIDEN) == 0 ||
        (Diag->VControl & RPI5_PV_VCONTROL_INTERLACE) != 0) {
      continue;
    }

    HSync = Diag->Horza & 0xFFFFU;
    HBackPorch = (Diag->Horza >> 16) & 0xFFFFU;
    HActive = Diag->Horzb & 0xFFFFU;
    HFrontPorch = (Diag->Horzb >> 16) & 0xFFFFU;
    VSync = Diag->Verta & 0xFFFFU;
    VBackPorch = (Diag->Verta >> 16) & 0xFFFFU;
    VActive = Diag->Vertb & 0xFFFFU;
    VFrontPorch = (Diag->Vertb >> 16) & 0xFFFFU;

    HTotal = HActive + HFrontPorch + HSync + HBackPorch;
    VTotal = VActive + VFrontPorch + VSync + VBackPorch;

    if (HActive != Width || VActive != Height ||
        HSync == 0 || VSync == 0 ||
        HTotal <= HActive || VTotal <= VActive ||
        HTotal > MAX_UINT16 || VTotal > MAX_UINT16) {
      DEBUG ((DEBUG_WARN,
        "Rpi5Display PixelValve%u geometry rejected control=0x%x vcontrol=0x%x "
        "h=%u+%u+%u+%u v=%u+%u+%u+%u GOP=%ux%u\n",
        PixelValve, Diag->Control, Diag->VControl,
        HActive, HFrontPorch, HSync, HBackPorch,
        VActive, VFrontPorch, VSync, VBackPorch,
        Width, Height));
      continue;
    }

    if (!MeasurePixelValveFramePeriod (Base, &FramePeriodNs)) {
      DEBUG ((DEBUG_WARN,
        "Rpi5Display PixelValve%u VFP measurement timed out\n", PixelValve));
      continue;
    }

    FramePixels = (UINT64)HTotal * (UINT64)VTotal;
    PixelClockHz =
      (FramePixels * 1000000000ULL + (FramePeriodNs / 2ULL)) / FramePeriodNs;
    if (PixelClockHz < 1000000ULL || PixelClockHz > 4000000000ULL) {
      DEBUG ((DEBUG_WARN,
        "Rpi5Display PixelValve%u measured pixel clock out of range: %LuHz\n",
        PixelValve, PixelClockHz));
      continue;
    }

    ZeroMem (Timing, sizeof (*Timing));
    *Display = PixelValve == 0 ? 2U : 7U;
    Timing->Display = (UINT8)*Display;
    Timing->Clock = (UINT32)((PixelClockHz + 500ULL) / 1000ULL);
    Timing->HDisplay = (UINT16)HActive;
    Timing->HSyncStart = (UINT16)(HActive + HFrontPorch);
    Timing->HSyncEnd = (UINT16)(HActive + HFrontPorch + HSync);
    Timing->HTotal = (UINT16)HTotal;
    Timing->VDisplay = (UINT16)VActive;
    Timing->VSyncStart = (UINT16)(VActive + VFrontPorch);
    Timing->VSyncEnd = (UINT16)(VActive + VFrontPorch + VSync);
    Timing->VTotal = (UINT16)VTotal;

    Refresh = (1000000000ULL + (FramePeriodNs / 2ULL)) / FramePeriodNs;
    if (Refresh <= MAX_UINT16) {
      Timing->VRefresh = (UINT16)Refresh;
    }

    if (!ValidateDisplayTiming (Timing, Width, Height)) {
      continue;
    }

    mRpi5DisplayDiag.StatusFlags |=
      RPI5_DISPLAY_DIAG_PV_TIMING_VALID |
      RPI5_DISPLAY_DIAG_VBLANK_MEASURED;
    mRpi5DisplayDiag.TimingSource = RPI5_DISPLAY_TIMING_SOURCE_PIXELVALVE;
    mRpi5DisplayDiag.SelectedPixelValve = PixelValve;
    mRpi5DisplayDiag.FramePeriodNs = FramePeriodNs;
    mRpi5DisplayDiag.DerivedClockKHz = Timing->Clock;
    mRpi5DisplayDiag.ActiveWidth = HActive;
    mRpi5DisplayDiag.ActiveHeight = VActive;
    mRpi5DisplayDiag.HTotal = HTotal;
    mRpi5DisplayDiag.VTotal = VTotal;

    DEBUG ((DEBUG_INFO,
      "Rpi5Display handoff stage=timing-selected source=pixelvalve pv=%u "
      "display=%u mode=%ux%u clock=%uKHz totals=%ux%u period=%Luns refresh=%u\n",
      PixelValve, *Display, Width, Height, Timing->Clock,
      Timing->HTotal, Timing->VTotal, FramePeriodNs, Timing->VRefresh));
    return TRUE;
  }

  return FALSE;
}

STATIC
EFI_STATUS
InstallDisplayDiagnosticsAcpi (
  IN EFI_STATUS LastStatus,
  IN UINT32 Width,
  IN UINT32 Height
  )
{
  RPI5_DISPLAY_DIAG_ACPI_TABLE Table;
  EFI_ACPI_TABLE_PROTOCOL *AcpiTable;
  EFI_STATUS Status;
  UINTN TableKey;

  CapturePixelValveRegisters (0);
  CapturePixelValveRegisters (1);
  mRpi5DisplayDiag.Version = 1;
  mRpi5DisplayDiag.StatusFlags |= RPI5_DISPLAY_DIAG_READY_TO_BOOT;
  mRpi5DisplayDiag.LastStatus = (UINT64)(UINTN)LastStatus;
  if (mRpi5DisplayDiag.ActiveWidth == 0) {
    mRpi5DisplayDiag.ActiveWidth = Width;
  }
  if (mRpi5DisplayDiag.ActiveHeight == 0) {
    mRpi5DisplayDiag.ActiveHeight = Height;
  }

  ZeroMem (&Table, sizeof (Table));
  Table.Header.Signature = SIGNATURE_32 ('R', '5', 'D', 'G');
  Table.Header.Length = sizeof (Table);
  Table.Header.Revision = RPI5_DISPLAY_DIAG_ACPI_REVISION;
  CopyMem (Table.Header.OemId, "RPIFW ", sizeof (Table.Header.OemId));
  CopyMem (&Table.Header.OemTableId, "R5DGDIAG", sizeof (Table.Header.OemTableId));
  Table.Header.OemRevision = 1;
  Table.Header.CreatorId = SIGNATURE_32 ('R', 'P', 'I', '5');
  Table.Header.CreatorRevision = 1;
  CopyMem (&Table.Diag, &mRpi5DisplayDiag, sizeof (Table.Diag));

  Status = gBS->LocateProtocol (
                  &gEfiAcpiTableProtocolGuid,
                  NULL,
                  (VOID **)&AcpiTable);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display R5DG stage=locate-acpi status=%r\n", Status));
    return Status;
  }

  TableKey = 0;
  Status = AcpiTable->InstallAcpiTable (
                        AcpiTable,
                        &Table,
                        sizeof (Table),
                        &TableKey);
  if (!EFI_ERROR (Status)) {
    mRpi5DisplayDiagTableKey = TableKey;
  }

  DEBUG ((EFI_ERROR (Status) ? DEBUG_WARN : DEBUG_INFO,
    "Rpi5Display R5DG stage=install status=%r key=%Lu flags=0x%x source=%u "
    "selectedPv=%u period=%Luns clock=%uKHz GOP=%ux%u\n",
    Status, (UINT64)TableKey, mRpi5DisplayDiag.StatusFlags,
    mRpi5DisplayDiag.TimingSource, mRpi5DisplayDiag.SelectedPixelValve,
    mRpi5DisplayDiag.FramePeriodNs, mRpi5DisplayDiag.DerivedClockKHz,
    Width, Height));
  return Status;
}

STATIC
EFI_STATUS
InstallDisplayHandoffAcpi (
  IN CONST RPI5_DISPLAY_HANDOFF *Handoff
  )
{
  RPI5_DISPLAY_HANDOFF_ACPI_TABLE Table;
  EFI_ACPI_TABLE_PROTOCOL *AcpiTable;
  EFI_STATUS Status;
  UINTN TableKey;

  if (Handoff == NULL ||
      (Handoff->Flags & RPI5_DISPLAY_HANDOFF_TIMING_VALID) == 0) {
    return EFI_INVALID_PARAMETER;
  }

  ZeroMem (&Table, sizeof (Table));
  Table.Header.Signature = SIGNATURE_32 ('R', '5', 'D', 'H');
  Table.Header.Length = sizeof (Table);
  Table.Header.Revision = RPI5_DISPLAY_ACPI_REVISION;
  CopyMem (Table.Header.OemId, "RPIFW ", sizeof (Table.Header.OemId));
  CopyMem (&Table.Header.OemTableId, "R5DHHAND", sizeof (Table.Header.OemTableId));
  Table.Header.OemRevision = 1;
  Table.Header.CreatorId = SIGNATURE_32 ('R', 'P', 'I', '5');
  Table.Header.CreatorRevision = 1;
  CopyMem (&Table.Handoff, Handoff, sizeof (Table.Handoff));

  Status = gBS->LocateProtocol (
                  &gEfiAcpiTableProtocolGuid,
                  NULL,
                  (VOID **)&AcpiTable);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display ACPI handoff stage=locate-acpi status=%r\\n", Status));
    return Status;
  }

  TableKey = 0;
  Status = AcpiTable->InstallAcpiTable (
                        AcpiTable,
                        &Table,
                        sizeof (Table),
                        &TableKey);
  if (!EFI_ERROR (Status)) {
    mRpi5DisplayAcpiTableKey = TableKey;
  }

  DEBUG ((EFI_ERROR (Status) ? DEBUG_WARN : DEBUG_INFO,
    "Rpi5Display ACPI handoff stage=install status=%r key=%Lu display=%u flags=0x%x clock=%uKHz totals=%ux%u\\n",
    Status, (UINT64)TableKey, Handoff->DisplayNumber, Handoff->Flags,
    Handoff->Timing.Clock, Handoff->Timing.HTotal, Handoff->Timing.VTotal));
  return Status;
}

STATIC
EFI_STATUS
PublishDisplayHandoff (
  IN UINT32 Width,
  IN UINT32 Height,
  IN BOOLEAN InstallAcpi
  )
{
  RPI5_DISPLAY_HANDOFF Handoff;
  RPI5_DISPLAY_HANDOFF Verify;
  RASPBERRY_PI_DISPLAY_TIMING Timing;
  EFI_STATUS Status;
  EFI_STATUS VariableStatus;
  EFI_STATUS AcpiStatus;
  UINTN VerifySize;
  UINT32 VerifyAttributes;
  UINT32 ExpectedAttributes;
  UINT32 Display;
  UINT32 DisplayCount;
  UINT32 DisplayIndex;
  UINT32 ProbeCount;
  UINT32 EdidBlocksRead;
  BOOLEAN EdidComplete;
  BOOLEAN TimingFound;
  BOOLEAN TimingFromEdid;
  UINT8 CandidateEdid[RPI5_DISPLAY_HANDOFF_MAX_EDID_BLOCKS * RASPBERRY_PI_EDID_BLOCK_SIZE];

  ExpectedAttributes = EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS;

  /*
   * Do not delete a previously verified handoff before a replacement is ready.
   * A late GOP SetMode can occur after ReadyToBoot. If its timing query fails,
   * keeping the previous per-boot value is safer: the Windows driver also
   * validates exact POST geometry before accepting it. The variable is volatile,
   * so it cannot survive a reboot.
   */
  ZeroMem (&Handoff, sizeof (Handoff));
  Handoff.Signature = RPI5_DISPLAY_HANDOFF_SIGNATURE;
  Handoff.Version = RPI5_DISPLAY_HANDOFF_VERSION;
  Handoff.Size = sizeof (Handoff);

  /*
   * Follow the same firmware-display discovery model used by Raspberry Pi
   * Linux: enumerate logical framebuffer displays, translate each logical
   * index through GET_DISPLAY_ID, then choose the active timing that matches
   * the GOP mode. This avoids assuming logical framebuffer index 0 is HDMI0.
   */
  DisplayCount = 0;
  Status = mFwProtocol->GetFbNumDisplays (&DisplayCount);
  if (EFI_ERROR (Status) || DisplayCount == 0) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=display-count status=%r count=%u; probing first two logical displays\\n",
      Status, DisplayCount));
    ProbeCount = 2;
  } else {
    ProbeCount = DisplayCount;
    if (ProbeCount > RPI5_DISPLAY_HANDOFF_MAX_PROBE_DISPLAYS) {
      ProbeCount = RPI5_DISPLAY_HANDOFF_MAX_PROBE_DISPLAYS;
    }
  }

  TimingFound = FALSE;
  TimingFromEdid = FALSE;
  Display = 0;
  ZeroMem (&Timing, sizeof (Timing));

  for (DisplayIndex = 0; DisplayIndex < ProbeCount; DisplayIndex++) {
    RASPBERRY_PI_DISPLAY_TIMING CandidateTiming;
    UINT32 CandidateDisplay;

    CandidateDisplay = DisplayIndex;
    Status = mFwProtocol->GetFbDisplayId (DisplayIndex, &CandidateDisplay);
    if (EFI_ERROR (Status) || CandidateDisplay > 0xFFU) {
      DEBUG ((DEBUG_WARN,
        "Rpi5Display handoff stage=display-id index=%u status=%r display=%u\\n",
        DisplayIndex, Status, CandidateDisplay));
      continue;
    }

    ZeroMem (&CandidateTiming, sizeof (CandidateTiming));
    Status = mFwProtocol->GetDisplayTiming (CandidateDisplay, &CandidateTiming);
    if (!EFI_ERROR (Status) &&
        ValidateDisplayTiming (&CandidateTiming, Width, Height)) {
      Display = CandidateDisplay;
      CopyMem (&Timing, &CandidateTiming, sizeof (Timing));
      TimingFound = TRUE;
      TimingFromEdid = FALSE;
      DEBUG ((DEBUG_INFO,
        "Rpi5Display handoff stage=timing-selected source=firmware index=%u display=%u "
        "mode=%ux%u clock=%u totals=%ux%u\\n",
        DisplayIndex, Display, Width, Height, Timing.Clock,
        Timing.HTotal, Timing.VTotal));
      break;
    }

    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=timing-fallback index=%u display=%u status=%r "
      "fw=%ux%u clock=%u totals=%ux%u flags=0x%x\\n",
      DisplayIndex, CandidateDisplay, Status,
      CandidateTiming.HDisplay, CandidateTiming.VDisplay,
      CandidateTiming.Clock, CandidateTiming.HTotal,
      CandidateTiming.VTotal, CandidateTiming.Flags));

    EdidBlocksRead = 0;
    EdidComplete = FALSE;
    Status = ReadDisplayEdid (
               CandidateDisplay,
               CandidateEdid,
               &EdidBlocksRead,
               &EdidComplete);
    if (EFI_ERROR (Status)) {
      DEBUG ((DEBUG_WARN,
        "Rpi5Display handoff stage=edid-read index=%u display=%u status=%r\\n",
        DisplayIndex, CandidateDisplay, Status));
      continue;
    }

    ZeroMem (&CandidateTiming, sizeof (CandidateTiming));
    if (!FindEdidDetailedTiming (
           CandidateEdid,
           EdidBlocksRead,
           Width,
           Height,
           CandidateDisplay,
           &CandidateTiming)) {
      DEBUG ((DEBUG_WARN,
        "Rpi5Display handoff stage=edid-no-matching-dtd index=%u display=%u "
        "mode=%ux%u blocks=%u complete=%u\\n",
        DisplayIndex, CandidateDisplay, Width, Height,
        EdidBlocksRead, EdidComplete));
      continue;
    }

    Display = CandidateDisplay;
    CopyMem (&Timing, &CandidateTiming, sizeof (Timing));
    TimingFound = TRUE;
    TimingFromEdid = TRUE;
    DEBUG ((DEBUG_INFO,
      "Rpi5Display handoff stage=timing-selected source=edid index=%u display=%u "
      "mode=%ux%u clock=%u totals=%ux%u refresh=%u\\n",
      DisplayIndex, Display, Width, Height, Timing.Clock,
      Timing.HTotal, Timing.VTotal, Timing.VRefresh));
    break;
  }

  if (!TimingFound) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=no-matching-timing mode=%ux%u probed=%u\\n",
      Width, Height, ProbeCount));
    return EFI_NOT_FOUND;
  }

  Handoff.DisplayNumber = Display;
  CopyMem (&Handoff.Timing, &Timing, sizeof (Timing));
  Handoff.Flags |= RPI5_DISPLAY_HANDOFF_TIMING_VALID;

  EdidBlocksRead = 0;
  EdidComplete = FALSE;
  Status = ReadDisplayEdid (
             Display,
             Handoff.Edid,
             &EdidBlocksRead,
             &EdidComplete);
  if (!EFI_ERROR (Status) && EdidComplete) {
    Handoff.EdidBlockCount = EdidBlocksRead;
    Handoff.Flags |= RPI5_DISPLAY_HANDOFF_EDID_VALID;
  } else {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=edid-optional status=%r display=%u blocks=%u complete=%u\\n",
      Status, Display, EdidBlocksRead, EdidComplete));
    Handoff.EdidBlockCount = 0;
    ZeroMem (Handoff.Edid, sizeof (Handoff.Edid));
  }

  DEBUG ((DEBUG_INFO,
    "Rpi5Display handoff stage=timing-source source=%a display=%u\\n",
    TimingFromEdid ? "edid" : "firmware", Display));

  VariableStatus = gST->RuntimeServices->SetVariable (
                  L"Rpi5DisplayHandoff",
                  &mRpi5DisplayHandoffGuid,
                  ExpectedAttributes,
                  sizeof (Handoff),
                  &Handoff);
  if (EFI_ERROR (VariableStatus)) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display variable handoff stage=set-variable status=%r display=%u flags=0x%x\\n",
      VariableStatus, Display, Handoff.Flags));
  } else {
    ZeroMem (&Verify, sizeof (Verify));
    VerifySize = sizeof (Verify);
    VerifyAttributes = 0;
    Status = gST->RuntimeServices->GetVariable (
                    L"Rpi5DisplayHandoff",
                    &mRpi5DisplayHandoffGuid,
                    &VerifyAttributes,
                    &VerifySize,
                    &Verify);
    if (EFI_ERROR (Status) ||
        VerifySize != sizeof (Verify) ||
        VerifyAttributes != ExpectedAttributes ||
        CompareMem (&Verify, &Handoff, sizeof (Handoff)) != 0) {
      DEBUG ((DEBUG_WARN,
        "Rpi5Display variable handoff stage=verify status=%r bytes=%u attrs=0x%x expected=0x%x\\n",
        Status, (UINT32)VerifySize, VerifyAttributes, ExpectedAttributes));
      (VOID)gST->RuntimeServices->SetVariable (
                                    L"Rpi5DisplayHandoff",
                                    &mRpi5DisplayHandoffGuid,
                                    0,
                                    0,
                                    NULL);
      VariableStatus = EFI_ERROR (Status) ? Status : EFI_COMPROMISED_DATA;
    } else {
      VariableStatus = EFI_SUCCESS;
      DEBUG ((DEBUG_INFO,
        "Rpi5Display variable handoff stage=published display=%u flags=0x%x %ux%u "
        "clock=%uKHz totals=%ux%u refreshHint=%u edidBlocks=%u attrs=0x%x\\n",
        Handoff.DisplayNumber, Handoff.Flags, Width, Height, Handoff.Timing.Clock,
        Handoff.Timing.HTotal, Handoff.Timing.VTotal, Handoff.Timing.VRefresh,
        Handoff.EdidBlockCount, VerifyAttributes));
    }
  }

  AcpiStatus = EFI_NOT_READY;
  if (InstallAcpi) {
    AcpiStatus = InstallDisplayHandoffAcpi (&Handoff);
  }

  if (!EFI_ERROR (VariableStatus) ||
      (InstallAcpi && !EFI_ERROR (AcpiStatus))) {
    return EFI_SUCCESS;
  }

  return InstallAcpi ? AcpiStatus : VariableStatus;
}

STATIC
VOID
EFIAPI
Rpi5DisplayReadyToBoot (
  IN EFI_EVENT Event,
  IN VOID *Context
  )
{
  EFI_STATUS Status;

  (VOID)Context;
  if (gDisplayProto.Mode == NULL || gDisplayProto.Mode->Info == NULL) {
    DEBUG ((DEBUG_WARN, "Rpi5Display handoff ReadyToBoot: GOP mode unavailable\\n"));
  } else {
    Status = PublishDisplayHandoff (
               gDisplayProto.Mode->Info->HorizontalResolution,
               gDisplayProto.Mode->Info->VerticalResolution,
               TRUE);
    DEBUG ((EFI_ERROR (Status) ? DEBUG_WARN : DEBUG_INFO,
      "Rpi5Display handoff ReadyToBoot status=%r\\n", Status));
  }

  if (Event != NULL) {
    (VOID)gBS->CloseEvent (Event);
  }
  mRpi5DisplayReadyToBootEvent = NULL;
}

"""
    display_set_mode_impl = """\
STATIC
EFI_STATUS
EFIAPI
DisplaySetMode (
  IN  EFI_GRAPHICS_OUTPUT_PROTOCOL *This,
  IN  UINT32                       ModeNumber
  )
{
"""
    replace_one(disp,
        display_set_mode_impl,
        handoff + display_set_mode_impl,
        ns.reverse)
    replace_one(disp,
        "  DEBUG((DEBUG_INFO, \"Reported Mode->FrameBufferSize is %u\\n\", This->Mode->FrameBufferSize));\n\n  ClearScreen (This);",
        "  DEBUG((DEBUG_INFO, \"Reported Mode->FrameBufferSize is %u\\n\", This->Mode->FrameBufferSize));\n\n  (VOID)PublishDisplayHandoff (Mode->Width, Mode->Height, FALSE);\n\n  ClearScreen (This);",
        ns.reverse)

    gop_install = """\
  Status = gBS->InstallMultipleProtocolInterfaces (
    &Controller, &gEfiGraphicsOutputProtocolGuid,
    &gDisplayProto, NULL);
  if (EFI_ERROR (Status)) {
    goto Done;
  }

"""
    gop_install_ready = gop_install + """\
  if (mRpi5DisplayReadyToBootEvent == NULL) {
    EFI_STATUS EventStatus;
    EventStatus = EfiCreateEventReadyToBootEx (
                    TPL_CALLBACK,
                    Rpi5DisplayReadyToBoot,
                    NULL,
                    &mRpi5DisplayReadyToBootEvent);
    if (EFI_ERROR (EventStatus)) {
      DEBUG ((DEBUG_WARN,
        "Rpi5Display handoff: ReadyToBoot event creation failed: %r\\n",
        EventStatus));
      mRpi5DisplayReadyToBootEvent = NULL;
    }
  }

"""
    replace_one(disp, gop_install, gop_install_ready, ns.reverse)

if __name__ == "__main__":
    main()
