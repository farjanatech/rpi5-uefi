"""Compile the actual UEFI detector against libfdt and test packaged DTBs.

Runs on GitHub's Linux build host; no hardware registers are accessed.
Requires cc, libfdt-dev and dtc. Arguments: Peripherals.c, base.dtb, d0.dtb.
"""
import pathlib
import subprocess
import sys
import tempfile


def main():
    source, base, d0 = map(pathlib.Path, sys.argv[1:])
    text = source.read_text()
    start = text.index("typedef enum {\n  Bcm2712PinctrlUnknown,")
    end = text.index("\nSTATIC\nEFI_STATUS", start)
    detector = text[start:end]
    # Keep the behavioral test tied to the exact C code used by the firmware.
    prefix = r'''
#include <libfdt.h>
#include <stdio.h>
#include <stdlib.h>
#define STATIC static
#define CONST const
#define VOID void
#define DEBUG(args) ((void)0)
#define FdtCheckHeader fdt_check_header
#define FdtNodeOffsetByCompatible fdt_node_offset_by_compatible
static void *InputFdt;
static void *FdtPlatformGetBase(void) { return InputFdt; }
'''
    suffix = r'''
int main(int argc, char **argv) {
    char buffer[262144];
    FILE *file;
    int expected, actual;
    if (argc != 3) return 2;
    expected = atoi(argv[2]);
    if (argv[1][0] != '-') {
        file = fopen(argv[1], "rb");
        if (!file) return 3;
        if (fread(buffer, 1, sizeof(buffer), file) == 0) return 4;
        fclose(file);
        InputFdt = buffer;
    }
    actual = GetBcm2712PinctrlRevision();
    if (actual != expected) {
        fprintf(stderr, "%s: expected %d, got %d\n", argv[1], expected, actual);
        return 1;
    }
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        cfile = root / "detector.c"
        exe = root / "detector"
        cfile.write_text(prefix + detector + suffix)
        subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(cfile),
                        "-lfdt", "-o", str(exe)], check=True)

        def check(path, expected):
            subprocess.run([str(exe), str(path), str(expected)], check=True)

        check(base, 1)
        check(d0, 2)
        check("-", 0)
        invalid = root / "invalid.dtb"
        invalid.write_bytes(bytes(128))
        check(invalid, 0)
        for name, compatible, expected in [
            ("legacy", '"brcm,bcm2712-pinctrl"', 1),
            ("c0", '"brcm,bcm2712c0-pinctrl"', 1),
            ("d0", '"brcm,bcm2712d0-pinctrl"', 2),
            ("d0-fallback", '"brcm,bcm2712d0-pinctrl", "brcm,bcm2712-pinctrl"', 2),
            ("unknown", '"test,unknown-pinctrl"', 0),
        ]:
            dts = root / (name + ".dts")
            dtb = root / (name + ".dtb")
            dts.write_text('/dts-v1/; / { pinctrl { compatible = ' + compatible + '; }; };')
            subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb), str(dts)], check=True)
            check(dtb, expected)
    print("PASS: packaged C0/D0 trees, legacy/modern names, fallback precedence, missing/invalid/unknown DTBs")


if __name__ == "__main__":
    main()
