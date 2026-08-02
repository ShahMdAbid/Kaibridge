# AI AGENT INSTRUCTIONS: KiCad Remote Execution Bridge

This script lets an AI agent execute Python code inside a running KiCad PCB Editor, via the abIDE plugin. abIDE must be open in KiCad (Tools > External Plugins > abIDE).

## USAGE: STDIN ONLY
To prevent shell-quoting errors and avoid creating temporary files, the agent **MUST** run all multi-line PCB generation code via `stdin` using a PowerShell Heredoc:

```powershell
@'
import pcbnew
board = pcbnew.GetBoard()
# ... your generated layout code ...
'@ | python kicad_agent_bridge.py --stdin --timeout 30
```
*Note: Do not use `--keep-state` or other flags. Every execution must be stateless.*

## AUTHENTICATION
The bridge uses a token-based authentication system. The port file (`kicad_agent_bridge.port`) contains `port:token`. The bridge client (`kicad_agent_bridge.py`) reads this automatically and includes the token in every request. You do not need to handle the token manually.

## WARNING (UI THREAD & WATCHDOG)
Your code runs on KiCad's main GUI thread! The bridge includes an **abIDE Watchdog** (using `sys.settrace`) that monitors execution. If your code enters an infinite loop or takes too long, the Watchdog will kill it to prevent KiCad from freezing.

**Default timeout: 30 seconds.** Use `--timeout <seconds>` to override for long operations.

**Important restrictions:**
- Do **not** use `time.sleep()` — it blocks the main thread and will trigger the Watchdog.
- Do **not** call `wx.MessageBox`, `ShowModal`, or any blocking dialog — it will deadlock the bridge.
- For long operations (auto-placement, full state fetch), always pass an explicit `--timeout` value (e.g., `--timeout 120`).

## ERROR HANDLING
If you get "KICAD NOT CONNECTED": abIDE is not open in KiCad. Tell the user to open it, then retry once. Do NOT search the filesystem.

If you get "Server busy": another execution is still in progress. Wait a few seconds and retry.

If you get "Authentication failed": the port file may be stale. Tell the user to close and reopen abIDE.
