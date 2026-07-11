# BirdNestCam – Schematic Documentation

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Power Supply – Solar and Battery Path](#2-power-supply--solar-and-battery-path)
3. [UVLO – Undervoltage Lockout](#3-uvlo--undervoltage-lockout)
4. [Battery Voltage Monitor (BAT_MON)](#4-battery-voltage-monitor-batmon)
5. [Voltage Reference – TL431](#5-voltage-reference--tl431)
6. [Boost Converter – ME2188](#6-boost-converter--me2188)
7. [ESP32-CAM](#7-esp32-cam)
8. [Temperature Sensor – DS18B20](#8-temperature-sensor--ds18b20)
9. [PIR Motion Sensor](#9-pir-motion-sensor)
10. [AM312 Connector Header](#10-am312-connector-header)
11. [Review – Notes and Recommendations](#11-review--notes-and-recommendations)
12. [Bill of Materials (BOM)](#12-bill-of-materials-bom)

---

## 1. System Overview

BirdNestCam is a solar-powered bird box monitoring system using an ESP32-CAM module for image capture and delivery via Telegram. The system can draw power from two sources:

- **Solar panel** (6V nominal, ~7–8V open-circuit voltage)
- **Li-Ion battery** (3.0–4.2V)

Automatic source selection is handled by a **power path** circuit. Between captures the system enters deep sleep to minimise energy consumption.

```
Solar panel
    │
    ├─► TP4056 module (charging) ──► Li-Ion battery
    │
    └─► D1 (1N5819) ─────────────────────────────┐
                                                  ▼
TP4056 OUT+ ──► Q8 (DMG2305UX) ─────────────► SYS_PWR ──► ME2188 Boost ──► +5V ──► ESP32-CAM
                                                  ▲
Li-Ion battery ──► Q7 (DMG2305UX) ───────────────┘
        │
        └─► UVLO comparator ──► Q6 (FQP27P06) ──► SYS_BATT_SW (protection)
```

---

## 2. Power Supply – Solar and Battery Path

### 2.1 Solar Path

| Reference | Value / Type | Function |
|-----------|-------------|----------|
| J3 | Solar panel connector | 6V solar input |
| U2 | TP4056_Module | Li-Ion charger module (with DW01A + FS8205 protection) |
| D1 | 1N5819 Schottky | Solar bypass diode – direct solar supply in strong sunlight |

The solar panel delivers energy via two paths:
- **Charging path:** J3 → U2 IN+ → battery charging
- **Bypass path:** J3 → D1 → SYS_PWR (direct supply, bypassing the battery)

The bypass path prevents unnecessary battery charge/discharge cycling during strong sunlight, extending battery lifetime.

> ⚠️ **Note:** The solar panel Voc (7–8V) is applied directly to SYS_PWR via the D1 bypass path. The ME2188 boost converter's maximum input voltage must be verified — if it is less than 8V, a DD4012SA buck converter should be inserted before D1, configured to output 4.2V.

### 2.2 Battery Path

| Reference | Value / Type | Function |
|-----------|-------------|----------|
| BT1 | Li-Ion battery | Energy storage, 3.0–4.2V |
| Q7 | DMG2305UX (N-MOS, SOT-23) | Battery-side switch |
| R24 | 2MΩ | Gate pull-down |
| R20 | 1MΩ | Gate drive divider |
| R26 | 1MΩ | Gate drive divider |
| C21 | 100nF | Gate filter capacitor |

Q7 is an N-MOSFET that connects the battery output to the SYS_PWR rail, controlled by the UVLO logic.

### 2.3 TP4056 OUT+ Path

| Reference | Value / Type | Function |
|-----------|-------------|----------|
| Q8 | DMG2305UX (N-MOS, SOT-23) | TP4056 OUT+ switch |
| R2 | 100kΩ | Gate pull-down / control |

The TP4056 module's OUT+ output connects to the SYS_PWR rail through Q8. This output is managed by the module's internal power path logic, automatically selecting solar or battery as the source.

### 2.4 SYS_BATT_SW – System Switch

| Reference | Value / Type | Function |
|-----------|-------------|----------|
| Q6 | FQP27P06 (P-MOS, TO-220) | Main system power switch |
| R15 | 100kΩ | Gate pull-up |

Q6 is a P-MOSFET load switch driven by the UVLO_GATE signal. It disconnects the entire system load when the battery voltage falls to a critically low level.

---

## 3. UVLO – Undervoltage Lockout

The UVLO circuit prevents the Li-Ion battery from deep-discharging, which would cause permanent cell damage.

### Operating Principle

| Reference | Value / Type | Function |
|-----------|-------------|----------|
| U7A | LM393 comparator | UVLO comparator |
| R17 | 22kΩ | REF2V5 divider, upper leg |
| R18 | 100kΩ | Hysteresis resistor |
| R22 | 39kΩ | BAT_RAW divider, upper leg |
| R23 | 100kΩ | BAT_RAW divider, lower leg |
| C20 | 100nF | Filter capacitor |
| JP7 | Jumper | Manual UVLO_GATE bypass |

**Comparator connections:**
- **Pin 3 (non-inverting, +):** REF2V5 reference (2.5V) via R17 divider
- **Pin 2 (inverting, –):** UVLO_SENSE — scaled battery voltage from R22/R23 divider
- **Pin 1 (output):** UVLO_GATE → Q6 gate

R18 implements positive feedback between the output and the non-inverting input, creating hysteresis so the switch-off and switch-on thresholds differ — preventing oscillation near the threshold.

**Estimated switching thresholds:**
- Shutdown: ~3.0–3.2V battery voltage
- Recovery: ~3.3–3.5V battery voltage (due to hysteresis)

> Exact thresholds can be calculated from the R22/R23/R17/R18 values.

---

## 4. Battery Voltage Monitor (BAT_MON)

| Reference | Value / Type | Function |
|-----------|-------------|----------|
| U7B / U7C | LM393 (second comparator) | BAT_MON signal generation |
| R25 | 680Ω | BAT_RAW divider |
| C7 | 100nF | Filter capacitor |

The BAT_MON signal connects to ESP32-CAM IO13, allowing the firmware to read a digital low/high battery status. Using an LM393 comparator is preferable to the ESP32's internal ADC, which has known non-linearity issues.

---

## 5. Voltage Reference – TL431

| Reference | Value / Type | Function |
|-----------|-------------|----------|
| U8 | TL431DBZ | Precision 2.5V shunt reference |
| R25 | 680Ω | Cathode resistor |

The TL431 provides a stable REF2V5 (2.5V) reference to both the UVLO and BAT_MON comparators. This is more accurate than a resistor-divided supply reference and is independent of battery state of charge.

---

## 6. Boost Converter – ME2188

| Reference | Value / Type | Function |
|-----------|-------------|----------|
| U3 | ME2188 | Step-up boost converter → +5V |
| L1 | 22µH | Boost inductor |
| C6 | 100µF | Input filter (electrolytic) |
| C10 | 100nF | Input filter (ceramic) |
| C8 | 22µF | Output filter |
| C9 | 47µF | Output filter |
| C11 | 100nF | Output bypass (ceramic) |
| C12 | 100µF | Output bypass (electrolytic) |
| D6 | SS14 Schottky | Boost rectifier diode |

The ME2188 boost converter generates a stable +5V rail from SYS_PWR (3.0–4.2V from battery, or potentially higher when the solar bypass path is active).

> ⚠️ **Critical:** Verify the ME2188's absolute maximum input voltage. If the solar bypass path (D1) can deliver 7–8V to SYS_PWR and this exceeds the ME2188's rating, a DD4012SA buck converter must be inserted before D1, configured to 4.2V output.

---

## 7. ESP32-CAM

| Pin | Function | Connection |
|-----|----------|------------|
| 5V | Power input | +5V boost output |
| GND | Ground | GND |
| 3V3 | 3.3V output | DS18B20 VDD, internal LDO |
| IO4 | Flash LED | Do not use for external signals (bootstrap pin) |
| IO12 | General GPIO | Available |
| IO13 | BAT_MON | Battery level input |
| IO14 | General GPIO | Available |
| IO15 | General GPIO | Available |
| IO2 | General GPIO | Available |
| IO0 | Boot / GPIO | Must be pulled to GND for flash mode |

**Bypass capacitors on the ESP32-CAM power rails:**

| Reference | Value | Rail | Function |
|-----------|-------|------|----------|
| C1 | 100nF | 5V | HF noise filtering |
| C2 | 100µF | 5V | Current spike absorption |
| C3 | 100nF | 3V3 | HF noise filtering |

> C3 (100nF) is placed on the 3V3 rail. Adding a 100µF electrolytic in parallel is recommended for full transient suppression during WiFi transmissions.

---

## 8. Temperature Sensor – DS18B20

| Reference | Value / Type | Function |
|-----------|-------------|----------|
| U1 | DS18B20 | 1-Wire digital temperature sensor |
| R6 | 4.7kΩ | 1-Wire pull-up resistor |

**Connections:**
- VDD → +3V3
- GND → GND
- DQ (data) → TEMP. SIG. → ESP32-CAM GPIO (via JP3 connector)

> ⚠️ Confirm which ESP32-CAM GPIO the TEMP. SIG. net connects to. IO4 is **not suitable** (flash LED and bootstrap pin conflict). Recommended: **IO12**.

---

## 9. PIR Motion Sensor

| Connector | Pin | Signal |
|-----------|-----|--------|
| JP3 | 1 | PIR. SIG. → ESP32-CAM GPIO |
| JP3 | 2 | DS18B20 data (PIR DR) |
| JP3 | 3 | TEMP. SIG. |

The PIR sensor signal allows the ESP32-CAM to wake from deep sleep on motion detection, reducing energy consumption and increasing the proportion of interesting captures.

> ⚠️ The schematic shows both BAT_MON and PIR. SIG. assigned to IO13. These must be separated — see section 11.

---

## 10. AM312 Connector Header

| Reference | Pin | Signal |
|-----------|-----|--------|
| J2 | 1 | +5V |
| J2 | 2 | PIR. SIG. |
| J2 | 3 | GND |

Connector for the AM312 mini PIR module. R1 (10kΩ) pull-down holds the PIR signal line stable in the idle state.

---

## 11. Review – Notes and Recommendations

### ✅ What is well designed

- **UVLO circuit** — excellent addition; protects the Li-Ion cell from deep discharge
- **TL431 reference** — accurate, supply-independent reference voltage for comparators
- **DMG2305UX switches** — compact SOT-23 N-MOSFETs, well suited for the switching role
- **Bypass capacitors** — C1/C2 on the 5V rail and C3 on the 3V3 rail are correctly placed
- **BAT_MON** — battery level is readable by firmware without using the ESP32's non-linear ADC
- **PIR sensor support** — motion-triggered wake is possible, saving significant energy
- **JP7 jumper** — UVLO can be bypassed manually during development and testing

### ⚠️ Critical Issues

#### 1. Solar bypass overvoltage on ME2188 input

The D1 (1N5819) bypass path can deliver the solar panel's open-circuit voltage (7–8V) directly to SYS_PWR and therefore to the ME2188 boost converter input.

**Fix:** Insert the **DD4012SA buck converter** before D1, configured to 4.2V output:
```
Solar → DD4012SA (→ 4.2V) → D1 → SYS_PWR
```
The DD4012SA requires a minimum input of 6.5V, so it will not conduct in weak sunlight — exactly when the bypass path should be inactive anyway. This gives natural alignment between solar availability and bypass activation.

#### 2. IO13 dual assignment

The schematic assigns both BAT_MON and PIR. SIG. to IO13. A single GPIO cannot serve two functions simultaneously.

**Fix:** Assign separate pins:
- BAT_MON → IO13
- PIR. SIG. → IO14

#### 3. DS18B20 TEMP. SIG. target pin not specified

The TEMP. SIG. net is not explicitly connected to a named ESP32-CAM GPIO in the schematic.

**Fix:** Route to **IO12** and label it clearly on the schematic.

### 🟡 Minor Recommendations

- **H1–H4 debug header** — exposes +3V3 and BAT_RAW for measurement. Add a label or note on the schematic describing its purpose.
- **Q6 FQP27P06 TO-220** — oversized for this application. If THT is required, a **BS250 (TO-92)** is a more compact P-MOSFET alternative with a lower gate threshold, better suited to 4.2V drive.
- **3V3 rail bulk capacitance** — C3 is only 100nF. A 100µF electrolytic in parallel is recommended to absorb WiFi transmission spikes on the 3V3 rail.
- **LM393 open-collector output** — the LM393 has open-collector outputs and requires a pull-up resistor to the supply on each output. Verify that pull-ups are present on the UVLO_GATE and BAT_MON nets (not clearly visible in the schematic).

---

## 12. Bill of Materials (BOM)

| Reference | Value / Type | Description |
|-----------|-------------|-------------|
| U1 | DS18B20 | 1-Wire temperature sensor |
| U2 | TP4056_Module | Li-Ion charger module (DW01A + FS8205) |
| U3 | ME2188 | Boost converter → +5V |
| U7A, U7B, U7C | LM393 | Dual comparator |
| U8 | TL431DBZ | 2.5V shunt voltage reference |
| U4 | ESP32-CAM | Camera + WiFi module |
| Q6 | FQP27P06 | P-MOSFET, TO-220, system load switch |
| Q7, Q8 | DMG2305UX | N-MOSFET, SOT-23, power path switches |
| D1 | 1N5819 | Schottky diode, solar bypass |
| D6 | SS14 | Schottky diode, boost rectifier |
| L1 | 22µH | Boost inductor |
| BT1 | Li-Ion | Rechargeable battery cell |
| J2 | AM312 connector | PIR sensor header |
| J3 | Solar panel connector | Solar panel input |
| JP7 | Jumper | UVLO bypass jumper |
| C1, C3, C7, C10, C11 | 100nF | Ceramic bypass capacitor |
| C2, C6, C12 | 100µF | Electrolytic filter capacitor |
| C8 | 22µF | Output filter capacitor |
| C9 | 47µF | Output filter capacitor |
| C20, C21 | 100nF | Filter capacitor |
| R1 | 10kΩ | PIR signal pull-down |
| R2 | 100kΩ | Q8 gate pull-down |
| R6 | 4.7kΩ | DS18B20 pull-up |
| R15 | 100kΩ | Q6 gate pull-up |
| R17 | 22kΩ | UVLO comparator divider |
| R18 | 100kΩ | UVLO hysteresis resistor |
| R19 | 1MΩ | Divider resistor |
| R20 | 1MΩ | Battery divider |
| R21 | 100kΩ | Battery divider |
| R22 | 39kΩ | UVLO_SENSE divider, upper leg |
| R23 | 100kΩ | UVLO_SENSE divider, lower leg |
| R24 | 2MΩ | Q7 gate pull-down |
| R25 | 680Ω | TL431 cathode resistor |
| R26 | 1MΩ | Battery divider |

---

*Documentation generated: 2026-06-07*  
*Based on: BirdNest_pcb.kicad.sch Rev v1.1*
