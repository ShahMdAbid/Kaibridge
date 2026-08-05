import os
import sys
import subprocess
import argparse

def run_freerouting(project_dir, jar_path=None):
    autoplacer_dir = os.path.dirname(os.path.abspath(__file__))
    bridge_path = os.path.join(autoplacer_dir, "kicad_agent_bridge.py")
    plugin_root = os.path.dirname(autoplacer_dir)
    
    jar_path = jar_path or os.path.join(plugin_root, "freerouting.jar")
    if not os.path.exists(jar_path):
        print(f"ERROR: freerouting.jar not found at {jar_path}")
        print("Please download it and place it in the plugin root.")
        return
    
    dsn_path = os.path.join(project_dir, "board.dsn")
    ses_path = os.path.join(project_dir, "board.ses")
    
    for old_file in [dsn_path, ses_path]:
        if os.path.exists(old_file):
            try:
                os.remove(old_file)
            except Exception:
                pass
    
    # 1. Export DSN
    print("[1/3] Exporting DSN from KiCad...")
    export_code = (
        "import pcbnew\n"
        "board = pcbnew.GetBoard()\n"
        f"success = pcbnew.ExportSpecctraDSN(board, r'{dsn_path}')\n"
        "print('DSN Export:', 'SUCCESS' if success else 'FAILED')\n"
    )
    res = subprocess.run([sys.executable, bridge_path, "--code", export_code, "--timeout", "120"], capture_output=True, text=True)
    print(res.stdout)
    if "FAILED" in res.stdout or not os.path.exists(dsn_path):
        print("Error exporting DSN.")
        return

    # 2. Run FreeRouting
    print("[2/3] Running FreeRouting headless...")
    cmd = ["java", "-jar", jar_path, "-de", dsn_path, "-do", ses_path, "--gui.enabled=false"]
    print(f"Executing: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print(f"ERROR: Java not found.")
        return
    except subprocess.CalledProcessError:
        print("ERROR: FreeRouting failed.")
        return

    # 3. Import SES
    if not os.path.exists(ses_path) or os.path.getsize(ses_path) < 100:
        print(f"ERROR: Expected SES file {ses_path} is missing or empty. FreeRouting failed.")
        return
        
    print("[3/3] Importing SES back to KiCad...")
    import_code = (
        "import pcbnew\n"
        "board = pcbnew.GetBoard()\n"
        f"success = pcbnew.ImportSpecctraSES(board, r'{ses_path}')\n"
        "if success:\n"
        "    pcbnew.Refresh()\n"
        "    print('SES Import: SUCCESS')\n"
        "else:\n"
        "    print('SES Import: FAILED')\n"
    )
    res2 = subprocess.run([sys.executable, bridge_path, "--code", import_code, "--timeout", "300"], capture_output=True, text=True)
    print(res2.stdout)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Headless FreeRouting for KiCad via Bridge")
    parser.add_argument("project_dir", help="Directory of the KiCad project")
    parser.add_argument("--jar", default=None, help="Path to freerouting.jar")
    args = parser.parse_args()
    
    run_freerouting(args.project_dir, args.jar)
