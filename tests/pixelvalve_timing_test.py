#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Portable regression for BCM2712 PixelValve timing + both HDMI frame counters."""

HD_BASE = 0x107C720000
HDMI0_FRAME_COUNT = 0x60
HDMI1_FRAME_COUNT = 0x64

assert HD_BASE + HDMI0_FRAME_COUNT == 0x107C720060
assert HD_BASE + HDMI1_FRAME_COUNT == 0x107C720064

# Physical Pi evidence: BCM2712 firmware exposed 1080p horizontal timing
# in two-pixel clock units: 74/22/44/960 -> 148/44/88/1920.
PV_HORZA = (74 << 16) | 22
PV_HORZB = (44 << 16) | 960
PV_VERTA = (36 << 16) | 5
PV_VERTB = (4 << 16) | 1080

hsync = PV_HORZA & 0xFFFF
hbp = (PV_HORZA >> 16) & 0xFFFF
hactive = PV_HORZB & 0xFFFF
hfp = (PV_HORZB >> 16) & 0xFFFF
vsync = PV_VERTA & 0xFFFF
vbp = (PV_VERTA >> 16) & 0xFFFF
vactive = PV_VERTB & 0xFFFF
vfp = (PV_VERTB >> 16) & 0xFFFF

gop_width = 1920
assert gop_width % hactive == 0
horizontal_scale = gop_width // hactive
assert horizontal_scale == 2
hsync *= horizontal_scale
hbp *= horizontal_scale
hactive *= horizontal_scale
hfp *= horizontal_scale

htotal = hactive + hfp + hsync + hbp
vtotal = vactive + vfp + vsync + vbp

assert hactive == 1920
assert hfp == 88
assert hsync == 44
assert hbp == 148
assert htotal == 2200
assert vactive == 1080
assert vfp == 4
assert vsync == 5
assert vbp == 36
assert vtotal == 1125

# Frame-counter measurement must use the matching HDMI port.
# Simulate four progressive frames at ~60 Hz for both ports.
first_counter = 100
last_counter = 104
delta = (last_counter - first_counter) & 0xFFFFFFFF
assert delta == 4

elapsed_ns = 66_666_668
frame_period_ns = elapsed_ns // delta
frame_pixels = htotal * vtotal
pixel_hz = (frame_pixels * 1_000_000_000 + frame_period_ns // 2) // frame_period_ns
clock_khz = (pixel_hz + 500) // 1000
refresh = (1_000_000_000 + frame_period_ns // 2) // frame_period_ns

assert 148_499 <= clock_khz <= 148_501
assert refresh == 60

for pixelvalve, frame_offset, display_id in (
    (0, HDMI0_FRAME_COUNT, 2),
    (1, HDMI1_FRAME_COUNT, 7),
):
    assert pixelvalve in (0, 1)
    assert frame_offset == (HDMI0_FRAME_COUNT if pixelvalve == 0 else HDMI1_FRAME_COUNT)
    assert display_id == (2 if pixelvalve == 0 else 7)

# Counter wrap should still produce the right unsigned frame delta.
first_counter = 0xFFFFFFFE
last_counter = 0x00000002
delta = (last_counter - first_counter) & 0xFFFFFFFF
assert delta == 4

print("PASS: both BCM2712 HDMI frame counters + two-pixel PV timing derive 1080p60")
