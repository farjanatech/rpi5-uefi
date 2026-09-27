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
        "#define RPI_MBOX_GET_FB_GPIOVIRTBUF                           0x00040010\n#define RPI_MBOX_GET_FB_DISPLAY_ID                            0x00040016\n#define RPI_MBOX_GET_DISPLAY_TIMING                           0x00040017\n",
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
        "  GET_TEMPERATURE        GetTemperature;\n  GET_FB_DISPLAY_ID      GetFbDisplayId;\n  GET_DISPLAY_TIMING     GetDisplayTiming;\n  GET_EDID_BLOCK_DISPLAY GetEdidBlockDisplay;\n} RASPBERRY_PI_FIRMWARE_PROTOCOL;",
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
        "  RpiFirmwareGetTemperature,\n  RpiFirmwareGetFbDisplayId,\n  RpiFirmwareGetDisplayTiming,\n  RpiFirmwareGetEdidBlockDisplay,\n};",
        ns.reverse)
    replace_one(fw,
        "  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetTemperature);\n",
        "  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetTemperature);\n  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetFbDisplayId);\n  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetDisplayTiming);\n  EfiConvertPointer (0x0, (VOID **)&mRpiFirmwareProtocol.GetEdidBlockDisplay);\n",
        ns.reverse)

    display_inf = r / "Platform/RaspberryPi/Drivers/DisplayDxe/DisplayDxe.inf"
    replace_one(display_inf,
        "  gEfiCpuArchProtocolGuid\n  gEfiSimpleFileSystemProtocolGuid\n",
        "  gEfiCpuArchProtocolGuid\n  gEfiVariableArchProtocolGuid\n  gEfiVariableWriteArchProtocolGuid\n  gEfiSimpleFileSystemProtocolGuid\n",
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
EFI_STATUS
PublishDisplayHandoff (
  IN UINT32 Width,
  IN UINT32 Height
  )
{
  RPI5_DISPLAY_HANDOFF Handoff;
  RPI5_DISPLAY_HANDOFF Verify;
  RASPBERRY_PI_DISPLAY_TIMING Timing;
  EFI_STATUS Status;
  EFI_STATUS DeleteStatus;
  UINTN VerifySize;
  UINT32 VerifyAttributes;
  UINT32 ExpectedAttributes;
  UINT32 Display;
  UINT32 Block;
  UINT32 WantedBlocks;

  ExpectedAttributes = EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS;

  DeleteStatus = gST->RuntimeServices->SetVariable (
                                     L"Rpi5DisplayHandoff",
                                     &mRpi5DisplayHandoffGuid,
                                     0,
                                     0,
                                     NULL);
  if (EFI_ERROR (DeleteStatus) && DeleteStatus != EFI_NOT_FOUND) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=delete status=%r\\n", DeleteStatus));
  }

  ZeroMem (&Handoff, sizeof (Handoff));
  Handoff.Signature = RPI5_DISPLAY_HANDOFF_SIGNATURE;
  Handoff.Version = RPI5_DISPLAY_HANDOFF_VERSION;
  Handoff.Size = sizeof (Handoff);

  Display = 0;
  Status = mFwProtocol->GetFbDisplayId (0, &Display);
  if (EFI_ERROR (Status) || Display > 0xFFU) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=display-id status=%r display=%u\\n",
      Status, Display));
    return EFI_ERROR (Status) ? Status : EFI_DEVICE_ERROR;
  }

  ZeroMem (&Timing, sizeof (Timing));
  Status = mFwProtocol->GetDisplayTiming (Display, &Timing);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=timing-query status=%r display=%u\\n",
      Status, Display));
    return Status;
  }

  if (!ValidateDisplayTiming (&Timing, Width, Height)) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=timing-validate display=%u mode=%ux%u "
      "fw=%ux%u clock=%u hsync=%u/%u/%u vsync=%u/%u/%u flags=0x%x\\n",
      Display, Width, Height, Timing.HDisplay, Timing.VDisplay, Timing.Clock,
      Timing.HSyncStart, Timing.HSyncEnd, Timing.HTotal,
      Timing.VSyncStart, Timing.VSyncEnd, Timing.VTotal, Timing.Flags));
    return EFI_COMPROMISED_DATA;
  }

  Handoff.DisplayNumber = Display;
  CopyMem (&Handoff.Timing, &Timing, sizeof (Timing));
  Handoff.Flags |= RPI5_DISPLAY_HANDOFF_TIMING_VALID;

  Status = mFwProtocol->GetEdidBlockDisplay (Display, 0, &Handoff.Edid[0]);
  if (!EFI_ERROR (Status) && ValidateEdidBlock (&Handoff.Edid[0], TRUE)) {
    WantedBlocks = 1U + Handoff.Edid[126];
    if (WantedBlocks <= RPI5_DISPLAY_HANDOFF_MAX_EDID_BLOCKS) {
      Handoff.EdidBlockCount = 1;
      for (Block = 1; Block < WantedBlocks; Block++) {
        Status = mFwProtocol->GetEdidBlockDisplay (
                                Display,
                                Block,
                                &Handoff.Edid[Block * RASPBERRY_PI_EDID_BLOCK_SIZE]);
        if (EFI_ERROR (Status) ||
            !ValidateEdidBlock (&Handoff.Edid[Block * RASPBERRY_PI_EDID_BLOCK_SIZE], FALSE)) {
          break;
        }
        Handoff.EdidBlockCount++;
      }
      if (Handoff.EdidBlockCount == WantedBlocks) {
        Handoff.Flags |= RPI5_DISPLAY_HANDOFF_EDID_VALID;
      }
    }
  }

  if ((Handoff.Flags & RPI5_DISPLAY_HANDOFF_EDID_VALID) == 0) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=edid optional-status=%r display=%u\\n",
      Status, Display));
    Handoff.EdidBlockCount = 0;
    ZeroMem (Handoff.Edid, sizeof (Handoff.Edid));
  }

  Status = gST->RuntimeServices->SetVariable (
                  L"Rpi5DisplayHandoff",
                  &mRpi5DisplayHandoffGuid,
                  ExpectedAttributes,
                  sizeof (Handoff),
                  &Handoff);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN,
      "Rpi5Display handoff stage=set-variable status=%r display=%u flags=0x%x\\n",
      Status, Display, Handoff.Flags));
    return Status;
  }

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
      "Rpi5Display handoff stage=verify status=%r bytes=%u attrs=0x%x expected=0x%x\\n",
      Status, (UINT32)VerifySize, VerifyAttributes, ExpectedAttributes));
    (VOID)gST->RuntimeServices->SetVariable (
                                  L"Rpi5DisplayHandoff",
                                  &mRpi5DisplayHandoffGuid,
                                  0,
                                  0,
                                  NULL);
    return EFI_ERROR (Status) ? Status : EFI_COMPROMISED_DATA;
  }

  DEBUG ((DEBUG_INFO,
    "Rpi5Display handoff stage=published display=%u flags=0x%x %ux%u "
    "clock=%uKHz totals=%ux%u refreshHint=%u edidBlocks=%u attrs=0x%x\\n",
    Handoff.DisplayNumber, Handoff.Flags, Width, Height, Handoff.Timing.Clock,
    Handoff.Timing.HTotal, Handoff.Timing.VTotal, Handoff.Timing.VRefresh,
    Handoff.EdidBlockCount, VerifyAttributes));
  return EFI_SUCCESS;
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
               gDisplayProto.Mode->Info->VerticalResolution);
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
        "  DEBUG((DEBUG_INFO, \"Reported Mode->FrameBufferSize is %u\\n\", This->Mode->FrameBufferSize));\n\n  (VOID)PublishDisplayHandoff (Mode->Width, Mode->Height);\n\n  ClearScreen (This);",
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
