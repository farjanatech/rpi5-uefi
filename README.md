# Damian Edition — direct CYW43455 Wi-Fi extension

This branch deliberately uses **Damian's Raspberry Pi 5 UEFI as the platform base**
and keeps its ACPI/native-driver contract intact.

Pinned baseline:

- `damian5466/rpi5-uefi`: `21c5034031a44595fbc008c38698889fe070a409` (release 0.1a)
- `damian5466/edk2-platforms`: `313a8915f8b8358ff5c5716668cccb59c11dd20d`
- Damian ACPI contract revision 1 is authoritative.
- Damian fan, graphics, mailbox/RTC, NVRAM, GPIO, RP1 services and device graph
  are not replaced by Farjanatech equivalents.

The only extension is an optional **Windows Direct NDIS** mode for the on-board
CYW43455 Wi-Fi controller. The default remains Damian's original **Standard SD Bus**
mode.

## Direct Wi-Fi design

The direct mode uses a new, collision-free ACPI hardware ID:

`ACPI\\RPI1060`

Damian already owns `ACPI\\RPI0011` for the RP1 shared interrupt provider, so
Farjanatech's historical Wi-Fi ID `RPI0011` is intentionally not reused.

In Standard SD Bus mode, Damian's original `SDC1` node remains present and
unchanged. In Direct NDIS mode, `SDC1` is hidden and a mutually-exclusive
`WFD0/RPI1060` node owns the same SDIO2 host MMIO and IRQ 306. Firmware then
applies only the direct-SDIO host preparation that the Farjanatech driver needs:
SD pin selection, 200 MHz capability metadata, forced card-present, and the
150 ms WL_ON settle delay. It intentionally does **not** apply the old
MAX_50MHZ_MODE strap override.

The configuration is available under:

`Device Manager -> Raspberry Pi Configuration -> ACPI / Device Tree -> Wi-Fi SDIO Mode`

Options:

- **Standard SD Bus (Damian)** — default, original Damian behavior.
- **Windows Direct NDIS (Farjanatech)** — exposes `ACPI\\RPI1060`.

## Companion driver

Farjanatech's current Wi-Fi driver 0.7.1.20 still binds to
`ACPI\\RPI0011`. Do **not** install that unmodified package with this branch:
on Damian firmware, `RPI0011` is the RP1 IRQ provider.

A source patch is included at
`driver-patches/0001-rpi5cyw-bind-rpi1060.patch`. Apply it to
`farjanatech/rpi5-wifi-driver-win11arm`, rebuild/re-sign the package, and use
that matching driver with Direct NDIS mode.

---

# Raspberry Pi 5 UEFI
This fork contains a TF-A + EDK2 UEFI firmware port for Raspberry Pi 5, including
BCM2712 D0 display/GPIO compatibility, ACPI peripheral descriptions, SD voltage
switching, RP1 handoff, fan control, and file-backed NVRAM.

Native driver authors should read the [ACPI driver contract](edk2-platforms/Platform/RaspberryPi/RPi5/ACPI-CONTRACT.md)
for resource ownership, the boot device connection graph, and shared-service interfaces.

![EDK2 Setup Screen](images/edk2_setup_screen.png)

# Getting started
Check the [Supported OSes](#supported-oses) and [Supported peripherals in UEFI](#supported-peripherals-in-uefi) sections to see what's currently possible with this firmware.

## 1. Prerequisites
* #### SD card, USB or NVME drive to store the firmware and/or operating system on

  **Note:** For OS, it is highly suggested to use a quality drive with **good random I/O performance**. In SD terms this means an A1/A2-rated card.
  
* #### Quality power supply and cable that can provide at least 5V 3A (15 W)
  Depending on the peripherals you use, more power may be needed. The recommended official power supply provides 5.1V 5A (25 W).

  **Note:** Using an inadequate supply can cause all sorts of issues, from underclocking to random crashes.

* #### HDMI display

* #### Some form of cooling (fan, heatsink)
  The device may thermal throttle otherwise.

Optionally, if display is not available or for debugging purposes, an UART serial adapter compatible with the special connector. Configuration is `115200 8n1`.

## 2. Download the firmware image
The latest version can be obtained from [Releases](https://github.com/damian5466/rpi5-uefi/releases).

## 3. Flash the firmware
Prepare an empty boot drive by formatting the first partition as FAT32, then extract the archive downloaded above to the root of this partition.

**Note:** do not rename or delete any of the boot files.

## 4. Connect peripherals and power on the device
You should first see a QR code screen, then shortly after, a centered Raspberry Pi logo with progress bar at the bottom. This indicates that the UEFI firmware has loaded.

At this stage, you can press <kbd>Esc</kbd> to enter the firmware setup, <kbd>F1</kbd> to launch the UEFI Shell, or, provided you also have an UEFI bootloader/app on a storage device, you can let the system automatically run that, which is the default behavior if no action is taken.

Check the configuration options described below, some of which may need to be changed depending on the OS used.

# Configuration settings
The UEFI provides options that can be viewed and changed using the UI configuration menu.

Configuration through the user interface is fairly straightforward and help/navigation information is provided around the menus.

## PCI Express
The PCIe connector is limited to Gen 2 speed by default. For other modes, go to `Device Manager`->`Raspberry Pi Configuration`->`PCI Express` and change `Link Speed`.

> [!NOTE]
> Raspberry Pi 5 is not officially rated for PCIe Gen 3. Some devices and adapters may run into reliability issues at this speed, either due to signal integrity or insufficient power.

## Linux
* If you're getting a Synchronous Exception when booting certain distros, go to `Device Manager`->`EFI Memory Attribute Protocol` and untick `Enable Protocol`.

* For maximum SD card performance, go to `Device Manager`->`Raspberry Pi Configuration`->`ACPI / Device Tree` and set `Compatibility Mode` to `Full Bay Trail`, then untick `Limit UHS-I Modes`.

  **Warning:** this may affect other OSes!

* To enable PCIe support, go to `Device Manager`->`Raspberry Pi Configuration`->`ACPI / Device Tree` and change `ECAM Compatibility Mode` to `AMAZON GRAVITON`.

* If you're running the RPi downstream kernel, enabling Device Tree instead of ACPI will provide better hardware support. To do so, go to `Device Manager`->`Raspberry Pi Configuration`->`ACPI / Device Tree` and change `System Table Mode`.

> [!NOTE]
> Windows support was tested with drivers from [rpi5-windows-drivers](https://github.com/damian5466/rpi5-windows-drivers).

# Status

## Supported OSes
### In ACPI mode
ACPI support is currently under development and limited to a few devices that have existing driver bindings.

| OS | Version | Tested/supported hardware | Notes |
| --- | --- | --- | --- |
| Windows | 11 (26100.9539) | Display, USB, SD, SDIO, PCIe, Ethernet, PWM | * SD is limited to DDR50.<br> * PL011 UART driver fails to start, but debugging over it still works via DBG2.<br> * PCIe is limited to single-function devices. |

### In Device Tree mode
The included DTB is meant for the RPi downstream 6.1.y kernel.

## Supported peripherals in UEFI
> [!NOTE]
> Only devices relevant to the firmware itself (not OS) are listed below.

| Device | Status | Notes |
| --- | --- | --- |
| RP1 USB                            | 🟢 Working     | |
| RP1 Ethernet                       | 🔴 Not working | |
| RP1 GPIO                           | 🔴 Not working | |
| RP1 PWM                            | 🟢 Working     | Cooling fan control and OS handoff. |
| PCIe                               | 🟢 Working     | |
| SD                                 | 🟢 Working     | SD cards up to SDR104. eMMC support is unknown. |
| Display                            | 🟢 Working     | HDMI, driven by the VPU firmware. |
| UART                               | 🟢 Working     | PL011 available on the dedicated connector at 115200 8n1. |
| GPIO                               | 🟢 Working     | GIO/AON, pin function. |
| RTC                                | 🟢 Working     | Get/set time, wake up alarm. |
| RNG                                | 🟢 Working     | |
| EEPROM                             | 🔴 Not working | Optional file-backed variable persistence is available. |

## Building
This process assumes a Linux machine. On Windows, use WSL.

1. Install required packages:

   For Ubuntu/Debian:
   ```bash
   sudo apt install git gcc g++ build-essential gcc-aarch64-linux-gnu iasl python3-pyelftools uuid-dev
   ```
   For Arch Linux:
   ```bash
   sudo pacman -Syu
   sudo pacman -S git base-devel gcc dtc aarch64-linux-gnu-binutils aarch64-linux-gnu-gcc aarch64-linux-gnu-glibc python python-pyelftools iasl --needed
   ```

2. Clone the repository:
   ```bash
   git clone --recurse-submodules https://github.com/damian5466/rpi5-uefi.git
   cd rpi5-uefi
   ```

3. Build the image:
   ```bash
   ./build.sh
   ```
   Append `--help` for more details.

If you get build errors, it is very likely that you're still missing some dependencies. The list of packages above is not complete and depending on the distro you may need to install additional ones. In most cases, looking up the error messages on the internet will point you at the right packages.

### Boot files

Assemble the firmware image, configuration, and pinned boot support files:

```bash
mkdir -p Build/boot/release
cp RPI_EFI.fd config.txt Build/boot/release/
cd Build/boot/release
mkdir -p overlays
curl -fL https://raw.githubusercontent.com/raspberrypi/firmware/1e403e23baab5673f0494a200f57cd01287d5b1a/boot/bcm2712-rpi-5-b.dtb -o bcm2712-rpi-5-b.dtb
curl -fL https://raw.githubusercontent.com/raspberrypi/firmware/bead686816848038563a542dc854346ab13253a2/boot/overlays/bcm2712d0.dtbo -o overlays/bcm2712d0.dtbo
echo "c5432acc8373fa6311e147221b8ba5c8685b957730afac7592c5deac2b27e732  bcm2712-rpi-5-b.dtb" | sha256sum -c -
echo "b73210c9256ff4b4963365f9acc49c0f7449f17eeddf21355e23dd011da899ec  overlays/bcm2712d0.dtbo" | sha256sum -c -
```

## Licenses
Most files are licensed under the default EDK2 license, [BSD-2-Clause-Patent](https://github.com/tianocore/edk2/blob/master/License.txt).

For TF-A, see: <https://github.com/ARM-software/arm-trusted-firmware/blob/master/docs/license.rst>
