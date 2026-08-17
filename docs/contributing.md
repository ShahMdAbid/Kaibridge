# Contributing to abIDE

First off, thank you for considering contributing to abIDE! It's people like you that make the open-source community such a great place to learn, inspire, and create.

## How Can I Contribute?

### 1. Reporting Bugs & Issues
If you encounter a bug, a crash, or unexpected behavior while using the KiCad AI bridge, please open an issue on our [GitHub Issue Tracker](https://github.com/ShahMdAbid/abIDE/issues).
When reporting an issue, please include:
- Your KiCad version (e.g., KiCad 10.0.0)
- Your Operating System
- The exact error log or traceback from the KiCad scripting console or the background terminal
- A description of what you were trying to do (e.g., "Tried to place U1 and the geometry gate crashed").

### 2. Suggesting Enhancements
If you have ideas for new features (like better prompt engineering, new sourcing providers besides LCSC, or UI improvements), feel free to open a feature request issue.

### 3. Submitting Pull Requests
We welcome pull requests! If you want to fix a bug or add a feature:
1. Fork the repository.
2. Create a new branch for your feature (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'feat: add amazing feature'`).
4. Push to the branch (`git push origin feature/amazing-feature`).
5. Open a Pull Request.

## Development Setup
- Please ensure you test your Python scripts against the **native KiCad Python interpreter** (`pcbnew`), not just a standalone Python environment.
- Avoid introducing blocking GUI operations that freeze the KiCad main thread.

## License
By contributing to abIDE, you agree that your contributions will be licensed under its **AGPL-3.0 License**.

Once again, thank you for your support!
