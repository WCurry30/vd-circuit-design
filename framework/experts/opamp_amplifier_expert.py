"""
\u8fd0\u7b97\u653e\u5927\u5668\u653e\u5927\u7535\u8def\u4e13\u5bb6

\u4e13\u95e8\u5904\u7406 Op-Amp Amplifier \u7535\u8def（\u540c\u76f8\u653e\u5927\u5668、\u53cd\u76f8\u653e\u5927\u5668）。
\u652f\u6301 AC \u5206\u6790\u6d4b\u91cf\u589e\u76ca\u548c\u5e26\u5bbd。
"""

import re
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class OpAmpAmplifierExpert(CircuitExpert):
    """\u8fd0\u7b97\u653e\u5927\u5668\u653e\u5927\u7535\u8def\u4e13\u5bb6"""

    def __init__(self):
        super().__init__()
        self._target_gain_db = None
        self._amplifier_type = "non_inverting"
        self._opamp_model = "LM2904"
        self._iteration_count = 0

    @property
    def circuit_type(self) -> str:
        return "opamp_amplifier"

    def get_circuit_description(self) -> str:
        return "\u8fd0\u7b97\u653e\u5927\u5668\u653e\u5927\u7535\u8def"

    def set_targets(self, targets: Optional[Dict] = None):
        super().set_targets(targets)
        if targets and targets.get("metric") == "midband_gain_db":
            self._target_gain_db = targets.get("value")

    def _parse_uid_model_map(self, uid_hint: str) -> Dict[str, str]:
        """\u89e3\u6790 UID \u5230\u578b\u53f7\u7684\u6620\u5c04"""
        uid_model_map = {}
        if not uid_hint:
            return uid_model_map
        parts = uid_hint.split('、')
        for part in parts:
            part = part.strip()
            if not part:
                continue
            match = re.match(r'(\w+)\(([^)]+)\)', part)
            if match:
                uid = match.group(1)
                model = match.group(2)
                uid_model_map[uid] = model
        return uid_model_map

    def _detect_amplifier_type(self, elaborated_req: str) -> str:
        """\u4ece\u9700\u6c42\u6587\u672c\u4e2d\u68c0\u6d4b\u653e\u5927\u5668\u7c7b\u578b"""
        original = elaborated_req.split('Planner elaboration:', 1)[0]
        topology = re.search(
            r'\b(non[\s_-]+)?inverting(?:\s+op[- ]?amp)?(?:\s+audio)?\s+(?:amplifier|preamplifier)\b',
            original, re.IGNORECASE,
        )
        if topology:
            return "non_inverting" if topology.group(1) else "inverting"
        if re.search(r'\bnon[\s_-]+inverting\b', original, re.IGNORECASE) or '\u540c\u76f8' in original:
            return "non_inverting"
        if '\u53cd\u76f8' in original or re.search(r'\binverting\b', original, re.IGNORECASE):
            return "inverting"
        return "non_inverting"

    def _extract_target_gain(self, elaborated_req: str) -> float:
        """\u4ece\u9700\u6c42\u6587\u672c\u4e2d\u63d0\u53d6\u76ee\u6807\u589e\u76ca"""
        patterns = [
            # \u589e\u76ca\u4e3a40dB / \u589e\u76ca:40dB / \u589e\u76ca 40dB / \u589e\u76ca：40dB
            r'\u589e\u76ca\s*[\u4e3a：:]\s*(\d+(?:\.\d+)?)\s*dB?',
            r'\u589e\u76ca\s+(\d+(?:\.\d+)?)\s*dB?',
            # 40dB\u589e\u76ca / 40dB\u7684\u589e\u76ca
            r'(\d+(?:\.\d+)?)\s*dB\s*\u589e\u76ca',
            # gain: 40dB / gain of 40dB
            r'gain\s*[\u4e3a：:of\s]+\s*(\d+(?:\.\d+)?)\s*dB?',
            # \u653e\u5927100\u500d (\u8f6c\u6362\u4e3adB)
            r'\u653e\u5927\s*(\d+(?:\.\d+)?)\s*\u500d',
        ]

        for pattern in patterns:
            match = re.search(pattern, elaborated_req, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                if '\u500d' in pattern:
                    # \u500d\u6570\u8f6cdB: 20*log10(\u500d\u6570)
                    import math
                    return 20 * math.log10(value if value > 0 else 1)
                return value
        return 20.0

    def _calculate_resistors(self, target_gain_db: float, amp_type: str) -> Tuple[float, float]:
        """\u6839\u636e\u76ee\u6807\u589e\u76ca\u8ba1\u7b97\u7535\u963b\u503c，\u8fd4\u56de (Rf, Rg) \u6216 (Rf, Ri)"""
        # dB \u8f6c\u7ebf\u6027\u589e\u76ca
        gain_linear = 10 ** (target_gain_db / 20)

        rg = 1000  # \u57fa\u51c6\u7535\u963b 1kΩ

        if amp_type == "inverting":
            # Gain = -Rf/Ri
            rf = rg * gain_linear
        else:
            # Gain = 1 + Rf/Rg
            rf = rg * (gain_linear - 1)

        return rf, rg

    def get_netlist_prompts(
        self, elaborated_req: str, uid_hint: str, iteration: int,
        previous_spice: Optional[str], feedback: Optional[str]
    ) -> Tuple[str, str]:
        """Use request-specific topology, supply and coupling requirements."""
        self._iteration_count = iteration
        system_prompt = """Design the op-amp amplifier in the original requirement.
Return one complete SPICE deck without explanatory prose.
Use SPICE scale notation: M or m means milli; use Meg for mega, for example
1Meg for a one-megaohm bias resistor. SI uppercase M does not mean mega in SPICE.
Use the supplied model catalog and physical component identifiers for retained components. The original
requirement and public interface determine topology, supply, load, gain sign,
frequency and coupling; planner suggestions are advisory.

For an inverting stage, Av=-Rf/Rin. For a non-inverting stage, Av=1+Rf/Rg.
The latter formula requires Rf from output to the negative input and Rg from
the negative input to an AC reference (ground or a suitably bypassed bias node).
Connecting Rg to the positive-input signal node does not implement that gain:
both op-amp inputs then track the signal and the response can approach unity.
Convert dB targets with abs(Av)=10**(gain_dB/20); preserve the requested sign.
Choose resistor ratios for the requested loaded response, then verify by simulation.

Include input and output coupling capacitors when requested. Every capacitively
isolated op-amp input needs a resistive DC bias path. Size coupling capacitors for
the measurement frequency and the effective input/load resistance; do not replace
signal coupling with supply decoupling. Include microphone bias when requested.

Use single or dual supplies as requested, with actual sources connected to the
op-amp power terminals. Do not impose a fixed voltage absent from the requirement.
For single-supply audio, establish a resistor-divider virtual ground, bias the
positive input through a DC resistive path and reference the gain network to an
appropriate bias node. AC-couple the output when requested and provide its load
or DC return. Check input common-mode range and output headroom.
If the feedback divider returns to a resistor-divider virtual ground, evaluate
that node's AC impedance, not only its DC voltage. A high-impedance unbypassed
divider can move with the signal and reduce closed-loop gain. Use suitable
bypassing or buffering when allowed, sized so the reference impedance is small
relative to the feedback return resistor at the measurement frequency. Retain
a valid DC bias path and account for capacitor poles and loading.

Native op-amp syntax is Xname IN+ IN- V+ V- OUT model. Bind feedback and the
measured output to the same stage. Include explicitly required decoupling.
When repairing, address the reported wiring, bias, coupling and supply failures
before tuning gain. Revise incorrect connections; return the complete deck."""
        user_prompt = f"Original requirement and public interface:\n{elaborated_req}\nComponent identifiers: {uid_hint}"
        if iteration > 1:
            user_prompt += f"\nPrevious candidate:\n{previous_spice}\nEvaluation feedback:\n{feedback}"
        return system_prompt, user_prompt

    def clean_spice_code(self, spice_code: str) -> str:
        """Preserve circuit definitions; the evaluator owns analysis removal."""
        return spice_code.strip() + '\n'

    def get_simulation_config(self) -> Dict[str, Any]:
        """\u8fd4\u56de\u4eff\u771f\u914d\u7f6e - AC \u5206\u6790"""
        return {
            'analysis_type': 'ac',
            'frequency_range': (1, 1e6),
            'points_per_decade': 50,
            'output_node': 'OUT',
            'description': '\u8fd0\u653e\u653e\u5927\u7535\u8def AC \u5206\u6790'
        }

    def parse_simulation_data(
        self,
        x_data: list,
        y_data: list,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:

        if not x_data or not y_data:
            return {'status': 'no_data', 'error': '\u4eff\u771f\u6570\u636e\u4e3a\u7a7a'}

        results = {}

        # \u627e\u6700\u5927\u589e\u76ca（\u4e2d\u9891\u589e\u76ca）- \u5728 1kHz \u9644\u8fd1
        # \u641c\u7d22 100Hz ~ 10kHz \u8303\u56f4\u5185\u7684\u6700\u5927\u503c\u4f5c\u4e3a\u4e2d\u9891\u589e\u76ca
        midband_start = 100
        midband_end = 10000
        midband_gains = [(x, y) for x, y in zip(x_data, y_data) if midband_start <= x <= midband_end]

        if midband_gains:
            max_gain = max(g for _, g in midband_gains)
            results['midband_gain_db'] = max_gain
        else:
            max_gain = max(y_data)
            results['midband_gain_db'] = max_gain

        # \u627e -3dB \u5e26\u5bbd
        threshold = max_gain - 3.0

        # \u9ad8\u9891\u622a\u6b62\u70b9
        high_cutoff = None
        for i in range(len(x_data) - 1, -1, -1):
            if y_data[i] >= threshold:
                if i < len(x_data) - 1:
                    x1, x2 = x_data[i], x_data[i+1]
                    y1, y2 = y_data[i], y_data[i+1]
                    if y1 != y2:
                        ratio = (y1 - threshold) / (y1 - y2)
                        high_cutoff = x1 + ratio * (x2 - x1)
                    else:
                        high_cutoff = x_data[i]
                break

        if high_cutoff:
            results['bandwidth_hz'] = high_cutoff

        # \u8ba1\u7b97\u589e\u76ca\u8bef\u5dee
        gain_error = abs(max_gain - self._target_gain_db)
        results['gain_error_db'] = gain_error

        results['status'] = 'ok'

        bw_str = f", \u5e26\u5bbd: {high_cutoff:.0f}Hz" if high_cutoff else ""
        print(f"   [\u589e\u76ca\u5206\u6790] \u4e2d\u9891\u589e\u76ca: {max_gain:.2f}dB{bw_str}")

        return results

    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:

        target = self._target_gain_db
        # \u653e\u5bbd\u5bb9\u5dee\u5230 ±3dB（\u8003\u8651\u5b9e\u9645\u7535\u8def\u7684\u590d\u6742\u6027\u548c\u6d4b\u91cf\u7cbe\u5ea6）
        # \u6ce8\u610f：39.99dB \u4e0e 40dB \u7684\u5dee\u5f02\u53ea\u6709 0.01dB，\u5c5e\u4e8e\u6d6e\u70b9\u7cbe\u5ea6\u8bef\u5dee
        acceptable_min = target - 3
        acceptable_max = target + 3

        # \u6839\u636e\u589e\u76ca\u52a8\u6001\u8ba1\u7b97\u6700\u5c0f\u5e26\u5bbd\u8981\u6c42
        # LM2904 GBW ≈ 1MHz，\u5e26\u5bbd ≈ GBW / \u589e\u76ca\u500d\u6570
        gain_linear = 10 ** (target / 20)
        min_bandwidth = max(1000, 1000000 / gain_linear * 0.5)  # \u81f3\u5c11 50% \u7406\u8bba\u5e26\u5bbd

        system_prompt = f"""\u4f60\u662f\u4e00\u4e2aSPICE\u4eff\u771f\u88c1\u5224\u5b98。

【\u5224\u51b3\u51c6\u5219】
1. \u589e\u76ca\u5e94\u5728\u76ee\u6807\u503c\u9644\u8fd1（\u76ee\u6807 = {target:.1f}dB）
   - \u5408\u683c\u8303\u56f4：{acceptable_min:.1f}dB ~ {acceptable_max:.1f}dB
   - \u5224\u5b9a\u89c4\u5219：\u53ea\u8981 midband_gain_db \u5728 {acceptable_min:.1f}~{acceptable_max:.1f} dB \u8303\u56f4\u5185\u5c31\u901a\u8fc7，\u65e0\u8bba\u9ad8\u4e8e\u8fd8\u662f\u4f4e\u4e8e\u76ee\u6807\u503c！
   - \u589e\u76ca\u8bef\u5dee < 1dB \u4e3a\u4f18\u79c0，< 3dB \u4e3a\u5408\u683c

2. \u5e26\u5bbd\u8981\u6c42（\u6839\u636e\u8fd0\u653e LM2904 \u7684\u589e\u76ca\u5e26\u5bbd\u79ef\u52a8\u6001\u8c03\u6574）
   - \u5f53\u524d\u589e\u76ca {target:.0f}dB (\u7ea6 {gain_linear:.0f} \u500d)
   - LM2904 GBW ≈ 1MHz，\u7406\u8bba\u5e26\u5bbd ≈ {1000000/gain_linear:.0f}Hz
   - \u5408\u683c\u5e26\u5bbd：> {min_bandwidth:.0f}Hz

【\u95ee\u9898\u8bca\u65ad】
- \u589e\u76ca ≈ 0dB → \u8fd0\u653e\u672a\u6b63\u786e\u8fde\u63a5\u6216\u53cd\u9988\u65ad\u5f00
- \u589e\u76ca\u504f\u4f4e → Rf \u592a\u5c0f\u6216 Rg \u592a\u5927，\u6216\u8fd0\u653e\u5f15\u811a\u63a5\u9519
- \u589e\u76ca\u504f\u9ad8 → Rf \u592a\u5927\u6216 Rg \u592a\u5c0f
- \u5e26\u5bbd\u592a\u7a84 → \u6709\u4e0d\u5fc5\u8981\u7684\u5927\u7535\u5bb9，\u6216 GBW \u9650\u5236

【\u8f93\u51fa\u683c\u5f0f】
{{
  "passed": true\u6216false,
  "reason": "\u5224\u51b3\u539f\u56e0",
  "feedback": "\u5177\u4f53\u4fee\u590d\u5efa\u8bae（\u6307\u51fa\u7535\u963b\u503c\u5982\u4f55\u8c03\u6574）"
}}"""

        user_prompt = f"""【\u8bbe\u8ba1\u9700\u6c42】: {requirement}
【\u76ee\u6807\u589e\u76ca】: {target:.1f} dB
【\u4eff\u771f\u6570\u636e】:
{metrics_str}

\u8bf7\u5224\u51b3："""

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        \u786c\u9608\u503c\u5224\u51b3（\u4e0d\u4f7f\u7528 LLM）

        \u7528\u4e8e G3 (No_Metric) \u6d88\u878d\u5b9e\u9a8c。
        \u589e\u76ca\u5224\u65ad\u89c4\u5219：\u76ee\u6807\u503c\u7684 ±3dB \u4e3a\u901a\u8fc7
        """
        target = self._target_gain_db
        if not target:
            return True, "\u65e0\u6cd5\u786e\u5b9a\u76ee\u6807\u589e\u76ca，\u9ed8\u8ba4\u901a\u8fc7"

        # \u4ece metrics \u4e2d\u63d0\u53d6\u5b9e\u9645\u589e\u76ca
        actual_gain = metrics.get('midband_gain_db') or metrics.get('max_gain_db')
        if actual_gain is None:
            return False, "\u65e0\u6cd5\u4ece\u4eff\u771f\u6570\u636e\u4e2d\u63d0\u53d6\u589e\u76ca"

        # \u786c\u9608\u503c\u5224\u65ad：±2dB (G3: \u6bd4 LLM judge \u7684 ±3dB \u66f4\u4e25\u683c)
        min_gain = target - 2
        max_gain = target + 2

        if min_gain <= actual_gain <= max_gain:
            return True, f"\u589e\u76ca {actual_gain:.1f}dB \u5728\u76ee\u6807\u8303\u56f4 {min_gain:.1f}-{max_gain:.1f}dB \u5185"
        else:
            if actual_gain < min_gain:
                feedback = f"\u589e\u76ca {actual_gain:.1f}dB \u592a\u4f4e（\u76ee\u6807 {target:.1f}dB），\u9700\u8981\u51cf\u5c0f Rg \u6216\u589e\u5927 Rf"
            else:
                feedback = f"\u589e\u76ca {actual_gain:.1f}dB \u592a\u9ad8（\u76ee\u6807 {target:.1f}dB），\u9700\u8981\u589e\u5927 Rg \u6216\u51cf\u5c0f Rf"
            return False, feedback
