# ART-Gate Layer 1 — Universal EE & DFM Checklist

**Version:** 1.0
**Scope:** Every Kaibridge-driven board, any project.
**Role:** Static attack surface for the ART-Gate adversarial verification pipeline.

---

## How This Checklist Works

1. **Applicability First:** Before evaluating any rule, determine whether it applies to the current design. A rule that does not apply produces no finding. Example: `IND-01` (inductive load protection) does not apply to a passive LED board.

2. **Three Tiers:**
   - **Tier A — Hard Rules:** Violation requires resolution or an explicit applicability exception with documented rationale. Severity is determined by actual consequences in context — a hard-rule violation is NOT automatically CRITICAL.
   - **Tier B — Strong Heuristics:** Comply, or document the deviation with engineering rationale.
   - **Tier C — Optional Recommendations:** Never produce a finding. Note only if contextually relevant. Never use to justify adding components.

3. **Evidence Required:** Every finding must state the physical failure mechanism and provide evidence (calculation, datasheet reference, specification conflict, or reasoned inference with stated confidence).

4. **Minimum Sufficient Engineering:** Before proposing any mitigation, the resolver must confirm:
   - There is a plausible failure mechanism.
   - The failure matters to this specific design.
   - The mitigation materially reduces the risk.
   - A simpler mitigation would be insufficient.

---

## Tier A — Hard Rules

Violation requires resolution or explicit applicability exception. Severity determined by consequences.

### Power Architecture (PWR)

| ID | Rule | Applicability |
|---|---|---|
| `PWR-01` | **Regulator thermal dissipation must be evaluated.** Calculate `P_d = (V_in - V_out) × I_peak` for linear regulators. If P_d exceeds the package thermal rating (considering PCB copper area), the power architecture must change (switching regulator, two-stage step-down, or reduced input voltage). | Any design with a voltage regulator. |
| `PWR-02` | **Voltage and current ratings of every power-path component must meet worst-case operating conditions.** This includes connectors, traces, switches, fuses, and protection devices. | Every design. |
| `PWR-03` | **External DC input connectors exposed to user wiring must have reverse-polarity protection** (Schottky diode, P-MOSFET, or series diode). The protection method must handle the expected input current without excessive voltage drop or power loss. | Any design with a user-accessible DC power input (barrel jack, screw terminal, battery connector). Not applicable to USB-only power (USB has keyed connectors). |

### Inductive & Transient Protection (IND)

| ID | Rule | Applicability |
|---|---|---|
| `IND-01` | **Every inductive load (relay coil, motor, solenoid, electromagnet) must have an appropriate energy-management path.** Flyback diode, TVS clamp, snubber RC, or integrated driver clamp. The clamp voltage must remain below the switching device's absolute maximum rating. | Any design driving an inductive load. |
| `IND-02` | **Switching transistors (BJT, MOSFET) driving inductive or capacitive loads must have defined gate/base bias at all operating states**, including MCU reset and power-up when GPIO pins are high-impedance. A pull-down resistor (10kΩ–100kΩ) on the gate/base prevents unintended activation. | Any design using discrete transistors to switch loads. |

### Microcontroller Boot & Configuration (MCU)

| ID | Rule | Applicability |
|---|---|---|
| `MCU-01` | **Every boot-mode, enable, and configuration pin required for normal startup must have a defined electrical state** (pull-up, pull-down, or direct connection to the appropriate rail). Floating boot/enable pins cause non-deterministic startup behavior. | Any design with an MCU or SoC that has boot-mode or enable pins. |
| `MCU-02` | **A programming or debug interface must be accessible** (SWD, JTAG, UART, USB, ISP header, or test pads) unless the MCU ships pre-programmed or the board is programmed through a dedicated connector that serves dual purpose. | Any design with a user-programmable MCU. Exception allowed if programming is explicitly handled through another interface (e.g., USB that also serves as programming port). |

### Mechanical & Connector Sanity (MECH)

| ID | Rule | Applicability |
|---|---|---|
| `MECH-01` | **Every connector's mating face and wire-entry direction must be physically accessible** from the board edge or enclosure opening without obstruction by other components, board features, or the enclosure itself. | Any design with connectors. |
| `MECH-02` | **Mounting holes must have sufficient keepout** (copper clearance and component clearance) for the fastener head, washer, and tool access. The specific keepout dimensions depend on the fastener size. | Any design with mounting holes. |

### Manufacturing & Sourcing (DFM)

| ID | Rule | Applicability |
|---|---|---|
| `DFM-01` | **Every component must have a verified LCSC C-Part ID bound before schematic compilation.** Use `kaibridge_lookup_lcsc_part` for offline resolution. Prefer JLCPCB Basic Parts (zero extended-component fee) when electrically equivalent options exist. | Every Kaibridge design targeting JLCPCB manufacturing. |

---

## Tier B — Strong Heuristics

Comply or document deviation with engineering rationale. Never treated as a defect without justification.

### Decoupling & Filtering (DEC)

| ID | Heuristic | Applicability |
|---|---|---|
| `DEC-01` | **Local bypass capacitors (typically 100nF ceramic) should be placed close to active IC supply pins.** Distance depends on operating frequency and IC requirements. Consult datasheet recommendations where available. | Any design with active ICs. |
| `DEC-02` | **Bulk filter capacitance (10µF–47µF) should exist at each power entry point** to absorb transient current demands and stabilize the rail during load steps. | Any design with active loads that have transient current demands. |

### Layout & Routing (LAY)

| ID | Heuristic | Applicability |
|---|---|---|
| `LAY-01` | **High-current switching loops should be minimized in area** to reduce radiated EMI and voltage ringing. Keep the power device, freewheeling element, and decoupling capacitor physically close. | Any design with switching regulators, motor drivers, or high-frequency switching. |
| `LAY-02` | **Power traces or pours carrying significant current should be sized appropriately** for the expected current, considering copper weight, temperature rise, and JLCPCB manufacturing capabilities. | Any design with power distribution above ~500mA. |

### Signal Integrity (SIG)

| ID | Heuristic | Applicability |
|---|---|---|
| `SIG-01` | **Sensitive analog traces should be routed away from noisy switching nodes** (PWM, motor drivers, switching regulators). Use physical separation or ground barriers where practical. | Any design mixing analog sensing with switching circuits. |
| `SIG-02` | **Crystal oscillator traces should be kept short and isolated** from high-current or noisy digital lines. Load capacitor values should match the crystal specification if provided. | Any design with an external crystal oscillator. |

### Thermal (THM)

| ID | Heuristic | Applicability |
|---|---|---|
| `THM-01` | **Components with significant power dissipation should have adequate thermal relief** — exposed pad connection to copper pour, sufficient copper area, or physical spacing from heat-sensitive components. | Any design where a component dissipates >0.25W continuously. |

---

## Tier C — Optional Recommendations

These NEVER produce a finding. Note only if contextually relevant and the user's design would clearly benefit.

| ID | Recommendation |
|---|---|
| `REC-01` | Consider larger component packages (0805 vs 0402) for easier hand assembly when board area permits and the user may assemble manually. |
| `REC-02` | Consider additional bulk capacitance near high-transient loads (motors, servos, solenoids) to reduce rail droop during current spikes. |
| `REC-03` | Consider adding test points on critical power rails and signals for debugging and validation. |
| `REC-04` | Consider ESD protection on externally exposed connectors if the operating environment or use case warrants it. |
