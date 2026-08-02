## 🛠️ KiCad Skill Redirect

If the user asks you to design, route, or modify a PCB in this workspace, you MUST NOT attempt to do it blindly. 
Instead, you MUST immediately read `.agents/skills/kicad_autonomous_flow/SKILL.md` and strictly follow the KiCad Autonomous Flow protocols.

##  Global Library Protection
**NEVER** configure global footprint or symbol libraries in the user's `AppData` directory (e.g. `fp-lib-table` in roaming). All KiCad libraries (like LCSC assets) must be downloaded and mapped locally inside the current active project folder to prevent naming collisions and cross-project hallucination.

##  Zero Scratch Script Policy
When executing Python scripts inside KiCad via the bridge, **DO NOT** use `write_to_file` to create temporary `.py` scratch files on the disk. You must always pipe your generated code directly into the KiCad environment via standard input (e.g. using a PowerShell Heredoc). Persistent project artifacts (`task.md`, YAML blueprints, state snapshots) are expected and allowed.
