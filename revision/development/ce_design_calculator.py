"""Analytical initial sizing for a divider-biased, unbypassed NPN CE stage.

This is a development calculator, not an automatic candidate replacement.
Inputs and assumptions must be recorded; SPICE validation remains necessary.
"""

import math


def size_ce(*, supply_v, gain_magnitude, load_ohms, collector_current_a,
            beta_assumption=100.0, vbe_assumption_v=0.65,
            thermal_voltage_v=0.026, divider_current_ratio=10.0):
    values = (supply_v, gain_magnitude, load_ohms, collector_current_a,
              beta_assumption, vbe_assumption_v, thermal_voltage_v, divider_current_ratio)
    if any(not math.isfinite(x) or x <= 0 for x in values):
        raise ValueError('all sizing inputs must be finite and positive')
    ic = collector_current_a
    ie = ic * (1 + 1 / beta_assumption)
    rc = supply_v / (2 * ic)
    loaded_rc = 1 / (1 / rc + 1 / load_ohms)
    intrinsic_re = thermal_voltage_v / ie
    re = loaded_rc / gain_magnitude - intrinsic_re
    if re <= 0:
        raise ValueError('requested gain exceeds the loaded unbypassed-stage estimate')
    ve = ie * re
    vb = ve + vbe_assumption_v
    vc = supply_v - ic * rc
    if vc <= vb:
        raise ValueError('requested gain/current combination leaves no forward-active headroom')
    ib = ic / beta_assumption
    lower_current = divider_current_ratio * ib
    rb_lower = vb / lower_current
    rb_upper = (supply_v - vb) / (lower_current + ib)
    return {
        'inputs': dict(zip(('supply_v', 'gain_magnitude', 'load_ohms', 'collector_current_a',
                           'beta_assumption', 'vbe_assumption_v', 'thermal_voltage_v',
                           'divider_current_ratio'), values)),
        'resistors_ohms': {'collector': rc, 'emitter': re,
                          'bias_upper': rb_upper, 'bias_lower': rb_lower},
        'estimated_bias_v': {'collector': vc, 'base': vb, 'emitter': ve},
        'estimated_midband_gain': -loaded_rc / (intrinsic_re + re),
        'scope': 'Unbypassed single-stage initial sizing; finite-beta/Vbe assumptions, no simulator search.',
    }
