# Contributing to Kaibridge

Thank you for considering contributing to Kaibridge!

## How Can I Contribute?

### 1. Reporting Bugs & Issues
If you encounter a bug, unexpected behavior, or DRC/ERC discrepancy, please report:
- Your KiCad version (e.g. KiCad 10.0.0)
- Your Operating System
- The terminal traceback or error log
- The minimal circuit prompt or `design.json` that triggered the issue

### 2. Suggesting Enhancements
Feature requests for new EDA capabilities, routing heuristics, or footprint libraries are welcome.

### 3. Verification & Testing
Before submitting contributions:
1. Verify the CLI:
   ```powershell
   kaibridge --help
   ```
2. Run automated test suite:
   ```powershell
   pytest -v
   ```

## Development Guidelines
- All PCB operations must maintain compatibility with KiCad 10's headless Python bindings (`pcbnew`).
- Avoid adding GUI blocking calls that prevent headless execution.

## License
By contributing to Kaibridge, you agree that your contributions will be licensed under its **GNU Affero General Public License v3.0 (AGPL-3.0)**.
