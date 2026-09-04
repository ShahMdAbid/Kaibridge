# Contributing to Kaibridge

Thank you for considering contributing to Kaibridge!

## How Can I Contribute?

### 1. Reporting Bugs & Issues
If you encounter a bug, unexpected behavior, or DRC/ERC discrepancy, please report:
- Your KiCad version (e.g. KiCad 10.0.0)
- Your Operating System
- The terminal traceback or MCP error log
- The minimal circuit prompt or `design.json` that triggered the issue

### 2. Suggesting Enhancements
Feature requests for new EDA capabilities, routing heuristics, or footprint libraries are welcome.

### 3. Verification & Testing
Before submitting contributions:
1. Verify all 8 root CLI tools:
   ```powershell
   python kicad_lib_init.py --help
   python kicad_pins.py --help
   python json2sch.py --help
   python kicad_pcb_sync.py --help
   python kicad_layout.py --help
   python pcb_snapshot.py --help
   python kicad_route.py --help
   python export_jlcpcb.py --help
   ```
2. Verify MCP server loading:
   ```powershell
   python -c "import server; print('Tools:', len(server.TOOLS_LIST))"
   ```

## Development Guidelines
- All PCB operations must maintain compatibility with KiCad 10's headless Python bindings (`pcbnew`).
- Avoid adding GUI blocking calls that prevent headless execution.

## License
By contributing to Kaibridge, you agree that your contributions will be licensed under its **GNU Affero General Public License v3.0 (AGPL-3.0)**.
