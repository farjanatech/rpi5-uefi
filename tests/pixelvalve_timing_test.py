#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Portable regression for BCM2712 PixelValve timing decode + measured clock."""

PV_HORZA = (148 << 16) | 44
PV_HORZB = (88 << 16) | 1920
PV_VERTA = (36 << 16) | 5
PV_VERTB = (4 << 16) | 1080
FRAME_PERIOD_NS = 16_666_667

hsync = PV_HORZA & 0xFFFF
hbp = (PV_HORZA >> 16) & 0xFFFF
hactive = PV_HORZB & 0xFFFF
hfp = (PV_HORZB >> 16) & 0xFFFF
vsync = PV_VERTA & 0xFFFF
vbp = (PV_VERTA >> 16) & 0xFFFF
vactive = PV_VERTB & 0xFFFF
vfp = (PV_VERTB >> 16) & 0xFFFF

htotal = hactive + hfp + hsync + hbp
vtotal = vactive + vfp + vsync + vbp
frame_pixels = htotal * vtotal
pixel_hz = (frame_pixels * 1_000_000_000 + FRAME_PERIOD_NS // 2) // FRAME_PERIOD_NS
clock_khz = (pixel_hz + 500) // 1000
refresh = (1_000_000_000 + FRAME_PERIOD_NS // 2) // FRAME_PERIOD_NS

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
assert 148_499 <= clock_khz <= 148_501
assert refresh == 60

print("PASS: BCM2712 PixelValve registers + measured VFP period derive 1080p60")
