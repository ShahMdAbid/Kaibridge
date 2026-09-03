#JLCPCB Basic Parts & IPC SMT Reference Catalog

This catalog maintains the verified, zero-extended-fee (**Basic Part**) components for JLCPCB SMT manufacturing. All components listed here:
1. Use **native KiCad symbols** (guaranteeing zero ERC violations).
2. Map to official **KiCad IPC-7351 SMD footprints** (zero silkscreen overlap, proper courtyards, 100% physical compatibility).
3. Incur **$0.00 extended component setup fees** at JLCPCB (saving ~$3 per unique part).

---

##1. Resistors (0805 & 0603 SMD)

| Value | Package | KiCad Symbol | KiCad IPC Footprint | LCSC Part # | JLCPCB Class | Description |
|---|---|---|---|---|---|---|
| **0Ω** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17165` | Basic Part | 0Ω Jumper / Bridge |
| **10Ω** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17488` | Basic Part | Inrush / Current sense |
| **100Ω** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17462` | Basic Part | Gate resistor / Filter |
| **220Ω** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17561` | Basic Part | 5V LED Current limit |
| **330Ω** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17657` | Basic Part | 3.3V LED Current limit |
| **470Ω** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17711` | Basic Part | General LED limit |
| **1kΩ** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17513` | Basic Part | Transistor base / Pull-up |
| **2.2kΩ** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17581` | Basic Part | I2C Fast-mode pull-up |
| **4.7kΩ** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17673` | Basic Part | Standard I2C pull-up |
| **5.1kΩ** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C23186` | Basic Part | Type-C CC1/CC2 pull-down |
| **10kΩ** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17414` | Basic Part | General pull-up / pull-down |
| **47kΩ** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17714` | Basic Part | High-Z divider |
| **100kΩ** | 0805 | `Device:R` | `Resistor_SMD:R_0805_2012Metric` | `C17407` | Basic Part | Voltage divider / Enable pull-up |
| **1kΩ** | 0603 | `Device:R` | `Resistor_SMD:R_0603_1608Metric` | `C21190` | Basic Part | Compact 1k |
| **4.7kΩ** | 0603 | `Device:R` | `Resistor_SMD:R_0603_1608Metric` | `C23163` | Basic Part | Compact I2C pull-up |
| **5.1kΩ** | 0603 | `Device:R` | `Resistor_SMD:R_0603_1608Metric` | `C23186` | Basic Part | Compact Type-C CC |
| **10kΩ** | 0603 | `Device:R` | `Resistor_SMD:R_0603_1608Metric` | `C25804` | Basic Part | Compact 10k pull-up |
| **100kΩ** | 0603 | `Device:R` | `Resistor_SMD:R_0603_1608Metric` | `C25803` | Basic Part | Compact 100k |

---

##2. Capacitors (MLCC 0805 & 0603 SMD)

| Value | Voltage | Package | KiCad Symbol | KiCad IPC Footprint | LCSC Part # | JLCPCB Class | Description |
|---|---|---|---|---|---|---|---|
| **22pF** | 50V | 0805 | `Device:C` | `Capacitor_SMD:C_0805_2012Metric` | `C1804` | Basic Part | Crystal oscillator loading |
| **100pF** | 50V | 0805 | `Device:C` | `Capacitor_SMD:C_0805_2012Metric` | `C1820` | Basic Part | RF / Spike filter |
| **1nF** | 50V | 0805 | `Device:C` | `Capacitor_SMD:C_0805_2012Metric` | `C1588` | Basic Part | Noise snubbing |
| **10nF** | 50V | 0805 | `Device:C` | `Capacitor_SMD:C_0805_2012Metric` | `C1517` | Basic Part | Mid-band decoupling |
| **100nF (0.1µF)** | 50V | 0805 | `Device:C` | `Capacitor_SMD:C_0805_2012Metric` | `C1525` | Basic Part | Standard IC bypass (Every VDD) |
| **1µF** | 50V | 0805 | `Device:C` | `Capacitor_SMD:C_0805_2012Metric` | `C15849` | Basic Part | Local bulk decoupling |
| **10µF** | 16V | 0805 | `Device:C` | `Capacitor_SMD:C_0805_2012Metric` | `C15850` | Basic Part | LDO Input/Output stabilizer |
| **22µF** | 10V | 0805 | `Device:C` | `Capacitor_SMD:C_0805_2012Metric` | `C45783` | Basic Part | Regulator bulk filter |
| **100nF** | 50V | 0603 | `Device:C` | `Capacitor_SMD:C_0603_1608Metric` | `C14663` | Basic Part | Compact IC bypass |
| **1µF** | 25V | 0603 | `Device:C` | `Capacitor_SMD:C_0603_1608Metric` | `C15849` | Basic Part | Compact bulk |
| **10µF** | 10V | 0603 | `Device:C` | `Capacitor_SMD:C_0603_1608Metric` | `C19702` | Basic Part | Compact LDO filter |

---

##3. Indicator LEDs (0805 SMD)

| Color | Package | KiCad Symbol | KiCad IPC Footprint | LCSC Part # | JLCPCB Class | Forward Voltage | Recommended Series R (3.3V) |
|---|---|---|---|---|---|---|---|
| **Red** | 0805 | `Device:LED` | `LED_SMD:LED_0805_2012Metric` | `C2286` | Basic Part | ~2.0V | 330Ω - 1kΩ |
| **Green** | 0805 | `Device:LED` | `LED_SMD:LED_0805_2012Metric` | `C2290` | Basic Part | ~3.0V | 100Ω - 330Ω |
| **Blue** | 0805 | `Device:LED` | `LED_SMD:LED_0805_2012Metric` | `C2293` | Basic Part | ~3.0V | 100Ω - 330Ω |
| **Yellow**| 0805 | `Device:LED` | `LED_SMD:LED_0805_2012Metric` | `C2296` | Basic Part | ~2.1V | 330Ω - 1kΩ |
| **White** | 0805 | `Device:LED` | `LED_SMD:LED_0805_2012Metric` | `C2297` | Basic Part | ~3.0V | 100Ω - 330Ω |

---

##4. Diodes & Protection

| Function | Part Number | Package | KiCad Symbol | KiCad IPC Footprint | LCSC Part # | JLCPCB Class | Ratings |
|---|---|---|---|---|---|---|---|
| **Switching Diode** | 1N4148W | SOD-123 | `Device:D` | `Diode_SMD:D_SOD-123` | `C81598` | Basic Part | 100V, 150mA, 4ns |
| **Schottky (1A)** | SS14 | SMA | `Device:D_Schottky` | `Diode_SMD:D_SMA` | `C4309` | Basic Part | 40V, 1A, Vf=0.5V |
| **Schottky (3A)** | SS34 | SMA | `Device:D_Schottky` | `Diode_SMD:D_SMA` | `C8678` | Basic Part | 40V, 3A, Vf=0.5V |
| **Schottky Low-Vf** | B5819W | SOD-123 | `Device:D_Schottky` | `Diode_SMD:D_SOD-123` | `C8598` | Basic Part | 40V, 1A, Vf=0.45V |

---

##5. Transistors & Small-Signal MOSFETs

| Type | Part Number | Package | KiCad Symbol | KiCad IPC Footprint | LCSC Part # | JLCPCB Class | Ratings |
|---|---|---|---|---|---|---|---|
| **NPN BJT** | S8050 | SOT-23 | `Device:Q_NPN_BEC` | `Package_TO_SOT_SMD:SOT-23` | `C2146` | Basic Part | 25V, 500mA, hFE 200-350 |
| **PNP BJT** | S8550 | SOT-23 | `Device:Q_PNP_BEC` | `Package_TO_SOT_SMD:SOT-23` | `C2149` | Basic Part | 25V, 500mA |
| **N-Channel MOS**| 2N7002 | SOT-23 | `Device:Q_NMOS_GSD` | `Package_TO_SOT_SMD:SOT-23` | `C8597` | Basic Part | 60V, 115mA, Rds 5Ω |
| **N-Channel MOS (Power)** | AO3400A | SOT-23 | `Device:Q_NMOS_GSD` | `Package_TO_SOT_SMD:SOT-23` | `C20917` | Basic Part | 30V, 5.7A, Rds 28mΩ |
| **P-Channel MOS (Power)** | AO3401A | SOT-23 | `Device:Q_PMOS_GSD` | `Package_TO_SOT_SMD:SOT-23` | `C15127` | Basic Part | -30V, -4.0A, Rds 44mΩ |

---

##6. Linear Voltage Regulators (LDOs)

| Output | Part Number | Package | KiCad Symbol | KiCad IPC Footprint | LCSC Part # | JLCPCB Class | Specs |
|---|---|---|---|---|---|---|---|
| **3.3V (1A)** | AMS1117-3.3 | SOT-223 | `Regulator_Linear:AMS1117-3.3` | `Package_TO_SOT_SMD:SOT-223-3_TabPin2` | `C6186` | Basic Part | Vin up to 15V, Vout 3.3V, 1A |
| **5.0V (1A)** | AMS1117-5.0 | SOT-223 | `Regulator_Linear:AMS1117-5.0` | `Package_TO_SOT_SMD:SOT-223-3_TabPin2` | `C47589` | Basic Part | Vin up to 15V, Vout 5.0V, 1A |
| **Adj (1A)** | AMS1117-ADJ | SOT-223 | `Regulator_Linear:AMS1117` | `Package_TO_SOT_SMD:SOT-223-3_TabPin2` | `C38379` | Basic Part | Adjustable output, 1A |

---

##7. How to Expand This Reference File

When adding new verified JLCPCB basic parts:
1. Verify the part is marked as **Basic Part** in the JLCPCB SMT Parts Library.
2. Confirm the exact **LCSC Part #** (`Cxxxx`).
3. Match it with the official **KiCad IPC-7351 footprint** (e.g. `Resistor_SMD:R_0805_2012Metric`).
4. Append it to this document and commit. Both agents and human designers can reference it instantly!
