#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Portable regression for the EDID detailed-timing fallback math."""

def parse_dtd(dtd: bytes):
    assert len(dtd) == 18
    pixel_clock_10khz = dtd[0] | (dtd[1] << 8)
    if not pixel_clock_10khz:
        return None

    hactive = dtd[2] | ((dtd[4] & 0xF0) << 4)
    hblank = dtd[3] | ((dtd[4] & 0x0F) << 8)
    vactive = dtd[5] | ((dtd[7] & 0xF0) << 4)
    vblank = dtd[6] | ((dtd[7] & 0x0F) << 8)
    hsync_offset = dtd[8] | ((dtd[11] & 0xC0) << 2)
    hsync_width = dtd[9] | ((dtd[11] & 0x30) << 4)
    vsync_offset = (dtd[10] >> 4) | ((dtd[11] & 0x0C) << 2)
    vsync_width = (dtd[10] & 0x0F) | ((dtd[11] & 0x03) << 4)

    clock_khz = pixel_clock_10khz * 10
    htotal = hactive + hblank
    vtotal = vactive + vblank
    frame_pixels = htotal * vtotal
    refresh = round(clock_khz * 1000 / frame_pixels)

    flags = 0
    if dtd[17] & 0x80:
        flags |= 0x4
    if (dtd[17] & 0x18) == 0x18:
        if dtd[17] & 0x02:
            flags |= 0x1
        if dtd[17] & 0x04:
            flags |= 0x2

    return {
        "clock_khz": clock_khz,
        "hdisplay": hactive,
        "hsync_start": hactive + hsync_offset,
        "hsync_end": hactive + hsync_offset + hsync_width,
        "htotal": htotal,
        "vdisplay": vactive,
        "vsync_start": vactive + vsync_offset,
        "vsync_end": vactive + vsync_offset + vsync_width,
        "vtotal": vtotal,
        "vrefresh": refresh,
        "flags": flags,
    }

# CTA/CEA 1920x1080p60 detailed timing:
# 148.5 MHz, 1920 active + 280 blank, 1080 active + 45 blank,
# H front porch 88 / sync 44, V front porch 4 / sync 5.
dtd_1080p60 = bytes([
    0x02, 0x3A, 0x80, 0x18, 0x71, 0x38, 0x2D, 0x40,
    0x58, 0x2C, 0x45, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x1E,
])

t = parse_dtd(dtd_1080p60)
assert t is not None
assert t["clock_khz"] == 148500
assert t["hdisplay"] == 1920
assert t["hsync_start"] == 2008
assert t["hsync_end"] == 2052
assert t["htotal"] == 2200
assert t["vdisplay"] == 1080
assert t["vsync_start"] == 1084
assert t["vsync_end"] == 1089
assert t["vtotal"] == 1125
assert t["vrefresh"] == 60
assert t["flags"] == 0x3
assert parse_dtd(bytes(18)) is None

print("PASS: EDID DTD fallback derives 1080p60 timing without hard-coded refresh")
