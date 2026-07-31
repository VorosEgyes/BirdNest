# BirdNest v0.1.3 — Release Notes

**Release tag:** `v0.1.3`
**Release date:** 2026-07-31
**Branch:** `release/v0.1.3-ota-code-fixes`
**Status:** Approved (Miklós, 2026-07-31)

This is the first formal OTA release of BirdNest. It is inspired by
the RaisedGarden OTA design and follows the same GitHub release /
SHA256 manifests / Telegram+MQTT control surface, but it is now
authored on the BirdNest repository and includes the v0.1.3 swarm
review fixes.

## What's new

### Anti-bricking foundation

- **Bootloader rollback enabled** — `sdkconfig.defaults` now sets
  `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y`. The bootloader will roll
  back to the previous image if the freshly installed one fails to
  mark itself valid within the IDF timeout. This is the first layer
  of the §8.2 safety story; the app-level `ghOtaConfirmHealthIfPending`
  remains the second layer.
- **Boot order stabilized** — `ghOtaInit`, `ghOtaConfirmHealthIfPending`,
  and the auto-check/install block now run **after** `telegramInit`
  and `mqttInit` in `setup()`. Previously the OTA confirm fired
  before the Telegram/MQTT clients were initialized, so the
  `health_confirmed` / `health_confirmed_degraded` events could be
  silently dropped. The §11 MQTT delivery promise now holds.
- **Battery 0-bypass fail-safe** — a non-positive battery reading
  (broken ADC, disconnected voltage divider, miscalibrated sensor)
  now **blocks** the install with a new `battery_unknown` reason.
  The previous code accepted ≤ 0.0 V as "battery is fine", which could
  brick the device mid-flash on a dying battery.

### OTA control surface

- **Telegram token failure now deletes the message** — when
  `/otatoken_set <token>` is rejected (token length not in 10..200),
  the operator's message is still removed from chat history via
  `deleteMessage`, and the response surfaces the actual length
  (`Token rejected: must be 10..200 chars (got 9)`). Previously a
  rejected token stayed in chat history forever.
- **`/reset_config` now erases the OTA NVS namespace** — a new
  `ghOtaResetAll()` API deletes every key under the `birdnest_gh`
  namespace (the GitHub token, the pending target, the last reason).
  This is critical if the device is sold or recycled.
- **`0.0.0-dev` local builds require an explicit flag** — local builds
  (no tag) report `FW_VERSION=0.0.0-dev` and would otherwise look like
  an outdated release against any tagged version. `/otastatus` now
  surfaces a `local_build: true` field, and `/otaupdate_check` and
  `/otaupdate_now` require an explicit `--allow-local-build` flag to
  run.

### SemVer parser refactor (S1-S7)

The `parseSemVer` / `comparePrerelease` / `semVerCompare` helpers
were refactored to follow SemVer 2.0.0 strictly:

- `+build` metadata is now stripped before parse (S1).
- Numeric identifiers are validated `[0-9]+` with no leading zeros
  (except for the single `0`) (S2).
- Numeric vs alphanumeric classification is strict (S3).
- Empty/leading-dot prerelease fields are rejected (S4).
- Two invalid versions no longer compare equal (lex fallback) (S5).
- `vv` prefix is rejected (S6).
- Lex comparison is documented to match §11 (S7).

A new `battery_unknown` reason code is added; the full 25-row
operator-view table is in `OTA_Design.md` §10.2.1.

### Documentation

- **New `docs/OTA_Design.md`** — the full design document, now
  BirdNest-native. Includes the manifest-MITM threat model (C-4), the
  `dashboard` for the §10.2.1 reason codes, the /otachannel inline
  argument form, the §9 NVS table plus the three keys that were
  missing (`otaWifiOk`, `otaRebootFlg`, `otaLastTgt`), the §11 8-field
  MQTT payload schema, and the §14 API surface with the
  `manualOverride` parameter.
- **New `docs/RELEASE.md`** — the operational playbook for cutting
  future BirdNest releases and rolling them out to a 4-camera fleet.
  Includes pre-release checklist, tag & release sequence, fleet
  rollout procedure (cam1 pilot → cam2-4 expand → auto-update
  re-enable), and rollback plan.
- **Auto-update default OFF reminder** — a `> Note` block in §10.1
  and a new §10.2.2 explicitly state that a release does NOT trigger
  auto-rollout. The operator must enable auto-update per camera.

## Known limitations (deferred to v0.1.4)

- **No `/otarollback` command** — runtime rollback still requires
  LAN-side `pio run -e camN_ota` or serial flash. The command is
  planned for v0.1.4. Until then, the bootloader rollback (C-1) is
  the only safety net for runtime bad images.
- **No CA-bundle / strict TLS** — GitHub endpoints are still reached
  via `WiFiClientSecure::setInsecure()`. The manifest-MITM threat
  is acknowledged (C-4) but accepted for V1.
- **RSSI threshold is dead code** — the install gate does not check
  RSSI in the current code path. The `GH_OTA_WIFI_STABLE_RSSI_MIN`
  constant is still defined and surfaced via `/netdiag`, but it is
  not enforced. Whether to revive it is open.
- **Low-severity cleanup** — 12 low-severity findings (L-1..L-12)
  from the swarm review are not addressed in v0.1.3 and will be
  reviewed for v0.1.4.

## Upgrade notes

For existing BirdNest devices on a pre-v0.1.3 firmware:

1. The `birdnest_gh` NVS namespace is preserved. Existing
   `otaToken`, `otaAuto`, `otaChannel`, etc. survive the upgrade.
2. The `v0.1.3` release asset is `birdnest-esp32cam-v0.1.3.bin`.
   The first install will set `FW_VERSION=v0.1.3` (no `v` prefix in
   the build flag).
3. Auto-update stays OFF after the upgrade. The operator must run
   `/otaupdate_auto_on` per camera after the pilot cycle.
4. After upgrading, run `/otastatus` and confirm the
   `local_build: false` and `current_version: v0.1.3` fields are
   present. Spot-check the `manual_override` behavior with
   `/otaupdate_check` (no need to install).

## Fleet rollout

Follow `docs/RELEASE.md` §3. Pilot on `cam1` for 24 hours, then
expand to `cam2`/`cam3`/`cam4`, then re-enable auto-update after
48 hours of stable operation.

## References

- `docs/OTA_Design.md` — the design document.
- `docs/RELEASE.md` — the rollout playbook.
- [Swarm review report](../../../../Shared/outbox/reports/Alfred_review_OTA_Design_v2_swarm.md)
  — the consolidated 29-finding review.
