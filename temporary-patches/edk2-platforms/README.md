# Temporary edk2-platforms patches

`0001-RPi5-add-fail-safe-fan-control-and-ACPI-interface.patch` keeps the
experimental Raspberry Pi 5 fan work separate from the upstream submodule.
`build.sh` applies it only for model 5 and restores a clean submodule after the
build. This makes future rebases and Windows driver development independent of
unrelated platform code.

`0003-RPi5-Windows-fan-safe-handoff-and-mailbox-routing.patch` is the current
Windows handoff layer. On the exp.5A branch it keeps the 100% ExitBootServices
fan fail-safe but intentionally removes the BCM2712 property-mailbox resource
from `FAN0`. Windows therefore sees only the four RP1 fan-control resources
(clocks, PWM1, GPIO bank 2, and pads bank 2). This is an isolation test for the
observed Code 12 / `STATUS_CONFLICTING_ADDRESSES` failure; temperature/mailbox
access is deliberately deferred to a separate provider design after FAN0 can
reach a non-resource-conflict state.

The patch is experimental and must be physically tested before it becomes a
wizard default.
