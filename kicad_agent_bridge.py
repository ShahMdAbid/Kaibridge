"""
======================================================================
AI AGENT INSTRUCTIONS: KiCad Remote Execution Bridge
======================================================================
This script lets an AI agent execute Python code inside a running KiCad
PCB Editor, via the abIDE plugin. abIDE must be open in KiCad
(Tools > External Plugins > abIDE) - it runs a small local TCP server
for as long as its window stays open. There is no polling and no temp
files: one connection = one request/response, answered as soon as
KiCad's GUI thread is free.

USAGE:
  1) Run a script file (fresh, stateless namespace - the default):
       python kicad_agent_bridge.py path/to/script.py [--timeout 30]
  2) Run code via stdin - use this for anything non-trivial. It avoids
     shell-quoting problems entirely, so it's the right default choice
     for any multi-line or otherwise non-trivial snippet:
       python kicad_agent_bridge.py --stdin --timeout 30 <<'PYEOF'
       import pcbnew
       board = pcbnew.GetBoard()
       ...
       PYEOF
  3) Run inline code - only for genuine one-liners. Quoting gets fragile
     fast for anything longer, so prefer --stdin as soon as the snippet
     is more than a single simple statement:
       python kicad_agent_bridge.py --code "print(1 + 1)"
  4) Query the pcbnew API ("oracle" mode):
       python kicad_agent_bridge.py --oracle "FOOTPRINT SetOrientationDegrees"
  5) Opt into REPL-style continuity across calls:
       python kicad_agent_bridge.py --stdin --keep-state <<'PYEOF'
       board = pcbnew.GetBoard()
       PYEOF
       python kicad_agent_bridge.py --code "print(board.GetFileName())" --keep-state
  6) Clear the shared namespace without running anything:
       python kicad_agent_bridge.py --reset-state

STATE: every agent call gets a completely fresh execution namespace by
default - equivalent to starting a new Python process each time. This
is deliberate: state silently leaking between calls (e.g. a stale
`board` object left over from a script you ran five minutes ago) is a
worse failure mode than a `NameError` from forgetting to re-import
something, so the safe default absorbs the annoying failure, not the
dangerous one.

Pass --keep-state to opt into a shared, persistent namespace across
calls instead (like a REPL) - only do this when you actually want
continuity between calls. Note that KiCad's manual "Run" button in the
abIDE window always uses that same shared namespace, since a human
tracking their own context is a different situation from an agent that
might not be. Pass --reset-state at any time (with or without
--keep-state) to wipe the shared namespace clean; call it with no other
arguments to just reset without running anything.

WARNING: Your code runs on KiCad's main GUI thread! Do NOT use infinite
loops (`while True:`) or long `time.sleep()` calls, or you will freeze
KiCad's UI until the process is killed. This is a KiCad/pcbnew
constraint, not something this bridge can work around.

If you get "KICAD NOT CONNECTED": abIDE is not open in KiCad. Tell the
user to open it, then retry once. Do NOT search the filesystem.
======================================================================
"""
import sys
import os
import json
import socket
import argparse

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORT_FILE = os.path.join(SCRIPT_DIR, "kicad_agent_bridge.port")


def get_port():
    if os.path.exists(PORT_FILE):
        try:
            with open(PORT_FILE, 'r', encoding='utf-8') as f:
                return int(f.read().strip())
        except Exception:
            pass
    return None


def _recv_line(sock, max_bytes=10_000_000):
    chunks = []
    total = 0
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\n" in chunk:
            break
        if total > max_bytes:
            break
    return b"".join(chunks)


def run_kicad_code(script_path=None, code_stdin=False, inline_code=None,
                    oracle_query=None, timeout=30.0, keep_state=False,
                    reset_state=False):
    code_str = ""
    mode = "execute"
    if oracle_query:
        mode = "oracle"
    elif inline_code is not None:
        code_str = inline_code
    elif code_stdin:
        code_str = sys.stdin.read()
    elif script_path:
        with open(script_path, 'r', encoding='utf-8') as f:
            code_str = f.read()
    elif reset_state:
        # No code source at all, just a bare --reset-state call.
        mode = "reset"

    payload = {
        "mode": mode,
        "code": code_str,
        "oracle_query": oracle_query or "",
        "keep_state": bool(keep_state),
        "reset_state": bool(reset_state),
        "timeout": timeout,
    }

    port = get_port()
    if port is None:
        print("--- KICAD NOT CONNECTED ---")
        print("FATAL ERROR: No port file found - abIDE has not been opened yet "
              "in this KiCad session. Open the abIDE window in KiCad's PCB "
              "Editor (Tools > External Plugins > abIDE) and try again.")
        print("AI AGENT: Do NOT search the filesystem or guess a fix - just ask "
              "the user to open abIDE, then retry once.")
        return

    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=3)
    except (ConnectionRefusedError, OSError):
        print("--- KICAD NOT CONNECTED ---")
        print("FATAL ERROR: abIDE is not listening. Open the abIDE window in "
              "KiCad's PCB Editor (Tools > External Plugins > abIDE) and try again.")
        print("AI AGENT: Do NOT search the filesystem or guess a fix - just ask "
              "the user to open abIDE, then retry once.")
        return

    try:
        sock.settimeout(timeout + 10)
        sock.sendall((json.dumps(payload) + "\n").encode('utf-8'))
        raw = _recv_line(sock)
        if not raw:
            print("--- KICAD ERROR ---")
            print("Connection closed by abIDE with no response.")
            return
        resp = json.loads(raw.decode('utf-8'))
        status = resp.get("status", "unknown")
        output = resp.get("output", "")
        print(f"--- KICAD {status.upper()} ---")
        print(output)
    except socket.timeout:
        print("--- KICAD TIMEOUT ---")
        print(f"No response from abIDE within {timeout}s. The script may still be "
              "running on KiCad's main thread (check the Output Console tab in "
              "abIDE). Increase --timeout if the script is expected to be slow.")
    except Exception as e:
        print("--- KICAD ERROR ---")
        print(f"Bridge communication error: {e}")
    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KiCad AI Agent Bridge")
    parser.add_argument("script_path", nargs="?", help="Path to the python script to execute")
    parser.add_argument("--stdin", action="store_true", help="Read code to execute from stdin")
    parser.add_argument("--code", type=str, default=None, help="Inline python code to execute")
    parser.add_argument("--oracle", type=str, help="Oracle query to execute (e.g. 'BOARD GetTracks')")
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout in seconds")
    parser.add_argument("--keep-state", action="store_true",
                         help="Reuse the shared persistent namespace across calls, like a REPL "
                              "(default: a brand new namespace every call). Also shared with "
                              "the manual 'Run' button in KiCad's abIDE window.")
    parser.add_argument("--reset-state", action="store_true",
                         help="Clear the shared persistent namespace. Independent of "
                              "--keep-state: can be combined with any call, or used alone "
                              "with no other arguments to just reset and run nothing.")
    args = parser.parse_args()
    if not args.script_path and not args.stdin and not args.code and not args.oracle and not args.reset_state:
        parser.error("Must provide a script_path, --stdin, --code, an --oracle query, or --reset-state")
    run_kicad_code(args.script_path, args.stdin, args.code, args.oracle,
                    args.timeout, args.keep_state, args.reset_state)
