#!/bin/bash
# Build the current hardware-validated Windows-oriented UEFI stack plus the
# isolated SOCB/GPU resource-scope experiment. Existing patches are applied
# unchanged; this wrapper adds only patch 0006.
set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIFI_PATCH="${WORKSPACE}/temporary-patches/edk2-platforms/0004-RPi5-WiFi-direct-SDIO-NDIS.patch"
SETTINGS_PATCH="${WORKSPACE}/temporary-patches/edk2-platforms/0005-RPi5-RTC-and-settings-persistence.patch"
DISPLAY_PATCH="${WORKSPACE}/temporary-patches/edk2-platforms/0006-RPi5-narrow-SOCB-resource-window-for-GPU.patch"
WIFI_PATCH_APPLIED=0
SETTINGS_PATCH_APPLIED=0
DISPLAY_PATCH_APPLIED=0

restore_candidate_patches() {
    if [[ "${DISPLAY_PATCH_APPLIED}" -eq 1 ]]; then
        git -C "${WORKSPACE}/edk2-platforms" apply --reverse "${DISPLAY_PATCH}"
        echo "Restored SOCB/GPU resource-scope patch"
    fi
    if [[ "${SETTINGS_PATCH_APPLIED}" -eq 1 ]]; then
        git -C "${WORKSPACE}/edk2-platforms" apply --reverse "${SETTINGS_PATCH}"
        echo "Restored RTC and settings persistence patch"
    fi
    if [[ "${WIFI_PATCH_APPLIED}" -eq 1 ]]; then
        git -C "${WORKSPACE}/edk2-platforms" apply --reverse "${WIFI_PATCH}"
        echo "Restored direct-SDIO Wi-Fi patch"
    fi
}
trap restore_candidate_patches EXIT

if ! git -C "${WORKSPACE}/edk2-platforms" diff --quiet; then
    echo "edk2-platforms worktree is not clean before display-resource candidate" >&2
    git -C "${WORKSPACE}/edk2-platforms" status --short >&2
    exit 1
fi

for spec in     "WIFI_PATCH_APPLIED:${WIFI_PATCH}:direct-SDIO Wi-Fi"     "SETTINGS_PATCH_APPLIED:${SETTINGS_PATCH}:RTC/settings persistence"     "DISPLAY_PATCH_APPLIED:${DISPLAY_PATCH}:SOCB/GPU resource-scope"; do
    var="${spec%%:*}"
    rest="${spec#*:}"
    file="${rest%%:*}"
    label="${rest#*:}"
    if ! git -C "${WORKSPACE}/edk2-platforms" apply --check "${file}"; then
        echo "${label} patch does not apply cleanly to the pinned edk2-platforms revision" >&2
        git -C "${WORKSPACE}/edk2-platforms" apply --check --verbose "${file}" >&2 || true
        exit 1
    fi
    git -C "${WORKSPACE}/edk2-platforms" apply "${file}"
    printf -v "${var}" '%s' 1
    echo "Applied ${label} patch"
done

status=0
"${WORKSPACE}/build.sh" "$@" || status=$?
exit "${status}"
