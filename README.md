# abIDE (Agent Bridged IDE) for automated PCB design using KiCad

This plugin connects external AI agents directly into KiCad (compatible with KiCad 8 / 9 / 10) and solves the API hallucination and component resolution problem.

---

### Key Features

- **Hybrid Native & Deterministic LCSC Component Search (v1.0.7):** 
  Combines offline native KiCad library validation with multi-backend LCSC/EasyEDA component discovery.
  - **Native KiCad Passives:** Instant zero-network resolution for generic resistors, capacitors, LEDs, pin headers, crystals, etc. using dictionary-based lookups (`component_classifier.py`).
  - **Deterministic LCSC Search:** Autonomous part resolution (`part_resolver.py`) that queries JLCPCB/LCSC APIs by specs, scores candidate parts based on MPN, package, pin count, and stock, and auto-gates clear winners.
  - **Multi-Backend Verification (`easyeda_client.py`):** Protects against Cloudflare WAF and missing geometry via a 5-tier fallback chain (In-process `easyeda2kicad`, Requests with warm-up cookies, `curl_cffi` TLS impersonation, In-memory Trial Download probes, and offline `jlcparts` SQLite).
  - **Flexible Component Sourcing:** Every component in `parts_spec.yaml` can be explicitly set to `source: native` or `source: lcsc`. Even generic passives can be forced to download directly from EasyEDA/LCSC on request.
  - **Safe Library Table Writer (`lib_table_writer.py`):** Additively registers project-local libraries (`${KIPRJMOD}/libs/easyeda2kicad`) without destroying or shadowing KiCad's global stock libraries (`Device`, `Resistor_SMD`, etc.).

- **Native Schematic Generation:** Generates `.kicad_sch` text files deterministically using `blueprint_to_sch.py` directly from YAML blueprints.
- **YAML Blueprinting Protocol:** Enforces a strict YAML-based hardware definition protocol (`parts_spec.yaml` and `circuit_blueprint.yaml`) as the single source of truth for BOM and schematic generation.
- **Bypasses KiCad's Closed Terminal:** Pipes Python scripts from external AI agents straight into KiCad via socket (`kicad_agent_bridge.py`).
- **Built-in API Oracle:** Solves C++ API method hallucination by querying live KiCad SWIG bindings via `oracle.py`.
- **Iterative Board State Fetching:** Agents can fetch exact component coordinates, unrouted nets, and board geometry in a token-optimized JSON format via `currentboardfetcher.py`.
- **abIDE UI Watchdog:** Actively monitors script execution and prevents UI thread freezes.

---

### Component Resolution & Hybrid Pipeline Overview

```text
                      parts_spec.yaml
                            │
                            ▼
              ┌───────────────────────────┐
              │    hybrid_pipeline.py     │
              └─────────────┬─────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
       source: native              source: lcsc
              │                           │
              ▼                           ▼
     library_resolver.py         part_resolver.py
     (Checks KiCad 10 local      (JLCPCB Search -> Multi-Backend
      fp & sym installation)      EasyEDA Verification -> Gate)
              │                           │
              │                           ▼
              │                   easyeda2kicad
              │                   (Batch Download LCSC Assets)
              │                           │
              └─────────────┬─────────────┘
                            ▼
                   build_manifest.json
                            │
                            ▼
                 Schematic & PCB Builders
```

#### 1. Native Component Resolution (`source: native`)
Generic passives (Resistors, Capacitors, LEDs, Diodes, Crystals, Pin Headers, etc.) use KiCad's built-in libraries. `component_classifier.py` converts plain-language requests (e.g. `"10k 1% 0603 pullup"`) into strict, verified KiCad identifiers (`Device:R` and `Resistor_SMD:R_0603_1608Metric`).

#### 2. LCSC Component Resolution (`source: lcsc`)
Complex ICs, modules, sensors, and custom connectors are assigned `source: lcsc`. `part_resolver.py` searches JLCPCB/LCSC, scores parts, and `easyeda_client.py` verifies geometry using trial download probes to ensure 100% CAD validity before generating the schematic.

#### 3. Forcing LCSC on Generic Parts
If a user explicitly requests an LCSC-sourced resistor or capacitor, the agent simply sets `source: lcsc` in `parts_spec.yaml`. The pipeline bypasses native lookups and fetches the exact physical CAD asset from EasyEDA.
