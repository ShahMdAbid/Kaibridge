"""Organic integration tests for the Master CLI dispatcher (kaibridge <subcommand>)."""
from __future__ import annotations

import importlib
import pytest
from kaibridge.cli import COMMANDS, main, __version__


class TestMasterCLI:
    def test_version_flag(self, capsys):
        code = main(["--version"])
        assert code == 0
        captured = capsys.readouterr()
        assert f"kaibridge v{__version__}" in captured.out

    def test_help_flag(self, capsys):
        code = main(["--help"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Unified CLI" in captured.out
        # Verify key subcommands are listed in the help output
        assert "init" in captured.out
        assert "pins" in captured.out
        assert "build" in captured.out
        assert "sync" in captured.out
        assert "layout" in captured.out
        assert "route" in captured.out
        assert "inspect" in captured.out
        assert "oracle" in captured.out
        assert "export" in captured.out
        assert "check" in captured.out
        assert "fetch" in captured.out

    def test_no_args_shows_help(self, capsys):
        code = main([])
        assert code == 0
        captured = capsys.readouterr()
        assert "kaibridge <command>" in captured.out

    def test_unknown_subcommand_with_fuzzy_matching(self, capsys):
        code = main(["oracl"])  # typo for oracle
        assert code == 2
        captured = capsys.readouterr()
        assert "Unknown command 'oracl'" in captured.err
        assert "Did you mean: kaibridge oracle?" in captured.err

    def test_unknown_subcommand_no_match(self, capsys):
        code = main(["xyz999"])
        assert code == 2
        captured = capsys.readouterr()
        assert "Unknown command 'xyz999'" in captured.err

    def test_commands_registry_integrity(self):
        """Ensure all registered subcommands point to real importable modules and valid callables."""
        assert len(COMMANDS) >= 15
        for cmd_name, cmd_info in COMMANDS.items():
            mod_path, func_name, desc = cmd_info
            # Dynamically import and verify the function exists
            mod = importlib.import_module(mod_path)
            assert hasattr(mod, func_name), f"Command '{cmd_name}' targets {mod_path}:{func_name}, but it does not exist"
            target_fn = getattr(mod, func_name)
            assert callable(target_fn), f"Target {mod_path}:{func_name} is not callable"

    def test_dispatch_to_oracle(self, capsys):
        """Test real dispatch to the oracle subcommand."""
        code = main(["oracle", "--list"])
        assert code == 0
        captured = capsys.readouterr()
        assert "drc_rules" in captured.out
        assert "jlcpcb_rules" in captured.out

    def test_dispatch_to_inspect_help(self, capsys):
        """Test dispatch to inspect with --help cleanly returns 0."""
        code = main(["inspect", "--help"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Live KiCad PCB State Inspector" in captured.out
