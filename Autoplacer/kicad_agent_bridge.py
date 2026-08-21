"""CLI bridge for sending python commands to the KiCad Kaibridge plugin."""
import sys
import os
import json
import socket
import argparse
import urllib.request
import urllib.error
import base64

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORT_FILE = os.path.join(SCRIPT_DIR, "kicad_agent_bridge.port")


def get_port_and_token():
    """Read the port file which now contains 'port:token' format (§2.8)."""
    if os.path.exists(PORT_FILE):
        try:
            with open(PORT_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if ':' in content:
                parts = content.split(':', 1)
                return int(parts[0]), parts[1]
            else:
                # Legacy format (just port number)
                return int(content), None
        except Exception:
            pass
    return None, None





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

    port, token = get_port_and_token()
    if port is None:
        print("--- KICAD NOT CONNECTED ---")
        print("FATAL ERROR: No port file found - Kaibridge has not been opened yet "
              "in this KiCad session. Open the Kaibridge window in KiCad's PCB "
              "Editor (Tools > External Plugins > Kaibridge) and try again.")
        print("AI AGENT: Do NOT search the filesystem or guess a fix - just ask "
              "the user to open Kaibridge, then retry once.")
        return False

    # §2.8: Include auth token in payload
    if token:
        payload["token"] = token

    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/execute",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=timeout + 10) as response:
            raw = response.read()
            if not raw:
                print("--- KICAD ERROR ---")
                print("Connection closed by Kaibridge with no response.")
                return False
            try:
                resp = json.loads(raw.decode('utf-8'))
            except json.JSONDecodeError:
                print("--- KICAD ERROR ---")
                print("Zombie Port Detected! Connected to a wrong program.")
                print("Please reopen the Kaibridge window in KiCad to refresh the port.")
                return False
            status = resp.get("status", "unknown")
            output = resp.get("output", "")
            print(f"--- KICAD {status.upper()} ---")
            print(output)
            if status != "success":
                return False
            if "KAIBRIDGE_RESULT" in output:
                for line in output.split("\n"):
                    if line.startswith("KAIBRIDGE_RESULT "):
                        try:
                            r = json.loads(line[13:])
                            if r.get("failed") or r.get("applied") is False:
                                return False
                        except Exception:
                            pass
            return True
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError) or isinstance(e.reason, OSError):
            print("--- KICAD NOT CONNECTED ---")
            print("FATAL ERROR: Kaibridge is not listening. Open the Kaibridge window in "
                  "KiCad's PCB Editor (Tools > External Plugins > Kaibridge) and try again.")
            print("AI AGENT: Do NOT search the filesystem or guess a fix - just ask "
                  "the user to open Kaibridge, then retry once.")
            return False
        if isinstance(e.reason, socket.timeout):
            print("--- KICAD TIMEOUT ---")
            print(f"No response from Kaibridge within {timeout}s. The script may still be "
                  "running on KiCad's main thread (check the Output Console tab in "
                  "Kaibridge). Increase --timeout if the script is expected to be slow.")
            return False
        print("--- KICAD ERROR ---")
        print(f"Bridge communication error: {e}")
        return False
    except socket.timeout:
        print("--- KICAD TIMEOUT ---")
        print(f"No response from Kaibridge within {timeout}s. The script may still be "
              "running on KiCad's main thread (check the Output Console tab in "
              "Kaibridge). Increase --timeout if the script is expected to be slow.")
        return False
    except Exception as e:
        print("--- KICAD ERROR ---")
        print(f"Bridge communication error: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KiCad AI Agent Bridge")
    parser.add_argument("script_path", nargs="?", help="Path to the python script to execute")
    parser.add_argument("--stdin", action="store_true", help="Read code to execute from stdin")
    parser.add_argument("--code", type=str, default=None, help="Inline python code to execute")
    parser.add_argument("--json-ops", type=str, default=None, help="Path to a JSON file containing apply_ops list")
    parser.add_argument("--commit", action="store_true", help="Apply operations for real (default is dry run)")
    parser.add_argument("--state", choices=["summary", "full"], help="Dump current board state JSON directly to stdout")
    parser.add_argument("--oracle", type=str, help="Oracle query to execute (e.g. 'BOARD GetTracks')")
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout in seconds")
    parser.add_argument("--keep-state", action="store_true",
                         help="Reuse the shared persistent namespace across calls, like a REPL "
                              "(default: a brand new namespace every call). Also shared with "
                              "the manual 'Run' button in KiCad's Kaibridge window.")
    parser.add_argument("--reset-state", action="store_true",
                         help="Clear the shared persistent namespace. Independent of "
                              "--keep-state: can be combined with any call, or used alone "
                              "with no other arguments to just reset and run nothing.")
    parser.add_argument("--reload", action="store_true",
                         help="Reload boardmanager module (for development only)")
    args = parser.parse_args()
    
    if args.json_ops:
        if not os.path.exists(args.json_ops):
            parser.error(f"JSON file not found: {args.json_ops}")
        with open(args.json_ops, "r", encoding="utf-8") as f:
            ops_json = f.read()
        ops_b64 = base64.b64encode(ops_json.encode()).decode()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        reload_stmt = "importlib.reload(boardmanager)\n"
        args.code = (
            "import sys, json, base64, importlib\n"
            f"sys.path.insert(0, r'{script_dir}')\n"
            "import boardmanager\n"
            f"{reload_stmt}"
            "from boardmanager import apply_ops\n"
            f"ops = json.loads(base64.b64decode('{ops_b64}').decode())\n"
            f"result = apply_ops(ops, dry_run={not getattr(args, 'commit', False)}, save={getattr(args, 'commit', False)}, refill=False, verify=False)\n"
            "print('\\nKAIBRIDGE_RESULT ' + json.dumps(result))\n"
        )

    if args.state:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        reload_stmt = "importlib.reload(boardmanager)\n"
        args.code = (
            "import sys, json, importlib\n"
            f"sys.path.insert(0, r'{script_dir}')\n"
            "import boardmanager\n"
            f"{reload_stmt}"
            f"boardmanager.ai_context(mode='{args.state}')\n"
        )
        args.timeout = max(args.timeout, 120.0)

    if not args.script_path and not args.stdin and not args.code and not args.oracle and not args.reset_state and not args.state:
        parser.error("Must provide a script_path, --stdin, --code, --json-ops, --state, an --oracle query, or --reset-state")
        
    success = run_kicad_code(args.script_path, args.stdin, args.code, args.oracle,
                             args.timeout, args.keep_state, args.reset_state)
    sys.exit(0 if success else 1)
