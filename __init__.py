import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    # pyrefly: ignore [missing-import]
    from .Autoplacer.script_runner import ScriptRunnerPlugin
    ScriptRunnerPlugin().register()
except Exception as e:
    import logging
    logging.exception(e)
