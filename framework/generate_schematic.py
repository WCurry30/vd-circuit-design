import json
import os
import sys
import uuid
import math
import re
import sexpdata 
from collections import defaultdict

LOCAL_LIB_NAME = "Project_Lib"
GRID_STEP = 1.27  

PREDEFINED_POWER_SYMBOLS = {
    "GND": """(symbol "Project_Lib:GND" (power) (pin_numbers hide) (pin_names (offset 0) hide) (in_bom yes) (on_board yes)
        (property "Reference" "#PWR" (at 0 -6.35 0) (effects (font (size 1.27 1.27)) (hide yes)))
        (property "Value" "GND" (at 0 -3.81 0) (effects (font (size 1.27 1.27))))
        (symbol "GND_0_1" (polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27)) (stroke (width 0) (type default)) (fill (type none))))
        (symbol "GND_1_1" (pin power_in line (at 0 0 270) (length 0) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27))))))
    )""",
    "VCC": """(symbol "Project_Lib:VCC" (power) (pin_numbers hide) (pin_names (offset 0) hide) (in_bom yes) (on_board yes)
        (property "Reference" "#PWR" (at 0 -3.81 0) (effects (font (size 1.27 1.27)) (hide yes)))
        (property "Value" "VCC" (at 0 3.556 0) (effects (font (size 1.27 1.27))))
        (symbol "VCC_0_1" (polyline (pts (xy -0.762 1.27) (xy 0 2.54)) (stroke (width 0) (type default)) (fill (type none))) (polyline (pts (xy 0 0) (xy 0 2.54)) (stroke (width 0) (type default)) (fill (type none))) (polyline (pts (xy 0 2.54) (xy 0.762 1.27)) (stroke (width 0) (type default)) (fill (type none))))
        (symbol "VCC_1_1" (pin power_in line (at 0 0 90) (length 0) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27))))))
    )""",
    "PWR_FLAG": """(symbol "Project_Lib:PWR_FLAG" (power) (pin_numbers hide) (pin_names (offset 0) hide) (in_bom yes) (on_board yes)
        (property "Reference" "#FLG" (at 0 1.905 0) (effects (font (size 1.27 1.27)) (hide yes)))
        (property "Value" "PWR_FLAG" (at 0 3.81 0) (effects (font (size 1.27 1.27))))
        (symbol "PWR_FLAG_0_0" (pin power_out line (at 0 0 90) (length 0) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27))))))
        (symbol "PWR_FLAG_0_1" (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.27 1.27) (xy 0 2.54) (xy 1.27 1.27) (xy 0 1.27)) (stroke (width 0) (type default)) (fill (type none))))
    )"""
}

class SchematicGenerator:
    def __init__(self):
        self.start_x, self.start_y = 38.1, 50.8
        self.page_width = 350.0
        self.retrieved_data = {}

        self.components = []
        self.nets = {}

        self.active_components = set()
        self.comp_centers = {}
        self.pin_offsets = {}
        self.abs_pins = {}

        self.parsed_wires = []
        self.drawn_wires = []
        self.power_instances = []
        self.input_ports = []   # 🔥 \u65b0\u589e：\u8f93\u5165\u7aef\u53e3\u5217\u8868
        self.output_ports = []  # 🔥 \u65b0\u589e：\u8f93\u51fa\u7aef\u53e3\u5217\u8868
        self.force_junctions = []
        self.used_powers = set()

    def _snap(self, val):
        return round(round(val / 1.27) * 1.27, 3)

    def load_data(self, retrieved_path, netlist_path):
        print(f"\n   📂 [\u539f\u7406\u56fe\u751f\u6210\u5668] \u52a0\u8f7d\u6570\u636e\u6587\u4ef6...")

        with open(retrieved_path, 'r', encoding='utf-8') as f:
            self.retrieved_data = json.load(f)

        # \u8fc7\u6ee4\u6389\u68c0\u7d22\u5931\u8d25\u7684\u5143\u4ef6
        valid_components = {uid: info for uid, info in self.retrieved_data.items() if info is not None}
        print(f"      - \u68c0\u7d22\u6570\u636e: {len(valid_components)}/{len(self.retrieved_data)} \u4e2a\u6709\u6548\u5143\u5668\u4ef6")

        with open(netlist_path, 'r', encoding='utf-8') as f:
            netlist_data = json.load(f)

        self.nets = netlist_data.get("nets", {})
        print(f"      - \u7f51\u7edc\u8868: {len(self.nets)} \u4e2a\u7f51\u7edc")

        raw_components = netlist_data.get("components", [])
        
        self.components = []
        for c in raw_components:
            if isinstance(c, str):
                self.components.append(c)
            elif isinstance(c, dict):
                uid = c.get('ref') or c.get('id') or c.get('name') or c.get('uid') or c.get('designator')
                if uid: self.components.append(str(uid))

        if not self.components:
            extracted_uids = set()
            for net_name, pins in self.nets.items():
                for pin in pins:
                    if isinstance(pin, str) and ":" in pin:
                        extracted_uids.add(pin.split(":")[0])
            self.components = list(extracted_uids)

    def _parse_pins_from_sexpr(self, sexpr_str):
        pins = {}
        try:
            parsed = sexpdata.loads(sexpr_str)
            def recurse(data):
                for item in data:
                    if isinstance(item, list) and len(item) > 0:
                        if isinstance(item[0], sexpdata.Symbol) and item[0].value() == 'pin':
                            try:
                                at_block = [x for x in item if isinstance(x, list) and x[0].value() == 'at'][0]
                                num_block = [x for x in item if isinstance(x, list) and x[0].value() == 'number'][0]
                                pins[str(num_block[1])] = (float(at_block[1]), float(at_block[2]))
                            except: pass
                        else: recurse(item)
            recurse(parsed)
        except: pass
        return pins

    def _norm_pin(self, p_str):
        """\u6807\u51c6\u5316\u5f15\u811a\u5b57\u7b26\u4e32，\u4f46\u4fdd\u6301 UID \u539f\u59cb\u5927\u5c0f\u5199"""
        result = str(p_str).replace(" ", "").replace("：", ":").strip()
        # \u4e0d\u8f6c\u5927\u5199，\u4fdd\u6301\u539f\u59cb\u5927\u5c0f\u5199
        return result

    def _classify_power_net(self, net_name: str) -> str:
        """
        \u667a\u80fd\u7535\u6e90\u7f51\u7edc\u8bc6\u522b
        \u8fd4\u56de: 'VCC', 'GND', \u6216 None（\u975e\u7535\u6e90\u7f51\u7edc）
        """
        net_upper = str(net_name).upper().strip()

        # VCC \u7c7b\u7f51\u7edc\u522b\u540d
        vcc_aliases = ['VCC', '+5V', 'VDD', '+9V', '+12V', '3V3', '3.3V', '5V', '12V',
                       '+3V3', '+3.3V', 'VCC_5V', 'VCC_3V3', 'POWER', '+VCC', 'AVCC', 'DVCC']

        # GND \u7c7b\u7f51\u7edc\u522b\u540d - \u5305\u542b SPICE \u6807\u51c6\u5730\u8282\u70b9 "0"
        gnd_aliases = ['GND', '0', '0V', 'VSS', 'AGND', 'DGND', 'GROUND', 'GND_PWR',
                       'EARTH', 'PGND', 'SGND', 'CHASSIS', 'GNDA', 'GNDD']

        if net_upper in [a.upper() for a in vcc_aliases]:
            return 'VCC'
        if net_upper in [a.upper() for a in gnd_aliases]:
            return 'GND'

        # \u6b63\u5219\u5339\u914d\u6570\u5b57\u7535\u538b\u683c\u5f0f（\u5982 +9V, 5V, 12V）
        if re.match(r'^[+]?\d+\.?\d*V$', net_upper):
            return 'VCC'

        return None

    def _extract_wires_from_nets(self):
        """
        \u4ece\u7f51\u7edc\u8868\u63d0\u53d6\u8fde\u7ebf\u4fe1\u606f
        🔥 \u589e\u5f3a：\u6269\u5c55\u7535\u6e90\u7f51\u7edc\u8bc6\u522b + \u8bca\u65ad\u65e5\u5fd7 + \u591a\u683c\u5f0f\u517c\u5bb9
        """
        wires = []
        total_nets = 0
        total_pins = 0
        power_nets = 0
        signal_nets = 0

        print(f"\n   🔧 [\u8fde\u7ebf\u63d0\u53d6] \u5f00\u59cb\u89e3\u6790\u7f51\u7edc\u8868...")

        if self.nets:
            # 🔥 \u5173\u952e\u4fee\u590d：\u652f\u6301\u5217\u8868\u683c\u5f0f\u7684 nets
            nets_dict = self.nets
            if isinstance(self.nets, list):
                # \u683c\u5f0f: [{"name": "VCC", "connections": [...]}, ...]
                nets_dict = {}
                for item in self.nets:
                    if isinstance(item, dict):
                        net_name = item.get("name") or item.get("net_name")
                        pin_list = item.get("connections") or item.get("pins") or item.get("pins_list")
                        if net_name and pin_list:
                            nets_dict[net_name] = pin_list
                print(f"      🔄 \u5df2\u8f6c\u6362\u5217\u8868\u683c\u5f0f\u7f51\u7edc\u4e3a\u5b57\u5178\u683c\u5f0f ({len(nets_dict)} \u4e2a\u7f51\u7edc)")

            for net_name, pin_list in nets_dict.items():
                total_nets += 1

                if not isinstance(pin_list, list):
                    print(f"      ⚠️ \u7f51\u7edc '{net_name}' \u5f15\u811a\u5217\u8868\u683c\u5f0f\u9519\u8bef: {type(pin_list)}")
                    continue

                valid_pins = []
                for p in pin_list:
                    if isinstance(p, str) and ':' in p:
                        valid_pins.append(self._norm_pin(p))
                        total_pins += 1
                    elif isinstance(p, dict):
                        for val in p.values():
                            if isinstance(val, str) and ':' in val:
                                valid_pins.append(self._norm_pin(val))
                                total_pins += 1
                                break

                if not valid_pins:
                    print(f"      ⚠️ \u7f51\u7edc '{net_name}' \u6ca1\u6709\u6709\u6548\u5f15\u811a")
                    continue

                # 🔥 \u4f7f\u7528\u667a\u80fd\u7535\u6e90\u7f51\u7edc\u8bc6\u522b
                power_type = self._classify_power_net(net_name)

                if power_type:
                    power_nets += 1
                    self.used_powers.add(power_type)
                    for pin in valid_pins:
                        wires.append({'from': pin, 'to': power_type})
                    print(f"      🔌 \u7535\u6e90\u7f51\u7edc '{net_name}' -> {power_type} ({len(valid_pins)} \u5f15\u811a)")
                else:
                    signal_nets += 1
                    if len(valid_pins) >= 2:
                        for i in range(len(valid_pins) - 1):
                            wires.append({'from': valid_pins[i], 'to': valid_pins[i+1]})
                        print(f"      🔗 \u4fe1\u53f7\u7f51\u7edc '{net_name}' ({len(valid_pins)} \u5f15\u811a)")
                    elif len(valid_pins) == 1:
                        # 🔥 \u65b0\u589e：\u5904\u7406\u5355\u5f15\u811a\u8f93\u5165/\u8f93\u51fa\u7f51\u7edc
                        net_upper = net_name.upper()
                        if net_upper in ['IN', 'INPUT', 'VIN', 'SIGNAL_IN', 'N_IN']: # <- \u8fd9\u91cc\u52a0\u4e0a N_IN
                            wires.append({'from': 'INPUT_PORT', 'to': valid_pins[0]})
                            print(f"      📥 \u8f93\u5165\u7f51\u7edc '{net_name}' -> \u6dfb\u52a0\u8f93\u5165\u7aef\u53e3")
                        elif net_upper in ['OUT', 'OUTPUT', 'VOUT', 'SIGNAL_OUT', 'N_OUT']: # <- \u8fd9\u91cc\u52a0\u4e0a N_OUT
                            wires.append({'from': valid_pins[0], 'to': 'OUTPUT_PORT'})
                            print(f"      📤 \u8f93\u51fa\u7f51\u7edc '{net_name}' -> \u6dfb\u52a0\u8f93\u51fa\u7aef\u53e3")
                        else:
                            print(f"      ⚠️ \u7f51\u7edc '{net_name}' \u53ea\u67091\u4e2a\u5f15\u811a，\u65e0\u6cd5\u8fde\u7ebf")

        print(f"\n   📊 [\u8fde\u7ebf\u7edf\u8ba1]")
        print(f"      - \u603b\u7f51\u7edc\u6570: {total_nets}")
        print(f"      - \u7535\u6e90\u7f51\u7edc: {power_nets}")
        print(f"      - \u4fe1\u53f7\u7f51\u7edc: {signal_nets}")
        print(f"      - \u603b\u5f15\u811a\u6570: {total_pins}")
        print(f"      - \u751f\u6210\u8fde\u7ebf: {len(wires)}")

        return wires

    def process_and_layout(self):
        self.parsed_wires = self._extract_wires_from_nets()
        for w in self.parsed_wires:
            try:
                if 'from' in w and ':' in str(w['from']): 
                    self.active_components.add(self._norm_pin(w['from']).split(':')[0])
                if 'to' in w and ':' in str(w['to']): 
                    self.active_components.add(self._norm_pin(w['to']).split(':')[0])
            except: pass

        for comp in self.components:
            self.active_components.add(comp)

        for uid in self.active_components:
            if uid not in self.retrieved_data or not self.retrieved_data[uid]: continue
            self.pin_offsets[uid] = self._parse_pins_from_sexpr(self.retrieved_data[uid].get('raw_symbol_definition', ''))

        curr_x, curr_y = self.start_x, self.start_y
        for uid in self.active_components:
            if uid in ['GND', 'VCC', '+5V', 'VDD', 'VSS']: continue
            if uid not in self.retrieved_data: continue

            if curr_x > self.page_width - 30.0:
                curr_x = self.start_x
                curr_y = self._snap(curr_y + 50.8) 
            
            self.comp_centers[uid] = (curr_x, curr_y)
            self.abs_pins[uid] = {}
            
            for pin_num, (ox, oy) in self.pin_offsets.get(uid, {}).items():
                px = round(curr_x + ox, 4)
                py = round(curr_y - oy, 4)
                self.abs_pins[uid][pin_num] = (px, py)
            curr_x = self._snap(curr_x + 40.64)

    def route_connections(self):
        for wire in self.parsed_wires:
            try:
                src_raw = self._norm_pin(wire['from'])
                dst_raw = self._norm_pin(wire['to'])

                # \u5904\u7406\u8f93\u5165\u7aef\u53e3（INPUT_PORT -> \u5f15\u811a）
                if src_raw.upper() == 'INPUT_PORT':
                    if ':' in dst_raw:
                        dst_comp, dst_pin = dst_raw.split(':')
                        if dst_comp in self.abs_pins and dst_pin in self.abs_pins[dst_comp]:
                            end_abs = self.abs_pins[dst_comp][dst_pin]
                            # \u521b\u5efa\u8f93\u5165\u7aef\u53e3\u8fde\u7ebf（\u4ece\u5de6\u8fb9\u5f15\u51fa）
                            port_x = round(end_abs[0] - 10.16, 4)
                            port_y = round(end_abs[1], 4)
                            self.drawn_wires.append(((port_x, port_y), (end_abs[0], end_abs[1])))
                            self.input_ports.append({'name': 'IN', 'x': port_x, 'y': port_y})
                    continue

                # \u5904\u7406\u8f93\u51fa\u7aef\u53e3（\u5f15\u811a -> OUTPUT_PORT）
                if dst_raw.upper() == 'OUTPUT_PORT':
                    if ':' in src_raw:
                        src_comp, src_pin = src_raw.split(':')
                        if src_comp in self.abs_pins and src_pin in self.abs_pins[src_comp]:
                            start_abs = self.abs_pins[src_comp][src_pin]
                            # \u521b\u5efa\u8f93\u51fa\u7aef\u53e3\u8fde\u7ebf（\u5411\u53f3\u8fb9\u5f15\u51fa）
                            port_x = round(start_abs[0] + 10.16, 4)
                            port_y = round(start_abs[1], 4)
                            self.drawn_wires.append(((start_abs[0], start_abs[1]), (port_x, port_y)))
                            self.output_ports.append({'name': 'OUT', 'x': port_x, 'y': port_y})
                    continue

                src_comp, src_pin = src_raw.split(':')

                if src_comp not in self.abs_pins or src_pin not in self.abs_pins[src_comp]: continue
                start_abs = self.abs_pins[src_comp][src_pin]
                start_q = (start_abs[0], start_abs[1])

                # \u5904\u7406\u7535\u6e90\u7f51\u7edc\u8fde\u63a5（\u4f7f\u7528\u5927\u5199\u5339\u914d）
                dst_upper = dst_raw.upper()
                if dst_upper in ['VCC', 'GND', '+5V', 'VDD', 'VSS', '+9V', '+12V', '0', '0V']:
                    pwr_type = "VCC" if dst_upper in ['VCC', '+5V', 'VDD', '+9V', '+12V'] else "GND"
                    offset_y = -5.08 if pwr_type == "VCC" else 5.08

                    pwr_x = round(start_abs[0], 4)
                    pwr_y = round(start_abs[1] + offset_y, 4)

                    self.drawn_wires.append((start_q, (pwr_x, pwr_y)))
                    self.power_instances.append({'type': pwr_type, 'x': pwr_x, 'y': pwr_y})
                    self.force_junctions.append((pwr_x, pwr_y))
                    continue

                if ':' in dst_raw:
                    dst_comp, dst_pin = dst_raw.split(':')
                    if dst_comp not in self.abs_pins or dst_pin not in self.abs_pins[dst_comp]: continue
                    end_abs = self.abs_pins[dst_comp][dst_pin]
                    end_q = (end_abs[0], end_abs[1])

                    esc_x_start = self._snap(start_abs[0] + (5.08 if start_abs[0] > self.comp_centers[src_comp][0] else -5.08))
                    esc_start = (esc_x_start, start_q[1])

                    esc_x_end = self._snap(end_abs[0] + (5.08 if end_abs[0] > self.comp_centers[dst_comp][0] else -5.08))
                    esc_end = (esc_x_end, end_q[1])

                    net_hash = (hash(wire['from']) + hash(wire['to'])) % 6
                    safe_y = self._snap(max(start_q[1], end_q[1]) + 15.24 + (net_hash * 2.54))

                    pt1 = esc_start
                    pt2 = (esc_start[0], safe_y)
                    pt3 = (esc_end[0], safe_y)
                    pt4 = esc_end

                    self.drawn_wires.append((start_q, pt1))
                    self.drawn_wires.append((pt1, pt2))
                    self.drawn_wires.append((pt2, pt3))
                    self.drawn_wires.append((pt3, pt4))
                    self.drawn_wires.append((pt4, end_q))
            except Exception as e:
                pass

    def _point_on_segment(self, p, a, b):
        px, py = round(p[0], 2), round(p[1], 2)
        ax, ay = round(a[0], 2), round(a[1], 2)
        bx, by = round(b[0], 2), round(b[1], 2)
        if abs(ax - bx) < 0.01:
            if abs(px - ax) < 0.01:
                return min(ay, by) - 0.01 <= py <= max(ay, by) + 0.01
        elif abs(ay - by) < 0.01:
            if abs(py - ay) < 0.01:
                return min(ax, bx) - 0.01 <= px <= max(ax, bx) + 0.01
        return False

    def _generate_junctions(self):
        point_counts = {}
        endpoints = set()
        for (p1, p2) in self.drawn_wires:
            q1 = (round(p1[0], 2), round(p1[1], 2))
            q2 = (round(p2[0], 2), round(p2[1], 2))
            point_counts[q1] = point_counts.get(q1, 0) + 1
            point_counts[q2] = point_counts.get(q2, 0) + 1
            endpoints.add(q1)
            endpoints.add(q2)

        junctions = set([pt for pt, count in point_counts.items() if count > 2])
        for ep in endpoints:
            for (a, b) in self.drawn_wires:
                qa = (round(a[0], 2), round(a[1], 2))
                qb = (round(b[0], 2), round(b[1], 2))
                if ep == qa or ep == qb: continue
                if self._point_on_segment(ep, a, b):
                    junctions.add(ep)
                    break 
        return list(junctions)

    def _process_raw_symbol(self, raw_sym, full_lib_id):
        """
        🔥 \u667a\u80fd\u591a\u5355\u5143\u5408\u5e76 (\u4fee\u590d\u57fa\u7840\u56fe\u5f62\u4e22\u5931 Bug \u7248)
        """
        if not raw_sym: return None
        base_lib_id = full_lib_id.split(':')[-1]
        
        match = re.search(r'\(\s*symbol\s+"([^"]+)"', raw_sym)
        if not match: return raw_sym
        orig_parent = match.group(1)

        raw_sym = raw_sym.replace(f'(symbol "{orig_parent}"', f'(symbol "{full_lib_id}"', 1)

        blocks = raw_sym.split(f'(symbol "{orig_parent}_')
        new_sym = blocks[0]
        
        for block in blocks[1:]:
            header = block.split('"', 1)[0]
            if len(header.split('_')) == 2:
                unit_idx, style = header.split('_')
                
                # 👇 【\u6838\u5fc3\u4fee\u590d】：Unit 0 \u662f\u6240\u6709\u57fa\u7840\u5143\u4ef6（\u963b\u5bb9\u4e8c\u6781\u7ba1\u7b49）\u7684\u516c\u5171\u56fe\u5f62！\u7edd\u4e0d\u80fd\u9690\u85cf！
                if unit_idx == '0':
                    new_sym += f'(symbol "{base_lib_id}_0_{style}' + block[len(header):]
                
                elif unit_idx == '1':
                    new_sym += f'(symbol "{base_lib_id}_1_{style}' + block[len(header):]
                
                else:
                    # \u5bf9\u4e8e Unit 2 \u53ca\u4ee5\u4e0a\u7684\u9644\u52a0\u5355\u5143 (\u591a\u5355\u5143\u5668\u4ef6)
                    # \u589e\u52a0\u4e86 circle \u548c arc \u7684\u5224\u65ad，\u9632\u6b62\u7535\u611f/\u6676\u4f53\u7ba1\u5916\u58f3\u88ab\u8bef\u5224
                    if 'polyline' not in block and 'rectangle' not in block and 'circle' not in block and 'arc' not in block:
                        # \u7eaf\u5f15\u811a\u5355\u5143（\u5982\u8fd0\u653e\u7684\u9690\u5f62\u7535\u6e90\u811a），\u5f3a\u884c\u5408\u5e76\u5230\u4e3b Unit 1
                        new_sym += f'(symbol "{base_lib_id}_1_{style}' + block[len(header):]
                    else:
                        # \u5e26\u6709\u91cd\u590d\u5916\u58f3\u7684\u95f2\u7f6e\u901a\u9053（\u5982\u53cc\u8fd0\u653e\u7684\u7b2c\u4e8c\u901a\u9053），\u653e\u9010\u9690\u85cf
                        new_sym += f'(symbol "{base_lib_id}_99_{style}' + block[len(header):]
            else:
                new_sym += f'(symbol "{orig_parent}_' + block
                
        return new_sym

    def generate_kicad_file(self, output_path):
        print(f"🔧 [SchGen] \u7ec4\u88c5\u6700\u7ec8 KiCad \u539f\u7406\u56fe...")
        content = ['(kicad_sch (version 20231120) (generator "AI_EDA_Pipeline")', '  (paper "A4")']
        lib_content = ['  (lib_symbols']
        inst_content, wire_content, junction_content = [], [], []
        defined_symbols = set()

        for uid in self.active_components:
            if uid in ['GND', 'VCC', '+5V', 'VDD', 'VSS']: continue
            if uid not in self.retrieved_data: continue
            info = self.retrieved_data[uid]
            base_lib_id = info.get('lib_id', uid)
            full_lib_id = f"{LOCAL_LIB_NAME}:{base_lib_id}"
            
            raw_sym = info.get('raw_symbol_definition', '')
            if full_lib_id not in defined_symbols:
                if raw_sym:
                    # \u5728\u5b58\u5165\u5185\u90e8\u5e93\u65f6，\u5143\u4ef6\u5df2\u7ecf\u88ab\u538b\u5e73\u4e3a\u5355\u4f53\u4e86
                    lib_content.append(self._process_raw_symbol(raw_sym, full_lib_id))
                defined_symbols.add(full_lib_id)

            cx, cy = self.comp_centers[uid]
            final_val = info.get('planned_value', base_lib_id)
            
            # 🔥 \u6781\u7b80\u4e3b\u4e49：\u4e0d\u7ba1\u662f\u4ec0\u4e48\u5143\u4ef6，\u6211\u53ea\u653e\u7f6e 1 \u6b21！\u7edd\u5bf9\u6ca1\u6709\u91cd\u53e0，\u6ca1\u6709\u9519\u4e71\u4f4d\u79fb！
            sym_uuid = str(uuid.uuid4())
            inst_content.append(f'  (symbol (lib_id "{full_lib_id}") (at {cx:.4f} {cy:.4f} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {sym_uuid})')
            inst_content.append(f'    (property "Reference" "{uid}" (id 0) (at {cx:.4f} {cy - 7.62:.4f} 0) (effects (font (size 1.27 1.27))))')
            inst_content.append(f'    (property "Value" "{final_val}" (id 1) (at {cx:.4f} {cy + 7.62:.4f} 0) (effects (font (size 1.27 1.27))))')
            inst_content.append(f'    (instances (project "" (path "/" (reference "{uid}") (unit 1))))')
            inst_content.append(f'  )')

        # 🔥 \u5904\u7406\u7535\u6e90\u4e0e\u5168\u5c40 PWR_FLAG，\u62ef\u6551 "\u8f93\u5165\u7535\u6e90\u672a\u53d7\u9a71\u52a8" \u7684\u62a5\u9519
        for p_type in self.used_powers:
            flag_id = f"{LOCAL_LIB_NAME}:PWR_FLAG"
            if flag_id not in defined_symbols:
                lib_content.append(PREDEFINED_POWER_SYMBOLS["PWR_FLAG"])
                defined_symbols.add(flag_id)
            
            flag_x = 300.0
            flag_y = 20.0 if p_type == 'VCC' else 30.0
            flag_uuid = str(uuid.uuid4())
            flag_ref = f"#FLG0{len(defined_symbols)}"
            
            inst_content.append(f'  (symbol (lib_id "{flag_id}") (at {flag_x:.4f} {flag_y:.4f} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {flag_uuid})')
            inst_content.append(f'    (property "Reference" "{flag_ref}" (id 0) (at {flag_x:.4f} {flag_y:.4f} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
            inst_content.append(f'    (property "Value" "PWR_FLAG" (id 1) (at {flag_x:.4f} {flag_y + 3.81:.4f} 0) (effects (font (size 1.27 1.27))))')
            inst_content.append(f'    (instances (project "" (path "/" (reference "{flag_ref}") (unit 1))))')
            inst_content.append(f'  )')
            
            sym_id = f"{LOCAL_LIB_NAME}:{p_type}"
            if sym_id not in defined_symbols:
                lib_content.append(PREDEFINED_POWER_SYMBOLS[p_type])
                defined_symbols.add(sym_id)
            sym_y = flag_y - 5.08 if p_type == 'VCC' else flag_y + 5.08
            pwr_uuid = str(uuid.uuid4())
            pwr_ref = f"#PWR{pwr_uuid[:4].upper()}"
            
            inst_content.append(f'  (symbol (lib_id "{sym_id}") (at {flag_x:.4f} {sym_y:.4f} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {pwr_uuid})')
            inst_content.append(f'    (property "Reference" "{pwr_ref}" (id 0) (at {flag_x:.4f} {sym_y:.4f} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
            inst_content.append(f'    (property "Value" "{p_type}" (id 1) (at {flag_x:.4f} {sym_y + 3.81:.4f} 0) (effects (font (size 1.27 1.27))))')
            inst_content.append(f'    (instances (project "" (path "/" (reference "{pwr_ref}") (unit 1))))')
            inst_content.append(f'  )')
            wire_content.append(f'  (wire (pts (xy {flag_x:.4f} {flag_y:.4f}) (xy {flag_x:.4f} {sym_y:.4f})) (stroke (width 0) (type default)) (uuid {str(uuid.uuid4())}))')

        for pwr in self.power_instances:
            full_pwr_id = f"{LOCAL_LIB_NAME}:{pwr['type']}"
            if full_pwr_id not in defined_symbols:
                lib_content.append(PREDEFINED_POWER_SYMBOLS[pwr['type']])
                defined_symbols.add(full_pwr_id)
            val_offset = 2.54 if pwr['type'] == 'GND' else 3.81
            pwr_uuid = str(uuid.uuid4())
            pwr_ref = f"#PWR{pwr_uuid[:4].upper()}"
            
            inst_content.append(f'  (symbol (lib_id "{full_pwr_id}") (at {pwr["x"]:.4f} {pwr["y"]:.4f} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {pwr_uuid})')
            inst_content.append(f'    (property "Reference" "{pwr_ref}" (id 0) (at {pwr["x"]:.4f} {pwr["y"]:.4f} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
            inst_content.append(f'    (property "Value" "{pwr["type"]}" (id 1) (at {pwr["x"]:.4f} {pwr["y"] + val_offset:.4f} 0) (effects (font (size 1.27 1.27))))')
            inst_content.append(f'    (instances (project "" (path "/" (reference "{pwr_ref}") (unit 1))))')
            inst_content.append(f'  )')

        for ((x1, y1), (x2, y2)) in self.drawn_wires:
            if abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01: continue
            wire_content.append(f'  (wire (pts (xy {x1:.4f} {y1:.4f}) (xy {x2:.4f} {y2:.4f})) (stroke (width 0) (type default)) (uuid {str(uuid.uuid4())}))')
            
        all_junctions = set(self._generate_junctions() + self.force_junctions)
        for (jx, jy) in all_junctions:
            junction_content.append(f'  (junction (at {jx:.4f} {jy:.4f}) (diameter 0) (color 0 0 0 0) (uuid {str(uuid.uuid4())}))')

        # ====================================================================
        # 🔥 \u65b0\u589e：\u5904\u7406\u60ac\u7a7a\u7684\u8f93\u5165/\u8f93\u51fa\u7aef\u53e3\u6807\u7b7e，\u751f\u6210 KiCad Global Labels
        # ====================================================================
        label_content = []
        
        # 1. \u6e32\u67d3\u8f93\u5165\u7aef\u53e3 (\u8fde\u63a5\u5728\u5bfc\u7ebf\u5de6\u4fa7，\u6587\u5b57\u5411\u5de6\u5bf9\u9f50)
        for port in self.input_ports:
            port_uuid = str(uuid.uuid4())
            label_content.append(
                f'  (global_label "{port["name"]}" (shape input) '
                f'(at {port["x"]:.4f} {port["y"]:.4f} 180) (fields_autoplaced) '
                f'(effects (font (size 1.27 1.27)) (justify right)) (uuid {port_uuid}))'
            )
            
        # 2. \u6e32\u67d3\u8f93\u51fa\u7aef\u53e3 (\u8fde\u63a5\u5728\u5bfc\u7ebf\u53f3\u4fa7，\u6587\u5b57\u5411\u53f3\u5bf9\u9f50)
        for port in self.output_ports:
            port_uuid = str(uuid.uuid4())
            label_content.append(
                f'  (global_label "{port["name"]}" (shape output) '
                f'(at {port["x"]:.4f} {port["y"]:.4f} 0) (fields_autoplaced) '
                f'(effects (font (size 1.27 1.27)) (justify left)) (uuid {port_uuid}))'
            )
        # ====================================================================

        lib_content.append('  )')
        content.extend(lib_content)
        content.extend(wire_content)
        content.extend(junction_content)
        content.extend(label_content)  # 🔥 \u65b0\u589e：\u786e\u4fdd\u6807\u7b7e\u5185\u5bb9\u88ab\u5199\u5165\u6587\u4ef6！
        content.extend(inst_content)
        content.append('  (sheet_instances (path "/" (page "1")) )\n)')

        with open(output_path, 'w', encoding='utf-8') as f: f.write('\n'.join(content))
        print(f"✅ [SchGen] \u539f\u7406\u56fe\u5df2\u751f\u6210！")
    
    def _generate_dynamic_pwr_symbols(self):
        """
        \u52a8\u6001\u8bc6\u522b\u7535\u8def\u4e2d\u7684\u7535\u6e90\u7f51\u7edc，\u5e76\u4e3a\u6bcf\u4e2a\u7f51\u7edc\u751f\u6210\u5bf9\u5e94\u7684\u7535\u6e90\u7b26\u53f7\u548c PWR_FLAG。
        """
        pwr_content = []
        # 1. \u5b9a\u4e49\u6211\u4eec\u5173\u5fc3\u7684\u7535\u6e90\u7f51\u7edc\u5173\u952e\u5b57（\u5305\u542b\u5927\u6a21\u578b\u53ef\u80fd\u751f\u6210\u7684\u53d8\u4f53）
        pwr_keywords = {
            'VCC': 'power:VCC',
            'VEE': 'power:VEE',
            'VDD': 'power:VDD',
            'VSS': 'power:VSS',
            'GND': 'power:GND',
            '0': 'power:GND',  # SPICE \u4e2d\u7684 0 \u901a\u5e38\u5bf9\u5e94 GND
        }

        # 2. \u627e\u51fa\u5f53\u524d\u7f51\u7edc\u8868\u4e2d\u5b9e\u9645\u5b58\u5728\u7684\u7535\u6e90\u7f51\u7edc
        active_pwr_nets = []
        for net_name in self.nets.keys():
            upper_name = net_name.upper()
            if upper_name in pwr_keywords:
                active_pwr_nets.append((net_name, pwr_keywords[upper_name]))

        # 3. \u7ed8\u5236\u5750\u6807\u8bbe\u5b9a（\u653e\u7f6e\u5728\u56fe\u7eb8\u53f3\u4fa7，\u907f\u514d\u4e0e\u4e3b\u7535\u8def\u91cd\u53e0）
        start_x = 270.0  # \u56fe\u7eb8\u53f3\u4fa7\u8fb9\u7f18
        start_y = 50.0
        spacing = 20.0   # \u6bcf\u4e2a\u7535\u6e90\u7ec4\u4e4b\u95f4\u7684\u95f4\u8ddd

        for i, (net_name, lib_id) in enumerate(active_pwr_nets):
            curr_y = start_y + (i * spacing)
            
            # --- A. \u751f\u6210\u5bf9\u5e94\u7684\u7535\u6e90\u7b26\u53f7 (\u5982 VCC, VEE, GND) ---
            symbol_uuid = str(uuid.uuid4())
            pwr_content.append(f"""
  (symbol (lib_id "{lib_id}") (at {start_x} {curr_y} 0) (unit 1)
    (in_bom no) (on_board yes) (fields_autoplaced)
    (uuid {symbol_uuid})
    (property "Reference" "#PWR{i}" (at {start_x} {curr_y + 3} 0)
      (effects (font (size 1.27 1.27)) hide)
    )
    (property "Value" "{net_name}" (at {start_x} {curr_y + 3} 0)
      (effects (font (size 1.27 1.27)))
    )
    (pin "1" (uuid {str(uuid.uuid4())}))
  )""")

            # --- B. \u751f\u6210\u5bf9\u5e94\u7684 PWR_FLAG (\u8fd9\u662f\u89e3\u51b3 ERC \u62a5\u9519\u7684\u5173\u952e) ---
            # \u5c06 PWR_FLAG \u653e\u7f6e\u5728\u7535\u6e90\u7b26\u53f7\u4e0a\u65b9\u4e00\u70b9\u70b9，\u5e76\u7528\u5bfc\u7ebf\u8fde\u63a5
            flag_uuid = str(uuid.uuid4())
            flag_y = curr_y - 5.0  # \u7a0d\u5fae\u5f80\u4e0a\u4e00\u70b9
            
            pwr_content.append(f"""
  (symbol (lib_id "power:PWR_FLAG") (at {start_x} {flag_y} 0) (unit 1)
    (in_bom no) (on_board yes) (fields_autoplaced)
    (uuid {flag_uuid})
    (property "Reference" "#FLG{i}" (at {start_x} {flag_y + 3} 0)
      (effects (font (size 1.27 1.27)) hide)
    )
    (property "Value" "PWR_FLAG" (at {start_x} {flag_y + 3} 0)
      (effects (font (size 1.27 1.27)) hide)
    )
    (pin "1" (uuid {str(uuid.uuid4())}))
  )""")

            # --- C. \u753b\u4e00\u6839\u77ed\u7ebf\u5c06\u7535\u6e90\u7b26\u53f7\u4e0e PWR_FLAG \u8fde\u63a5\u8d77\u6765 ---
            pwr_content.append(f'  (wire (pts (xy {start_x} {curr_y}) (xy {start_x} {flag_y})) (stroke (width 0) (type solid)) (uuid {str(uuid.uuid4())}))')

        return pwr_content

if __name__ == "__main__":
    pass