import sys
import re
import os

def suggest(file_content, method_name, limit=8):
    frag = method_name[:6].lower()
    if not frag:
        return ""
    names = sorted({m.group(1) for m in re.finditer(r"\n[ \t]*def (\w+)", file_content)
                    if frag in m.group(1).lower()})
    if names:
        return "\n  did you mean: " + ", ".join(names[:limit])
    return "\n  no similar name -- grep all_functionName.md for the real spelling"

def find_pcbnew_source():
    """The live pcbnew.py is the only source of truth. Never a pasted copy."""
    try:
        import pcbnew
        p = pcbnew.__file__
        if p.endswith((".pyc", ".pyo")):
            p = p[:-1]
        if os.path.isfile(p):
            return p
    except Exception:
        pass
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from kicad_pins import load_paths
        d = load_paths().get("kicad_python_dir")
        if d and (d / "pcbnew.py").is_file():
            return str(d / "pcbnew.py")
    except Exception:
        pass
    return None

def extract_docstring(method_body):
    # Match the def line and docstring if it exists
    doc_match = re.search(r'^[ \t]*def[^\n]+:\s*r?(?:"""|\'\'\')[\s\S]*?(?:"""|\'\'\')', method_body, re.MULTILINE)
    if doc_match:
        return doc_match.group(0)
    
    # If no docstring, return the def line AND the next line of code (to expose aliases)
    lines = method_body.strip().split('\n')
    if len(lines) > 1:
        return lines[0] + '\n' + lines[1]
    return lines[0] if lines else ""

def get_kicad_signature(file_content, class_name, method_name):
    if not class_name or not method_name:
        return ""

    # --- BONUS: Global Function Support ---
    if class_name.upper() in ("GLOBAL", "NONE"):
        method_regex = re.compile(rf'(?:^|\n)[ \t]*def {method_name}\b[\s\S]*?(?=(?:\n[ \t]*def |\n[ \t]*class |$))')
        match = method_regex.search(file_content)
        if not match:
            return f"[GLOBAL.{method_name}] -> GLOBAL FUNCTION NOT FOUND.{suggest(file_content, method_name)}\n"
        
        final_output = extract_docstring(match.group(0).strip())
        return f"[GLOBAL.{method_name}] EXACT SWIG OUTPUT:\n{final_output.strip()}\n"

    # --- Standard Class Method Support ---
    queue = [class_name]
    visited_classes = set()

    while queue:
        current_class = queue.pop(0)
        if current_class in visited_classes or current_class == 'object':
            continue
        visited_classes.add(current_class)

        # 1. Find where the class starts
        class_regex = re.compile(rf'(?:^|\n)class {current_class}\b(?:\(([^)]+)\))?:')
        class_match = class_regex.search(file_content)

        if not class_match:
            # If we couldn't find the class, just skip it and check other parents
            if current_class == class_name:
                return f"[{class_name}.{method_name}] -> CLASS '{current_class}' NOT FOUND.\n"
            continue

        # 2. Slice out JUST this class's body
        class_start_index = class_match.start()
        next_class_index = file_content.find('\nclass ', class_start_index + 1)
        if next_class_index == -1:
            next_class_index = len(file_content)
        
        class_body = file_content[class_start_index:next_class_index]

        # 3. Find the method inside this specific class body
        method_regex = re.compile(rf'(?:^|\n)[ \t]*def {method_name}\b[\s\S]*?(?=(?:\n[ \t]*def |\n[ \t]*class |$))')
        method_match = method_regex.search(class_body)

        if method_match:
            final_output = extract_docstring(method_match.group(0).strip())
            result = f"[{current_class}.{method_name}] EXACT SWIG OUTPUT:\n{final_output.strip()}\n"
            if current_class != class_name:
                result = f"(Inherited from base class: {current_class})\n" + result
            return result

        # 4. Enqueue ALL parent classes for Multiple Inheritance support
        if class_match.group(1):
            parents = [p.strip() for p in class_match.group(1).split(',')]
            queue.extend(parents)

    return f"[{class_name}.{method_name}] -> METHOD NOT FOUND.{suggest(file_content, method_name)}\n"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="KiCad 10 API Oracle")
    parser.add_argument("class_name", nargs="?", help="The class name (e.g. BOARD)")
    parser.add_argument("method_name", nargs="?", help="The method name (e.g. Add)")
    parser.add_argument("--batch", action="store_true", help="Read ClassName MethodName from stdin")
    
    args = parser.parse_args()

    if not args.batch and (not args.class_name or not args.method_name):
        print("Usage: python oracle.py <ClassName> <MethodName>")
        print("   Or: python oracle.py --batch (and pass lines via stdin)")
        sys.exit(1)
        
    file_path = find_pcbnew_source()
    if not file_path:
        sys.exit('Live pcbnew.py not reachable from this interpreter.\n'
                 'Use the bridge instead (it runs inside KiCad, always resolves):\n'
                 '  python "<PLUGIN_DIR>/Autoplacer/kicad_agent_bridge.py" --oracle "BOARD GetTracks"\n'
                 'Or add "kicad_python_dir" to kicad_paths.json.')
        
    with open(file_path, 'r', encoding='utf-8') as f:
        file_content = f.read()

    if args.batch:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                c_name = parts[0]
                m_name = parts[1]
                print(f"### {c_name} {m_name}")
                print(get_kicad_signature(file_content, c_name, m_name))
            else:
                print(f"Invalid format: '{line}' -> Please use 'ClassName MethodName'")
    else:
        print(get_kicad_signature(file_content, args.class_name, args.method_name))


