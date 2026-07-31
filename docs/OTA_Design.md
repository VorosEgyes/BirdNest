# BirdNest OTA Update Design

## 1. Purpose

This document defines a robust, fail-safe OTA strategy for BirdNest that can:

1. Check GitHub for newer firmware.
2. Respect battery and maintenance safety limits.
3. Update automatically or manually (runtime configurable).
4. Recover safely if an update fails (rollback).
5. Work with private repositories now and public repositories later.

This design extends the existing local network OTA path and does not remove current behavior.

## 2. Current Baseline (Already in Project)

Current firmware already has:

1. Local ArduinoOTA support with startup window and recovery behavior.
2. Telegram command handling and runtime config persisted in NVS.
3. MQTT status/event publishing.
4. Deep sleep and maintenance mode logic.
5. Battery voltage measurement and alerting.

Relevant files:

- [src/ota.cpp](src/ota.cpp)
- [include/ota.h](include/ota.h)
- [src/main.cpp](src/main.cpp)
- [src/telegram.cpp](src/telegram.cpp)
- [src/mqtt_client.cpp](src/mqtt_client.cpp)
- [include/config.h](include/config.h)

### 2.1 Existing Symbols Referenced by This Design (verified snapshot)

The symbols below are verified against the current repository snapshot and are normative for this design. If any of these signatures change in code later, update this section first, then update all dependent sections.

| Symbol | Verified signature | File | Status |
|---|---|---|---|
| `wifiInit()` | `bool wifiInit()` | [include/wifi_manager.h](include/wifi_manager.h) | verified |
| `telegramInit()` | `void telegramInit()` | [include/telegram.h](include/telegram.h) | verified |
| `telegramSendDebug(msg, level)` | `bool telegramSendDebug(const String& message, uint8_t level = 1)` | [include/telegram.h](include/telegram.h) | verified |
| `syncTimeIfNeeded()` | `static bool syncTimeIfNeeded()` | [src/main.cpp](src/main.cpp) | verified |
| `formatNextWakeTime()` guard | `if (now <= 100000) return "unknown";` | [src/main.cpp](src/main.cpp) | verified |
| `otaArmed`, `otaCycles` | existing NVS keys, <=15 chars | [src/ota.cpp](src/ota.cpp) | verified (naming precedent only) |
| `s_client.setInsecure()` | existing `WiFiClientSecure` instance (`s_client`) | [src/telegram.cpp](src/telegram.cpp) | verified |

### 2.2 Logging Convention for New Code

`telegramSendDebug` level semantics are already defined in [include/telegram.h](include/telegram.h): `0` = minimal, `1` = normal, `2` = verbose. The new `gh_ota.cpp` module (section 14, Phase 1) must reuse this convention exactly and must not define a separate OTA-only level mapping.

## 3. Target Outcomes

### 3.1 Functional Goals

1. Firmware versioning with Semantic Versioning (SemVer).
2. GitHub release check at wake-up (with once-per-day policy for auto checks).
3. Channel selection: stable or beta.
4. Auto-update toggle: ON/OFF at runtime.
5. Manual commands to check and update immediately.
6. Silent retry policy with capped attempts.
7. Robust rollback and health confirmation after update.

### 3.2 Safety Goals

1. OTA **install** gate is battery + connectivity based; maintenance mode is informational in current implementation and does not hard-block GitHub OTA install.
2. Never start OTA **install** when battery is below 3.60 V.
3. Avoid aggressive network retries to protect battery.
4. Prefer fail-safe behavior over update aggressiveness.
5. Remote **check** (status query only) is allowed regardless of battery level — it costs a few KB over HTTPS and diagnostic visibility into "is an update available" must not depend on having enough battery to install it.

### 3.3 Operational Goals

1. Support private GitHub repo via token now.
2. Allow seamless transition to public repo later.
3. Keep all control and diagnostics available via Telegram and MQTT.
4. Never transmit the GitHub token in plaintext over Telegram chat history.

## 4. Non-Goals (V1)

1. Delta/binary patch updates.
2. Cryptographic signature framework beyond HTTPS + hash validation.
3. Fleet orchestration or staged rollout service.

## 5. Firmware/Release Contract

To make device-side OTA reliable, releases must follow a strict contract.

### 5.1 Version Rules

1. Firmware defines a current version string (for example: 1.2.3).
2. GitHub release tag format: vMAJOR.MINOR.PATCH, optionally with a prerelease suffix (vMAJOR.MINOR.PATCH-beta.N).
3. Device compares remote version against local SemVer using full SemVer precedence rules (see 5.5).

#### 5.1.1 Single Source of Version Truth

The local version string is the **basis of every comparison in 5.5**, so it must not drift from the git tag. There is currently no `FW_VERSION` defined anywhere in the codebase (no build flag, no `config.h` constant). To avoid the build-flag-vs-git-tag mismatch:

1. The CI pipeline (section 13) injects the version from the pushed git tag as a build flag, e.g. `-D FW_VERSION="1.2.3"` (the `v` prefix is optional; `parseSemVer` strips a single leading `v` per SemVer 2.0.0 §2, see swarm review M-3 and M-2 S6), derived from the `v*` tag that triggered the build.
2. `config.h` provides only a fallback default (e.g. `0.0.0-dev`) for local/manual builds that are not tag-driven, so non-release builds never claim a real release version and never appear "up to date" against a real release.
3. The device reports this exact string in `/otastatus` and in MQTT `current_version`.

### 5.2 Channel Rules

1. Stable channel accepts non-prerelease releases only.
2. Beta channel accepts prerelease releases.

### 5.3 Release Assets

Each release should include:

1. Board-specific binary.
2. OTA manifest JSON.

Recommended names:

1. birdnest-esp32cam-v0.1.3.bin
2. birdnest-esp32cam-v0.1.4-beta.1.bin
3. ota-manifest.json

### 5.4 Manifest Schema (V1)

Example fields:

1. version
2. channel
3. board
4. bin_asset_name
5. sha256
6. min_battery_v

Notes:

1. board supports future multi-hardware variants.
2. sha256 is mandatory before flashing.
3. `min_battery_v` is optional and **per-release advisory** (some builds may need a healthier battery to flash safely). When present, the effective install threshold is `max(min_battery_v, 3.60 V)` — the firmware's fixed 3.60 V floor (3.2/6.2) is a hard minimum that a manifest can raise but never lower. This keeps the device conservative and prevents a malformed or over-optimistic manifest from authorizing an install below the safe floor. The firmware-side floor remains independent of the (currently commented-out) `BATTERY_LOW_ALERT_V` alerting threshold in `platformio.ini`; the OTA floor is intentionally a separate, stricter constant.

### 5.5 SemVer Precedence and the Equal-Core-Version Case

This is an explicit rule because it is easy to get wrong and cause an update loop when switching channels.

Per SemVer spec, a prerelease version has **lower** precedence than the associated normal version:

```
1.3.0-beta.1 < 1.3.0
```

Decision rule when comparing remote vs local:

1. Compare MAJOR.MINOR.PATCH numerically first.
   - If remote core > local core → update available.
   - If remote core < local core → no update (never silently downgrade).
2. If remote core == local core:
   - If remote has no prerelease tag and local has one → update available (promotion from beta to matching stable).
   - If remote has a prerelease tag and local has none → **no update** (this would be a downgrade from stable to beta with the same core version).
   - If both have prerelease tags → compare prerelease identifiers per SemVer rules (numeric fields compared numerically, else lexically); higher precedence wins.
   - If both have no prerelease tag and are otherwise identical → no update.

This rule prevents the device from oscillating between "update available" states purely because of a channel switch with no real new build.

### 5.6 Device-Side GitHub Fetch Contract (concrete)

This section removes the guesswork an implementer would otherwise face. All values below are explicit.

#### 5.6.1 Repository Configuration

Owner/repo are **not** hardcoded in OTA logic; they come from build flags so the public/private transition needs no code change:

```ini
build_flags =
    '-D OTA_GH_OWNER="your-user"'
    '-D OTA_GH_REPO="VorosEgyes/BirdNest"'
    '-D OTA_GH_API_HOST="api.github.com"'
```

#### 5.6.2 Endpoints and Headers

1. **List releases:** `GET https://api.github.com/repos/{OTA_GH_OWNER}/{OTA_GH_REPO}/releases`
   - Use the releases list (not `/releases/latest`) so the beta channel can see prereleases; `/latest` excludes prereleases.
2. **Required headers on every GitHub API call:**
   - `Accept: application/vnd.github+json`
   - `User-Agent: BirdNest-OTA` — **mandatory**; GitHub rejects requests without a User-Agent.
   - `X-GitHub-Api-Version: 2022-11-28`
   - If token present: `Authorization: Bearer <token>` (omit entirely for public/anonymous).
3. **Asset download (the redirect/private pitfall — see 8.1.1):**
   - Public repo: `assets[].browser_download_url` works anonymously but **redirects** to `objects.githubusercontent.com`.
   - Private repo: do **not** use `browser_download_url`. Call the asset API URL `assets[].url` with header `Accept: application/octet-stream` plus the `Authorization` header; GitHub returns a redirect to a signed object URL.
   - In both cases the HTTP client must **follow redirects** across hosts.

#### 5.6.3 Check/Download Sequence

1. `GET /releases` → parse JSON array (ArduinoJson, already a dependency; use a filter/streaming parse — release lists are large and will not fit a single in-RAM document otherwise).
2. Apply channel filter (5.2) and SemVer precedence (5.5) to pick the best candidate.
3. From the chosen release, locate the `ota-manifest.json` asset and the board `.bin` asset by name (5.3).
4. **FetchManifest** (6.1 step 5): download `ota-manifest.json` (same redirect/auth rules as 5.6.2). Do not touch the `.bin` asset yet.
5. **InstallEligibilityCheck** (6.1 step 6 / Install Gate, 6.2) using `manifest.min_battery_v` (5.4). Current implementation gate checks battery and Wi-Fi stability (maintenance mode does not block install).
6. **DownloadAndVerifyBinary** (6.1 step 7): stream the `.bin` via `esp_http_client` + `esp_ota_write`, verifying `manifest.sha256` incrementally (8.1.1).

JSON memory note: the releases response can be hundreds of KB. Use ArduinoJson's `DeserializationOption::Filter` or parse from the `WiFiClientSecure` stream — do **not** read the whole body into a `String` first.

## 6. Runtime Decision Model

The OTA flow runs as a state machine.

### 6.1 States

1. Idle
2. EligibilityCheck (Check Gate, per 6.2)
3. CheckRemote
4. UpdateAvailable
5. FetchManifest — download `ota-manifest.json` only (5.6.3 step 4); no binary bytes move yet.
6. InstallEligibilityCheck (Install Gate, per 6.2) — evaluated using `manifest.min_battery_v` from step 5. This is a hard sequencing requirement, not just an ordering suggestion: steps 5 and 6 must not be collapsed into "DownloadAndVerify" as a single atomic step, or an implementer following this list literally could end up downloading and flashing the firmware binary *before* checking battery/Wi-Fi gate state.
7. DownloadAndVerifyBinary — only entered if step 6 passes; streams the `.bin` and verifies SHA256 (8.1.1).
8. Install
9. RebootPending
10. PostBootHealthCheck
11. Confirmed
12. Rollback (bootloader-managed path; currently not forced by health-probe failure in `ghOtaConfirmHealthIfPending()`)

### 6.2 Eligibility Gates (split by purpose)

OTA eligibility is split into two separate gates so that status checks remain available even when the device cannot safely install an update yet. Conflating these into a single gate (checked before 6.2 in the original design) blocks diagnostics exactly when they are most useful — e.g. you want to know an update exists even if the battery is currently too low to install it.

**Check Gate** (must all pass before CheckRemote):

1. Wi-Fi connected.
2. Wi-Fi stable per 6.3.
3. Backoff timer expired (auto mode only).
4. For auto mode: daily check interval reached.

Manual `/otaupdate_check` is explicitly diagnostic and bypasses item 2, item 3 and item 4 in current implementation; it still requires Wi-Fi connected (item 1).

**Install Gate** (must all pass before DownloadAndVerifyBinary, evaluated only after FetchManifest — see 6.1 steps 5–7):

1. Battery >= effective install threshold, i.e. `max(3.60 V, manifest.min_battery_v)` per 5.4. The 3.60 V firmware floor is a hard minimum a manifest can raise but never lower.
2. Wi-Fi still stable per 6.3, except manual `/otaupdate_now` currently passes `manualOverride=true` to install and bypasses Wi-Fi stability gating.
3. Maintenance mode currently does not block install; it is logged as informational.

If the Check Gate passes and an update is found but the Install Gate fails, the device keeps `otaTarget` pending and retries install eligibility on next wake when auto mode is enabled.

### 6.3 Wi-Fi Stability Definition

For this project, treat Wi-Fi as stable if:

1. Wi-Fi status is connected.
2. RSSI threshold (`GH_OTA_WIFI_STABLE_RSSI_MIN`, default `-85 dBm`) is **defined but not currently enforced** — the install/check gates solely on the `ghOtaHealthProbe()` HTTPS reachability. The RSSI value is still surfaced via `/netdiag` for the operator. See swarm review M-1 (v0.1.3).
3. A short HTTPS request to GitHub API succeeds — concretely, `GET https://api.github.com/rate_limit` with the standard headers from 5.6.2 (minus `Authorization` if no token), with timeout from `GH_OTA_HTTP_TIMEOUT_MS` (current build default: `12000 ms`). This endpoint is used specifically because it is cheap, does not count meaningfully against API rate limits, and requires no repo-specific parameters — it is purely a reachability probe, not a real check. This is the exact implementation of `ghOtaHealthProbe()` (14, Phase 1 Module API), reused unchanged by both 6.3 and the post-boot health confirmation in 8.3.

If unstable:

1. Do not start update (check or install).
2. Increment retry/backoff counters silently — but only the **Wi-Fi-stability-related** counter (see 7.3), not the general fail streak.

## 7. Retry and Backoff Policy

### 7.1 Per Wake Cycle

1. Maximum `GH_OTA_MAX_CHECK_ATTEMPTS` remote check attempts (current build default: 4).
2. Short delay between attempts.

### 7.2 Persistent Backoff

On repeated failures:

1. 6 hours
2. 12 hours
3. 24 hours
4. 48 hours max cap

Add small random jitter to avoid synchronized retries.

### 7.3 Backoff Reset Conditions (corrected)

The original "reset on any successful check" rule is too lenient: a network that is unstable often enough to fail every other day would never accumulate meaningful backoff, defeating the purpose of protecting battery on bad Wi-Fi.

Track two independent signals:

1. `wifiStabilityFailStreak` — incremented whenever 6.3 fails. Reset only after **N consecutive** wake cycles (suggested N = 2) where Wi-Fi was stable, not after a single good cycle.
2. `otaCheckFailStreak` — incremented on HTTP/parse failure during CheckRemote despite stable Wi-Fi (e.g. GitHub API error, malformed manifest). Reset immediately on a single successful parse, since this reflects remote-side issues, not local network flakiness.

Backoff duration (6h/12h/24h/48h) escalates based on `wifiStabilityFailStreak`, since that is the dominant real-world failure mode for a battery device on a weak signal.

### 7.4 Time/NTP Gate (epoch correctness)

All backoff and daily-check logic is epoch-based (`otaLastChk`, `otaBackoff` per section 9), but on this device the clock is only valid after NTP sync, which happens **after** wake via `syncTimeIfNeeded()` ([src/main.cpp](src/main.cpp)). Implementation rules to avoid acting on a bogus clock:

1. Evaluate the Check Gate's daily-interval and backoff-timer conditions **only after** `syncTimeIfNeeded()` returns true.
2. If time is not synced (`time(nullptr)` returns an implausibly small value, e.g. `<= 100000`, matching the existing guard in `formatNextWakeTime()`), treat the daily-check and backoff timers as **not yet evaluable**: skip auto mode checks this wake rather than fail-open and check every wake. Manual `/otaupdate_check` still proceeds (by design it bypasses daily interval and backoff timing), but should include an explicit warning that timer-based gating could not be evaluated due to unsynced time.
3. "Wake cycle" = one `setup()` run between deep-sleep periods. The "max 3 attempts per wake cycle" (7.1) is bounded within a single `setup()`, not across sleeps.

## 8. Rollback and Health Confirmation

This is mandatory due to difficult physical access.

### 8.1 OTA Install

1. Download binary over HTTPS.
2. Validate expected size (if available).
3. Validate SHA256 against manifest.
4. Flash update partition via ESP-IDF OTA ops (`esp_ota_begin`/`esp_ota_write`/`esp_ota_end`) over an `esp_http_client` stream.
5. Reboot.

**Install path is native ESP-IDF OTA ops, not Arduino `Update`.** The rollback behavior in 8.2 depends on writing through the IDF OTA ops layer that maintains partition-table boot state (`esp_ota_set_boot_partition` + pending-verify marking). The existing `ArduinoOTA` flow in [src/ota.cpp](src/ota.cpp) is a **separate, retained** path used only for the local-network recovery window; the GitHub-OTA path described here uses `esp_http_client` download + `esp_ota_*` write/finalize and must not be mixed with the Arduino `Update` API for the install step. Both paths coexist:

- Local `ArduinoOTA` window: unchanged, manual LAN recovery.
- GitHub `esp_http_client` + `esp_ota_*` path: versioned, battery-aware, rollback-protected.

#### 8.1.1 Redirect Following and SHA256 Verification

Two concrete implementation requirements that are easy to get wrong:

1. **Cross-host redirect following is mandatory.** GitHub asset URLs (both `browser_download_url` and the private-repo asset API URL) redirect to a different host (`objects.githubusercontent.com` / signed object storage). Configure `esp_http_client` to follow redirects (e.g. `disable_auto_redirect = false`; handle redirects per client behavior). A client that does not follow redirects will appear to "download 0 bytes" and fail opaquely.

2. **SHA256 verification strategy.** The OTA path streams data directly into flash, so the manifest `sha256` cannot be verified from a separate full in-RAM copy. V1 contract: compute SHA256 incrementally over the same chunks read from `esp_http_client_read()` and written by `esp_ota_write()`, then compare to `manifest.sha256` before `esp_ota_end()`. Abort on mismatch (do not finalize).

#### 8.1.2 Behavior on Interrupted Download (covers Field Safety Test 16.3 #1)

This is the specification the field-safety test in 16.3 is validating against — it must be implemented, not just tested for:

1. If the Wi-Fi connection drops mid-download, `esp_http_client_read()` / transport returns an error. Treat this identically to a SHA256 mismatch: call `esp_ota_abort()` (do **not** call `esp_ota_end()`), which discards the partially-written update partition without altering the active boot partition.
2. The currently running partition is unaffected — the device continues operating on the firmware it booted with. No reboot is triggered by a failed download.
3. Publish `ota_update_fail` over MQTT (11) with a reason code distinguishing "network interrupted" from "hash mismatch" from "size mismatch", so the three failure modes in 8.1 steps 2–3 and this section are distinguishable in logs.
4. `otaTargetVersion` (9, NVS key `otaTarget`) is **not cleared** on this failure path — the device should retry the Install Gate on the next eligible wake, going through the normal backoff policy (7) rather than abandoning the known-available update.
5. This failure path does not increment `otaWifiFail` / `otaChkFail` (7.3) — those track Check Gate / remote-check reachability, not mid-install failures, which are a distinct failure class with its own (implicit, via 7's wake-cycle cadence) retry cadence.

### 8.2 Native ESP-IDF Rollback as the Safety Foundation

The original design proposed a custom NVS-flag-based `otaPendingVerify` state to gate rollback. This is risky as the *sole* mechanism: if power is lost or the device crashes before the custom flag is cleared, and that flag-clearing logic is itself what triggers the rollback check, the rollback can silently never fire.

Instead, use the ESP-IDF bootloader's native app rollback support as the foundation, and layer the custom health check on top of it — not instead of it. The bootloader-level mechanism survives power loss because the "pending verify" state lives in the OTA partition table itself, not in application-level NVS.

#### 8.2.1 Required Preconditions (do not skip)

Native rollback has two hard prerequisites that are easy to omit and would cause the rollback to silently never engage — the exact failure mode 8.2 is trying to prevent:

1. **Dual app partitions.** A/B rollback requires a partition table with two OTA app slots (`ota_0` / `ota_1`) plus an `otadata` partition. The default single-app layout cannot roll back. The `esp32-c3-devkitm-1` board has 4 MB flash, verified sufficient for dual-OTA:

   **Verified 4 MB layout (current fw ~1.1 MB, 876 KB margin per slot):**
   - nvs: 0x9000–0xe000 (20 KB)
   - otadata: 0xe000–0x10000 (8 KB)
   - ota_0: 0x10000–0x200000 (1.96 MB)
   - ota_1: 0x200000–0x3f0000 (1.96 MB)
   - Reserved: 0x3f0000–0x400000 (64 KB)

   V1 uses `partitions_ota_4m.csv` (in repo):

   ```ini
   board_build.partitions = partitions_ota_4m.csv
   ```

   **Post-update verification:**
   1. `/otastatus` → confirm `current_version` matches new tag
   2. MQTT: `ota_update_ok` event published
   3. Sleep cycle (`/sleep_min 1`) → confirm normal wake (no re-entry to pending-verify)

2. **Bootloader rollback enabled in sdkconfig, verified.** Under the Arduino framework, ESP-IDF Kconfig options are **not** reliably applied by a plain `-D` build flag — they live in `sdkconfig`. Setting only `-DCONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=1` may compile cleanly yet leave the bootloader feature off, so rollback silently does nothing. Apply it through an sdkconfig override mechanism that the build actually consumes — V1 uses `sdkconfig.defaults` (in repo) with `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y`. The PlatformIO build pipeline automatically merges this into the effective sdkconfig before compiling the bootloader.

   **Verification:**
   - At build time: `pio run` output shows no errors; `sdkconfig` file generated (in `.pio/build/release/`) includes `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y` (check via `grep CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE .pio/build/release/sdkconfig`).
   - At runtime (post-OTA, during first boot after update): Call `esp_ota_get_state_partition()` and confirm it returns `ESP_OTA_IMG_PENDING_VERIFY` if the update succeeded; this is the only definitive proof the feature is live. Implement this in the health confirmation phase (8.3) where it will be checked, not in a separate unit test.

### 8.3 First Boot After OTA

This runs inside `setup()` **after** the existing `wifiInit()` and `telegramInit()` calls (see 15.1), because the health check needs Wi-Fi and Telegram already up. It must not be placed "before anything else" — it depends on the normal connectivity bring-up that the existing boot sequence already performs.

The code uses only symbols that exist in this codebase: `wifiInit()` returns `bool` ([include/wifi_manager.h](include/wifi_manager.h)), `telegramInit()` returns `void` ([include/telegram.h](include/telegram.h)) so its success is inferred from `WiFi.status()` plus a successful health probe, not from a return value (there is no `waitForWifiConnect()` / `bool telegramInit()` in this project — do not invent them).

Current implementation behavior in `ghOtaConfirmHealthIfPending()` ([src/gh_ota.cpp](src/gh_ota.cpp)):

1. If running image state is not `ESP_OTA_IMG_PENDING_VERIFY`, do nothing.
2. Run up to 3 health probe attempts with 2 s delay between attempts.
3. Call `esp_ota_mark_app_valid_cancel_rollback()` regardless of probe outcome.
4. If probe succeeded: publish `ota_update_ok` with `health_confirmed`.
5. If probe failed: still publish `ota_update_ok` with `health_confirmed_degraded` and additionally `ota_check_fail` with `health_probe_failed`.

This is an explicit anti-bricking tradeoff in current firmware: unstable internet during first boot after OTA must not force rollback.

### 8.4 Relationship to Deep Sleep

The health-confirmation path in 8.3 forces a blocking Wi-Fi + Telegram init at boot, which would be costly to run on every `DEEP_SLEEP_SEC` wake on a battery device. It does **not** run on every wake: the gate is `ota_state == ESP_OTA_IMG_PENDING_VERIFY`, which the bootloader sets **only** on the first boot of a freshly flashed image and clears once `esp_ota_mark_app_valid_cancel_rollback()` runs. On all subsequent normal wake cycles the partition is already `ESP_OTA_IMG_VALID`, the block is skipped entirely, and the standard low-power wake path proceeds unchanged. The confirmation cost is therefore paid exactly once per successful update, not per sleep cycle, and never conflicts with the deep-sleep/maintenance logic.

## 9. Runtime Configuration and NVS Keys

Suggested NVS keys (namespace raised_garden).

**Hard constraint: ESP32 NVS keys are limited to 15 characters and are silently truncated beyond that.** The descriptive names from the original draft (e.g. `otaWifiStabilityFailStreak`) exceed this and would collide or fail. Use the short keys below; the descriptive names are kept only as comments for readability. This matches the existing convention in the codebase (`otaArmed`, `otaCycles` in [src/ota.cpp](src/ota.cpp)).

| NVS key (<=15 chars) | Type | Meaning |
|----------------------|------|---------|
| `otaAuto` | bool | auto-update on/off |
| `otaChannel` | string | `stable` or `beta` |
| `otaToken` | string | GitHub token, empty if public — see 12.4 |
| `otaLastChk` | uint32 | last check epoch (otaLastCheckEpoch) |
| `otaWifiFail` | uint16 | wifiStabilityFailStreak |
| `otaChkFail` | uint16 | otaCheckFailStreak |
| `otaBackoff` | uint32 | otaBackoffUntilEpoch |
| `otaTarget` | string | target version when Install Gate not yet passed |
| `otaLastReason` | string | last OTA blocked/fail reason code for diagnostics (for example `battery_low`) |

Note: `otaPendingVerify` is intentionally **not** a custom NVS key — that state is owned by the ESP-IDF OTA partition table per 8.2, to avoid the dual-source-of-truth problem from the original design.

### 9.1 Default Values on First Boot / Missing Key

`ghOtaInit()` (14, Phase 1 Module API) must handle every key above being **absent** — this is the normal state on first boot of this feature, and `nvs_get_*` returns `ESP_ERR_NVS_NOT_FOUND` rather than a zeroed value in that case. Treat a not-found result as the default below, not as an error to surface to the user:

| NVS key | Default if missing |
|---|---|
| `otaAuto` | `false` — auto-update must be an explicit opt-in, never silently on after a flash/upgrade |
| `otaChannel` | `"stable"` |
| `otaToken` | `""` (empty — treated as public/anonymous per 5.6.2) |
| `otaLastChk` | `0` |
| `otaWifiFail` | `0` |
| `otaChkFail` | `0` |
| `otaBackoff` | `0` (no backoff in effect) |
| `otaTarget` | `""` (no install pending) |
| `otaLastReason` | `""` (no last block/fail reason recorded yet) |

`ghOtaInit()` should write these defaults back to NVS on first encounter (rather than re-deriving them from "not found" on every boot), mirroring the existing pattern used for `otaArmed`/`otaCycles` in [src/ota.cpp](src/ota.cpp) — verify that pattern (2.1) and follow it rather than introducing a second initialization style.

## 10. Telegram Command Set

### 10.1 Control Commands

1. /otaupdate_check
2. /otaupdate_now
3. /otaupdate_auto_on   *(default OFF — see 10.2.2; the operator must explicitly enable auto-update)*
4. /otaupdate_auto_off
5. /otachannel stable
6. /otachannel beta
7. /otatoken_set <token>
8. /otatoken_clear
9. /otastatus

> **Note (v0.1.3):** auto-update is **OFF by default**. A release cut does NOT trigger auto-rollout; the operator must run `/otaupdate_auto_on` per camera (see `docs/RELEASE.md` §3 stage 3). The same note is rendered at the top of the `/status` JSON output and at the bottom of the `/help` text.

### 10.2 Expected Behavior

1. Check command: runs Check Gate + CheckRemote only, reports result regardless of battery level.
   - Deterministic override rule: manual `/otaupdate_check` calls `ghOtaCheckForUpdate(..., true)` and bypasses time/backoff and Wi-Fi stability gating, but still requires Wi-Fi connected.
2. Update now: uses the same manual check override and then calls `ghOtaInstall(..., true)`, which also bypasses install-time Wi-Fi stability gating. Battery threshold and private-token rules remain enforced.
   - If install does not start or is blocked, command response includes an immediate `reason=<code>` line (for example `reason=battery_low`) from OTA state.
3. Channel command: persists to NVS.
4. Token commands: see 12.4 — token must not remain in plaintext chat history.
5. Status command: returns local version, channel, auto mode, last check, both fail streaks, backoff info, and pending/install diagnostics.
   - `pending_target`: pending target version or null.
   - `pending_reason`: pending reason if present; otherwise fallback to `last_reason`.
   - `last_reason`: last blocked/fail reason persisted independently in NVS (`otaLastReason`) so diagnostics remain available even when `otaTarget` is empty/unreadable.

### 10.2.2 Auto-update default OFF (v0.1.3)

Auto-update is **OFF by default** on every fresh boot, factory reset, and OTA update. The runtime flag `otaAuto` is only set to `true` when the operator explicitly sends `/otaupdate_auto_on`. This is a deliberate safety policy: a release cut on GitHub does NOT silently roll out to the fleet. The operator must:

1. Wait for the `boot` MQTT event on the channel assigned to each camera.
2. Confirm the new `current_version` field via `/otastatus` (or the JSON `current_version` field).
3. Run `/otaupdate_auto_on` on each camera, one at a time, after the pilot cycle (see `docs/RELEASE.md` §3 stage 3).

The `/status` JSON output starts with a `local_build` boolean and includes the `auto` field. The Telegram `/help` text ends with the same explicit reminder. Both are operator-facing guards against the assumption that a tagged release implies auto-distribution.

## 11. MQTT Event Model

Publish OTA lifecycle events to existing event topic family.

Recommended event names:

1. ota_check_start
2. ota_check_no_update
3. ota_update_available
4. ota_install_blocked (battery, Wi-Fi stability, token-related block)
5. ota_update_start
6. ota_update_progress
7. ota_update_ok
8. ota_update_fail

Payload should include:

1. current_version
2. target_version
3. channel
4. reason/result code

### 11.1 Reason Code Contract (Firmware-Synced)

To keep backend automations deterministic, reason codes are fixed string enums.
The current firmware implementation in [src/gh_ota.cpp](src/gh_ota.cpp) uses the
following values:

1. no_update
2. update_found
3. wifi_disconnected
4. wifi_unstable
5. github_releases_http
6. github_releases_parse
7. manifest_http
8. manifest_parse
9. manifest_missing_fields
10. bin_asset_not_found
11. battery_low
12. token_missing_for_private_target
13. no_update_partition
14. manifest_sha256_invalid
15. install_start
16. ota_begin_failed
17. download_network_interrupted
18. flash_write_failed
19. size_mismatch
20. ota_finish_failed
21. sha256_mismatch
22. health_confirmed
23. health_confirmed_degraded
24. health_probe_failed

Event-specific behavior:

1. `ota_update_progress` uses `reason` as the integer percentage string (`"0".."100"`).
2. `ota_install_blocked` and `ota_update_fail` must include `target_version` when known.
3. `ota_check_no_update` sets reason to `no_update` and leaves `target_version` empty.
4. `ota_update_ok` sets reason to `health_confirmed` or `health_confirmed_degraded` and `target_version` to the running firmware version.

### 10.2.1 Reason codes (operator view, v0.1.3)

Human-readable mapping for the operator when a `/otaupdate_check` or
`/otaupdate_now` returns `no_update`, `skipped`, or `failed`. Each reason
code maps to a likely cause and a concrete next action — the operator
should not need to read serial logs or debug chat to know what to do.

| Reason code | Likely cause | Operator action |
|---|---|---|
| `no_update` | Local FW is at or above the latest release on the channel. | None — periodic check is healthy. |
| `update_found` | A newer release is available on the channel. | Run `/otastatus` for the version, then `/otaupdate_now` if battery and connectivity allow. |
| `wifi_disconnected` | WiFi association lost before or during the check. | Check `/netdiag`; if RSSI is low, move the device closer to the AP. |
| `wifi_unstable` | Health probe to `api.github.com` failed; check is skipped. | Run `/netdiag` to see RSSI / reconnect count; retry from `/otaupdate_check` once stable. |
| `github_releases_http` | Non-200 from the GitHub `/releases` endpoint. | Check `https://github.com/VorosEgyes/BirdNest/releases` from a browser; GitHub may be down or rate-limited. |
| `github_releases_parse` | Releases JSON parsed but expected fields are missing. | Open a bug with the response payload; do not retry until the maintainer confirms. |
| `manifest_http` | Manifest endpoint failed (network or non-200). | Check the manifest URL in the release; the asset may have been replaced or removed. |
| `manifest_parse` | Manifest JSON failed to parse. | Same as `github_releases_parse` — escalate. |
| `manifest_missing_fields` | `version`, `binAssetUrl`, or `sha256` missing from the manifest. | Release is malformed; skip this release and wait for a fixed one. |
| `bin_asset_not_found` | The `bin` asset name in the manifest does not match the actual release asset. | Transient during the public-repo transition; wait for the next release or check the `release-ota.yml` workflow. |
| `battery_low` | Battery below the manifest's `min_battery_v` threshold (default 3.60 V). | Wait for sun / charge; the install will retry on the next wake cycle. |
| `battery_unknown` | Battery ADC read returned ≤ 0.0 V (sensor fault, broken divider, miscalibration). | Inspect the battery harness; do not flash until the sensor is fixed. |
| `token_missing_for_private_target` | A private-repo target is pending but no GitHub token is set. | Run `/otatoken_set <token>` and then `/otaupdate_check`. |
| `no_update_partition` | No free `ota_0` / `ota_1` partition found. | Reflash over serial (see `## 17.3`); the partition table is corrupted. |
| `manifest_sha256_invalid` | The `sha256` field in the manifest is not a 64-char hex string. | Release is malformed; skip and escalate. |
| `install_start` | Install starting. (Informational; not a failure.) | None. |
| `ota_begin_failed` | `esp_ota_begin` failed — flash write-protected or invalid state. | Sometimes recoverable on next boot; if persistent, reflash over serial. |
| `download_network_interrupted` | HTTPS stream stalled or dropped. | Check WiFi signal; retry with `/otaupdate_now`. |
| `flash_write_failed` | `esp_ota_write` returned non-OK. | Battery may have died mid-flash; if device boots OK, retry. If bricked, reflash over serial. |
| `size_mismatch` | Downloaded byte count ≠ `Content-Length` from server. | Network glitch; retry. |
| `ota_finish_failed` | `esp_ota_end` or `esp_ota_set_boot_partition` failed. | Often recoverable on next boot; if persistent, reflash over serial. |
| `sha256_mismatch` | Manifest SHA256 does not match the downloaded binary. | Release is malformed or the binary was tampered with; do NOT retry, escalate. |
| `health_confirmed` | Post-install health probe succeeded; image marked valid. (Informational.) | None. |
| `health_confirmed_degraded` | Post-install health probe failed but the image was accepted (anti-bricking policy). | Investigate the runtime issue; the new image is running but may be impaired. |
| `health_probe_failed` | Health probe failed 3 times during `ghOtaConfirmHealthIfPending`. | The new image is still marked valid; investigate runtime. |

## 12. Security Model (Practical for Simple Projects)

1. Use HTTPS for API and binary fetch.
2. For private repo, use GitHub token with minimal scope.
3. For public repo, token can be removed.
4. Validate binary hash (sha256) before install.
5. Keep this simple; no certificate pinning required in V1.

### 12.0 TLS Validation Mode (match project convention)

V1 uses `WiFiClientSecure::setInsecure()` for the GitHub connections, consistent with the existing Telegram client in [src/telegram.cpp](src/telegram.cpp) which already calls `s_client.setInsecure()`. Do **not** introduce a CA-bundle / cert-store mechanism for V1 — it is brittle on this device, inconsistent with the current codebase, and stricter TLS is explicitly deferred (see 18).

**Integrity guarantees (sharpened for v0.1.3):** the SHA256 manifest check (8.1.1) protects **binary integrity given a trusted manifest**. It does NOT protect the manifest or the release-list endpoint: an on-path attacker (compromised router, captive portal, ISP) that can answer the `/releases` API can serve a manifest whose SHA256 matches an attacker-chosen binary, and the device will accept it. The manifest integrity therefore relies on the TLS chain and the absence of an on-path attacker. This is acceptable for V1 (no CA-bundle, see above) but the threat model is acknowledged: a network-level adversary can rewrite the perceived "latest release". Stricter TLS (CA-bundle validation) remains an open decision (18) for later.

### 12.4 Token Handling via Telegram (corrected)

The original design allowed `/otatoken_set <token>` to sit in plain chat history indefinitely — this is worse than the NVS storage trade-off it was trying to accept, since Telegram's servers and the chat log both retain it.

Required behavior for `/otatoken_set`:

1. On receiving `/otatoken_set <token>`, store the token in NVS.
2. Immediately call Telegram `deleteMessage` on the command message itself, removing it from chat history.
3. Reply with a confirmation message that does **not** echo the token back (e.g. "Token saved." with a short masked suffix like `...a1b2` for visual confirmation only).

Required behavior for `/otatoken_clear` when an update is already pending:

1. Clear `otaToken` in NVS.
2. If `otaTarget` is non-empty and was discovered as a private-repo target (`isPrivateRepo == true` in `GhOtaTarget`), immediately invalidate that pending target by clearing `otaTarget` and publish an `ota_install_blocked` / `token_missing_for_private_target` event.
3. Reply that token was cleared and the pending private target was dropped; user must run a fresh `/otaupdate_check`.

This rule is intentional: it avoids non-deterministic install failures where a stale private target remains pending after credentials are removed.

This does not make NVS storage hardware-secure — that limitation remains and is acceptable for this project's threat model — but it removes the strictly worse exposure of the token sitting in Telegram's chat history and servers.

Known remaining technical debt:

1. Token in NVS is not equivalent to hardware-secure key storage (e.g. no secure element).
2. OTA and AP plaintext build flags remain a separate, pre-existing security debt outside this design's scope.

## 13. PlatformIO and Build/Release Pipeline

No release binary is currently published. Add CI to produce OTA artifacts.

### 13.1 CI Objectives

1. Build board firmware for release.
2. Generate versioned binary file name.
3. Compute SHA256.
4. Generate ota-manifest.json.
5. Attach assets to GitHub Release.

### 13.2 Minimum Workflow Steps

1. Trigger on tag push (v*).
2. Inject the version from the triggering tag into the build as `-D FW_VERSION="<tag-without-v>"` (per 5.1.1), so the binary's reported version always matches the release tag.
3. Run PlatformIO build for target environment.
4. Collect firmware binary from build output.
5. Generate manifest.
6. Upload assets to release.

## 14. Implementation Plan (Repository Changes)

### Phase 1: Core OTA Versioning and Check

1. Add firmware version handling: CI-injected `FW_VERSION` build flag plus a `config.h` non-release fallback default (per 5.1.1).
2. Create module:
   - include/gh_ota.h
   - src/gh_ota.cpp
3. Implement:
   - release check
   - channel filter
   - SemVer compare (full precedence rules per 5.5)
   - daily scheduling + split backoff (per 7.3)

#### Phase 1 Module API (suggested public surface for `gh_ota.h`)

Provide a small, explicit surface so the [src/main.cpp](src/main.cpp) call sites are unambiguous (names illustrative, keep the project's existing style):

```cpp
enum class GhOtaCheck { NoUpdate, UpdateAvailable, Skipped, Error };

struct GhOtaTarget {
    String version;        // e.g. "1.3.0" or "1.3.0-beta.1"
    String channel;        // "stable" | "beta"
    String binAssetUrl;    // see isPrivateRepo below for which URL scheme this is
    String sha256;         // from manifest (per 8.1.1)
    float  minBatteryV;    // manifest.min_battery_v, 0 if absent (per 5.4)
    bool   isPrivateRepo;  // true if otaToken (9) was non-empty at fetch time
};

void        ghOtaInit();                              // load NVS config (section 9)

GhOtaCheck  ghOtaCheckForUpdate(GhOtaTarget& out);    // Check Gate + CheckRemote + FetchManifest (6.1 steps 2-5); out is populated with manifest data, no .bin bytes moved yet
bool        ghOtaInstall(const GhOtaTarget& target);  // InstallEligibilityCheck + DownloadAndVerifyBinary + Install via esp_http_client + esp_ota_* (6.1 steps 6-8 / 8.1)
bool        ghOtaHealthProbe();                       // short HTTPS probe (6.3, used by 8.3)
void        ghOtaConfirmHealthIfPending();            // first-boot rollback gate (8.3)
String      ghOtaStatusJson();                        // for /otastatus + MQTT (10.2/11)
```

`binAssetUrl` is ambiguous on its own — 5.6.2 requires two different fetch schemes (different URL field from the GitHub API response, different headers, different `Accept` value) depending on whether the repo is private or public. `isPrivateRepo` is set once, at `FetchManifest` time, based on whether `otaToken` (9) was non-empty for that check, and `ghOtaInstall` must branch on it when fetching `binAssetUrl`:

- `isPrivateRepo == true` → `binAssetUrl` holds the asset API URL (`assets[].url`); request with `Accept: application/octet-stream` plus `Authorization: Bearer <otaToken>`.
- `isPrivateRepo == false` → `binAssetUrl` holds `assets[].browser_download_url`; request anonymously, no `Authorization` header.

Both cases still require following the cross-host redirect per 8.1.1. Do not infer the scheme from whether `otaToken` is currently set in NVS at install time; carry `isPrivateRepo` on `GhOtaTarget` from fetch-time context. If `/otatoken_clear` is executed while a private target is pending, follow the explicit invalidation rule in 12.4 (clear `otaTarget`, publish reason, require fresh check) rather than attempting install with missing credentials.

These map onto the state machine in 6.1, but at coarser granularity: `ghOtaCheckForUpdate` internally covers states 2 through 5 (through FetchManifest) and returns before any Install Gate decision is made, while `ghOtaInstall` covers states 6 through 8 and is the **only** function permitted to perform the binary stream and OTA write/finalize (`esp_ota_begin`/`esp_ota_write`/`esp_ota_end`). An implementer should not collapse these two functions into one — doing so is exactly how the install-before-gate ordering bug (6.1, step 6 note) would be reintroduced at the API level.

### Phase 2: Install and Rollback

1. Keep the GitHub-OTA install step on streamed `esp_http_client` + native `esp_ota_*` (per 8.1), keeping the existing `ArduinoOTA` local recovery path untouched.
2. Partition table already added (`partitions_ota_4m.csv` in repo, `platformio.ini` already configured per 8.2.1). At build time, verify binary stays under 1.5 MB: `pio run` output must show `Flash: [%] (used < 1,536,000 bytes)` to maintain ~460 KB margin per slot.
3. Bootloader rollback already configured in `sdkconfig.defaults` (in repo). Verify at build time: `grep CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE .pio/build/release/sdkconfig | grep -q "=y"` must exit 0. Then implement `ghOtaConfirmHealthIfPending()` in Phase 3 (8.3) to check `esp_ota_get_state_partition()` and confirm `ESP_OTA_IMG_PENDING_VERIFY` at runtime post-OTA.
4. Add the native post-boot health confirmation path in setup (per 8.3), gated on `ESP_OTA_IMG_PENDING_VERIFY` so it runs only once per update and not on every deep-sleep wake (per 8.4).
5. Preserve current health-confirmation policy: on `ESP_OTA_IMG_PENDING_VERIFY`, mark image valid after probe attempts and report degraded health when probe fails, instead of forcing rollback.

### Phase 3: Telegram/MQTT Integration

1. Add OTA commands in [src/telegram.cpp](src/telegram.cpp), including secure token handling per 12.4.
2. Add OTA event publishing helper in [src/mqtt_client.cpp](src/mqtt_client.cpp), including `ota_install_blocked`.
3. Extend /status output with OTA fields including pending-install-blocked state.

### Phase 4: CI Release Pipeline

1. Add GitHub Actions workflow file.
2. Produce release assets + manifest.
3. Document release procedure.

## 15. Integration Points in Existing Code

### 15.1 Boot Sequence

In [src/main.cpp](src/main.cpp):

1. Keep existing local OTA startup window and recovery behavior.
2. After Wi-Fi (`wifiInit()`) and Telegram (`telegramInit()`) init and `syncTimeIfNeeded()`, run native rollback health confirmation (8.3) if `ESP_OTA_IMG_PENDING_VERIFY` — it needs connectivity, so it cannot literally run "before anything else"; it runs before the *normal OTA check*, not before bring-up.
3. Then run Check Gate (6.2) then CheckRemote if eligible (and only after time is synced, per 7.4).
4. If update found, evaluate Install Gate separately — in current implementation this gate is battery + Wi-Fi stability; maintenance mode is not a blocker.

### 15.2 Loop Behavior

In [src/main.cpp](src/main.cpp):

1. Keep OTA checks lightweight in loop.
2. Avoid long blocking operations unless update is explicitly running.
3. Never conflict with deep sleep and maintenance logic.

## 16. Test Plan

### 16.1 Unit/Logic Tests (if framework added later)

1. SemVer compare — equal core + no prerelease vs prerelease (both directions, per 5.5).
2. Channel filter logic.
3. Backoff progression and reset (split streaks per 7.3).
4. Check Gate and Install Gate evaluated independently.

### 16.2 On-Device Validation Matrix

1. Auto OFF + manual check.
2. Auto ON + no update.
3. Auto ON + update available, battery OK → installs.
4. Auto ON + update available, battery below 3.60 V → check succeeds, install blocked, retried next wake.
5. Maintenance mode ON → check/install behavior unchanged (GitHub install still allowed by current code), while maintenance mode continues to control deep-sleep behavior.
6. Weak Wi-Fi / API timeout → wifiStabilityFailStreak increments, requires 2 good cycles to reset.
7. Corrupt binary/hash mismatch.
8. Post-update health success → native rollback cancelled.
9. Post-update health failure (all 3 probe attempts fail, per 8.3) → image still marked valid with degraded event (`health_confirmed_degraded`) and explicit `health_probe_failed` diagnostic event.
10. Post-update transient health failure (1st or 2nd probe attempt fails, a later attempt succeeds within the same boot, per 8.3) → image confirmed valid with normal health-confirmed event.
11. Channel switch stable→beta and beta→stable with identical core version → no spurious update loop.

### 16.3 Field Safety Tests

1. Power interruption during download — verify behavior matches 8.1.2 exactly: active partition unaffected, no reboot, `ota_update_fail` published, `otaTarget` retained for retry.
2. Power interruption during first boot after update (before `esp_ota_mark_app_valid_cancel_rollback` executes) — confirm bootloader still rolls back on next boot.
3. Consecutive failed checks and backoff behavior, verifying wifiStabilityFailStreak vs otaCheckFailStreak are tracked independently.

## 17. Operational Runbook

### 17.1 Initial Setup (Private Repo)

1. Flash firmware with OTA GitHub feature enabled.
2. Set channel (stable or beta).
3. Set GitHub token using Telegram command — confirm the command message is auto-deleted from chat (12.4).
4. Trigger /otaupdate_check and verify diagnostics.

### 17.2 Transition to Public Repo

1. Keep same release asset + manifest contract.
2. Clear token by command. If a private pending target exists, it is invalidated per 12.4 and must be rechecked.
3. Confirm check works anonymously.

### 17.3 Emergency Recovery

1. If remote OTA path fails, use existing local ArduinoOTA recovery window.
2. If update causes a hard boot failure before app confirmation, native bootloader rollback remains the safety net. If app reaches `ghOtaConfirmHealthIfPending()`, current policy confirms image even on network-health failure (degraded mode).
3. If both unavailable, serial flash is final fallback.

## 18. Open Decisions (for Later)

1. Optional stricter TLS validation policy.
2. Whether to expose separate command for force-install ignoring daily check (but still respecting Install Gate).
3. Optional per-board release channels once multiple hardware variants are active.

## 19. Summary

This design now mirrors the current firmware implementation exactly: a GitHub-based, battery-aware OTA workflow that coexists with the local `ArduinoOTA` recovery path; split check/install sequencing; SemVer-aware release selection; persisted pending-target retry flow; and token hygiene in Telegram via command-message deletion. Safety behavior reflects the implemented policy: install gating is battery + Wi-Fi based (maintenance mode does not hard-block GitHub install), and post-boot pending-verify health confirmation is anti-bricking oriented (image is marked valid even when health probe retries fail, with degraded diagnostics). Native bootloader rollback remains the foundation for true boot failures before app-level confirmation, while the app-level health path favors availability under unstable internet.

This revision adds the implementability layer needed to hand the document to an AI agent or developer without further clarification: an explicit table of every existing-codebase symbol this design depends on, verified against the current repository snapshot (2.1), plus a logging-level convention for new code (2.2); a concrete, fully specified `ghOtaHealthProbe()` endpoint and timeout (`GET /rate_limit`, timeout from `GH_OTA_HTTP_TIMEOUT_MS`, current build default 12000 ms) used consistently by both the Wi-Fi stability check and the post-boot health confirmation (6.3); explicit NVS default values for every config key on first boot, since `nvs_get_*` returns not-found rather than zero (9.1); a `GhOtaTarget.isPrivateRepo` field so the install step can deterministically choose the correct GitHub fetch scheme even if the token is cleared between check and install (14, Phase 1 Module API); and a full behavior specification — not just a test case — for a download interrupted mid-transfer, covering partition safety, MQTT reporting, and retry persistence (8.1.2). It prioritizes reliability over aggressiveness, supports private-to-public repository transition, and integrates cleanly with existing Telegram/MQTT/deep-sleep architecture.

## 20. As-Implemented Transfer Contract (Current Code Truth)

This section is intentionally implementation-first. If another repository wants to copy this OTA model, this is the minimum behavior contract to preserve from the current code.

### 20.1 What Is Already Implemented (and should be preserved)

1. Two OTA paths coexist:
   - local `ArduinoOTA` recovery window path ([src/ota.cpp](src/ota.cpp))
   - GitHub release OTA path with streamed install via `esp_http_client` + `esp_ota_*` ([src/gh_ota.cpp](src/gh_ota.cpp))
2. GitHub OTA state is persisted in NVS with short keys under namespace `raised_garden` (see [include/gh_ota.h](include/gh_ota.h)).
3. Automatic flow at boot (when `otaAuto=true`):
   - load pending target and try install first
   - otherwise run remote check and install if update exists
   (integration in [src/main.cpp](src/main.cpp)).
4. Manual Telegram flow exists for full runtime control: `/otastatus`, `/otaupdate_check`, `/otaupdate_now`, `/otaupdate_auto_on|off`, `/otachannel`, `/otatoken_set`, `/otatoken_clear` ([src/telegram.cpp](src/telegram.cpp)).
5. Manual `/otaupdate_now` replies include immediate block/fail reason reporting (`reason=<code>`) when install does not start.
6. `/otastatus` diagnostics expose both pending and persistent reason context (`pending_target`, `pending_reason`, `last_reason`) with fallback from pending reason to last reason.
7. Token command message deletion is implemented after `/otatoken_set` to reduce token exposure in chat history.
8. Binary is downloaded in stream mode, SHA256 is computed incrementally, and flashing is aborted on any integrity or transport failure.

### 20.2 Important As-Implemented Nuances (do not assume older draft behavior)

1. Install Gate currently enforces battery and Wi-Fi stability; maintenance mode does not hard-block GitHub install in current code path.
2. `ghOtaConfirmHealthIfPending()` currently marks image valid even if probe retries fail (with degraded warning), to avoid field-bricking due to unstable internet.
3. Manual `/otaupdate_check` and `/otaupdate_now` call `ghOtaCheckForUpdate(..., true)` and bypass timing gates by design.
4. Private/public repo handling is decided from runtime token presence and asset URL type during check, then carried in `GhOtaTarget.isPrivateRepo` for install.

If a target project requires stricter safety (for example mandatory rollback on failed post-boot probe or strict maintenance-mode install block), treat that as an explicit policy fork and document it locally.

## 21. Agent-Ready Porting Playbook (Other Repo / Other Hardware)

Use this as a deterministic migration recipe. An AI agent can execute these steps with minimal interpretation.

### 21.1 Preconditions Checklist

1. Target board supports dual OTA partitions and has enough flash for A/B layout.
2. Project uses ESP32 Arduino framework with access to ESP-IDF OTA APIs.
3. Project has NVS initialized and a Telegram-like runtime control channel (or substitute command interface).
4. Existing build can inject compile-time constants (`FW_VERSION`, GitHub owner/repo/api host, OTA tuning).

### 21.2 Files to Copy or Recreate

1. OTA module API/header equivalent to [include/gh_ota.h](include/gh_ota.h).
2. OTA module implementation equivalent to [src/gh_ota.cpp](src/gh_ota.cpp).
3. Config fallbacks in [include/config.h](include/config.h):
   - `FW_VERSION`
   - `OTA_GH_OWNER`, `OTA_GH_REPO`, `OTA_GH_API_HOST`
   - `GH_OTA_WIFI_STABLE_RSSI_MIN`, `GH_OTA_HTTP_TIMEOUT_MS`, `GH_OTA_MAX_CHECK_ATTEMPTS`, `GH_OTA_CHECK_RETRY_DELAY_MS`
4. Boot integration in [src/main.cpp](src/main.cpp): init, pending-verify confirm, auto-check/install sequence.
5. Runtime command integration in [src/telegram.cpp](src/telegram.cpp): all OTA commands and token-message deletion.
6. Partition table and build config in [platformio.ini](platformio.ini) + [partitions_ota_4m.csv](partitions_ota_4m.csv) + [sdkconfig.defaults](sdkconfig.defaults).

### 21.3 Required Adaptation Interfaces (replace project-specific dependencies)

When porting `gh_ota.cpp`, map these dependencies to the destination project:

1. Battery read function:
   - current: `batteryReadVoltage()`
   - required behavior: return current battery voltage in volts, `<=0` if unavailable
2. Maintenance/runtime policy function:
   - current: `telegramIsMaintMode()`
   - required behavior: return whether maintenance/service mode is active
3. Debug logger:
   - current: `telegramSendDebug(msg, level)`
   - required behavior: non-blocking log channel with levels 0/1/2 semantics
4. OTA event publisher:
   - current: `mqttPublishOtaEvent(...)` via local wrapper
   - required behavior: publish lifecycle events (or no-op stub if MQTT absent)
5. Wi-Fi state:
   - current: `WiFi.status()`, `WiFi.RSSI()`
   - required behavior: connected/disconnected + RSSI signal quality data

Porting rule: if the destination has no Telegram/MQTT, keep the OTA core module intact and provide small adapter stubs for command/log/event integration first.

### 21.4 Hardware-Specific Parameters to Re-Tune

1. Minimum install battery floor (default hard floor 3.60 V) based on target chemistry and regulator dropout.
2. Wi-Fi stability RSSI threshold (`GH_OTA_WIFI_STABLE_RSSI_MIN`) for actual antenna/environment.
3. HTTP timeout and retry count (`GH_OTA_HTTP_TIMEOUT_MS`, `GH_OTA_MAX_CHECK_ATTEMPTS`) for expected network quality.
4. OTA download buffer size (currently 4096 B static buffer) versus RAM headroom.
5. Partition slot size margin versus final firmware size growth.

### 21.5 CI/CD Requirements for Ported Repo

1. Trigger release build on `v*` tag.
2. Inject `FW_VERSION` from tag (without `v`).
3. Build target environment.
4. Compute binary SHA256.
5. Generate `ota-manifest.json` with `version`, `channel`, `board`, `bin_asset_name`, `sha256`, optional `min_battery_v`.
6. Attach `.bin` and manifest assets to release.

### 21.6 Acceptance Tests After Port

1. `/otaupdate_check` finds update and reports metadata correctly.
2. `/otaupdate_now` installs successfully and reboots to new version.
3. Intentional SHA mismatch blocks install and keeps active app intact.
4. Mid-download disconnect triggers abort path without partition switch.
5. Pending target survives reboot and retries when gates permit.
6. Token clear drops pending private target and forces fresh check.

## 22. Copy-Paste Brief for Another Agent

Use the block below as-is when delegating migration into another repository.

```text
Implement GitHub OTA in this repository using BirdNest OTA_Design.md as the source-of-truth, specifically sections 20 and 21 for transfer behavior.

Mandatory outcomes:
1) Add a gh_ota module with check/install/status/health APIs equivalent to BirdNest.
2) Use streamed install (esp_http_client + esp_ota_begin/write/end), incremental SHA256 verification, and redirect-safe GitHub asset download.
3) Persist OTA runtime state in NVS with <=15 char keys.
4) Integrate boot flow: ghOtaInit(), ghOtaConfirmHealthIfPending(), auto pending install, auto check+install.
5) Add runtime commands for status/check/install/channel/auto/token set+clear, including token command message deletion where chat platform supports it.
6) Add MQTT (or equivalent) OTA lifecycle events.
7) Ensure partition table is dual OTA and rollback config is enabled.
8) Keep version single source from CI tag -> FW_VERSION build flag.

Constraints:
- Preserve existing project architecture and naming style.
- If destination lacks Telegram/MQTT, implement adapters/stubs so OTA core remains unchanged.
- Do not use Arduino Update API for GitHub OTA install path.
- Keep local/manual OTA recovery path if project already has one.

Deliverables:
- list of changed files
- brief mapping table for local adapters (battery/log/events/maintenance)
- test evidence for: no-update, successful update, hash-fail abort, interrupted-download abort
```
