"""Audited single-call calculator interface for a future model tool loop."""

import json
import math
import time

from ce_design_calculator import size_ce


REQUIRED = ('supply_v', 'gain_magnitude', 'load_ohms', 'collector_current_a')
OPTIONAL = ('beta_assumption', 'vbe_assumption_v', 'thermal_voltage_v', 'divider_current_ratio')
TOOL = {'type': 'function', 'function': {
    'name': 'size_ce',
    'description': ('Compute initial resistor values for a single unbypassed NPN CE stage. '
                    'Use explicit requirement values or recorded design choices; '
                    'this is not a simulator or a completed circuit.'),
    'parameters': {'type': 'object', 'properties': {
        key: {'type': 'number', 'exclusiveMinimum': 0} for key in REQUIRED + OPTIONAL},
        'required': list(REQUIRED), 'additionalProperties': False},
}}


class SizingTool:
    def __init__(self):
        self.events = []

    def execute(self, *, name, arguments, call_id):
        if self.events:
            raise ValueError('one analytical tool invocation per generation attempt')
        started = time.monotonic()
        event = {'call_id': call_id, 'name': name, 'arguments': arguments,
                 'status': 'error', 'simulator_calls': 0, 'api_calls': 0}
        self.events.append(event)
        try:
            if name != 'size_ce':
                raise ValueError('unsupported sizing function')
            if not isinstance(arguments, str) or len(arguments) > 4096:
                raise ValueError('arguments must be a bounded JSON object')
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('duplicate argument key')
                    result[key] = value
                return result
            values = json.loads(arguments, object_pairs_hook=unique)
            if not isinstance(values, dict) or set(values) - set(REQUIRED + OPTIONAL) or set(REQUIRED) - set(values):
                raise ValueError('incorrect calculator argument fields')
            if any(isinstance(v, bool) or not isinstance(v, (int, float))
                   or not math.isfinite(v) or v <= 0 for v in values.values()):
                raise ValueError('calculator arguments must be finite positive numbers')
            event['result'] = size_ce(**values)
            event['status'] = 'success'
        except (ValueError, TypeError, OverflowError, ZeroDivisionError) as error:
            event['error'] = str(error)
        finally:
            event['elapsed_seconds'] = time.monotonic() - started
        payload = {'status': event['status'], 'result': event.get('result'), 'error': event.get('error')}
        return {'role': 'tool', 'tool_call_id': call_id,
                'content': json.dumps(payload, allow_nan=False)}
