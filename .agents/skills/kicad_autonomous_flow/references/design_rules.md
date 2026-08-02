# PCB Auto-Placement Design Rules
# Version: 1.0 | For: abIDE Agentic Hardware EDA (Rule 9B)
#
# AGENT INSTRUCTIONS:
# Read this document fully before generating the placement YAML.
# These rules define how components must be physically arranged on a PCB.
# Apply every applicable rule to each component in the circuit_blueprint.

---

## ZONE DEFINITIONS
The board is divided into logical zones. Reference these names in the YAML.

- EDGE_TOP    : Top 15% of board height — connectors, USB, power jacks
- EDGE_BOTTOM : Bottom 15% — connectors, debug headers
- EDGE_LEFT   : Left 15% — power input, bulk capacitors
- EDGE_RIGHT  : Right 15% — output connectors, antenna
- CENTER       : Remaining interior area — ICs, MCUs, logic
- ANALOG_ZONE  : Physically isolated sub-region (CENTER, left half preferred)
- DIGITAL_ZONE : Remaining CENTER area

---

## RULE 1 — CONNECTORS & POWER ENTRY
- All connectors (J*, CON*, USB*) MUST be placed in an EDGE zone.
- Power entry connectors (PWR*, CONN_PWR*) go to EDGE_LEFT or EDGE_TOP.
- USB connectors go to EDGE_TOP or EDGE_BOTTOM for mechanical alignment.
- Constraint type: `anchor` with `zone`.

## RULE 2 — DECOUPLING CAPACITORS
- Every decoupling cap (C* where value is 100nF, 10nF, 1uF) MUST be grouped
  with its associated IC using `tight_group`.
- Max distance from IC power pin: 3mm. Preferred: 1–2mm.
- Orientation: place on the same side as the IC power pin (check net name).
- Derive decoupling relationships from your `power_distribution` section in the
  circuit_blueprint: caps that share a VCC/VDD/3V3 net with an IC are its
  decoupling caps.
- Constraint type: `tight_group` with `anchor_ref` pointing to the IC.

## RULE 3 — BULK CAPACITORS
- Large electrolytic caps (C* where value >= 10uF) go near power entry.
- Place in EDGE_LEFT zone or adjacent to the voltage regulator.
- Constraint type: `zone_preference`.

## RULE 4 — MICROCONTROLLERS & MAIN ICs
- MCU, CPU, FPGA, and main processing ICs go in CENTER or DIGITAL_ZONE.
- Orient so that UART/SPI/I2C pins face their peripheral components.
- Preferred rotation: 0° unless net topology suggests otherwise.
- Constraint type: `zone_preference` + `rotation_deg`.

## RULE 5 — VOLTAGE REGULATORS
- LDO and switching regulators (U*LDO, U*REG, IC*PWR) go near power entry.
- Place between the power connector and the MCU (left-to-right power flow).
- Keep their input bulk cap within 5mm, output cap within 3mm.
- Constraint type: `anchor` near EDGE_LEFT, then `tight_group` for caps.

## RULE 6 — CRYSTAL / OSCILLATOR
- Crystal (Y*, XTAL*) and oscillator (OSC*) MUST be placed immediately
  adjacent to the MCU's XTAL pins.
- Max distance: 5mm. Minimize trace length for signal integrity.
- No other components between the crystal and the MCU.
- Constraint type: `tight_group` with `anchor_ref` = MCU reference.
- Add `keep_clear_radius_mm: 3` to prevent other components nearby.

## RULE 7 — ANALOG / DIGITAL ISOLATION
- Op-amps (U*AMP, IC*OP), ADCs (U*ADC), DACs (U*DAC), sensors (U*SENS)
  go in ANALOG_ZONE.
- No switching regulators or high-frequency digital ICs in ANALOG_ZONE.
- If a ground pour separation is needed, note it in `notes` field.
- Constraint type: `zone_preference: ANALOG_ZONE`.

## RULE 8 — RF / ANTENNA COMPONENTS
- RF ICs (U*RF, IC*RF), inductors (L*), and antennas (ANT*) go to EDGE_RIGHT
  or a corner, away from clocks and switching regulators.
- Constraint type: `anchor` with `zone: EDGE_RIGHT`.

## RULE 9 — MOUNTING HOLES
- Mounting holes (H*, MH*) are fixed at board corners.
- Always `locked: true`. Never moved by the physics engine.
- Constraint type: `anchor` with `locked: true`.

## RULE 10 — COMPONENT ROTATION HINTS
- SOT-23 transistors driving LEDs: rotate 90° so collector faces load.
- Polarized caps: orient positive terminal toward power source.
- ICs with thermal pads: no rotation constraint, but note copper pour need.
- Use `rotation_deg` in the YAML when a specific angle improves routing.

## RULE 11 — KEEP-OUT / CLEARANCE
- Maintain minimum 0.5mm between all component courtyard boundaries.
- High-voltage components (>50V): minimum 3mm clearance from logic.
- Use `margin_mm` in `keep_clear_zones` definitions when needed.

## RULE 12 — COMPONENT ORDERING PRIORITY
When generating the YAML, process components in this order:
1. Locked / mounting holes (always first, never moved)
2. Edge connectors and power entry
3. Voltage regulators
4. Main ICs / MCU
5. Crystals and oscillators (grouped to MCU)
6. Decoupling caps (grouped to their IC)
7. Bulk capacitors
8. Analog components
9. RF components
10. Remaining passives (R*, L* not already grouped)
