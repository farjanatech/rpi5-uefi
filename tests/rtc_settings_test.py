"""GitHub-hosted, hardware-free tests of the exact patched firmware C functions.

Compile RTC with the pinned EDK2 TimeBaseLib and mocked mailbox; compile the
actual file I/O, target validation and save state machine with fault injection.
No Windows driver or firmware is executed on the developer's PC.
"""
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "edk2-platforms/Platform/RaspberryPi"


def no_includes(source):
    return re.sub(r"^#include.*$", "", source, flags=re.M)


def function(source, name):
    match = re.search(r"(?:STATIC\s+)?(?:EFI_STATUS|VOID)\s+(?:EFIAPI\s+)?" + name + r"\s*\(", source)
    assert match, name
    start = source.index("{", match.end())
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end] + "\n"


COMMON = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#define IN
#define OUT
#define OPTIONAL
#define STATIC static
#define CONST const
#define VOID void
#define EFIAPI
#define TRUE 1
#define FALSE 0
#define DEBUG(x) ((void)0)
#define ASSERT(x) assert(x)
#define ASSERT_EFI_ERROR(x) assert(!EFI_ERROR(x))
#define ASSERT_RETURN_ERROR(x) assert(!(x))
#define EFI_ERROR(x) ((x) != 0)
#define EFI_SUCCESS 0
#define EFI_INVALID_PARAMETER 2
#define EFI_UNSUPPORTED 3
#define EFI_DEVICE_ERROR 7
#define EFI_OUT_OF_RESOURCES 9
#define EFI_VOLUME_CORRUPTED 10
#define EFI_NO_MEDIA 12
#define EFI_NOT_FOUND 14
#define EFI_ACCESS_DENIED 15
#define EFI_NOT_READY 6
#define MAX_UINT32 UINT32_MAX
#define MAX_UINT64 UINT64_MAX
#define MIN(a,b) ((a)<(b)?(a):(b))
typedef uint8_t UINT8, BOOLEAN;
typedef int8_t INT8;
typedef uint16_t UINT16;
typedef int16_t INT16;
typedef uint32_t UINT32;
typedef uint64_t UINT64;
typedef uintptr_t UINTN;
typedef intptr_t INTN;
typedef int EFI_STATUS, RETURN_STATUS;
typedef void *EFI_EVENT, *EFI_HANDLE;
typedef wchar_t CHAR16;
static unsigned Checks;
#define CHECK(x) do { Checks++; if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); abort(); } } while(0)
'''

RTC_PREFIX = r'''
#define EFI_UNSPECIFIED_TIMEZONE 2047
#define EFI_TIME_ADJUST_DAYLIGHT 1
#define EFI_TIME_IN_DAYLIGHT 2
#define SEC_PER_MIN 60
#define SEC_PER_HOUR 3600
#define SEC_PER_DAY 86400
#define EPOCH_JULIAN_DATE 2440588
#define BUILD_EPOCH 1790164800
#define EVT_NOTIFY_SIGNAL 0x200
#define TPL_NOTIFY 16
typedef struct { UINT16 Year; UINT8 Month,Day,Hour,Minute,Second,Pad1; UINT32 Nanosecond; INT16 TimeZone; UINT8 Daylight,Pad2; } EFI_TIME;
typedef struct { UINT32 Resolution,Accuracy; BOOLEAN SetsToZero; } EFI_TIME_CAPABILITIES;
enum { RpiRtcTime, RpiRtcAlarm, RpiRtcAlarmEnable, RpiRtcAlarmPending };
static UINT32 Rtc[4];
static EFI_STATUS ReadStatus, WriteStatus, LocateStatus, EventStatus;
static unsigned Writes;
static EFI_STATUS MockGet(int which, UINT32 *value) { if(ReadStatus) return ReadStatus; *value=Rtc[which]; return 0; }
static EFI_STATUS MockSet(int which, UINT32 value) { if(WriteStatus) return WriteStatus; Writes++; Rtc[which]=value; return 0; }
typedef struct { EFI_STATUS (*GetRtc)(int,UINT32*); EFI_STATUS (*SetRtc)(int,UINT32); } RASPBERRY_PI_FIRMWARE_PROTOCOL;
static RASPBERRY_PI_FIRMWARE_PROTOCOL Firmware={MockGet,MockSet};
static int gRaspberryPiFirmwareProtocolGuid, gEfiEventVirtualAddressChangeGuid;
static EFI_STATUS Locate(void *guid,void *unused,void **out) { (void)guid; (void)unused; *out=&Firmware; return LocateStatus; }
static EFI_STATUS Event(UINT32 type, UINTN tpl, void (*cb)(EFI_EVENT,void*),void *ctx,void *guid,EFI_EVENT *out) { (void)type;(void)tpl;(void)cb;(void)ctx;(void)guid; *out=NULL; return EventStatus; }
static struct { EFI_STATUS (*LocateProtocol)(void*,void*,void**); EFI_STATUS (*CreateEventEx)(UINT32,UINTN,void(*)(EFI_EVENT,void*),void*,void*,EFI_EVENT*); } Boot={Locate,Event}, *gBS=&Boot;
typedef struct { int unused; } EFI_SYSTEM_TABLE;
static void EfiConvertPointer(int flags, void **p) {(void)flags;(void)p;}
'''

RTC_MAIN = r'''
int main(void) {
  EFI_TIME input={.Year=2026,.Month=9,.Day=23,.Hour=18,.Minute=45,.Second=37}, output;
  EFI_TIME_CAPABILITIES caps;
  UINTN epoch=EfiTimeToEpoch(&input);
  unsigned before;
  int daylight[3]={0,1,3};
  Rtc[RpiRtcTime]=(UINT32)epoch;
  CHECK(LibRtcInitialize(NULL,NULL)==0);
  CHECK(Writes==0); // A valid RTC must not be reset to firmware build time.
  for(int zone=-1440;zone<=1441;zone++) {
    input.TimeZone=(INT16)(zone==1441?EFI_UNSPECIFIED_TIMEZONE:zone);
    for(unsigned d=0;d<3;d++) {
      input.Daylight=(UINT8)daylight[d];
      CHECK(LibSetTime(&input)==0);
      CHECK(Rtc[RpiRtcTime]==epoch); // Every minute offset, no double conversion.
      memset(&output,0xa5,sizeof(output));
      output.TimeZone=input.TimeZone; output.Daylight=input.Daylight;
      memset(&caps,0xa5,sizeof(caps));
      CHECK(LibGetTime(&output,&caps)==0);
      CHECK(EfiTimeToEpoch(&output)==epoch);
      CHECK(output.TimeZone==input.TimeZone && output.Daylight==input.Daylight);
      CHECK(caps.Resolution==1 && caps.Accuracy==0 && caps.SetsToZero==FALSE);
      before=Writes;
      CHECK(LibRtcInitialize(NULL,NULL)==0 && Writes==before);
      output.TimeZone=EFI_UNSPECIFIED_TIMEZONE; output.Daylight=0;
      CHECK(LibGetTime(&output,NULL)==0 && EfiTimeToEpoch(&output)==epoch);
      CHECK(LibSetWakeupTime(TRUE,&input)==0 && Rtc[RpiRtcAlarm]==epoch);
      BOOLEAN enabled,pending;
      CHECK(LibGetWakeupTime(&enabled,&pending,&output)==0 && enabled);
      CHECK(EfiTimeToEpoch(&output)==epoch);
    }
  }
  // Dhaka, fractional zones and daylight rules are covered above, including a
  // reboot with missing timezone metadata. Check boundaries and error paths.
  input.TimeZone=EFI_UNSPECIFIED_TIMEZONE; input.Daylight=0;
  input.Year=2024; input.Month=2; input.Day=29; input.Hour=23; input.Minute=59; input.Second=59;
  CHECK(LibSetTime(&input)==0);
  Rtc[RpiRtcTime]++;
  CHECK(LibGetTime(&output,NULL)==0 && output.Month==3 && output.Day==1 && output.Hour==0);
  input.Year=2023;
  CHECK(LibSetTime(&input)==EFI_INVALID_PARAMETER);
  input.Year=1969;input.Month=12;input.Day=31;
  CHECK(LibSetTime(&input)==EFI_UNSUPPORTED);
  CHECK(LibSetWakeupTime(TRUE,&input)==EFI_UNSUPPORTED);
  EpochToEfiTime(UINT32_MAX,&input);
  CHECK(LibSetTime(&input)==0 && Rtc[RpiRtcTime]==UINT32_MAX);
  input.Second++;
  before=Writes;
  CHECK(LibSetTime(&input)==EFI_UNSUPPORTED && Writes==before);
  CHECK(LibSetWakeupTime(TRUE,&input)==EFI_UNSUPPORTED && Writes==before);
  CHECK(LibSetTime(NULL)==EFI_INVALID_PARAMETER);
  CHECK(LibGetTime(NULL,NULL)==EFI_INVALID_PARAMETER);
  CHECK(LibSetWakeupTime(FALSE,NULL)==0);
  CHECK(LibGetWakeupTime(NULL,NULL,NULL)==EFI_INVALID_PARAMETER);
  Rtc[RpiRtcTime]=0;before=Writes;
  CHECK(LibRtcInitialize(NULL,NULL)==0 && Writes==before+1 && Rtc[RpiRtcTime]==BUILD_EPOCH);
  ReadStatus=EFI_DEVICE_ERROR; before=Writes;
  CHECK(LibRtcInitialize(NULL,NULL)==EFI_DEVICE_ERROR && Writes==before);
  CHECK(LibGetTime(&output,NULL)==EFI_DEVICE_ERROR);
  ReadStatus=0;WriteStatus=EFI_DEVICE_ERROR;
  input.Year=2026;input.Month=9;input.Day=23;input.Second=0;
  CHECK(LibSetTime(&input)==EFI_DEVICE_ERROR);
  printf("PASS RTC: %u checks; all 2881 offsets + unspecified, DST metadata, reboot, boundaries and faults\n",Checks);
  return 0;
}
'''

FILE_PREFIX = r'''
typedef int EFI_DEVICE_PATH_PROTOCOL;
typedef struct { int unused; } EFI_FIRMWARE_VOLUME_HEADER;
typedef struct FILE_PROTOCOL EFI_FILE_PROTOCOL;
struct FILE_PROTOCOL {
  EFI_STATUS (*SetPosition)(EFI_FILE_PROTOCOL*,UINT64);
  EFI_STATUS (*Write)(EFI_FILE_PROTOCOL*,UINTN*,void*);
  EFI_STATUS (*Flush)(EFI_FILE_PROTOCOL*);
  EFI_STATUS (*Close)(EFI_FILE_PROTOCOL*);
  EFI_STATUS (*Read)(EFI_FILE_PROTOCOL*,UINTN*,void*);
  EFI_STATUS (*GetPosition)(EFI_FILE_PROTOCOL*,UINT64*);
};
#define EFI_FILE_MODE_READ 1
#define EFI_FILE_MODE_WRITE 2
#define PLATFORM_RESET_DELAY 3500000
#define CompareMem memcmp
static UINT8 Disk[16384], LoadedFv[4096], Vars[5000];
static UINTN Position, DiskSize=sizeof(Disk);
static int Fault, Runtime, Mutate;
static unsigned WriteCalls, FlushCalls, CloseCalls, OpenCalls;
static EFI_STATUS Seek(EFI_FILE_PROTOCOL *f,UINT64 pos) { (void)f; if(Fault==1)return EFI_DEVICE_ERROR; Position=pos==MAX_UINT64?DiskSize:(UINTN)pos;return 0; }
static EFI_STATUS Tell(EFI_FILE_PROTOCOL *f,UINT64 *pos) { (void)f; *pos=Position;return 0; }
static void MutateStore(void);
static EFI_STATUS Write(EFI_FILE_PROTOCOL *f,UINTN *size,void *b) { (void)f; WriteCalls++;if(Fault==2)return EFI_DEVICE_ERROR;if(Fault==3)(*size)--;CHECK(Position+*size<=sizeof(Disk));memcpy(Disk+Position,b,*size);Position+=*size;if(Mutate)MutateStore();return 0; }
static EFI_STATUS Flush(EFI_FILE_PROTOCOL *f) { (void)f;FlushCalls++;return Fault==4?EFI_DEVICE_ERROR:0; }
static EFI_STATUS Close(EFI_FILE_PROTOCOL *f) { (void)f;CloseCalls++;return Fault==7?EFI_DEVICE_ERROR:0; }
static EFI_STATUS Read(EFI_FILE_PROTOCOL *f,UINTN *size,void *b) { (void)f;if(Fault==5)return EFI_DEVICE_ERROR;if(Fault==6)(*size)--;CHECK(Position+*size<=sizeof(Disk));memcpy(b,Disk+Position,*size);Position+=*size;if(Fault==8 && *size)((UINT8*)b)[0]^=1;return 0; }
static EFI_FILE_PROTOCOL File={Seek,Write,Flush,Close,Read,Tell};
static EFI_STATUS FileOpen(EFI_DEVICE_PATH_PROTOCOL *d,CHAR16 *name,EFI_FILE_PROTOCOL **out,UINT64 mode) { (void)d;(void)name;(void)mode;OpenCalls++;if(Fault==9)return EFI_DEVICE_ERROR;*out=&File;return 0; }
static BOOLEAN EfiAtRuntime(void) {return Runtime;}
static UINT32 PcdGet32(int x) {(void)x;return PLATFORM_RESET_DELAY;}
static RETURN_STATUS PcdSet32S(int x,UINT32 y) {(void)x;(void)y;return 0;}
#define PcdPlatformResetDelay 1
#define PcdFdSize sizeof(Disk)
#define PcdFvSize sizeof(LoadedFv)
#define PcdFvBaseAddress ((UINTN)LoadedFv)
#define PcdFdBaseAddress ((UINTN)LoadedFv-256)
#define FixedPcdGet32(x) (x)
#define FixedPcdGet64(x) (x)
static unsigned Warnings;
typedef struct CONSOLE CONSOLE;
struct CONSOLE { EFI_STATUS (*OutputString)(CONSOLE*,const CHAR16*); };
static EFI_STATUS Output(CONSOLE *c,const CHAR16*s) {(void)c;(void)s;Warnings++;return 0;}
static CONSOLE Console={Output};
static struct {CONSOLE *ConOut;} System={&Console},*gST=&System;
static void *AllocateCopyPool(UINTN n,void *p) {void *out=malloc(n);if(out)memcpy(out,p,n);return out;}
typedef struct {BOOLEAN MediaPresent,ReadOnly;} MEDIA;
static MEDIA Media={TRUE,FALSE};
typedef struct {MEDIA *Media;} EFI_BLOCK_IO_PROTOCOL;
static EFI_BLOCK_IO_PROTOCOL Block={&Media};
static EFI_STATUS HandleProtocol(EFI_HANDLE h,void *guid,void *out) {(void)h;(void)guid;*(EFI_BLOCK_IO_PROTOCOL**)out=&Block;return 0;}
static struct {EFI_STATUS (*HandleProtocol)(EFI_HANDLE,void*,void*);} BS={HandleProtocol},*gBS=&BS;
static int gEfiBlockIoProtocolGuid, Device;
static EFI_DEVICE_PATH_PROTOCOL *DevicePathFromHandle(EFI_HANDLE h) {(void)h;return &Device;}
static EFI_DEVICE_PATH_PROTOCOL *DuplicateDevicePath(EFI_DEVICE_PATH_PROTOCOL *p) {return AllocateCopyPool(sizeof(*p),p);}
'''

FILE_MAIN = r'''
static void MutateStore(void) {mFvInstance->Generation++;}
int main(void) {
  EFI_FW_VOL_INSTANCE instance={.FvBase=(UINTN)Vars,.FvLength=sizeof(Vars),.Offset=8192,.Device=&Device,.MappedFile=L"RPI_EFI.FD"};
  EFI_DEVICE_PATH_PROTOCOL *chosen;
  mFvInstance=&instance;
  memset(Vars,0x57,sizeof(Vars));memset(LoadedFv,0xb6,sizeof(LoadedFv));
  memcpy(Disk+256,LoadedFv,sizeof(LoadedFv));memcpy(Disk+8192,Vars,sizeof(Vars));
  CHECK(CaptureBootVariableStore()==0);
  CHECK(CheckStore(NULL,&chosen)==0 && chosen!=NULL);free(chosen);
  CHECK(WriteCalls==0); // Target discovery must never modify a candidate file.
  Disk[256]^=1;
  CHECK(CheckStore(NULL,&chosen)!=0 && chosen==NULL);Disk[256]^=1;
  Disk[8192]^=1;
  CHECK(CheckStore(NULL,&chosen)!=0 && chosen==NULL);Disk[8192]^=1;
  DiskSize--;
  CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);DiskSize++;
  Media.ReadOnly=TRUE;CHECK(CheckStore(NULL,&chosen)==EFI_ACCESS_DENIED);Media.ReadOnly=FALSE;
  Media.MediaPresent=FALSE;CHECK(CheckStore(NULL,&chosen)==EFI_NO_MEDIA);Media.MediaPresent=TRUE;
  for(int fault=1;fault<=9;fault++) {
    Fault=fault; instance.Dirty=TRUE;unsigned before=WriteCalls;
    DumpVars();CHECK(instance.Dirty);CHECK(Warnings>0);
    if(fault==9)CHECK(WriteCalls==before);
    Fault=0;DumpVars();CHECK(!instance.Dirty);CHECK(!memcmp(Vars,Disk+8192,sizeof(Vars)));
  }
  for(int value=0;value<=1;value++) { // enable -> disable -> enable survives file reload
    Vars[0]=(UINT8)value;instance.Dirty=TRUE;instance.Generation++;DumpVars();
    CHECK(!instance.Dirty && Disk[8192]==value);
  }
  unsigned before=WriteCalls;DumpVars();CHECK(WriteCalls==before);
  instance.Dirty=TRUE;instance.Device=NULL;DumpVars();CHECK(instance.Dirty && WriteCalls==before);instance.Device=&Device;
  mSaving=TRUE;DumpVars();CHECK(instance.Dirty && WriteCalls==before);mSaving=FALSE;
  Runtime=TRUE;DumpVars();CHECK(instance.Dirty && WriteCalls==before);Runtime=FALSE;
  Mutate=TRUE;DumpVars();CHECK(instance.Dirty);Mutate=FALSE;DumpVars();CHECK(!instance.Dirty);
  before=OpenCalls;instance.Dirty=TRUE;StopFilePersistence(NULL,NULL);DumpVars();
  CHECK(OpenCalls==before && instance.Dirty); // No file/boot services after EBS.
  free(mBootVariableStore);
  printf("PASS settings: %u checks; target identity, short writes, flush/read/close faults, retries, both toggle directions, runtime guard and concurrent updates\n",Checks);
  return 0;
}
'''


def run(name, text):
    with tempfile.TemporaryDirectory(prefix="rpi5-uefi-test-") as tmp:
        source = pathlib.Path(tmp) / (name + ".c")
        exe = source.with_suffix("")
        source.write_text(COMMON + text)
        subprocess.run(["cc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-ftrivial-auto-var-init=pattern",
                        "-fsanitize=address,undefined", str(source), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


def main():
    rtc = no_includes((PLATFORM / "Library/RpiRtcLib/RpiRtcLib.c").read_text())
    timebase = no_includes((ROOT / "edk2/EmbeddedPkg/Library/TimeBaseLib/TimeBaseLib.c").read_text())
    run("rtc", RTC_PREFIX + timebase + rtc + RTC_MAIN)
    folder = PLATFORM / "Drivers/VarBlockServiceDxe"
    io = (folder / "FileIo.c").read_text()
    dxe = (folder / "VarBlockServiceDxe.c").read_text()
    header = (folder / "VarBlockService.h").read_text()
    struct = header[header.index("typedef struct {"):header.index("} EFI_FW_VOL_INSTANCE;") + len("} EFI_FW_VOL_INSTANCE;")]
    declarations = struct + "\nstatic EFI_FW_VOL_INSTANCE *mFvInstance;\n" + dxe[dxe.index("STATIC VOID     *mBootVariableStore;"):dxe.index("EFI_STATUS\nCaptureBootVariableStore")]
    chunks = [function(io,n) for n in ["FileVerify","FileWrite","FileClose"]]
    chunks += [function(dxe,n) for n in ["CaptureBootVariableStore","VerifyBootVariableStore","ReportSaveFailure","DoDump","DumpVars","StopFilePersistence"]]
    chunks += [function(io,"CheckStore")]
    run("settings", FILE_PREFIX + declarations + "\n".join(chunks) + FILE_MAIN)
    assert "EVT_TIMER | EVT_NOTIFY_SIGNAL, TPL_CALLBACK" in dxe
    assert "2 * 10000000ULL" in dxe
    assert "gEfiEventExitBootServicesGuid" in dxe
    assert "Generation++" in (folder / "VarBlockService.c").read_text()
    print("PASS: periodic boot-only persistence wiring; actual source used by firmware")


if __name__ == "__main__":
    main()
