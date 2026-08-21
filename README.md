<div align="center">
  <h1>Kaibridge</h1>
  <p><em>KiCad ↔ AI Agent Bridge</em></p>
  <p><b>An end-to-end KiCad plugin that connects external AI agents to architect circuits, source verified components, compile multi-sheet schematics, place components via closed-loop visual feedback, and route PCBs inside the native KiCad environment—operating alongside a human engineer.</b></p>


[![Download Kaibridge (Windows)](https://img.shields.io/badge/Download_Kaibridge_(Windows)-v1.0-2EA043?style=flat-square&logo=windows&logoColor=white)](https://github.com/ShahMdAbid/Kaibridge/releases/latest/download/Kaibridge_v1.0.zip)

<br/>

[![License: AGPL v3.0](https://img.shields.io/badge/License-AGPL_v3.0-blue.svg)](LICENSE)
![KiCad](https://img.shields.io/badge/KiCad-10-blue?logo=kicad)
![Java](https://img.shields.io/badge/Java-17%2B-EA2D2E?logo=openjdk&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)

</div>

<br/>

### Documentation

* [Core Capabilities](docs/core-capabilities.md)
* [Architecture](docs/architecture.md)
* [User Guide](docs/user-guide.md)
* [Contributing Guidelines](docs/contributing.md)
* [Issue Tracker](https://github.com/ShahMdAbid/Kaibridge/issues)


## Quick Start

### 1. Install
- Download Kaibridge.
- Extract the folder into your KiCad 10 plugins directory (`Documents\KiCad\10.0\scripting\plugins\`).

### 2. Configure
- Open `kicad_paths.json` inside the plugin folder and update the paths.

### 3. Run
1. Open **KiCad 10** and open your project.
2. Click to open the **PCB Editor**.
3. In the top menu, click **Tools** → **External Plugins** → **Kaibridge**.
4. Open the plugin folder in your AI agent (e.g. Antigravity IDE) and start prompting! (See the [User Guide](docs/user-guide.md) for a step-by-step example conversation).

## AI Disclosure
 
This project was developed with the support of AI-assisted coding tools. AI tools were used to accelerate development — creative decisions and architecture remain entirely with the author(s).

## Disclaimer

This project is provided without any warranty, express or implied. The author(s) accept no liability for damages of any kind arising from the use of this plugin, including but not limited to: 

- Errors in generated schematics, PCB layouts, or manufacturing files
- Damage to hardware, components, or devices caused by incorrect designs
- Financial losses due to manufacturing errors or incorrect orders
- Data loss or corruption of KiCAD project files.

 **A Note on Fundamentals:** Although this tool is designed to accelerate and streamline your workflow, it requires a foundational understanding of PCB design. **AI-generated design suggestions do not replace qualified engineering review.**

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
You are free to use and modify this plugin. However, if you modify the code and make it available over a network (e.g., as a SaaS or web tool), you **must** open-source your modified backend code under the same AGPL-3.0 license.

