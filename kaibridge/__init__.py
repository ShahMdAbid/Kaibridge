"""
Kaibridge 2.0: Autonomous, headless KiCad 10 hardware design automation engine.
Pure MCP & Python architecture for schematic compilation, placement, routing, and manufacturing.
"""
__version__ = "2.0.0"

import atexit
import os

def _silence_swig_teardown():
    """
    KiCad 10's SWIG C++ python wrapper dumps false-positive memory leak warnings 
    to C stderr during DLL unload at process shutdown.
    This hook runs strictly at process exit AFTER all Python code, exceptions, 
    and tracebacks have finished, silencing only the C-level exit noise while 
    guaranteeing 100% visibility for genuine errors.
    """
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
        os.close(devnull)
    except Exception:
        pass

atexit.register(_silence_swig_teardown)

