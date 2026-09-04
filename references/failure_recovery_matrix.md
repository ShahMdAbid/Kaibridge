#Universal Fallback & Failure Recovery Matrix

This reference document contains the exhaustive, deterministic recovery procedures for all known KiCad 10, Freerouting, SWIG Python, and ERC/DRC failure modes within the Kaibridge 2.0 engine.

---

##1. Schematic & ERC Violations

| Violation / Error Code | Root Cause | Exact Deterministic Remedy |
|---|---|---|
| **ERC: `[pin_not_driven]` (Passive components)** | EasyEDA passive symbol has `"Input"` electrical pin type instead of `"Passive"` | Switch symbol `lib_id` to native KiCad symbol (`Device:R`, `Device:C`, `Device:LED`, `Device:D`, `Device:L`, `Connector_Generic:Conn_01x*`). Bind to official KiCad IPC footprint (`Resistor_SMD:R_0805_2012Metric`, etc.) and specify upfront LCSC ID. Never use raw EasyEDA passive symbols. |
| **ERC: `[pin_not_driven]` (Switched / Interrupted Power Rail)** | Power rail downstream of passive components (switch, push-button, Schottky diode, PTC fuse, inductor) feeding active IC `power_in` pins lacks an active driving source | Add the specific interrupted power rail name (e.g. `VIN_SW`, `VBUS_SW`, `VBAT_PROT`, `DC_IN`, `5V_FUSED`) to `"power_flags"` array in `design.json`: `"power_flags": ["<RAIL_NAME>", "GND"]`. |
| **ERC: `[pin_to_pin]` (Power Output Conflict)** | Two `power_out` pins tied to the same net, or `PWR_FLAG` mistakenly attached to an active regulator output | Remove `power_flags` from the actively driven regulator/converter output rail (e.g. `AMS1117` VOUT / `+3V3`). Regulators already have `power_out` pin types; adding a power flag causes a driver collision. |
| **ERC: `[pin_not_connected]`** | An active IC `power_in` or bidirectional pin is left floating without wiring | Either wire the pin to its appropriate rail/signal, or declare it explicitly in the `"no_connect"` array in `design.json`: `"no_connect": ["U1.5", "J1.A6", "J1.A7"]`. |
| **ERC: `[stacked_pins]` / Label Ladder Overlap** | Multiple stacked identical pins sharing the exact same coordinate (e.g. multi-GND pins on MCU or USB-C) | Only declare the single visible pin in `design.json`. KiCad internally connects all stacked pins sharing coordinates. Declaring all of them creates an illegible text ladder. Refer to [`references/stacked_pins_fix.md`](stacked_pins_fix.md). |
| **Netlist: `Symbol 'Mechanical:MountingHole' has no pins`** | User/agent selected pinless mounting hole symbol in `design.json` but tried to wire it to `GND` | Replace symbol `lib_id` with `Mechanical:MountingHole_Pad` (declares Pin 1 for electrical bonding to chassis ground). |

---

##2. Layout, DRC & Physical Violations

| Violation / Error Code | Root Cause | Exact Deterministic Remedy |
|---|---|---|
| **DRC: `[annular_width]` (0.0000mm on mechanical post holes)** | EasyEDA through-hole footprints declare plastic alignment pegs as `thru_hole` with `size == drill` (0mm copper ring) | Automatically sanitized upon fetch by `kaibridge_fetch_lcsc_component`. If encountering existing legacy footprint, convert unnumbered pads with `size == drill` from `thru_hole` to `np_thru_hole` (Non-Plated Through Hole) with `*.Mask` layer. |
| **DRC: `[copper_edge_clearance]`** | KiCad 10 default `0.50mm` copper edge clearance triggers false errors on edge connectors or perimeter pads | Inject JLCPCB production constraint (`min_copper_edge_clearance: 0.15`) into `.kicad_pro` `design_settings.rules`. Handled automatically by `compiler.py` and `router.py`. |
| **DRC: `[starved_thermal]`** | Thermal relief spokes too narrow or restricted on dense SMT pads | Use solid copper pad connections (`zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)`) with `0.2mm` minimum copper thickness when calling `kaibridge_add_ground_plane`. |
| **DRC: `[zones_intersect]`** | Multiple overlapping zones on the same layer with identical priority | Delete existing zones on that layer before pouring new plane (`kaibridge_add_ground_plane` handles this automatically). Or call `{"op": "zone.delete"}` / `kaibridge_unroute_pcb(remove_zones=True)`. |
| **DRC: `[malformed_courtyard]`** | Footprint contains zero-length or self-intersecting lines in `F.CrtYd` | Replace footprint with official KiCad IPC-7351 footprint (e.g. `Resistor_SMD:R_0805_2012Metric`). |
| **DRC: `[clearance]` (Track-to-Track / Track-to-Pad)** | Traces routed closer than design rule clearance (`0.15mm` / `0.20mm`) | Unroute affected tracks using `kaibridge_unroute_pcb(net="<NET_NAME>")` and re-route with `python kicad_route.py` (or `kaibridge_route_pcb`). |
| **DRC: `[unconnected_items]`** | Unrouted airwires remaining on board | Check if net was unrouted or pads are too cramped for routing channels. Increase board dimensions with `{"op": "board.set_size", ...}` or adjust component spacing using `kicad_layout.py` (or `kaibridge_apply_ops_layout`) on the 0.5mm grid, then re-run `python kicad_route.py` (or `kaibridge_route_pcb`). |

---

##3. Autorouter (Freerouting) & DSN Failures

| Failure Symptom | Root Cause | Exact Deterministic Remedy |
|---|---|---|
| **Freerouting: `SES_IMPORTED: 0 tracks`** | Netlist pads not bound to nets in `.kicad_pcb` | Call `python kicad_pcb_sync.py` (or `kaibridge_sync_to_pcb`) to synchronize footprints and bind nets before exporting Specctra DSN. |
| **Freerouting: All tracks routed with same width** | `.kicad_pro` missing `netclass_patterns` binding | Ensure `_ensure_netclass_patterns()` runs before `ExportSpecctraDSN`. In `design.json`, list power rails in `"netclasses.Power.nets"`. Router will automatically generate separate width classes in the DSN file. |
| **Freerouting: `OutOfMemoryError`** | Java heap space exhausted on complex multi-layer boards | Run Java Freerouting with increased heap: `java -Xmx2048m -jar freerouting.jar ...`. |
| **Freerouting: Timeout expired** | Dense placement with blocked routing channels causing endless rip-up loops | Increase component spacing or widen board outline by 10–20% using `{"op": "board.set_size", ...}`, then re-run `python kicad_route.py` (or `kaibridge_route_pcb`). |

---

##4. SWIG Python & Engine Memory Safety

| Error / Failure Symptom | Root Cause | Exact Deterministic Remedy |
|---|---|---|
| **`AttributeError: 'SwigPyObject' has no attribute...`** | Ghost C++ pointer or invalid SWIG wrapper retained across operations | Call `del board; gc.collect()`. Execute board mutations in isolated subprocesses via `load_kicad_python()`. |
| **`ModuleNotFoundError: No module named 'pcbnew'`** | Running script from standard Python interpreter rather than KiCad's bundled Python | Ensure backend tools call `load_kicad_python()` to dispatch to KiCad's bundled Python 3.11 environment (`C:\Program Files\KiCad\10.0\bin\python.exe`). Or use Kaibridge MCP tools (`kaibridge_apply_ops_layout`) instead of raw SWIG scripts. |
| **`sqlite3.OperationalError: no such table: parts`** | Raw SQL queries assuming generic table/column names in `easyeda-std.elib` | Canonical schema: Table `devices` (`uuid`, `title`), Table `attributes` (`device_uuid`, `key`, `value` where `key='Supplier Part'` contains LCSC ID). Use `kaibridge_lookup_lcsc_part` or join `devices` with `attributes WHERE key='Supplier Part'`. |
| **File Open Warning: `Project is already open...`** | Orphaned `~*.lck` lock files left by interrupted KiCad process | Kill lingering Python/KiCad background processes and delete `~*.lck` files from project folder. |
| **Corrupt / 0-byte `.kicad_pcb` file** | Write operation aborted abruptly mid-save | Call `kaibridge_restore_snapshot(tag="<previous_checkpoint>")` or restore backup `.kicad_pcb` from `kaibridge_dump/`. Never rebuild from scratch. |

---

##5. Algorithmic Dead-End Policy

If the exact same error persists across **two consecutive automated attempts** after applying the prescribed fix from this matrix:
1. **HALT Execution Immediately.** Do not loop or retry the same action.
2. Report the failing command, error message, and relevant lines of the schematic/PCB file to the user.
3. Request human guidance or clarification.
