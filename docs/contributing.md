#Contributing to Kaibridge

Thank you for considering contributing to Kaibridge!

##How Can I Contribute?

###1. Reporting Bugs & Issues
If you encounter a bug, unexpected behavior, or DRC/ERC discrepancy, please open an issue on the [GitHub Issue Tracker](https://github.com/ShahMdAbid/Kaibridge/issues).
When reporting an issue, please include:
- Your KiCad version (e.g. KiCad 10.0.0)
- Your Operating System
- The terminal traceback or MCP error log
- The minimal circuit prompt or `design.json` that triggered the issue

###2. Suggesting Enhancements
Feature requests for new EDA capabilities, routing heuristics, or footprint libraries are welcome via GitHub issues.

###3. Submitting Pull Requests
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/my-feature`).
3. Ensure all tests pass:
   ```powershell
   python tests/run_all_tests.py
   ```
4. Commit your changes (`git commit -m 'feat: description of changes'`).
5. Push to your fork and submit a Pull Request.

##Development Guidelines
- All PCB operations must maintain compatibility with KiCad 10's headless Python bindings (`pcbnew`).
- Avoid adding GUI blocking calls that prevent headless execution.
- Maintain deterministic behavior in placement and routing scripts.

##License
By contributing to Kaibridge, you agree that your contributions will be licensed under its **GNU Affero General Public License v3.0 (AGPL-3.0)**.
