# AI AGENT INSTRUCTIONS: KiCad Remote Execution Bridge

This script lets an AI agent execute Python code inside a running KiCad PCB Editor, via the abIDE plugin. abIDE must be open in KiCad (Tools > External Plugins > abIDE).

## USAGE: STDIN ONLY
To prevent shell-quoting errors and avoid creating temporary files, the agent **MUST** run all multi-line PCB generation code via `stdin` using a PowerShell Heredoc:

```bash
python kicad_agent_bridge.py --stdin --timeout 30 <<'PYEOF'
import pcbnew
board = pcbnew.GetBoard()
# ... your generated layout code ...
PYEOF
```
*Note: Do not use `--keep-state` or other flags. Every execution must be stateless.*

## WARNING (UI THREAD & WATCHDOG)
Your code runs on KiCad's main GUI thread! However, this bridge includes an **abIDE Watchdog** (using `sys.settrace`) that actively monitors execution. If your code enters an infinite loop or takes longer than 15 seconds to execute, the Watchdog will automatically kill the execution to prevent KiCad from freezing permanently. 

*Note: Do not use `time.sleep()` for polling, as it blocks the main thread and may trigger the Watchdog.*

## ERROR HANDLING
If you get "KICAD NOT CONNECTED": abIDE is not open in KiCad. Tell the user to open it, then retry once. Do NOT search the filesystem.
