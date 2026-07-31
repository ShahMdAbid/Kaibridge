import os
import sys
import json
import socket
import threading
import wx
import pcbnew
import traceback
import io
import time

PORT_FILE = os.path.join(os.path.dirname(__file__), "kicad_agent_bridge.port")
DEBUG_LOG = os.path.join(os.path.dirname(__file__), "kicad_agent_bridge_debug.log")


class ScriptRunnerFrame(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(
            self, 
            parent, 
            id=wx.ID_ANY, 
            title="abIDE", 
            size=(700, 500),
            style=wx.DEFAULT_FRAME_STYLE
        )
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.notebook = wx.Notebook(panel)
        self.tab_file = wx.Panel(self.notebook)
        vbox_file = wx.BoxSizer(wx.VERTICAL)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self.tab_file, label="Script Path:")
        hbox1.Add(lbl, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        self.txt_path = wx.TextCtrl(self.tab_file)
        hbox1.Add(self.txt_path, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL)
        self.btn_browse = wx.Button(self.tab_file, label="Browse...")
        self.btn_browse.Bind(wx.EVT_BUTTON, self.OnBrowse)
        hbox1.Add(self.btn_browse, flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT, border=8)
        vbox_file.Add(hbox1, proportion=0, flag=wx.EXPAND | wx.ALL, border=20)
        self.tab_file.SetSizer(vbox_file)
        self.tab_code = wx.Panel(self.notebook)
        vbox_code = wx.BoxSizer(wx.VERTICAL)
        lbl_code = wx.StaticText(self.tab_code, label="Paste your Python code here:")
        vbox_code.Add(lbl_code, flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8)
        self.txt_code = wx.TextCtrl(self.tab_code, style=wx.TE_MULTILINE | wx.TE_DONTWRAP | wx.TE_RICH2)
        font = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.txt_code.SetFont(font)
        vbox_code.Add(self.txt_code, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
        self.tab_code.SetSizer(vbox_code)
        self.tab_output = wx.Panel(self.notebook)
        vbox_out = wx.BoxSizer(wx.VERTICAL)
        lbl_out = wx.StaticText(self.tab_output, label="Terminal Output:")
        vbox_out.Add(lbl_out, flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8)
        self.txt_output = wx.TextCtrl(self.tab_output, style=wx.TE_MULTILINE | wx.TE_DONTWRAP | wx.TE_RICH2 | wx.TE_READONLY)
        self.txt_output.SetFont(font)
        self.txt_output.SetBackgroundColour(wx.Colour(30, 30, 30))
        self.txt_output.SetForegroundColour(wx.Colour(220, 220, 220))
        vbox_out.Add(self.txt_output, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
        self.tab_output.SetSizer(vbox_out)
        self.tab_oracle = wx.Panel(self.notebook)
        vbox_oracle = wx.BoxSizer(wx.VERTICAL)
        lbl_oracle_in = wx.StaticText(self.tab_oracle, label="Query (ClassName MethodName, one per line):")
        vbox_oracle.Add(lbl_oracle_in, flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8)
        self.txt_oracle_in = wx.TextCtrl(self.tab_oracle, style=wx.TE_MULTILINE | wx.TE_DONTWRAP)
        self.txt_oracle_in.SetFont(font)
        vbox_oracle.Add(self.txt_oracle_in, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
        self.btn_fetch = wx.Button(self.tab_oracle, label="Fetch SWIG Signature")
        self.btn_fetch.Bind(wx.EVT_BUTTON, self.OnOracleFetch)
        vbox_oracle.Add(self.btn_fetch, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=8)
        lbl_oracle_out = wx.StaticText(self.tab_oracle, label="Parsed Oracle Output:")
        vbox_oracle.Add(lbl_oracle_out, flag=wx.LEFT | wx.BOTTOM, border=8)
        self.txt_oracle_out = wx.TextCtrl(self.tab_oracle, style=wx.TE_MULTILINE | wx.TE_DONTWRAP | wx.TE_READONLY)
        self.txt_oracle_out.SetFont(font)
        self.txt_oracle_out.SetBackgroundColour(wx.Colour(20, 30, 40))
        self.txt_oracle_out.SetForegroundColour(wx.Colour(220, 220, 220))
        vbox_oracle.Add(self.txt_oracle_out, proportion=2, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
        self.tab_oracle.SetSizer(vbox_oracle)
        self.notebook.AddPage(self.tab_file, "Run from File")
        self.notebook.AddPage(self.tab_code, "Paste Code")
        self.notebook.AddPage(self.tab_output, "Output Console")
        self.notebook.AddPage(self.tab_oracle, "API Oracle")
        vbox.Add(self.notebook, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_run = wx.Button(panel, label="Run Script")
        self.btn_run.SetDefault()
        self.btn_run.Bind(wx.EVT_BUTTON, self.OnRun)
        hbox2.Add(self.btn_run, flag=wx.RIGHT, border=10)
        self.btn_close = wx.Button(panel, label="Close")
        self.btn_close.Bind(wx.EVT_BUTTON, self.OnClose)
        hbox2.Add(self.btn_close)
        vbox.Add(hbox2, flag=wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, border=10)
        panel.SetSizer(vbox)
        self.CenterOnScreen()
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnTabChanged)

        # Shared execution namespace: OPT-IN only. The manual "Run" button
        # always uses this (a human tracking their own context is a
        # different situation from an agent that might not), and agent
        # calls only use it if they explicitly pass --keep-state. Agent
        # calls default to a brand new namespace every time so nothing can
        # silently leak between calls - see _execute()'s use_shared param.
        self.shared_globals = globals().copy()
        self.shared_globals['__name__'] = '__main__'

        self._server_socket = None
        self._server_thread = None
        self._server_running = False
        self.start_agent_server()

    def log_debug(self, msg):
        try:
            with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            pass

    def start_agent_server(self):
        """Start a loopback-only TCP server used by kicad_agent_bridge.py.
        Binding to port 0 lets the OS pick a free port; that port is
        published to a small discovery file so the client can find it.
        Every launch overwrites the port file with a fresh port, so a
        stale file from a crashed previous session just causes the next
        client connection attempt to fail cleanly (handled on the CLI
        side) rather than silently doing the wrong thing.
        The accept loop handles one connection fully before accepting the
        next, so requests are naturally serialized on the OS's own TCP
        backlog - no locks, no shared mutable files, no clobbering.
        """
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            srv.listen(5)
            srv.settimeout(0.5)
            self._server_socket = srv
            port = srv.getsockname()[1]
            with open(PORT_FILE, "w", encoding="utf-8") as f:
                f.write(str(port))
            self._server_running = True
            self._server_thread = threading.Thread(target=self._serve_forever, daemon=True)
            self._server_thread.start()
        except Exception as e:
            msg = f"abIDE: could not start agent bridge server: {e}"
            wx.LogWarning(msg)
            self.log_debug(msg)

    def stop_agent_server(self):
        self._server_running = False
        try:
            if self._server_socket:
                self._server_socket.close()
        except Exception:
            pass
        try:
            if os.path.exists(PORT_FILE):
                os.remove(PORT_FILE)
        except Exception:
            pass

    def _serve_forever(self):
        while self._server_running:
            try:
                conn, _addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self._handle_agent_connection(conn)
            except Exception as e:
                self.log_debug(f"Unhandled error in agent connection: {e}\n{traceback.format_exc()}")

    @staticmethod
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

    @staticmethod
    def _send_json(sock, obj):
        try:
            sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))
        except Exception:
            pass

    def _handle_agent_connection(self, conn):
        with conn:
            conn.settimeout(10)
            try:
                raw = self._recv_line(conn)
            except socket.timeout:
                return
            if not raw:
                return
            try:
                req = json.loads(raw.decode("utf-8"))
            except Exception as e:
                self._send_json(conn, {"status": "error", "output": f"Bad request JSON: {e}"})
                return
            mode = req.get("mode", "execute")
            timeout = float(req.get("timeout", 30.0))
            keep_state = bool(req.get("keep_state", False))
            reset_state = bool(req.get("reset_state", False))
            done = threading.Event()
            result = {"status": "error", "output": "Internal error: no result produced."}
            def run_on_main():
                try:
                    if reset_state:
                        self.shared_globals = globals().copy()
                        self.shared_globals['__name__'] = '__main__'
                    if mode == "reset":
                        result["status"] = "success"
                        result["output"] = "Shared persistent state cleared."
                    elif mode == "oracle":
                        out = self._run_oracle_for_agent(req.get("oracle_query", ""))
                        result["status"] = "success"
                        result["output"] = out
                    else:
                        out, ok = self._run_code_for_agent(req.get("code", ""), keep_state)
                        result["status"] = "success" if ok else "error"
                        result["output"] = out
                except Exception as e:
                    err = f"Internal error while executing on main thread: {e}\n{traceback.format_exc()}"
                    result["status"] = "error"
                    result["output"] = err
                    self.log_debug(err)
                finally:
                    done.set()
            wx.CallAfter(run_on_main)
            finished = done.wait(timeout=timeout + 5)
            if not finished:
                self._send_json(conn, {
                    "status": "error",
                    "output": ("Execution did not finish within the timeout. KiCad's main "
                               "thread may still be busy running it - check the Output "
                               "Console tab in abIDE. Avoid infinite loops / long sleeps.")
                })
                return
            self._send_json(conn, result)

    def _run_code_for_agent(self, code_str, keep_state):
        """Runs agent-submitted code on the main thread and updates the GUI.
        Stateless by default (fresh namespace, nothing can leak in from a
        previous call) - keep_state=True reuses the shared namespace
        instead, the same one the manual 'Run' button uses. Returns
        (output_text, success)."""
        if not code_str:
            msg = "Error: no code provided by agent."
            self.txt_output.SetValue(msg)
            self.notebook.SetSelection(2)
            return msg, False
        self.txt_code.SetValue(code_str)
        self.notebook.SetSelection(2)
        tag = "[KEEP-STATE]" if keep_state else "[STATELESS]"
        self.txt_output.AppendText(f"\n[{time.strftime('%H:%M:%S')}] [AI AGENT EXECUTED CODE] {tag}\n")
        return self._execute(code_str=code_str, is_file_mode=False, use_shared=keep_state)

    def _run_oracle_for_agent(self, query):
        if not query:
            msg = "Error: no oracle query provided by agent."
            self.txt_oracle_out.SetValue(msg)
            return msg
        self.txt_oracle_in.SetValue(query)
        self.notebook.SetSelection(3)
        return self._execute_oracle(query)

    def _execute(self, path="", code_str="", is_file_mode=False, use_shared=True):
        """Core execution routine. Returns (output_text, success).
        use_shared=True runs against self.shared_globals, which persists
        across calls like a REPL - this is what the manual 'Run' button
        always uses. use_shared=False (the agent default) runs against a
        brand new namespace built fresh for this call only, so nothing
        from a previous call can leak in."""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured_output = io.StringIO()
        sys.stdout = captured_output
        sys.stderr = captured_output
        success = False
        error_tb = ""
        script_dir = None
        old_argv = sys.argv
        if use_shared:
            globals_dict = self.shared_globals
        else:
            globals_dict = globals().copy()
            globals_dict['__name__'] = '__main__'
        had_file = '__file__' in globals_dict
        old_file = globals_dict.get('__file__')

        # --- WATCHDOG SETUP ---
        start_time = time.time()
        instruction_count = [0]
        timeout_seconds = 15.0

        def trace_calls(frame, event, arg):
            instruction_count[0] += 1
            if instruction_count[0] > 1000:
                instruction_count[0] = 0
                if time.time() - start_time > timeout_seconds:
                    raise Exception(f"Execution timed out ({timeout_seconds}s limit exceeded). Killed by abIDE Watchdog to prevent KiCad freeze.")
            return trace_calls

        old_trace = sys.gettrace()
        sys.settrace(trace_calls)
        # ----------------------

        try:
            if is_file_mode:
                sys.argv = [path]
                script_dir = os.path.dirname(path)
                sys.path.insert(0, script_dir)
                with open(path, 'r', encoding='utf-8') as f:
                    file_code = f.read()
                code_obj = compile(file_code, path, 'exec')
                globals_dict['__file__'] = path
                exec(code_obj, globals_dict)
            else:
                code_obj = compile(code_str, '<Code Snippet>', 'exec')
                exec(code_obj, globals_dict)
            pcbnew.UpdateUserInterface()
            pcbnew.Refresh()
            success = True
        except Exception:
            error_tb = traceback.format_exc()
        finally:
            sys.settrace(old_trace)
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.argv = old_argv
            if script_dir and script_dir in sys.path:
                sys.path.remove(script_dir)
            # __file__ must never linger in a namespace beyond the run that
            # set it - restore whatever was there before (usually nothing),
            # regardless of which namespace we just ran against.
            if is_file_mode:
                if had_file:
                    globals_dict['__file__'] = old_file
                else:
                    globals_dict.pop('__file__', None)
        out_text = captured_output.getvalue()
        if error_tb:
            out_text += "\n--- EXECUTION ERROR ---\n" + error_tb
        self.txt_output.SetValue(out_text)
        self.notebook.SetSelection(2)
        return out_text, success

    def _execute_oracle(self, input_text):
        if not input_text:
            return ""
        self.txt_oracle_out.SetValue("Loading pcbnew.py...")
        self.Update()
        try:
            import pcbnew
            pcbnew_path = pcbnew.__file__
            if pcbnew_path.endswith('.pyc') or pcbnew_path.endswith('.pyo'):
                pcbnew_path = pcbnew_path[:-1]
            if not os.path.exists(pcbnew_path):
                out = f"Error: Could not find pcbnew.py at {pcbnew_path}"
                self.txt_oracle_out.SetValue(out)
                return out
            with open(pcbnew_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            lines = [l.strip() for l in input_text.split('\n') if l.strip()]
            output_text = ""
            for line in lines:
                parts = line.split(' ')
                if len(parts) >= 2:
                    class_name = parts[0]
                    method_name = parts[1]
                    output_text += self._get_kicad_signature(file_content, class_name, method_name) + '\n'
                else:
                    output_text += f"[Invalid format: \"{line}\"] -> Please use \"ClassName MethodName\"\n\n"
            self.txt_oracle_out.SetValue(output_text)
            return output_text
        except Exception:
            err_msg = f"Error: {traceback.format_exc()}"
            self.txt_oracle_out.SetValue(err_msg)
            return err_msg

    def _get_kicad_signature(self, file_content, class_name, method_name):
        import re
        if not class_name or not method_name:
            return ""
            
        def extract_docstring(method_body):
            doc_match = re.search(r'^[ \t]*def[^\n]+:\s*r?(?:"""|\'\'\')[\s\S]*?(?:"""|\'\'\')', method_body, re.MULTILINE)
            if doc_match:
                return doc_match.group(0)
            lines = method_body.split('\n')
            if len(lines) > 1:
                return lines[0] + '\n' + lines[1]
            return lines[0]
            
        if class_name.upper() in ["GLOBAL", "NONE"]:
            method_regex = re.compile(rf'(?:^|\n)[ \t]*def {method_name}\b[\s\S]*?(?=(?:\n[ \t]*def |\n[ \t]*class |$))')
            match = method_regex.search(file_content)
            if not match:
                return f"[GLOBAL.{method_name}] -> GLOBAL FUNCTION NOT FOUND.\n"
            final_output = extract_docstring(match.group(0).strip())
            return f"[GLOBAL.{method_name}] EXACT SWIG OUTPUT:\n{final_output.strip()}\n"
            
        queue = [class_name]
        visited_classes = set()
        
        while queue:
            current_class = queue.pop(0)
            if current_class in visited_classes or current_class == 'object':
                continue
            visited_classes.add(current_class)
            
            class_regex = re.compile(rf'(?:^|\n)class {current_class}\b(?:\(([^)]+)\))?:')
            class_match = class_regex.search(file_content)
            
            if not class_match:
                if current_class == class_name:
                    return f"[{class_name}.{method_name}] -> CLASS '{current_class}' NOT FOUND.\n"
                continue
                
            class_start_index = class_match.start()
            next_class_index = file_content.find('\nclass ', class_start_index + 1)
            if next_class_index == -1:
                next_class_index = len(file_content)
            class_body = file_content[class_start_index:next_class_index]
            
            method_regex = re.compile(rf'(?:^|\n)[ \t]*def {method_name}\b[\s\S]*?(?=(?:\n[ \t]*def |\n[ \t]*class |$))')
            method_match = method_regex.search(class_body)
            
            if method_match:
                final_output = extract_docstring(method_match.group(0).strip())
                result = f"[{current_class}.{method_name}] EXACT SWIG OUTPUT:\n{final_output.strip()}\n"
                if current_class != class_name:
                    result = f"(Inherited from base class: {current_class})\n" + result
                return result
                
            if class_match.group(1):
                parents = [p.strip() for p in class_match.group(1).split(',')]
                queue.extend(parents)
                
        return f"[{class_name}.{method_name}] -> METHOD NOT FOUND.\n"

    def OnTabChanged(self, event):
        sel = self.notebook.GetSelection()
        show_buttons = (sel in [0, 1])
        if hasattr(self, 'btn_run') and hasattr(self, 'btn_close'):
            self.btn_run.Show(show_buttons)
            self.btn_close.Show(show_buttons)
            self.btn_run.GetParent().Layout()
        event.Skip()

    def OnBrowse(self, event):
        wildcard = "Python files (*.py)|*.py"
        dialog = wx.FileDialog(
            self, message="Choose a file",
            defaultDir=os.getcwd(), 
            defaultFile="",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        )
        if dialog.ShowModal() == wx.ID_OK:
            self.txt_path.SetValue(dialog.GetPath())
        dialog.Destroy()

    def OnRun(self, event):
        active_tab = self.notebook.GetSelection()
        path = self.txt_path.GetValue().strip()
        code_str = self.txt_code.GetValue().strip()
        is_file_mode = (active_tab == 0)
        if active_tab == 2:
            if not path and code_str:
                is_file_mode = False
            elif path:
                is_file_mode = True
            else:
                is_file_mode = False
        if active_tab == 1:
            is_file_mode = False
        if is_file_mode:
            if not path or not os.path.exists(path):
                wx.MessageBox("Please select a valid Python script file.", "File Not Found", wx.OK | wx.ICON_ERROR, self)
                return
        else:
            if not code_str:
                wx.MessageBox("Please enter some Python code to run.", "Empty Code", wx.OK | wx.ICON_ERROR, self)
                return
        self._execute(path=path, code_str=code_str, is_file_mode=is_file_mode, use_shared=True)

    def OnOracleFetch(self, event):
        input_text = self.txt_oracle_in.GetValue().strip()
        self._execute_oracle(input_text)

    def OnClose(self, event):
        self.Close()

    def OnCloseWindow(self, event):
        self.stop_agent_server()
        event.Skip()



class ScriptRunnerPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "abIDE"
        self.category = "Utility"
        self.description = "Select and run any external board python script or paste code directly"
        self.show_toolbar_button = True
    def Run(self):
        frame = ScriptRunnerFrame(None)
        frame.Show()
