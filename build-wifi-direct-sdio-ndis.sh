#!/bin/bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIFI_PATCH="${WORKSPACE}/temporary-patches/edk2-platforms/0004-RPi5-WiFi-direct-SDIO-NDIS.patch"
WIFI_PATCH_APPLIED=0

restore_wifi_patch() {
    if [[ "${WIFI_PATCH_APPLIED}" -eq 1 ]]; then
        git -C "${WORKSPACE}/edk2-platforms" apply --reverse "${WIFI_PATCH}"
        echo "Restored direct-SDIO Wi-Fi patch"
    fi
}
trap restore_wifi_patch EXIT

if ! git -C "${WORKSPACE}/edk2-platforms" diff --quiet; then
    echo "edk2-platforms worktree is not clean before direct-SDIO patch" >&2
    git -C "${WORKSPACE}/edk2-platforms" status --short >&2
    exit 1
fi

if git -C "${WORKSPACE}/edk2-platforms" apply --check "${WIFI_PATCH}"; then
    git -C "${WORKSPACE}/edk2-platforms" apply "${WIFI_PATCH}"
    WIFI_PATCH_APPLIED=1
    echo "Applied isolated RPi5 Wi-Fi direct-SDIO NDIS patch"
else
    echo "Direct-SDIO Wi-Fi patch does not apply to pinned edk2-platforms" >&2
    git -C "${WORKSPACE}/edk2-platforms" apply --check --verbose "${WIFI_PATCH}" >&2 || true
    exit 1
fi

exec_status=0
"${WORKSPACE}/build.sh" "$@" || exec_status=$?
exit "${exec_status}"
