# ART-Gate — Adversarial Red-Team Engineering Gate Protocol

**Version:** 1.0
**Scope:** Every Kaibridge design task, executed on Turn 1 before writing `implementation_plan.md`.
**Companion:** `references/adversarial_dfm_checklist.md` (Layer 1 static checklist).

---

## Overview

The ART-Gate is a bounded adversarial engineering verification pipeline. It runs silently between the user's prompt and the user-facing `implementation_plan.md`. The user — even a child with no engineering background — receives one clean, hardened plan. The complexity exists; the user does not carry it.

---

## Step 0 — Requirement Extraction & Interactive Clarification

### 0.1 — Prompt Triage

Read the user's prompt and perform an initial classification of design parameters into three states:

- **STATED:** Explicitly provided by the user.
- **INFERRED:** Reasonably deduced from context (e.g., "robot car" implies motors, battery, MCU).
- **UNKNOWN:** Cannot be determined from the prompt and affects design decisions.

Each INFERRED and UNKNOWN field must be impact-rated:

- **CRITICAL impact:** Could fundamentally alter the power architecture, component selection, or safety design (e.g., motor stall current, battery chemistry, input voltage).
- **HIGH impact:** Affects component sizing or layout decisions but not the fundamental architecture (e.g., exact sensor count, board form factor).
- **LOW impact:** Minimal engineering consequence (e.g., LED color preference, silkscreen text).

### 0.2 — Interactive Clarification (User-Facing Questions)

The agent MUST present clarifying questions for fields classified as INFERRED or UNKNOWN with CRITICAL or HIGH impact. When operating in an IDE planning mode, these questions MUST be embedded directly into the Turn 1 `implementation_plan.md` artifact under `## Open Questions` with selectable options (do NOT invoke external modal tools like `ask_question`). This ensures the user actively participates in the most important design decisions without interrupting automated compiler flows.

**Question format (mandatory for every question):**
- **3 agent-suggested options** — phrased in plain, non-technical language that a school student can understand. The agent picks the 3 most likely answers based on the prompt context.
- **"I'm not sure — you decide for me"** — the agent uses a conservative engineering default and documents it as an assumption.
- *(The system provides write-in capability for advanced users who want to specify their own answer).*

**Rules:**
- **Max 4 questions per design prompt.** Never overwhelm the user. Prioritize by impact: CRITICAL-impact unknowns first, then HIGH-impact.
- **Questions must be non-technical.** Never ask "What is your input voltage range?" — ask "What powers your project?" with options like "AA/AAA batteries", "9V battery or 12V adapter", "USB cable".
- **STATED fields are never questioned.** If the user already specified it, don't ask again.
- **LOW-impact unknowns are never questioned.** The agent decides these silently using engineering judgment.
- **"I'm not sure" answers** → the agent uses a conservative default, documents it in the Assumptions section, and flags it in Unresolved if the impact is CRITICAL.

**Example questions for prompt *"make me a robot car board"*:**

```
Q1: "What powers your robot?"
    → Rechargeable LiPo battery (7.4V)
    → AA batteries (4×1.5V = 6V)
    → 9V battery or 12V adapter
    → I'm not sure — you decide for me

Q2: "What controller/brain do you want?"
    → Arduino (ATmega328P) — simple, beginner-friendly
    → ESP32 — has WiFi and Bluetooth built in
    → Raspberry Pi Pico — fast, good for sensors
    → I'm not sure — you decide for me

Q3: "How should the robot detect the line or obstacles?"
    → IR sensors (for line following)
    → Ultrasonic sensor (for obstacle avoidance)
    → Both IR + ultrasonic
    → I'm not sure — you decide for me
```

---

## Step 1 — Design Contract

After receiving the user's clarification answers, build the complete **Design Contract** — a compact structured specification covering at minimum:

- **Input power:** voltage, current, source (battery, USB, adapter) — with state (STATED / INFERRED / UNKNOWN) and impact rating.
- **Active ICs:** MCU/SoC family, supply voltage.
- **Loads:** type, count, estimated current.
- **Interfaces:** connectors, communication protocols.
- **Manufacturing target:** assembler (JLCPCB), hand vs SMT assembly.

Every field retains its classification (STATED / INFERRED / UNKNOWN) and impact rating. "I'm not sure" answers are marked as INFERRED with the conservative default noted.

---

## Step 2 — Architecture Draft

Synthesize the initial circuit architecture: component list, power rail topology, netlist connections, and preliminary board dimensions. This is the draft that the adversarial gate will attack.

---

## Step 3 — Three-Layer Adversarial Attack

The agent internally attacks the draft architecture. The critic produces **structured findings only** — it does NOT redesign the board.

### Layer 0 — Requirement Attack

Examine what the user stated vs what the agent inferred. Flag every INFERRED requirement as an assumption. Identify UNKNOWN variables with CRITICAL or HIGH impact. If a CRITICAL-impact variable is UNKNOWN, the architecture must use a conservative design margin and the variable must appear in the Unresolved section of the final plan — it must NOT be silently assumed away.

### Layer 1 — Universal EE & DFM Gate

Read `references/adversarial_dfm_checklist.md`. For each rule:

1. **Applicability:** Does this rule apply to the current design? If not, skip it entirely.
2. **Evidence evaluation:** Evaluate the draft against the rule with evidence (calculation, datasheet reference, specification conflict, or reasoned inference with stated confidence level).
3. **Finding:** If the rule is violated, produce a structured finding.

Hard Rule violations require resolution or an explicit applicability exception with documented rationale. Severity is determined by actual consequences in context — not automatically CRITICAL because the rule is Tier A. Strong Heuristic deviations require documented justification. Optional Recommendations never produce findings.

### Layer 2 — Domain-Specific Attack

1. Classify the project domain from the user's prompt (Motor Control, IoT/WiFi, Sensor Array, Power Supply, Audio, LED/Display, etc.).
2. Compose a structured **attack surface taxonomy** for the identified domain. Example for "Robot Motor Controller": Power (battery reverse polarity, motor stall current, regulator brownout), Motor (inductive transients, driver thermal stress, shoot-through), MCU (boot behavior, brownout reset, GPIO defaults at startup), Communication (UART/USB failure modes), Mechanical (motor connector retention, battery connector orientation).
3. Systematically attack each surface using **failure-mode scenarios**:
   - What happens at **startup**? (GPIO defaults, inrush, sequencing)
   - What happens at **shutdown**? (inductive kick, data loss)
   - What happens during a **fault**? (sensor disconnect, stall, short)
   - What happens during **brownout**? (motor load droops supply, MCU resets)
   - What happens if the **user makes a wiring mistake**? (reversed polarity, swapped pins)

---

## Step 4 — Structured Findings

Each finding MUST contain:

```
Finding ID:        [checklist ID or DOMAIN-XX]
Affected item:     [component / net / subsystem]
Failure mechanism: [physical description of what breaks and when]
Evidence:          [calculation, datasheet spec, or reasoned inference]
Evidence basis:    [calculation | datasheet | checklist rule | inference]
Severity:          [CRITICAL | HIGH | MEDIUM | LOW]
Confidence:        [HIGH | MEDIUM | LOW]
Minimum fix:       [the simplest adequate correction]
```

**Severity and Confidence are independent axes.** A finding can be CRITICAL severity / LOW confidence (e.g., thermal issue depends on unconfirmed peak current). A finding can be LOW severity / HIGH confidence (e.g., verified minor silkscreen overlap).

---

## Step 5 — Design Resolver (Critic ≠ Architect)

The adversarial pass produces findings. A separate resolver step applies minimum-sufficient fixes. Before adding any component or changing any architecture element, the resolver MUST pass the **Why-Should-This-Exist test**:

1. Is there a plausible failure mechanism? (If no → REJECT)
2. Does the failure matter to this specific design? (If no → REJECT)
3. Does the mitigation materially reduce the risk? (If no → REJECT)
4. Would a simpler mitigation be sufficient? (If yes → use the simpler one)

**Do NOT over-engineer.** No TVS arrays on an LED board. No 4-layer controlled impedance for a 10 kHz sensor. No ferrite beads without a demonstrated EMI threat.

---

## Step 6 — Verification Gate & Convergence

After resolving findings, verify that fixes did not introduce new violations (second-order effects). Specifically ask: "Did our fix create a new current path, thermal issue, timing problem, or mechanical conflict?"

**Convergence condition (ALL must be true):**
- No unresolved CRITICAL findings.
- No unresolved HIGH-severity findings.
- No requirement contradictions.
- No DFM blockers.
- All mandatory assumptions documented.
- No CRITICAL-impact UNKNOWN variable is silently assumed (must be either conservatively designed around or flagged as Unresolved).

If the convergence condition is NOT met after Pass 1 → run Pass 2 (Steps 3–6 again).

**MAX_REVIEW_PASSES = 2.** After 2 passes, present the plan with any remaining unresolved items clearly marked.

---

## Step 7 — Final Plan Structure

The `implementation_plan.md` delivered to the user MUST be formatted according to the **Mandatory 4-Part Structure**:

1. **Section 1: Baseline Architecture (Initial Draft):**
   - The straightforward starting point derived directly from user requirements before adversarial inspection (explaining why an unverified happy-path design carries severe failure risks).

2. **Section 2: ART-Gate Adversarial Loop & Corrections:**
   - **Iteration 1 (The Attack):** Concrete findings across Layer 0, Layer 1, and Layer 2 (inrush, short circuits, thermal runaway, inductive kick, creepage breakdown, ground pour hazards).
   - **The Delta Table (Baseline vs. Hardened by ART-Gate):** Explicit table mapping each subsystem:
     `[Subsystem]` | `[Baseline (Naive)]` | `[Hardened by ART-Gate]` | `[Component Added with LCSC ID]` | `[Why-Should-This-Exist Justification]`
   - **Iteration 2 (Convergence & Second-Order Effects):** Verifies that additions introduced no new hazards (voltage drop, board structural weakening, sourcing availability).

3. **Section 3: Final Hardened Implementation Specification:**
   - Circuit architecture block diagram.
   - Verified Bill of Materials (BOM) with LCSC C-IDs and official KiCad IPC footprints.
   - **Zero-Hallucinated Pins Protocol:** Active IC and module pins are **NEVER** guessed or hardcoded upfront in the plan. The plan explicitly mandates querying pins directly from `.kicad_sym` via `kaibridge_query_symbol_pins` immediately after fetching.
   - Physical layout strategy, zoning, and creepage isolation barrier rules (e.g. milling slots in `Edge.Cuts`, secondary-only ground pours).

4. **Section 4: Sequential Execution Roadmap:**
   - Clear progression through checkpoints (Checkpoint 1: Schematic SVG review, Checkpoint 2: Placement SVG review, Checkpoint 3: DRC clean review).

The **full machine-readable audit** (all findings with evidence, severity, confidence, and resolution status) is written to `kaibridge_dump/art_gate_audit.md` for traceability.
