<div align="center">
  <h1>Kaibridge 2.0</h1>
  <p><em>KiCad <-> AI Agent Bridge</em></p>
  <p><b>An end-to-end bridge that connects external AI agents to architect circuits, source verified components, compile multi-sheet schematics, place components, and route PCBs inside KiCad 10—operating alongside a human engineer.</b></p>

[![Download Kaibridge (Windows)](https://img.shields.io/badge/Download_Kaibridge_(Windows)-v2.0-2EA043?style=flat-square&logo=windows&logoColor=white)](https://github.com/ShahMdAbid/Kaibridge/releases/latest/download/Kaibridge_v2.0.zip)

<br/>

[![License: AGPL v3.0](https://img.shields.io/badge/License-AGPL_v3.0-blue.svg)](LICENSE)
[![KiCad](https://img.shields.io/badge/KiCad-10-blue?logo=kicad)](https://www.kicad.org/)
[![Java](https://img.shields.io/badge/Java-25_LTS-EA2D2E?logo=openjdk&logoColor=white)](https://adoptium.net/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Last Commit](https://img.shields.io/github/last-commit/ShahMdAbid/Kaibridge?logo=github&color=2ea043)](https://github.com/ShahMdAbid/Kaibridge/commits)

</div>

<br/>

### Documentation

* [Core Capabilities](docs/core-capabilities.md)
* [User Guide](docs/user-guide.md)
* [Changelog](CHANGELOG.md)
* [Contributing Guidelines](docs/contributing.md)
* [Issue Tracker](https://github.com/ShahMdAbid/Kaibridge/issues)


## Quick Start

### 1. Setup
- Download or clone the repository.
- Configure `kicad_paths.json` if your KiCad installation paths differ from standard locations.
- Add Kaibridge to your agent's MCP configuration (`mcp_config.json`):

```json
{
  "mcpServers": {
    "kaibridge": {
      "command": "python",
      "args": [
        "Kaibridge/server.py"
      ]
    }
  }
}
```

### 2. Run
1. Start your AI coding agent (e.g. Antigravity IDE).
2. Enter your circuit design requirements.
3. The agent sources components, compiles schematics, verifies ERC, places footprints, and routes the board headlessly. While the engine can operate fully autonomously, guiding the agent step-by-step through checkpoints is recommended to maintain clear visibility over your design—**AI-generated design suggestions do not replace qualified engineering review**. (See the [User Guide](docs/user-guide.md) for details).


## AI Disclosure

This project was developed with the support of AI-assisted coding tools. AI tools were used to accelerate development — creative decisions and architecture remain entirely with the author(s).


## Disclaimer

This project is provided without any warranty, express or implied. The author(s) accept no liability for damages of any kind arising from the use of this tool, including but not limited to: 

- Errors in generated schematics, PCB layouts, or manufacturing files
- Damage to hardware, components, or devices caused by incorrect designs
- Financial losses due to manufacturing errors or incorrect orders


## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
You are free to use and modify this project. However, if you modify the code and make it available over a network (e.g., as a SaaS or web tool), you **must** open-source your modified backend code under the same AGPL-3.0 license.
