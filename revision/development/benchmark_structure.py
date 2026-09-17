"""Explicit topology checks for the proposed synthesis tasks."""

from revision_spec import statements, _path, structural_checks


def testbench_connections(deck, checks):
    """Validate the unified benchmark's named load and supply interfaces."""
    rows = statements(deck)
    result = {}
    for index, check in enumerate(checks, 1):
        condition = check.get('condition', {})
        nodes = check['nodes']
        declared_sources = {name.upper() for name in condition.get('dc_sources', {})}
        if 'VEE' in declared_sources and declared_sources & {'VDD', 'VCC'}:
            opamps = [r for r in rows if r[0].startswith('X') and len(r) >= 7
                      and r[6] in {'LM2904', 'LM358', 'LM324', 'OPAMP'}]
            result[f'condition_{index}_opamp_dual_rail_connections'] = all(
                amp[3:5] == ['VCC', 'VEE'] for amp in opamps)
        if 'RLOAD' in condition.get('resistances', {}):
            loads = [r for r in rows if r[0] == 'RLOAD']
            expected = {nodes['output'].upper(), nodes.get('ground', '0').upper()}
            result[f'condition_{index}_load_connections'] = (
                len(loads) == 1 and set(loads[0][1:3]) == expected)
        for name in condition.get('dc_sources', {}):
            upper = name.upper()
            if upper not in {'VDD', 'VCC', 'VEE'}:
                continue
            rail = 'VEE' if upper == 'VEE' else 'VCC'
            sources = [r for r in rows if r[0] == upper]
            result[f'condition_{index}_{upper}_connections'] = (
                len(sources) == 1 and sources[0][1:3] == [rail, '0'])
    return result


def led_series_path(rows, start, end):
    """Require an unbranched directed LED chain between supply and probe."""
    leds = [r for r in rows if r[0].startswith('D') and len(r) >= 4 and r[3] == 'LED']
    node, visited = start, set()
    while node != end:
        if node in visited or node == '0':
            return False
        visited.add(node)
        outgoing = [d for d in leds if d[1] == node]
        if len(outgoing) != 1:
            return False
        node = outgoing[0][2]
        if node != end:
            # Internal series nodes cannot have a parallel or shunt branch.
            attached = []
            for row in rows:
                count = 4 if row[0].startswith('M') else 3 if row[0].startswith('Q') else len(row) - 2 if row[0].startswith('X') else 2
                if not row[0].startswith('.') and node in row[1:1 + count]:
                    attached.append(row)
            if len(attached) != 2 or any(r not in leds for r in attached):
                return False
    return bool(visited)


def topology_diagnostics(deck, topology):
    """Explain failed public-interface connections without changing acceptance."""
    if all(topology_checks(deck, topology).values()):
        return []
    rows = statements(deck)
    messages = []
    if topology in {'noninverting_ac', 'mic_preamp', 'single_supply_audio'}:
        for amp in rows:
            if not (amp[0].startswith('X') and len(amp) >= 7
                    and amp[6] in {'LM2904', 'LM358', 'LM324', 'OPAMP'}):
                continue
            messages.append(f'{amp[0]} op-amp terminals: positive_input={amp[1]}, '
                            f'negative_input={amp[2]}, positive_supply={amp[3]}, '
                            f'negative_supply={amp[4]}, output={amp[5]}.')
            if topology == 'single_supply_audio' and amp[5] == 'OUT':
                messages.append('The op-amp output is directly named OUT. The requested AC-coupled '
                                'public output must instead be on the load side of the output '
                                'coupling capacitor; use a distinct internal amplifier output node.')
        messages.append('Trace the input coupling capacitor to the positive input and its resistive '
                        'DC bias path. Check that feedback returns to the negative input of this '
                        'same amplifier and that the evaluated OUT is the requested output node.')
    if topology in {'ce', 'degenerated_ce', 'two_ce'}:
        for q in rows:
            if q[0].startswith('Q') and len(q) >= 5:
                messages.append(f'{q[0]} terminals: collector={q[1]}, base={q[2]}, emitter={q[3]}.')
                if q[1] == 'OUT':
                    messages.append('OUT is directly the collector; the requested AC-coupled output must be on the load side of the output coupling capacitor.')
        messages.append('Check the AC-coupled input/base and collector/output paths and the emitter DC return; retain the requested stage count.')
    if topology in {'opamp_nmos_led', 'two_bjt_led'}:
        probes = [r for r in rows if r[0] == 'VLOAD' and len(r) >= 4]
        leds = [r for r in rows if r[0].startswith('D') and len(r) >= 4 and r[3] == 'LED']
        if not probes:
            messages.append('The required series current probe VLOAD is missing.')
        for v in probes:
            messages.append(f'VLOAD actual terminals: positive={v[1]}, negative={v[2]}.')
            if v[2] != 'OUT':
                messages.append('VLOAD negative terminal must connect to the pass-device drain/collector at OUT, not ground.')
            if not led_series_path(rows, 'VCC', v[1]):
                messages.append('No unbranched forward LED chain connects from VCC to the positive terminal of VLOAD. Check this series supply path.')
        for d in leds:
            messages.append(f'{d[0]} LED actual terminals: anode={d[1]}, cathode={d[2]}.')
        for m in rows:
            if m[0].startswith('M') and len(m) >= 6:
                messages.append(f'{m[0]} terminals: drain={m[1]}, gate={m[2]}, source={m[3]}, bulk={m[4]}.')
        messages.append('Check the source/emitter-to-ground sense resistor and negative feedback from its upper node. Component names do not create node connections.')
    if topology in {'zener', 'loaded_zener', 'buffered_zener'}:
        zeners = [r for r in rows if r[0].startswith('D') and len(r) >= 4
                  and r[3] == '1N4733A']
        if not zeners:
            messages.append('No top-level diode uses the supplied 1N4733A Zener model.')
        for diode in zeners:
            messages.append(f'{diode[0]} Zener actual terminals: anode={diode[1]}, cathode={diode[2]}. '
                            'SPICE diode order is anode then cathode.')
            if diode[2] == '0' and diode[1] != '0':
                messages.append('This Zener has its cathode grounded. A positive shunt reference requires '
                                'reverse bias: anode at ground and cathode at the fed reference node. '
                                'Check polarity before changing resistor values.')
    return messages[:12]


def supply_diagnostics(deck):
    """Describe an unpowered public rail without inferring source-name aliases."""
    rows = statements(deck)
    uses_vcc = any('VCC' in r[1:3] for r in rows if r[0].startswith(('R', 'C', 'D')))
    sources = [r for r in rows if r[0].startswith('V') and len(r) >= 4]
    if not uses_vcc or any(r[1:3] == ['VCC', '0'] for r in sources):
        return []
    details = [f'{r[0]} connects positive={r[1]}, negative={r[2]}.' for r in sources[:4]]
    return ['No top-level voltage source connects from VCC to ground. The circuit uses '
            'the VCC node, but a source named VCC does not power that node unless its '
            'positive terminal is VCC. Check the actual supply path.'] + details


def topology_checks(deck, topology, *, reference_divider=False):
    rows = statements(deck)
    resistors = [row for row in rows if row[0].startswith('R') and len(row) >= 4]
    capacitors = [row for row in rows if row[0].startswith('C') and len(row) >= 4]
    bjts = [row for row in rows if row[0].startswith('Q') and len(row) >= 5]
    mosfets = [row for row in rows if row[0].startswith('M') and len(row) >= 6]
    opamps = [row for row in rows if row[0].startswith('X') and len(row) >= 7
              and row[6] in {'LM2904', 'LM358', 'LM324', 'OPAMP'}]

    # Ideal DC rails are AC ground, not signal paths through bias resistors.
    ac_ground = {'0'}
    for row in rows:
        if row[0].startswith('V') and len(row) >= 4 and 'AC' not in row and '0' in row[1:3]:
            ac_ground.update(row[1:3])
    signal_rows = [row for row in rows if len(row) >= 3
                   and not (set(row[1:3]) & ac_ground)]

    def edge(devices, a, b):
        return any(set(row[1:3]) == {a, b} for row in devices)

    def coupled(a, b):
        return (_path(signal_rows, a, b, capacitors=True)
                and not _path(signal_rows, a, b, capacitors=False))

    def emitter_network(node):
        seen, pending, grounded = set(), [node], False
        while pending:
            current = pending.pop()
            if current in seen or current in ac_ground:
                continue
            seen.add(current)
            for r in resistors:
                if current in r[1:3]:
                    other = r[2] if r[1] == current else r[1]
                    grounded |= other == '0'
                    if other not in ac_ground:
                        pending.append(other)
        return seen, grounded

    def biased_ce(q, unbypassed=False):
        emitter_nodes, grounded = emitter_network(q[3])
        bias = (edge(resistors, 'VCC', q[1])
                and edge(resistors, 'VCC', q[2]) and edge(resistors, q[2], '0'))
        if not bias or not grounded:
            return False
        if unbypassed:
            for start in emitter_nodes:
                visited, pending = {start}, [start]
                while pending:
                    current = pending.pop()
                    for cap in capacitors:
                        if current not in cap[1:3]:
                            continue
                        other = cap[2] if cap[1] == current else cap[1]
                        if other in ac_ground or (other in emitter_nodes and other != start):
                            return False
                        if other not in visited:
                            visited.add(other)
                            pending.append(other)
        return True

    def zener(node):
        return any(row[0].startswith('D') and len(row) >= 4 and row[1:3] == ['0', node]
                   and row[3] == '1N4733A' for row in rows)

    def led_load(drain):
        return any(v[0] == 'VLOAD' and v[2] == drain and
                   led_series_path(rows, 'VCC', v[1])
                   for v in rows if len(v) >= 4)

    if topology == 'passive_rc':
        return structural_checks(deck, {'passive_rc': True})
    if topology in {'noninverting_ac', 'mic_preamp', 'single_supply_audio'}:
        constraints = {'devices': ['opamp'], 'input_coupling': True}
        if topology == 'single_supply_audio':
            constraints.update(output_coupling=True, supply='single')
        checks = structural_checks(deck, constraints)

        def output_path(amp):
            if topology == 'single_supply_audio':
                return coupled(amp[5], 'OUT')
            return _path(signal_rows, amp[5], 'OUT', capacitors=True)

        def virtual_bias(amp):
            if topology != 'single_supply_audio':
                return True
            return any(node not in {'0', 'VCC', 'IN', 'OUT'}
                       and edge(resistors, 'VCC', node) and edge(resistors, node, '0')
                       and _path(signal_rows, node, amp[1], capacitors=False)
                       for r in resistors for node in r[1:3])

        checks['noninverting_feedback'] = any(
            coupled('IN', a[1]) and edge(resistors, a[5], a[2])
            and any(a[2] in r[1:3] and a[5] not in r[1:3] for r in resistors)
            and output_path(a) and virtual_bias(a)
            for a in opamps)
        if topology == 'mic_preamp':
            checks['microphone_bias'] = edge(resistors, 'VCC', 'IN')
        return checks
    if topology == 'buffered_rc':
        return {'buffered_rc': any(a[2] == a[5] == 'OUT' and edge(resistors, 'IN', a[1])
                                  and edge(capacitors, a[1], '0') for a in opamps)}
    if topology == 'active_rc':
        return {'single_opamp': len(opamps) == 1,
                'active_rc_feedback': any(a[5] == 'OUT' and edge(resistors, 'IN', a[2])
                                         and edge(resistors, 'OUT', a[2])
                                         and edge(capacitors, 'OUT', a[2]) for a in opamps)}

    if topology in {'inverter', 'loaded_inverter'}:
        valid = any(a[1] == '0' and a[5] == 'OUT' and edge(resistors, 'IN', a[2])
                    and edge(resistors, 'OUT', a[2]) for a in opamps)
        checks = {'inverting_feedback': valid}
        if topology == 'inverter':
            checks.update(structural_checks(deck, {'supply': 'dual'}))
        if topology == 'loaded_inverter':
            checks['output_load'] = edge(resistors, 'OUT', '0')
        return checks
    if topology == 'difference_amplifier':
        return {'four_resistor_difference_topology': any(
            a[5] == 'OUT' and edge(resistors, 'INN', a[2]) and edge(resistors, 'OUT', a[2])
            and edge(resistors, 'INP', a[1]) and edge(resistors, a[1], '0') for a in opamps)}
    if topology in {'ce', 'degenerated_ce'}:
        return {'unbypassed_ce_signal_path': any(
            coupled('IN', q[2]) and coupled(q[1], 'OUT')
            and biased_ce(q, unbypassed=topology == 'degenerated_ce') for q in bjts)}
    if topology == 'two_ce':
        return {'two_coupled_ce_stages': any(
            q1 != q2 and coupled('IN', q1[2]) and coupled(q1[1], q2[2])
            and coupled(q2[1], 'OUT') and q1[2] != q2[2]
            and biased_ce(q1) and biased_ce(q2) for q1 in bjts for q2 in bjts)}
    if topology == 'two_buffered_rc':
        return {'two_sequential_buffered_rc_sections': any(
            a != b and a[2] == a[5] and b[2] == b[5] == 'OUT'
            and edge(resistors, 'IN', a[1]) and edge(capacitors, a[1], '0')
            and edge(resistors, a[5], b[1]) and edge(capacitors, b[1], '0')
            for a in opamps for b in opamps)}
    if topology == 'sallen_key':
        return {'sallen_key_feedback': any(
            a[2] == a[5] == 'OUT' and edge(capacitors, a[1], '0')
            and edge(resistors, 'IN', node) and edge(resistors, node, a[1])
            and edge(capacitors, node, 'OUT')
            for a in opamps for row in resistors for node in row[1:3])}
    if topology in {'zener', 'loaded_zener'}:
        if topology == 'zener':
            direct = zener('OUT') and edge(resistors, 'VCC', 'OUT')
            buffered = any(a[2] == a[5] == 'OUT' and a[3:5] == ['VCC', '0']
                           and zener(a[1]) and edge(resistors, 'VCC', a[1])
                           for a in opamps)
            return {'zener_reference_output_path': direct or buffered}
        checks = {'reverse_zener': zener('OUT'), 'series_feed': edge(resistors, 'VCC', 'OUT')}
        if topology == 'loaded_zener':
            checks['output_load'] = edge(resistors, 'OUT', '0')
        return checks
    if topology == 'buffered_zener':
        return {'zener_emitter_follower': any(
            q[1] == 'VCC' and q[3] == 'OUT' and zener(q[2])
            and edge(resistors, 'VCC', q[2]) for q in bjts),
                'output_load': edge(resistors, 'OUT', '0')}
    if topology == 'opamp_nmos_led':
        def reference_connected(amp):
            if not reference_divider:
                return True
            return any(node not in {'0', 'VCC', 'OUT'}
                       and edge(resistors, 'VCC', node) and edge(resistors, node, '0')
                       and _path(signal_rows, node, amp[1], capacitors=False)
                       for r in resistors for node in r[1:3])
        return {'opamp_nmos_sense_loop': any(
            a[2] == m[3] and (a[5] == m[2] or edge(resistors, a[5], m[2]))
            and edge(resistors, m[3], '0') and led_load(m[1]) and reference_connected(a)
            for m in mosfets for a in opamps)}
    if topology == 'two_bjt_led':
        return {'two_bjt_sense_loop': any(
            p != c and c[1] == p[2] and c[2] == p[3] and c[3] == '0'
            and edge(resistors, p[3], '0') and led_load(p[1])
            for p in bjts for c in bjts)}
    raise ValueError(f'unknown topology: {topology}')
