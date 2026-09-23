"""GitHub-hosted, hardware-free tests of the exact patched firmware C functions.

Compile RTC with the pinned EDK2 TimeBaseLib and mocked mailbox; compile the
actual file I/O, target validation and save state machine with fault injection.
No Windows driver or firmware is executed on the developer's PC.
"""
import pathlib
import re
import subprocess
import sys
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
#pragma pack(push,1)
typedef struct { UINT32 NumBlocks,Length; } EFI_FV_BLOCK_MAP_ENTRY;
typedef struct {
  UINT8 ZeroVector[16],FileSystemGuid[16];UINT64 FvLength;
  UINT32 Signature,Attributes;UINT16 HeaderLength,Checksum,ExtHeaderOffset;
  UINT8 Reserved,Revision;EFI_FV_BLOCK_MAP_ENTRY BlockMap[1];
} EFI_FIRMWARE_VOLUME_HEADER;
typedef struct { UINT8 Name[16],IntegrityCheck[2],Type,Attributes,Size[3],State; } EFI_FFS_FILE_HEADER;
#pragma pack(pop)
_Static_assert(sizeof(EFI_FIRMWARE_VOLUME_HEADER)==64,"FV layout");
_Static_assert(sizeof(EFI_FFS_FILE_HEADER)==24,"FFS layout");
#define EFI_FVH_SIGNATURE 0x4856465f
#define EFI_FVH_REVISION 2
#define EFI_FV_FILETYPE_SECURITY_CORE 3
#define EFI_FV_FILETYPE_FIRMWARE_VOLUME_IMAGE 11
#define FFS_ATTRIB_LARGE_FILE 1
#define ALIGN_VALUE(v,a) (((v)+(a)-1)&~((UINTN)(a)-1))
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
#ifndef TEST_DISK_SIZE
#define TEST_DISK_SIZE 16384
#define TEST_FV_SIZE 4096
#define TEST_FV_OFFSET 256
#define TEST_NV_SIZE 5000
#define TEST_NV_OFFSET 8192
#endif
static UINT8 Disk[TEST_DISK_SIZE], LoadedFv[TEST_FV_SIZE], Vars[TEST_NV_SIZE];
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
#define PcdFdBaseAddress ((UINTN)LoadedFv-TEST_FV_OFFSET)
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
static void InitFv(void) {
  memset(LoadedFv,0xff,sizeof(LoadedFv));
  EFI_FIRMWARE_VOLUME_HEADER *fv=(void*)LoadedFv;
  memset(fv,0,sizeof(*fv));fv->Signature=EFI_FVH_SIGNATURE;fv->Revision=2;
  fv->HeaderLength=72;fv->FvLength=sizeof(LoadedFv);
  EFI_FFS_FILE_HEADER *sec=(void*)(LoadedFv+72),*dxe=(void*)(LoadedFv+328);
  memset(sec,0,sizeof(*sec));sec->Type=3;sec->Size[0]=255; // exercise alignment padding
  memset(dxe,0,sizeof(*dxe));dxe->Type=11;dxe->Size[1]=2;
}
int main(void) {
  EFI_FW_VOL_INSTANCE instance={.FvBase=(UINTN)Vars,.FvLength=sizeof(Vars),.Offset=8192,.Device=&Device,.MappedFile=L"RPI_EFI.FD"};
  EFI_DEVICE_PATH_PROTOCOL *chosen;
  mFvInstance=&instance;
  memset(Vars,0x57,sizeof(Vars));InitFv();
  memcpy(Disk+256,LoadedFv,sizeof(LoadedFv));memcpy(Disk+8192,Vars,sizeof(Vars));
  CHECK(CaptureBootVariableStore()==0);
  CHECK(CheckStore(NULL,&chosen)==0 && chosen!=NULL);free(chosen);
  CHECK(WriteCalls==0); // Target discovery must never modify a candidate file.
  // Every SEC payload byte may change in RAM during startup, unlike FV/FFS
  // headers and the compressed DXE payload. The old whole-FV check must fail.
  for(unsigned i=96;i<327;i++) LoadedFv[i]^=0x5a;
  CHECK(FileVerify(&File,256,(UINTN)LoadedFv,sizeof(LoadedFv))==EFI_DEVICE_ERROR);
  CHECK(CheckStore(NULL,&chosen)==0 && chosen!=NULL);free(chosen);
  CHECK(WriteCalls==0);
  const unsigned immutable[]={0,48,72,95,327,328,352,839,4095};
  for(unsigned i=0;i<sizeof(immutable)/sizeof(*immutable);i++) {
    Disk[256+immutable[i]]^=1;
    CHECK(CheckStore(NULL,&chosen)!=0 && chosen==NULL);
    Disk[256+immutable[i]]^=1;
  }
  UINT8 snapshot[sizeof(LoadedFv)];memcpy(snapshot,LoadedFv,sizeof(snapshot));
  EFI_FIRMWARE_VOLUME_HEADER *fv=(void*)LoadedFv;
  EFI_FFS_FILE_HEADER *sec=(void*)(LoadedFv+72),*dxe=(void*)(LoadedFv+328);
  // Reject malformed / unsupported loaded layouts before any candidate write.
  fv->HeaderLength=0;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  fv->HeaderLength=4096;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  fv->ExtHeaderOffset=64;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  fv->FvLength++;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  sec->Type=11;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  sec->Attributes=1;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  sec->Size[0]=24;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  sec->Size[2]=255;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  dxe->Type=3;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  dxe->Attributes=1;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  dxe->Size[2]=255;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  dxe->Size[1]=0;CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);memcpy(LoadedFv,snapshot,sizeof(snapshot));
  Disk[256]^=1;
  CHECK(CheckStore(NULL,&chosen)!=0 && chosen==NULL);Disk[256]^=1;
  Disk[8192]^=1;
  CHECK(CheckStore(NULL,&chosen)!=0 && chosen==NULL);Disk[8192]^=1;
  DiskSize=instance.Offset+instance.FvLength; // Valid image with omitted reserved tail.
  CHECK(CheckStore(NULL,&chosen)==0);free(chosen);
  DiskSize--;
  CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);
  DiskSize=sizeof(Disk)+1;
  CHECK(CheckStore(NULL,&chosen)==EFI_VOLUME_CORRUPTED);DiskSize=sizeof(Disk);
  Media.ReadOnly=TRUE;CHECK(CheckStore(NULL,&chosen)==EFI_ACCESS_DENIED);Media.ReadOnly=FALSE;
  Media.MediaPresent=FALSE;CHECK(CheckStore(NULL,&chosen)==EFI_NO_MEDIA);Media.MediaPresent=TRUE;
  Fault=7;CHECK(CheckStore(NULL,&chosen)==EFI_DEVICE_ERROR && chosen==NULL);Fault=0;
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
  const UINT8 speeds[]={3,2,3};
  for(unsigned i=0;i<sizeof(speeds);i++) {
    Vars[1]=speeds[i];instance.Dirty=TRUE;instance.Generation++;DumpVars();
    CHECK(!instance.Dirty && Disk[8193]==speeds[i]);
    // Model next boot from persisted data, including a new boot-store snapshot.
    memset(Vars,0,sizeof(Vars));memcpy(Vars,Disk+8192,sizeof(Vars));
    free(mBootVariableStore);CHECK(CaptureBootVariableStore()==0);
    CHECK(CheckStore(NULL,&chosen)==0);free(chosen);CHECK(Vars[1]==speeds[i]);
  }
  unsigned before=WriteCalls;DumpVars();CHECK(WriteCalls==before);
  instance.Dirty=TRUE;instance.Device=NULL;DumpVars();CHECK(instance.Dirty && WriteCalls==before);instance.Device=&Device;
  mSaving=TRUE;DumpVars();CHECK(instance.Dirty && WriteCalls==before);mSaving=FALSE;
  Runtime=TRUE;DumpVars();CHECK(instance.Dirty && WriteCalls==before);Runtime=FALSE;
  Mutate=TRUE;DumpVars();CHECK(instance.Dirty);Mutate=FALSE;DumpVars();CHECK(!instance.Dirty);
  before=OpenCalls;instance.Dirty=TRUE;StopFilePersistence(NULL,NULL);DumpVars();
  CHECK(OpenCalls==before && instance.Dirty); // No file/boot services after EBS.
  free(mBootVariableStore);
  printf("PASS settings: %u checks; mutable SEC regression, immutable identity, malformed layouts, short writes, flush/read/close faults, Gen3/Gen2 simulated reload, runtime guard and concurrent updates\n",Checks);
  return 0;
}
'''


FILE_ARTIFACT_MAIN = r'''
static void MutateStore(void) {mFvInstance->Generation++;}
int main(int argc,char **argv) {
  CHECK(argc==2);FILE *input=fopen(argv[1],"rb");CHECK(input!=NULL);
  DiskSize=fread(Disk,1,sizeof(Disk),input);CHECK(!ferror(input));CHECK(fclose(input)==0);
  CHECK(DiskSize>=TEST_NV_OFFSET+sizeof(Vars));
  memcpy(LoadedFv,Disk+TEST_FV_OFFSET,sizeof(LoadedFv));memcpy(Vars,Disk+TEST_NV_OFFSET,sizeof(Vars));
  EFI_FW_VOL_INSTANCE instance={.FvBase=(UINTN)Vars,.FvLength=sizeof(Vars),.Offset=TEST_NV_OFFSET,.Device=&Device,.MappedFile=L"RPI_EFI.FD"};
  mFvInstance=&instance;EFI_DEVICE_PATH_PROTOCOL *chosen;
  CHECK(CaptureBootVariableStore()==0);CHECK(CheckStore(NULL,&chosen)==0);free(chosen);
  EFI_FIRMWARE_VOLUME_HEADER *fv=(void*)LoadedFv;
  UINTN secOffset=ALIGN_VALUE(fv->HeaderLength,8);
  EFI_FFS_FILE_HEADER *sec=(void*)(LoadedFv+secOffset);
  UINTN secSize=sec->Size[0]|((UINTN)sec->Size[1]<<8)|((UINTN)sec->Size[2]<<16);
  const UINT32 request[8]={32,0,0x10005,8,0,0,0,0};
  UINTN mailbox=0;unsigned matches=0;
  for(UINTN i=secOffset+sizeof(*sec);i+sizeof(request)<=secOffset+secSize;i++) {
    if(!memcmp(LoadedFv+i,request,sizeof(request))) {mailbox=i;matches++;}
  }
  CHECK(matches==1);
  // Model the actual SEC mailbox response, not execution of firmware/hardware.
  const UINT32 response[8]={32,0x80000000,0x10005,8,0x80000008,0,0x3fc00000,0};
  memcpy(LoadedFv+mailbox,response,sizeof(response));
  CHECK(FileVerify(&File,TEST_FV_OFFSET,(UINTN)LoadedFv,sizeof(LoadedFv))==EFI_DEVICE_ERROR);
  CHECK(CheckStore(NULL,&chosen)==0);free(chosen);CHECK(WriteCalls==0);
  UINTN dxeOffset=ALIGN_VALUE(secOffset+secSize,8);
  Disk[TEST_FV_OFFSET+dxeOffset+sizeof(EFI_FFS_FILE_HEADER)+32]^=1;
  CHECK(CheckStore(NULL,&chosen)!=0 && chosen==NULL);
  Disk[TEST_FV_OFFSET+dxeOffset+sizeof(EFI_FFS_FILE_HEADER)+32]^=1;
  Disk[TEST_NV_OFFSET+128]^=1;CHECK(CheckStore(NULL,&chosen)!=0 && chosen==NULL);
  Disk[TEST_NV_OFFSET+128]^=1;CHECK(CheckStore(NULL,&chosen)==0);free(chosen);
  DumpVars();StopFilePersistence(NULL,NULL); // clean store: no file writes
  CHECK(WriteCalls==0);free(mBootVariableStore);
  printf("PASS actual FD: %u checks; SEC mailbox at 0x%lx; old full-FV check rejects, fixed identity accepts; DXE/NV mismatches rejected, no writes\n",Checks,(unsigned long)(TEST_FV_OFFSET+mailbox));
  return 0;
}
'''


def run(name, text, args=()):
    with tempfile.TemporaryDirectory(prefix="rpi5-uefi-test-") as tmp:
        source = pathlib.Path(tmp) / (name + ".c")
        exe = source.with_suffix("")
        source.write_text(COMMON + text)
        subprocess.run(["cc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-ftrivial-auto-var-init=pattern",
                        "-fsanitize=address,undefined", str(source), "-o", str(exe)], check=True)
        subprocess.run([str(exe), *args], check=True)


def file_checker_source():
    folder = PLATFORM / "Drivers/VarBlockServiceDxe"
    io = (folder / "FileIo.c").read_text()
    dxe = (folder / "VarBlockServiceDxe.c").read_text()
    header = (folder / "VarBlockService.h").read_text()
    struct = header[header.index("typedef struct {"):header.index("} EFI_FW_VOL_INSTANCE;") + len("} EFI_FW_VOL_INSTANCE;")]
    declarations = struct + "\nstatic EFI_FW_VOL_INSTANCE *mFvInstance;\n" + dxe[dxe.index("STATIC VOID     *mBootVariableStore;"):dxe.index("EFI_STATUS\nCaptureBootVariableStore")]
    chunks = [function(io,n) for n in ["FileVerify","FileVerifyFirmware","FileWrite","FileClose"]]
    chunks += [function(dxe,n) for n in ["CaptureBootVariableStore","VerifyBootVariableStore","ReportSaveFailure","DoDump","DumpVars","StopFilePersistence"]]
    chunks += [function(io,"CheckStore")]
    return FILE_PREFIX + declarations + "\n".join(chunks)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--firmware":
        image = pathlib.Path(sys.argv[2]).read_bytes()
        fdf = (PLATFORM / "RPi5/RPi5.fdf").read_text()
        # Assert this fixture's layout against pinned FDF before testing the
        # emitted artifact: final populated NV region ends before reserved tail.
        assert "0x003b0000|0x0000e000" in fdf
        assert "0x003c0000|0x00010000" in fdf
        assert "Size          = 0x003e0000" in fdf
        assert 0x003d0000 <= len(image) <= 0x003e0000
        assert image[0x003b0028:0x003b002c] == b"_FVH"
        assert int.from_bytes(image[0x003b0020:0x003b0028], "little") == 0x20000
        print(f"PASS packaged FD: {len(image)} bytes; full NV store present, reserved-tail omission accepted")
        layout = "\n".join(f"#define {key} {value}" for key, value in {
            "TEST_DISK_SIZE": "0x3e0000", "TEST_FV_SIZE": "0x390000",
            "TEST_FV_OFFSET": "0x20000", "TEST_NV_SIZE": "0x20000",
            "TEST_NV_OFFSET": "0x3b0000"}.items()) + "\n"
        run("artifact", layout + file_checker_source() + FILE_ARTIFACT_MAIN,
            [str(pathlib.Path(sys.argv[2]).resolve())])
        return
    rtc = no_includes((PLATFORM / "Library/RpiRtcLib/RpiRtcLib.c").read_text())
    timebase = no_includes((ROOT / "edk2/EmbeddedPkg/Library/TimeBaseLib/TimeBaseLib.c").read_text())
    run("rtc", RTC_PREFIX + timebase + rtc + RTC_MAIN)
    folder = PLATFORM / "Drivers/VarBlockServiceDxe"
    dxe = (folder / "VarBlockServiceDxe.c").read_text()
    run("settings", file_checker_source() + FILE_MAIN)
    assert "EVT_TIMER | EVT_NOTIFY_SIGNAL, TPL_CALLBACK" in dxe
    assert "2 * 10000000ULL" in dxe
    assert "gEfiEventExitBootServicesGuid" in dxe
    assert "Generation++" in (folder / "VarBlockService.c").read_text()
    print("PASS: periodic boot-only persistence wiring; actual source used by firmware")


if __name__ == "__main__":
    main()
