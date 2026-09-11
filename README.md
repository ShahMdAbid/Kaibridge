<div align="center">
  <h1>Kaibridge</h1>
  <p><b>An open-source framework connecting AI agents to KiCad — enabling headless PCB design: architecting circuits from intent, sourcing verified components, compiling multi-sheet schematics, optimizing placement along with deterministic visual push-shove and routing alongside a human engineer in the loop</p>

[![License: AGPL v3.0](https://img.shields.io/badge/License-AGPL_v3.0-blue.svg)](LICENSE)
[![KiCad](https://img.shields.io/badge/KiCad-10-blue?logo=kicad)](https://www.kicad.org/)
[![Java](https://img.shields.io/badge/Java-25_LTS-EA2D2E?logo=openjdk&logoColor=white)](https://adoptium.net/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Version](https://img.shields.io/badge/Version-Beta_v2.6.0-green.svg)](CHANGELOG.md)
[![Last Commit](https://img.shields.io/github/last-commit/ShahMdAbid/Kaibridge?logo=github&color=2ea043)](https://github.com/ShahMdAbid/Kaibridge/commits)

</div>

<br/>

### Documentation

* [Core Capabilities](docs/core-capabilities.md)
* [System Architecture ](docs/architecture.md)
* [Contributing Guidelines](docs/contributing.md)
* [Changelog](CHANGELOG.md)
* [Issue Tracker](https://github.com/ShahMdAbid/Kaibridge/issues)



## Prerequisites & Installation

### 1. System Requirements
- **Python**: 3.10 or higher
- **KiCad**: KiCad 10.0 (or 9.0/8.0) with `kicad-cli` and bundled Python interpreter
- **Java**: Java 17+ LTS (required for Freerouting headless autorouting)

### 2. Installation
Clone the repository and install Kaibridge in editable mode:
```bash
git clone https://github.com/ShahMdAbid/Kaibridge.git
cd Kaibridge
pip install -e .
```

### 3. Autorouter Setup (Freerouting)
For headless trace routing (`kaibridge route`):
1. Download `freerouting-2.4.1.jar` from [Freerouting Releases](https://github.com/freerouting/freerouting/releases).
2. Place `freerouting-2.4.1.jar` in the Kaibridge root directory, or specify its location in `kicad_paths.json`.

### 4. Verify Installation & Test Suite
```bash
kaibridge --help
pytest
```
