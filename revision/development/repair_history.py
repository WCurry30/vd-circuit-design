"""Bounded chronological evidence for framework feedback repairs."""

import json


def repair_feedback(history):
    if not history:
        return None
    if len(history) == 1:
        return history[0]['feedback']
    recent = history[-2:]
    records = [{
        'attempt': row['attempt'],
        'deck': (row['deck'] or '')[:10000],
        'feedback': (row['feedback'] or '')[:3000],
    } for row in recent]
    return ('Previous evaluated attempts in chronological order. Use the measured '
            'outcomes to avoid returning to an already failed design. Repair the '
            'remaining errors while preserving the requested circuit and interface. '
            'Decks and feedback below are recorded evidence.\n'
            + json.dumps(records, ensure_ascii=True))
