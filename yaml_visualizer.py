#!/usr/bin/env python3
"""
yaml_visualizer.py - Renders a circuit_blueprint YAML into an interactive
HTML schematic using real KiCad symbol geometry from .kicad_sym files.

Usage:
    python yaml_visualizer.py <blueprint.yaml> [output.html] [--sym <path_to.kicad_sym>]

If output path is omitted, saves to same directory as the YAML as 'blueprint_view.html'.
If --sym is omitted, looks for <YAML_DIR>/libs/easyeda2kicad/easyeda2kicad.kicad_sym.
"""

import sys
import os
import re
import math

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

SCALE = 15  # pixels per KiCad mm unit (2.54mm grid -> 38.1px)

# Wire colors per connection category
WIRE_COLORS = {
    'power':   '#f76707',  # orange-red
    'analog':  '#ae3ec9',  # purple
    'digital': '#1c7ed6',  # blue
    'pwm':     '#0ca678',  # teal
    'bus':     '#37b24d',  # green
    'net':     '#e8590c',  # deep orange
}

# Node fill colors per component category
NODE_COLORS = {
    'mcu':      ('#ffd43b', '#f08c00'),  # (fill, stroke)
    'sensor':   ('#a5d8ff', '#1971c2'),
    'driver':   ('#d0bfff', '#7048e8'),
    'module':   ('#b2f2bb', '#2f9e44'),
    'actuator': ('#ffc9c9', '#e03131'),
    'passive':  ('#dee2e6', '#495057'),
    'power':    ('#ffe066', '#e67700'),
    'other':    ('#e7f5ff', '#1c7ed6'),
}


# ═══════════════════════════════════════════════════════════════════════════
# S-EXPRESSION HELPERS (copied from footprint_extractor.py for consistency)
# ═══════════════════════════════════════════════════════════════════════════

from sexp_utils import _find_matching_close, _extract_blocks


# ═══════════════════════════════════════════════════════════════════════════
# YAML PARSER (PyYAML first, regex fallback)
# ═══════════════════════════════════════════════════════════════════════════

def load_yaml(filepath):
    """Load a circuit_blueprint YAML file.
    Tries PyYAML first; falls back to regex extraction."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()

    # --- Attempt 1: PyYAML ---
    try:
        import yaml
        data = yaml.safe_load(raw)
        if isinstance(data, dict) and 'circuit_blueprint' in data:
            return data['circuit_blueprint']
        return data
    except ImportError:
        pass
    except Exception:
        pass  # corrupt YAML, try fallback

    # --- Attempt 2: Regex fallback ---
    return _parse_yaml_fallback(raw)


def _parse_yaml_fallback(raw):
    """Minimal regex-based YAML parser for the abIDE blueprint schema."""
    result = {
        'metadata': {},
        'components': {},
        'passive_components': [],
        'power_distribution': {},
        'signal_routing': {'analog_signals': [], 'digital_signals': [], 'pwm_signals': []},
        'signal_nets': [],
        'communication_buses': {'I2C': [], 'SPI': [], 'UART': []},
    }

    # --- Metadata ---
    for key in ('project_name', 'description', 'main_controller'):
        m = re.search(key + r':\s*"?([^"\n]+)"?', raw)
        if m and m.group(1).strip() != 'null':
            result['metadata'][key] = m.group(1).strip()

    # --- Components (inline dict format) ---
    #   MCU1: { type: "Microcontroller", model: "ESP32", lcsc_id: "C2913202" }
    for m in re.finditer(r'^\s+(\w+\d+)\s*:\s*\{([^}]+)\}', raw, re.MULTILINE):
        comp_id = m.group(1)
        inner = m.group(2)
        comp = {}
        for kv in re.finditer(r'(\w+)\s*:\s*"([^"]*)"', inner):
            comp[kv.group(1)] = kv.group(2)
        if comp:
            result['components'][comp_id] = comp

    # --- Passive components ---
    pas_section = re.search(r'passive_components:\s*\n((?:\s+[-\s].*\n)*)', raw)
    if pas_section:
        for entry in re.split(r'(?=\s+- id:)', pas_section.group(1)):
            comp = {}
            for kv in re.finditer(r'(\w+)\s*:\s*"([^"]*)"', entry):
                comp[kv.group(1)] = kv.group(2)
            if comp.get('id'):
                result['passive_components'].append(comp)

    # --- Power distribution ---
    pwr_section = re.search(r'power_distribution:\s*\n((?:\s+.*\n)*?)(?=\n\s{2}\w|\Z)', raw)
    if pwr_section:
        block = pwr_section.group(1)
        for net_m in re.finditer(r'^\s{4}(\w+):\s*$', block, re.MULTILINE):
            net_name = net_m.group(1)
            # Find source and connections after this net name
            after = block[net_m.end():]
            src_m = re.search(r'source:\s*"([^"]*)"', after)
            conn_m = re.search(r'connections:\s*\[([^\]]*)\]', after)
            source = src_m.group(1) if src_m else ''
            connections = re.findall(r'"([^"]+)"', conn_m.group(1)) if conn_m else []
            result['power_distribution'][net_name] = {
                'source': source, 'connections': connections
            }

    # --- Signal routing ---
    for sig_type in ('analog_signals', 'digital_signals', 'pwm_signals'):
        section = re.search(sig_type + r':\s*\n((?:\s+[-\s].*\n)*)', raw)
        if not section:
            continue
        for entry in re.split(r'(?=\s+- source:)', section.group(1)):
            sig = {}
            src_m = re.search(r'source:\s*"([^"]*)"', entry)
            dst_m = re.search(r'destination:\s*"([^"]*)"', entry)
            pur_m = re.search(r'purpose:\s*"([^"]*)"', entry)
            if src_m: sig['source'] = src_m.group(1)
            if dst_m: sig['destination'] = dst_m.group(1)
            if pur_m: sig['purpose'] = pur_m.group(1)
            if sig.get('source') and sig.get('destination'):
                result['signal_routing'][sig_type].append(sig)

    # --- Signal nets ---
    nets_section = re.search(r'signal_nets:\s*\n((?:\s+[-\s].*\n)*)', raw)
    if nets_section:
        for entry in re.split(r'(?=\s+- net_name:)', nets_section.group(1)):
            net = {}
            nm = re.search(r'net_name:\s*"([^"]*)"', entry)
            pm = re.search(r'purpose:\s*"([^"]*)"', entry)
            mm = re.search(r'members:\s*\[([^\]]*)\]', entry)
            if nm: net['net_name'] = nm.group(1)
            if pm: net['purpose'] = pm.group(1)
            net['members'] = re.findall(r'"([^"]+)"', mm.group(1)) if mm else []
            if net.get('net_name') and net.get('members'):
                result['signal_nets'].append(net)

    # --- Communication buses ---
    for bus_type in ('I2C', 'SPI', 'UART'):
        bus_section = re.search(bus_type + r':\s*\n((?:\s+[-\s].*\n)*)', raw)
        if not bus_section:
            continue
        for entry in re.split(r'(?=\s+- bus_id:)', bus_section.group(1)):
            bus = {'bus_id': '', 'lines': []}
            bid = re.search(r'bus_id:\s*"([^"]*)"', entry)
            if bid: bus['bus_id'] = bid.group(1)
            line_pat = re.compile(
                r'(\w+):\s*\{[^}]*source:\s*"([^"]*)"[^}]*destinations:\s*\[([^\]]*)\][^}]*\}'
            )
            for lm in line_pat.finditer(entry):
                if lm.group(1) == 'bus_id':
                    continue
                bus['lines'].append({
                    'name': lm.group(1),
                    'source': lm.group(2),
                    'destinations': re.findall(r'"([^"]+)"', lm.group(3)),
                })
            if bus['bus_id']:
                result['communication_buses'][bus_type].append(bus)

    return result


# ═══════════════════════════════════════════════════════════════════════════
# .kicad_sym PARSER (Symbol Geometry + LCSC ID Mapping)
# ═══════════════════════════════════════════════════════════════════════════

def parse_kicad_sym(filepath):
    """Parse a .kicad_sym file and return:
        symbols:  { symbol_name: { primitives: [...], pins: {...} } }
        lcsc_map: { lcsc_id: symbol_name }  (reverse lookup)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    symbols = {}
    lcsc_map = {}  # "C2913202" -> "ESP32-WROOM-32"

    for block in _extract_blocks(content, 'symbol'):
        name_m = re.match(r'\(symbol\s+"([^"]+)"', block)
        if not name_m:
            continue
        name = name_m.group(1)

        # Skip library wrapper and sub-symbols
        if name == 'kicad_symbol_lib':
            continue
        if re.search(r'_\d+_\d+$', name):
            continue

        # --- Extract LCSC Part property (for reverse lookup) ---
        lcsc_m = re.search(
            r'\(property\s+"LCSC\s+Part"\s+"(C\d+)"',
            block, re.IGNORECASE
        )
        if lcsc_m:
            lcsc_map[lcsc_m.group(1)] = name

        primitives = []
        pins = {}

        # --- Rectangles ---
        for rect in _extract_blocks(block, 'rectangle'):
            start_m = re.search(r'\(start\s+([-\d.]+)\s+([-\d.]+)\)', rect)
            end_m = re.search(r'\(end\s+([-\d.]+)\s+([-\d.]+)\)', rect)
            if start_m and end_m:
                primitives.append({
                    'type': 'rect',
                    'x1': float(start_m.group(1)),
                    'y1': float(start_m.group(2)),
                    'x2': float(end_m.group(1)),
                    'y2': float(end_m.group(2)),
                })

        # --- Polylines ---
        for poly in _extract_blocks(block, 'polyline'):
            pts_m = re.search(r'\(pts\s+(.*?)\)', poly, re.DOTALL)
            if pts_m:
                points = []
                for xy in re.finditer(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)', pts_m.group(1)):
                    points.append((float(xy.group(1)), float(xy.group(2))))
                if points:
                    # Check fill type
                    filled = bool(re.search(r'\(fill\s+\(type\s+background\)', poly))
                    primitives.append({
                        'type': 'polyline',
                        'points': points,
                        'filled': filled,
                    })

        # --- Circles ---
        for circ in _extract_blocks(block, 'circle'):
            center_m = re.search(r'\(center\s+([-\d.]+)\s+([-\d.]+)\)', circ)
            radius_m = re.search(r'\(radius\s+([-\d.]+)\)', circ)
            if center_m and radius_m:
                primitives.append({
                    'type': 'circle',
                    'cx': float(center_m.group(1)),
                    'cy': float(center_m.group(2)),
                    'r': float(radius_m.group(1)),
                })

        # --- Arcs ---
        for arc in _extract_blocks(block, 'arc'):
            start_m = re.search(r'\(start\s+([-\d.]+)\s+([-\d.]+)\)', arc)
            mid_m = re.search(r'\(mid\s+([-\d.]+)\s+([-\d.]+)\)', arc)
            end_m = re.search(r'\(end\s+([-\d.]+)\s+([-\d.]+)\)', arc)
            if start_m and end_m:
                primitives.append({
                    'type': 'arc',
                    'x1': float(start_m.group(1)),
                    'y1': float(start_m.group(2)),
                    'x2': float(end_m.group(1)),
                    'y2': float(end_m.group(2)),
                    'mx': float(mid_m.group(1)) if mid_m else 0,
                    'my': float(mid_m.group(2)) if mid_m else 0,
                })

        # --- Pins ---
        #
        # CRITICAL PIN GEOMETRY (verified against real .kicad_sym files):
        #   (pin <type> <shape> (at <TIP_X> <TIP_Y> <ANGLE>) (length <L>) ...)
        #
        # - (at x y angle) = the pin TIP position (where wires connect)
        # - The pin STUB extends FROM the tip TOWARD the component body
        # - angle 0   = stub extends to the RIGHT  (+X direction)
        # - angle 90  = stub extends UPWARD         (+Y in KiCad = -Y in SVG)
        # - angle 180 = stub extends to the LEFT    (-X direction)
        # - angle 270 = stub extends DOWNWARD       (-Y in KiCad = +Y in SVG)
        #
        # Body-end formula (KiCad coords):
        #   body_x = tip_x + cos(angle_rad) * length
        #   body_y = tip_y + sin(angle_rad) * length
        #
        for pin_block in _extract_blocks(block, 'pin'):
            at_m = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)', pin_block)
            len_m = re.search(r'\(length\s+([-\d.]+)\)', pin_block)
            name_m = re.search(r'\(name\s+"([^"]*)"', pin_block)
            num_m = re.search(r'\(number\s+"([^"]*)"', pin_block)

            if at_m and len_m and name_m:
                pin_name = name_m.group(1)
                pins[pin_name] = {
                    'tip_x': float(at_m.group(1)),
                    'tip_y': float(at_m.group(2)),
                    'angle': float(at_m.group(3)),
                    'length': float(len_m.group(1)),
                    'number': num_m.group(1) if num_m else '',
                }

        symbols[name] = {'primitives': primitives, 'pins': pins}

    return symbols, lcsc_map


# ═══════════════════════════════════════════════════════════════════════════
# COMPONENT CATEGORY CLASSIFIER
# ═══════════════════════════════════════════════════════════════════════════

def _classify(comp_id):
    """Classify component by its ID prefix."""
    prefixes = {
        'MCU': 'mcu', 'SEN': 'sensor', 'DRV': 'driver',
        'MOD': 'module', 'ACT': 'actuator', 'PSU': 'power', 'PAS': 'passive',
    }
    for prefix, cat in prefixes.items():
        if comp_id.upper().startswith(prefix):
            return cat
    return 'other'


# ═══════════════════════════════════════════════════════════════════════════
# DUMMY SYMBOL GENERATOR (when .kicad_sym data is missing)
# ═══════════════════════════════════════════════════════════════════════════

def _pad_sort_key(n):
    try: return (0, int(n), '')
    except ValueError: return (1, 0, n)

def _generate_dummy_symbol(comp_id, pin_names_needed):
    """Create a generic rectangular symbol with evenly-spaced pins.

    pin_names_needed: set of pin names that this component must have
                      (collected from YAML connection references).
    """
    pin_list = sorted(pin_names_needed, key=_pad_sort_key) if pin_names_needed else ['1', '2']
    n_pins = len(pin_list)
    half = (n_pins + 1) // 2

    # Body size
    body_w = 5.08  # mm
    body_h = max(5.08, half * 2.54 + 2.54)  # mm, scales with pin count

    primitives = [{
        'type': 'rect',
        'x1': -body_w / 2, 'y1': body_h / 2,
        'x2': body_w / 2,  'y2': -body_h / 2,
    }]

    pins = {}
    # Left-side pins (angle 0 = stub extends right toward body)
    for i in range(half):
        pin_name = pin_list[i] if i < len(pin_list) else str(i + 1)
        y = body_h / 2 - 2.54 - i * 2.54
        pins[pin_name] = {
            'tip_x': -(body_w / 2 + 2.54),
            'tip_y': y,
            'angle': 0,
            'length': 2.54,
            'number': pin_name,
        }
    # Right-side pins (angle 180 = stub extends left toward body)
    for i in range(half, n_pins):
        pin_name = pin_list[i]
        y = body_h / 2 - 2.54 - (i - half) * 2.54
        pins[pin_name] = {
            'tip_x': body_w / 2 + 2.54,
            'tip_y': y,
            'angle': 180,
            'length': 2.54,
            'number': pin_name,
        }

    return {'primitives': primitives, 'pins': pins}


# ═══════════════════════════════════════════════════════════════════════════
# COLLECT ALL PIN REFERENCES FROM YAML (for dummy symbol generation)
# ═══════════════════════════════════════════════════════════════════════════

def _collect_pin_refs(blueprint):
    """Scan the entire YAML blueprint and return a dict:
       { 'MCU1': {'GND', 'IO4', '3V3'}, 'SEN1': {'VCC', 'DATA', 'GND'}, ... }
    """
    refs = {}

    def add_ref(pin_ref):
        if not isinstance(pin_ref, str) or '.' not in pin_ref:
            return
        comp_id, pin_name = pin_ref.split('.', 1)
        refs.setdefault(comp_id, set()).add(pin_name)

    # Power distribution
    for net_data in (blueprint.get('power_distribution') or {}).values():
        if isinstance(net_data, dict):
            add_ref(net_data.get('source', ''))
            for c in (net_data.get('connections') or []):
                add_ref(c)

    # Signal routing
    for sig_type in ('analog_signals', 'digital_signals', 'pwm_signals'):
        for sig in ((blueprint.get('signal_routing') or {}).get(sig_type) or []):
            if isinstance(sig, dict):
                add_ref(sig.get('source', ''))
                add_ref(sig.get('destination', ''))

    # Signal nets
    for net in (blueprint.get('signal_nets') or []):
        if isinstance(net, dict):
            for member in (net.get('members') or []):
                add_ref(member)

    # Communication buses
    for bus_type in ('I2C', 'SPI', 'UART'):
        for bus in ((blueprint.get('communication_buses') or {}).get(bus_type) or []):
            if isinstance(bus, dict):
                for line in (bus.get('lines') or []):
                    if isinstance(line, dict):
                        add_ref(line.get('source', ''))
                        for d in (line.get('destinations') or []):
                            add_ref(d)
                # Also check direct key format (SDA, SCL, etc.)
                for key in ('SDA', 'SCL', 'MOSI', 'MISO', 'SCK', 'CS', 'TX', 'RX'):
                    val = bus.get(key)
                    if isinstance(val, dict):
                        add_ref(val.get('source', ''))
                        for d in (val.get('destinations') or []):
                            add_ref(d)

    return refs


# ═══════════════════════════════════════════════════════════════════════════
# LAYOUT ENGINE (Grid-based, upgradeable to force-directed later)
# ═══════════════════════════════════════════════════════════════════════════

def layout_components(blueprint, symbols, lcsc_map):
    """Place each component on a grid and resolve its symbol geometry.

    Returns:
        layout: { comp_id: { 'x': float, 'y': float, 'sym': symbol_dict } }
    """
    pin_refs = _collect_pin_refs(blueprint)

    comps = list((blueprint.get('components') or {}).items())
    for p in (blueprint.get('passive_components') or []):
        if isinstance(p, dict) and p.get('id'):
            comps.append((p['id'], p))

    # Resolve symbol for each component
    resolved = []  # list of (comp_id, symbol_dict)
    for comp_id, comp_data in comps:
        lcsc_id = comp_data.get('lcsc_id', '') if isinstance(comp_data, dict) else ''
        sym = None

        # Strategy 1: Look up by LCSC ID in the reverse map
        if lcsc_id and lcsc_id in lcsc_map:
            sym_name = lcsc_map[lcsc_id]
            sym = symbols.get(sym_name)

        # Strategy 2: Look up by model name directly as symbol name
        if not sym and isinstance(comp_data, dict):
            model = comp_data.get('model', '')
            if model and model in symbols:
                sym = symbols[model]

        # Strategy 3: Generate dummy symbol with known pins
        if not sym:
            needed_pins = pin_refs.get(comp_id, set())
            sym = _generate_dummy_symbol(comp_id, needed_pins)

        resolved.append((comp_id, sym))

    # --- Grid placement ---
    # Calculate bounding box of each symbol to determine spacing
    cols = max(1, min(4, int(math.ceil(math.sqrt(len(resolved))))))
    grid_x = 0
    grid_y = 0
    col_idx = 0
    row_max_h = 0
    layout = {}

    for comp_id, sym in resolved:
        # Calculate symbol bounds
        min_x, min_y, max_x, max_y = _symbol_bounds(sym)
        w = (max_x - min_x) * SCALE
        h = (max_y - min_y) * SCALE

        cx = grid_x + w / 2 + 80  # 80px left margin
        cy = grid_y + h / 2 + 80  # 80px top margin

        layout[comp_id] = {
            'x': cx - min_x * SCALE,  # offset so symbol (0,0) maps correctly
            'y': cy - min_y * SCALE,
            'sym': sym,
        }

        grid_x += w + 160  # 160px gap between columns
        row_max_h = max(row_max_h, h)
        col_idx += 1
        if col_idx >= cols:
            col_idx = 0
            grid_x = 0
            grid_y += row_max_h + 160  # 160px gap between rows
            row_max_h = 0

    return layout


def _symbol_bounds(sym):
    """Calculate bounding box of a symbol in KiCad coords.
    Returns (min_x, min_y, max_x, max_y) already Y-inverted for SVG."""
    xs = []
    ys = []
    for prim in sym.get('primitives', []):
        if prim['type'] == 'rect':
            xs.extend([prim['x1'], prim['x2']])
            ys.extend([-prim['y1'], -prim['y2']])
        elif prim['type'] == 'polyline':
            for px, py in prim['points']:
                xs.append(px)
                ys.append(-py)
        elif prim['type'] == 'circle':
            xs.extend([prim['cx'] - prim['r'], prim['cx'] + prim['r']])
            ys.extend([-prim['cy'] - prim['r'], -prim['cy'] + prim['r']])
    for pin in sym.get('pins', {}).values():
        xs.append(pin['tip_x'])
        ys.append(-pin['tip_y'])
    if not xs:
        return -5, -5, 5, 5
    return min(xs), min(ys), max(xs), max(ys)


# ═══════════════════════════════════════════════════════════════════════════
# SVG GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

def generate_svg(layout, blueprint):
    """Generate the complete SVG string with components and wires."""

    # --- Pass 1: Draw components, collect absolute pin locations ---
    pin_locations = {}  # "MCU1.GND" -> (abs_x, abs_y)
    comp_svg_parts = []

    for comp_id, pos in layout.items():
        sym = pos['sym']
        ox, oy = pos['x'], pos['y']
        category = _classify(comp_id)
        fill_color, stroke_color = NODE_COLORS.get(category, NODE_COLORS['other'])

        parts = []
        parts.append(f'<g transform="translate({ox:.1f}, {oy:.1f})">')

        # -- Primitives --
        for prim in sym.get('primitives', []):
            if prim['type'] == 'rect':
                x1s, y1s = prim['x1'] * SCALE, -prim['y1'] * SCALE
                x2s, y2s = prim['x2'] * SCALE, -prim['y2'] * SCALE
                rx = min(x1s, x2s)
                ry = min(y1s, y2s)
                rw = abs(x2s - x1s)
                rh = abs(y2s - y1s)
                parts.append(
                    f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" '
                    f'fill="{fill_color}" stroke="{stroke_color}" stroke-width="2" rx="3"/>'
                )
            elif prim['type'] == 'polyline':
                pts_str = ' '.join(
                    f'{px * SCALE:.1f},{-py * SCALE:.1f}' for px, py in prim['points']
                )
                pfill = fill_color if prim.get('filled') else 'none'
                parts.append(
                    f'<polyline points="{pts_str}" fill="{pfill}" '
                    f'stroke="{stroke_color}" stroke-width="2"/>'
                )
            elif prim['type'] == 'circle':
                parts.append(
                    f'<circle cx="{prim["cx"] * SCALE:.1f}" cy="{-prim["cy"] * SCALE:.1f}" '
                    f'r="{prim["r"] * SCALE:.1f}" fill="none" stroke="{stroke_color}" stroke-width="2"/>'
                )
            elif prim['type'] == 'arc':
                # Approximate arc as a polyline through start, mid, end
                pts = [
                    (prim['x1'] * SCALE, -prim['y1'] * SCALE),
                    (prim['mx'] * SCALE, -prim['my'] * SCALE),
                    (prim['x2'] * SCALE, -prim['y2'] * SCALE),
                ]
                pts_str = ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
                parts.append(
                    f'<polyline points="{pts_str}" fill="none" '
                    f'stroke="{stroke_color}" stroke-width="2"/>'
                )

        # -- Pins (Pass 1: Draw and set authoritative names) --
        for pin_name, pin in sym.get('pins', {}).items():
            tx = pin['tip_x'] * SCALE
            ty = -pin['tip_y'] * SCALE  # Y invert for SVG
            angle_rad = math.radians(pin['angle'])
            length_px = pin['length'] * SCALE

            # Body end: from tip toward component body
            bx = tx + math.cos(angle_rad) * length_px
            by = ty - math.sin(angle_rad) * length_px  # sin inverted for SVG

            # Draw pin stub
            parts.append(
                f'<line x1="{tx:.1f}" y1="{ty:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                f'stroke="#73daca" stroke-width="2"/>'
            )

            # Draw pin dot (connection point)
            parts.append(
                f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="3" fill="#73daca"/>'
            )

            # Pin label positioning (outside the component, near the tip)
            label_x, label_y = tx, ty
            anchor = 'middle'
            if pin['angle'] == 0:      # stub goes right, tip is on left
                label_x -= 8
                anchor = 'end'
            elif pin['angle'] == 180:  # stub goes left, tip is on right
                label_x += 8
                anchor = 'start'
            elif pin['angle'] == 90:   # stub goes up, tip is below
                label_y += 14
            elif pin['angle'] == 270:  # stub goes down, tip is above
                label_y -= 8

            safe_name = pin_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            parts.append(
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" '
                f'font-size="10" fill="#c0caf5" font-family="monospace">{safe_name}</text>'
            )

            # Store ABSOLUTE pin tip location for wiring (names are authoritative)
            pin_locations[f"{comp_id}.{pin_name}"] = (ox + tx, oy + ty)

        # -- Pins (Pass 2: Aliases fill gaps without overwriting) --
        for pin_name, pin in sym.get('pins', {}).items():
            num = pin.get('number')
            if not num:
                continue
            alias = f"{comp_id}.{num}"
            coord = (ox + pin['tip_x'] * SCALE, oy - pin['tip_y'] * SCALE)
            if alias in pin_locations:
                if pin_locations[alias] != coord:
                    print(f"       [WARN] ambiguous pin ref '{alias}' — name/number collide, keeping name")
                continue
            pin_locations[alias] = coord

        # -- Component ID label (above the symbol) --
        min_x, min_y, _, _ = _symbol_bounds(sym)
        title_y = min_y * SCALE - 12
        parts.append(
            f'<text x="0" y="{title_y:.1f}" text-anchor="middle" '
            f'font-size="14" font-weight="bold" fill="#ff9e64" font-family="sans-serif">'
            f'{comp_id}</text>'
        )

        parts.append('</g>')
        comp_svg_parts.append('\n'.join(parts))

    # --- Pass 2: Draw wires ---
    wire_parts = []
    unresolved_endpoints = set()

    def draw_wire(src_pin, dst_pin, label, category):
        """Draw a single wire between two pin references."""
        src_pos = pin_locations.get(src_pin)
        dst_pos = pin_locations.get(dst_pin)
        if not src_pos or not dst_pos:
            if not src_pos and src_pin: unresolved_endpoints.add(src_pin)
            if not dst_pos and dst_pin: unresolved_endpoints.add(dst_pin)
            return  # pin not found, skip silently
        sx, sy = src_pos
        dx, dy = dst_pos
        color = WIRE_COLORS.get(category, '#868e96')

        # Orthogonal routing: go right from source, then vertical, then horizontal to dest
        mid_x = (sx + dx) / 2
        wire_parts.append(
            f'<path d="M {sx:.1f} {sy:.1f} C {mid_x:.1f} {sy:.1f}, {mid_x:.1f} {dy:.1f}, {dx:.1f} {dy:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="2" opacity="0.8"/>'
        )

        # Label at midpoint
        if label:
            safe_label = label.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            lx = (sx + dx) / 2
            ly = (sy + dy) / 2 - 6
            wire_parts.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
                f'font-size="9" fill="{color}" font-family="monospace" opacity="0.9">'
                f'{safe_label}</text>'
            )

    # Power distribution wires
    for net_name, net_data in (blueprint.get('power_distribution') or {}).items():
        if not isinstance(net_data, dict):
            continue
        src = net_data.get('source', '')
        for conn in (net_data.get('connections') or []):
            draw_wire(src, conn, net_name, 'power')

    # Signal routing wires
    type_map = {'analog_signals': 'analog', 'digital_signals': 'digital', 'pwm_signals': 'pwm'}
    for sig_type, cat in type_map.items():
        for sig in ((blueprint.get('signal_routing') or {}).get(sig_type) or []):
            if isinstance(sig, dict):
                draw_wire(
                    sig.get('source', ''), sig.get('destination', ''),
                    sig.get('purpose', cat), cat
                )

    # Signal nets (star topology: first member to all others)
    for net in (blueprint.get('signal_nets') or []):
        if isinstance(net, dict):
            members = net.get('members', [])
            name = net.get('net_name', 'net')
            if len(members) >= 2:
                for member in members[1:]:
                    draw_wire(members[0], member, name, 'net')

    # Communication buses
    for bus_type in ('I2C', 'SPI', 'UART'):
        for bus in ((blueprint.get('communication_buses') or {}).get(bus_type) or []):
            if not isinstance(bus, dict):
                continue
            lines = bus.get('lines', [])
            if not lines:
                for key in ('SDA', 'SCL', 'MOSI', 'MISO', 'SCK', 'CS', 'TX', 'RX'):
                    val = bus.get(key)
                    if isinstance(val, dict):
                        lines.append({
                            'name': key,
                            'source': val.get('source', ''),
                            'destinations': val.get('destinations', []),
                        })
            for line in lines:
                if not isinstance(line, dict):
                    continue
                src = line.get('source', '')
                label = f"{bus_type} {line.get('name', '')}"
                for dst in (line.get('destinations') or []):
                    draw_wire(src, dst, label, 'bus')

    # --- Compute dynamic viewBox ---
    all_x = []
    all_y = []
    for px, py in pin_locations.values():
        all_x.append(px)
        all_y.append(py)
    if not all_x:
        all_x = [0, 800]
        all_y = [0, 600]
    margin = 100
    vx = min(all_x) - margin
    vy = min(all_y) - margin
    vw = max(all_x) - min(all_x) + margin * 2
    vh = max(all_y) - min(all_y) + margin * 2

    # --- Assemble final SVG ---
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vx:.0f} {vy:.0f} {vw:.0f} {vh:.0f}" '
        f'width="{vw:.0f}" height="{vh:.0f}" id="circuit-svg">',
    ]
    # Wires first (behind components)
    svg.append('<g class="wires">')
    svg.extend(wire_parts)
    svg.append('</g>')
    # Components on top
    svg.append('<g class="components">')
    svg.extend(comp_svg_parts)
    svg.append('</g>')
    svg.append('</svg>')
    
    unresolved_list = sorted(unresolved_endpoints)
    import json
    if unresolved_list:
        print(f"\n[WARN] {len(unresolved_list)} wire endpoints unresolved in blueprint:")
        for ep in unresolved_list[:10]:
            print(f"  - {ep}")
        if len(unresolved_list) > 10:
            print(f"  ... and {len(unresolved_list) - 10} more")
        print("These wires will not appear in the visualization.")
    print(f"RESULT: {json.dumps({'unresolved': len(unresolved_list), 'refs': unresolved_list})}\n")

    return '\n'.join(svg), unresolved_list


# ═══════════════════════════════════════════════════════════════════════════
# HTML PAGE GENERATOR (with pan/zoom)
# ═══════════════════════════════════════════════════════════════════════════

def generate_html(svg_content, metadata, unresolved=None):
    """Wrap SVG in a dark-themed HTML page with pan/zoom."""
    project = metadata.get('project_name', 'Circuit Blueprint')
    desc = metadata.get('description', '')

    # Escape for HTML
    project = project.replace('&', '&amp;').replace('<', '&lt;')
    desc = desc.replace('&', '&amp;').replace('<', '&lt;')
    
    banner = ""
    if unresolved:
        banner = f'<div style="background: #f03e3e; color: white; padding: 0.6rem 1.2rem; font-size: 0.9rem; font-weight: bold; z-index: 20; position: relative;">[WARNING] {len(unresolved)} wire endpoints unresolved! The AI must fix these before you approve the blueprint. Example missing pins: {", ".join(unresolved[:5])}</div>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project} — Blueprint Visualizer</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #1a1b26; color: #c0caf5;
    font-family: 'Segoe UI', system-ui, sans-serif;
    overflow: hidden; height: 100vh;
    display: flex; flex-direction: column;
}}
.toolbar {{
    background: #24283b; border-bottom: 1px solid #3b4261;
    padding: 0.6rem 1.2rem;
    display: flex; align-items: center; gap: 1rem;
    flex-shrink: 0; z-index: 10;
}}
.toolbar h1 {{ font-size: 1.1rem; color: #7aa2f7; }}
.toolbar p {{ font-size: 0.8rem; color: #565f89; }}
.legend {{
    display: flex; gap: 0.8rem; margin-left: auto;
    flex-wrap: wrap;
}}
.legend-item {{
    display: flex; align-items: center; gap: 0.3rem;
    font-size: 0.7rem;
}}
.legend-dot {{
    width: 10px; height: 10px; border-radius: 2px;
}}
.canvas-container {{
    flex: 1; overflow: hidden; cursor: grab;
    position: relative;
}}
.canvas-container:active {{ cursor: grabbing; }}
#svg-wrap {{
    transform-origin: 0 0;
    position: absolute; top: 0; left: 0;
}}
.hint {{
    position: fixed; bottom: 12px; right: 16px;
    font-size: 0.7rem; color: #3b4261;
}}
</style>
</head>
<body>
{banner}
<div class="toolbar">
    <div>
        <h1>{project}</h1>
        <p>{desc}</p>
    </div>
    <div class="legend">
        <div class="legend-item"><div class="legend-dot" style="background:#f76707"></div>Power</div>
        <div class="legend-item"><div class="legend-dot" style="background:#1c7ed6"></div>Digital</div>
        <div class="legend-item"><div class="legend-dot" style="background:#ae3ec9"></div>Analog</div>
        <div class="legend-item"><div class="legend-dot" style="background:#0ca678"></div>PWM</div>
        <div class="legend-item"><div class="legend-dot" style="background:#37b24d"></div>Bus</div>
        <div class="legend-item"><div class="legend-dot" style="background:#e8590c"></div>Net</div>
    </div>
</div>
<div class="canvas-container" id="canvas">
    <div id="svg-wrap">
        {svg_content}
    </div>
</div>
<div class="hint">Scroll to zoom · Drag to pan</div>
<script>
(function() {{
    const container = document.getElementById('canvas');
    const wrap = document.getElementById('svg-wrap');
    let scale = 1, panX = 0, panY = 0;
    let dragging = false, startX, startY;

    function applyTransform() {{
        wrap.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
    }}

    container.addEventListener('wheel', function(e) {{
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        const rect = container.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        panX = mx - (mx - panX) * delta;
        panY = my - (my - panY) * delta;
        scale *= delta;
        applyTransform();
    }}, {{ passive: false }});

    container.addEventListener('mousedown', function(e) {{
        dragging = true;
        startX = e.clientX - panX;
        startY = e.clientY - panY;
    }});
    window.addEventListener('mousemove', function(e) {{
        if (!dragging) return;
        panX = e.clientX - startX;
        panY = e.clientY - startY;
        applyTransform();
    }});
    window.addEventListener('mouseup', function() {{ dragging = false; }});

    applyTransform();
}})();
</script>
</body>
</html>'''


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python yaml_visualizer.py <blueprint.yaml> [output.html] [--sym path]")
        print()
        print("Example:")
        print('  python yaml_visualizer.py "C:\\MyProject\\circuit_blueprint.yaml"')
        print()
        print("Options:")
        print("  --sym <path>   Explicit path to .kicad_sym file")
        print("                 (default: <yaml_dir>/libs/easyeda2kicad/easyeda2kicad.kicad_sym)")
        sys.exit(1)

    yaml_path = sys.argv[1]
    if not os.path.isfile(yaml_path):
        print(f"ERROR: File not found: {yaml_path}")
        sys.exit(1)

    # Parse arguments
    html_path = None
    sym_path = None
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--sym' and i + 1 < len(sys.argv):
            sym_path = sys.argv[i + 1]
            i += 2
        elif not html_path:
            html_path = sys.argv[i]
            i += 1
        else:
            i += 1

    if not html_path:
        html_path = os.path.join(os.path.dirname(yaml_path), 'blueprint_view.html')

    # Auto-discover .kicad_sym if not specified
    if not sym_path:
        yaml_dir = os.path.dirname(os.path.abspath(yaml_path))
        sym_path = os.path.join(yaml_dir, 'libs', 'easyeda2kicad', 'easyeda2kicad.kicad_sym')

    # --- Pipeline ---
    print(f"[1/5] Loading blueprint: {yaml_path}")
    blueprint = load_yaml(yaml_path)

    print(f"[2/5] Parsing symbol library: {sym_path}")
    symbols = {}
    lcsc_map = {}
    if os.path.isfile(sym_path):
        symbols, lcsc_map = parse_kicad_sym(sym_path)
        print(f"       Found {len(symbols)} symbols, {len(lcsc_map)} LCSC mappings")
    else:
        print(f"       WARNING: Symbol file not found. Using dummy symbols.")

    print("[3/5] Laying out components...")
    layout = layout_components(blueprint, symbols, lcsc_map)
    print(f"       Placed {len(layout)} components")

    print("[4/5] Generating SVG...")
    svg, unresolved = generate_svg(layout, blueprint)

    metadata = blueprint.get('metadata', {}) if isinstance(blueprint.get('metadata'), dict) else {}

    print("[5/5] Generating HTML...")
    html = generate_html(svg, metadata, unresolved)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nSUCCESS: {html_path}")
    print("Open this file in a browser to view the interactive diagram.")


if __name__ == "__main__":
    main()
