"""
\u6ee4\u6ce2\u5668\u7535\u8def\u4e13\u5bb6

\u4e13\u95e8\u5904\u7406 Sallen-Key \u4f4e\u901a\u6ee4\u6ce2\u5668\u7b49\u6ee4\u6ce2\u7535\u8def\u7684\u7f51\u8868\u751f\u6210、\u4eff\u771f\u914d\u7f6e\u548c\u8bc4\u4f30。
\u6240\u6709\u6ee4\u6ce2\u5668\u76f8\u5173\u7684\u786c\u7f16\u7801\u903b\u8f91\u90fd\u4ece ngspice_critic.py \u548c netlist_generator.py \u8fc1\u79fb\u81f3\u6b64。
"""

import re
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class FilterExpert(CircuitExpert):
    """Low-pass filter expert covering passive and active topologies."""

    def __init__(self):
        super().__init__()
        self._target_cutoff_hz = None

    @property
    def circuit_type(self) -> str:
        return "filter"

    def set_targets(self, targets: Optional[Dict] = None):
        super().set_targets(targets)
        if targets and targets.get("metric") == "cutoff_freq_hz":
            self._target_cutoff_hz = targets.get("value")

    def get_circuit_description(self) -> str:
        return "\u6ee4\u6ce2\u7535\u8def"

    @staticmethod
    def _topology(requirement: str) -> str:
        lowered = requirement.lower()
        if "passive rc" in lowered or "passive" in lowered:
            return "passive_rc"
        if "feedback capacitor" in lowered and "feedback resistor" in lowered:
            return "inverting_active"
        if "first-order" in lowered or "first order" in lowered or "buffer" in lowered:
            return "buffered_rc"
        return "sallen_key"

    @staticmethod
    def _template(topology: str) -> tuple[str, str]:
        if topology == "passive_rc":
            return (
                "V1 IN 0 DC 0 AC 1\nR1 IN OUT <calculate>\nC1 OUT 0 <calculate>",
                "fc = 1 / (2*pi*R1*C1); preserve the one-resistor, one-capacitor passive topology",
            )
        if topology == "buffered_rc":
            return (
                "VCC VCC 0 DC 9\nV1 IN 0 DC 0 AC 1\nR1 IN N1 <calculate>\n"
                "C1 N1 0 <calculate>\nX1 N1 OUT VCC 0 OUT LM2904\nCDEC VCC 0 100n",
                "fc = 1 / (2*pi*R1*C1); preserve the RC input followed by a unity-gain buffer",
            )
        if topology == "inverting_active":
            return (
                "VCC VCC 0 DC 12\nVEE VEE 0 DC -12\nV1 IN 0 DC 0 AC 1\n"
                "R1 IN NMIN <calculate>\nR2 NMIN OUT <calculate>\n"
                "C1 NMIN OUT <calculate>\nX1 0 NMIN VCC VEE OUT LM2904\n"
                "CDECP VCC 0 100n\nCDECN VEE 0 100n",
                "fc = 1 / (2*pi*R2*C1); use R1=R2 for unity-magnitude low-frequency gain",
            )
        return (
            "VCC VCC 0 DC 9\nV1 IN 0 DC 0 AC 1\nR1 IN N1 <calculate>\n"
            "C1 N1 0 <calculate>\nR2 N1 N2 <calculate>\nC2 N2 OUT <calculate>\n"
            "X1 N2 OUT VCC 0 OUT LM2904\nCDEC VCC 0 100n",
            "fc = 1 / (2*pi*sqrt(R1*R2*C1*C2)); preserve the unity-gain Sallen-Key topology",
        )

    def get_netlist_prompts(
        self,
        elaborated_req: str,
        uid_hint: str,
        iteration: int,
        previous_spice: Optional[str],
        feedback: Optional[str]
    ) -> Tuple[str, str]:
        topology = self._topology(elaborated_req)
        template, design_rule = self._template(topology)
        system_prompt = f"""You generate SPICE netlists for low-pass filters.

Visible component hints: {uid_hint}
Selected topology from the visible requirement: {topology}

Required topology template:
```spice
{template}
```

Rules:
1. {design_rule}.
2. Preserve the selected topology and node names IN, OUT, and 0.
3. Use the source V1 exactly once with AC magnitude 1.
4. Do not add a different filter order or substitute another topology.
5. Do not emit .control, .end, .include, .model, or .subckt directives.
6. Output only SPICE code."""

        user_prompt = f"Design requirement:\n{elaborated_req}\n"
        if iteration > 1:
            user_prompt += f"\nPrevious SPICE:\n```spice\n{previous_spice}\n```\n"
            user_prompt += f"\nSimulator feedback:\n{feedback}\n"
            user_prompt += "Change component values only; keep the required topology unchanged.\n"
        else:
            user_prompt += "\nCalculate component values for the requested cutoff.\n"
        return system_prompt, user_prompt

    def clean_spice_code(self, spice_code: str) -> str:
        """
        \u6e05\u6d17 SPICE \u4ee3\u7801，\u79fb\u9664 LLM \u9519\u8bef\u6dfb\u52a0\u7684\u591a\u4f59\u5143\u4ef6

        \u4ece netlist_generator.py \u7b2c94-143\u884c\u8fc1\u79fb
        """
        # \u8fd9\u4e9b\u5143\u4ef6\u4f1a\u7834\u574f Sallen-Key \u5355\u4f4d\u589e\u76ca\u914d\u7f6e
        forbidden_patterns = [
            r'^R3\s+.*$',           # \u79fb\u9664 R3
            r'^R4\s+.*$',           # \u79fb\u9664 R4
            r'^R_feedback\s+.*$',   # \u79fb\u9664 R_feedback
        ]

        lines = spice_code.split('\n')
        cleaned_lines = []
        removed_count = 0

        for line in lines:
            line_stripped = line.strip()
            should_remove = False
            skip_message = None

            for pattern in forbidden_patterns:
                if re.match(pattern, line_stripped, re.IGNORECASE):
                    should_remove = True
                    skip_message = f"[\u7981\u6b62\u5143\u4ef6] {line_stripped}"
                    break

            # \u68c0\u6d4b\u4e24\u7aef\u90fd\u63a5\u5730\u7684\u5143\u4ef6（\u7535\u6c14\u77ed\u8def，\u65e0\u610f\u4e49）
            if not should_remove:
                # \u5339\u914d Cxxx 0 0 value \u6216 Rxxx 0 0 value
                short_circuit_match = re.match(r'^([RC]\w+)\s+0\s+0\s+', line_stripped, re.IGNORECASE)
                if short_circuit_match:
                    should_remove = True
                    skip_message = f"[\u77ed\u8def\u9519\u8bef] {line_stripped} - \u4e24\u7aef\u90fd\u63a5\u5730，\u65e0\u610f\u4e49"

            # \u68c0\u6d4b\u91cd\u590d\u7684\u53bb\u8026\u7535\u5bb9（\u53ea\u4fdd\u7559\u4e00\u4e2a）
            if not should_remove:
                # \u5339\u914d\u53bb\u8026\u7535\u5bb9 C_decxxx VCC 0 \u6216 C_decxxx 0 VCC
                decap_match = re.match(r'^(C_dec\d*)\s+(VCC|0)\s+(0|VCC)\s+', line_stripped, re.IGNORECASE)
                if decap_match:
                    # \u68c0\u67e5\u662f\u5426\u5df2\u7ecf\u6709\u53bb\u8026\u7535\u5bb9\u4e86
                    if any('C_dec' in l and ('VCC' in l.upper() or '0' in l.split()) for l in cleaned_lines):
                        should_remove = True
                        skip_message = f"[\u91cd\u590d\u53bb\u8026] {line_stripped} - \u5df2\u6709\u53bb\u8026\u7535\u5bb9，\u79fb\u9664\u91cd\u590d"

            if should_remove:
                removed_count += 1
                print(f"   [\u81ea\u52a8\u6e05\u6d17] {skip_message}")
            else:
                cleaned_lines.append(line)

        if removed_count > 0:
            print(f"   \u8b66\u544a：LLM \u751f\u6210\u4e86 {removed_count} \u4e2a\u9519\u8bef\u5143\u4ef6，\u5df2\u81ea\u52a8\u79fb\u9664")

        return '\n'.join(cleaned_lines)

    def get_simulation_config(self) -> Dict[str, Any]:
        """
        \u8fd4\u56de\u6ee4\u6ce2\u5668\u4eff\u771f\u914d\u7f6e

        \u4ece ngspice_critic.py SimulationConfig['filter'] \u8fc1\u79fb
        """
        return {
            'analysis_type': 'ac',
            'metrics': ['cutoff_freq', 'passband_gain', 'roll_off'],
            'frequency_range': (1, 1e6),
            'output_node': 'OUT',
            'points_per_decade': 50,
            'description': '\u6ee4\u6ce2\u7535\u8def'
        }

    def parse_simulation_data(
        self,
        x_data: list,
        y_data: list,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        \u89e3\u6790\u6ee4\u6ce2\u5668\u4eff\u771f\u6570\u636e，\u8ba1\u7b97\u5173\u952e\u6307\u6807

        \u4ece ngspice_critic.py \u7b2c297-436\u884c\u8fc1\u79fb
        \u91cd\u70b9：\u8ba1\u7b97\u622a\u6b62\u9891\u7387（-3dB \u70b9）、\u901a\u5e26\u589e\u76ca\u7b49
        """
        if not x_data:
            return None

        results = {}

        # AC \u5206\u6790\u6307\u6807
        # \u627e\u5230\u771f\u6b63\u7684\u901a\u5e26\u533a\u57df（\u589e\u76ca\u6700\u5927\u7684\u533a\u57df）
        # \u4f7f\u7528\u6ed1\u52a8\u7a97\u53e3\u627e\u5230\u589e\u76ca\u6700\u5e73\u7a33\u7684\u533a\u57df\u4f5c\u4e3a\u901a\u5e26\u53c2\u8003

        # \u5148\u627e\u5230\u6700\u5927\u589e\u76ca\u70b9\u53ca\u5176\u9644\u8fd1\u4f5c\u4e3a\u901a\u5e26\u53c2\u8003
        max_gain = max(y_data)
        max_idx = y_data.index(max_gain)
        results['max_gain_db'] = max_gain

        # \u4ee5\u6700\u5927\u589e\u76ca\u9644\u8fd1（±1\u4e2a decade）\u7684\u589e\u76ca\u4f5c\u4e3a\u901a\u5e26\u589e\u76ca
        # \u8fd9\u6837\u53ef\u4ee5\u907f\u514d\u9ad8\u9891\u8870\u51cf\u533a\u62c9\u4f4e\u5e73\u5747\u503c
        freq_at_max = x_data[max_idx]
        passband_low = max(1, freq_at_max / 10)
        passband_high = min(freq_at_max * 10, x_data[-1])

        passband_gains = [(x, y) for x, y in zip(x_data, y_data)
                          if passband_low <= x <= passband_high and y >= max_gain - 1]

        if passband_gains:
            passband_gain = sum(g for _, g in passband_gains) / len(passband_gains)
        else:
            passband_gain = max_gain
        results['passband_gain_db'] = passband_gain

        # \u622a\u6b62\u9891\u7387\u68c0\u6d4b - \u5bf9\u4e8e\u4f4e\u901a\u6ee4\u6ce2\u5668，\u4ece\u4f4e\u9891\u5f80\u9ad8\u9891\u641c\u7d22
        # \u622a\u6b62\u9891\u7387：\u589e\u76ca\u4e0b\u964d\u5230\u901a\u5e26\u589e\u76ca -3dB \u7684\u9891\u7387\u70b9
        threshold = passband_gain - 3.0

        # \u4ece\u4f4e\u9891\u5f80\u9ad8\u9891\u641c\u7d22，\u627e\u5230\u589e\u76ca\u7b2c\u4e00\u6b21\u4f4e\u4e8e threshold \u7684\u70b9
        # \u8fd9\u662f\u4f4e\u901a\u6ee4\u6ce2\u5668\u7684\u6b63\u786e\u68c0\u6d4b\u65b9\u5f0f
        cutoff_freq = None
        for i in range(len(x_data)):
            if y_data[i] <= threshold:
                # \u627e\u5230\u7cbe\u786e\u7684\u622a\u6b62\u9891\u7387\u70b9（\u7ebf\u6027\u63d2\u503c）
                if i > 0:
                    x1, x2 = x_data[i-1], x_data[i]
                    y1, y2 = y_data[i-1], y_data[i]
                    if y1 != y2:
                        ratio = (y1 - threshold) / (y1 - y2)
                        cutoff_freq = x1 + ratio * (x2 - x1)
                    else:
                        cutoff_freq = x_data[i]
                else:
                    cutoff_freq = x_data[i]
                break

        if cutoff_freq:
            results['cutoff_freq_hz'] = cutoff_freq
        else:
            # \u5982\u679c\u6574\u4e2a\u9891\u6bb5\u90fd\u6ca1\u6709\u4f4e\u4e8e threshold，\u8bf4\u660e\u622a\u6b62\u9891\u7387\u8d85\u51fa\u4e86\u4eff\u771f\u8303\u56f4
            # \u6b64\u65f6\u53d6\u6700\u9ad8\u9891\u7387\u70b9\u4f5c\u4e3a\u53c2\u8003
            results['cutoff_freq_hz'] = x_data[-1]
            print(f"   ⚠️ \u622a\u6b62\u9891\u7387\u8d85\u51fa\u4eff\u771f\u8303\u56f4，\u4e0a\u9650 {x_data[-1]:.0f} Hz")

        # \u5e26\u5bbd（\u5982\u679c\u6709\u622a\u6b62\u9891\u7387）
        if 'cutoff_freq_hz' in results:
            results['bandwidth_hz'] = results['cutoff_freq_hz']

        # \u622a\u6b62\u9891\u7387\u504f\u79bb\u5ea6\u767e\u5206\u6bd4
        if self._target_cutoff_hz and results.get('cutoff_freq_hz'):
            results['cutoff_deviation_pct'] = abs(results['cutoff_freq_hz'] - self._target_cutoff_hz) / self._target_cutoff_hz * 100

        return results

    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:
        """
        \u751f\u6210\u6ee4\u6ce2\u5668\u5224\u51b3\u6240\u9700\u7684 Prompt

        \u4ece ngspice_critic.py \u7b2c457-520\u884c\u8fc1\u79fb
        """
        # \u4f18\u5148\u4f7f\u7528 set_targets() \u6ce8\u5165\u7684\u76ee\u6807\u503c
        target_freq = self._target_cutoff_hz
        if target_freq is None:
            # fallback: \u4ece\u9700\u6c42\u4e2d\u63d0\u53d6\u76ee\u6807\u622a\u6b62\u9891\u7387（\u5355\u4f4d：Hz）
            match = re.search(r'(\d+(?:\.\d+)?)\s*([kK]?)Hz', requirement, re.IGNORECASE)
            if match:
                target_freq = float(match.group(1))
                if match.group(2).lower() == 'k':
                    target_freq *= 1000
            if not target_freq:
                match = re.search(r'\u622a\u6b62\u9891\u7387.*?(\d+(?:\.\d+)?)', requirement)
                if match:
                    target_freq = float(match.group(1))

        # \u8ba1\u7b97\u5bb9\u5dee\u8303\u56f4 (±20%)
        if target_freq:
            min_freq = target_freq * 0.8
            max_freq = target_freq * 1.2
            range_str = f"{min_freq:.0f}Hz ~ {max_freq:.0f}Hz"
        else:
            range_str = "\u672a\u77e5\u76ee\u6807\u503c，\u8bf7\u6839\u636e\u9700\u6c42\u81ea\u884c\u5224\u65ad\u5408\u7406\u8303\u56f4"

        system_prompt = f"""\u4f60\u662f\u4e00\u4e2a\u4e13\u4e1a\u7684 SPICE \u4eff\u771f\u88c1\u5224\u5b98\u548c\u7535\u8def\u4f18\u5316\u987e\u95ee。

【\u7535\u8def\u7c7b\u578b】: \u6ee4\u6ce2\u7535\u8def

【\u5224\u51b3\u51c6\u5219】\u622a\u6b62\u9891\u7387\u5224\u65ad\u89c4\u5219
\u5982\u679c\u9700\u6c42\u4e2d\u660e\u786e\u4e86\u76ee\u6807\u622a\u6b62\u9891\u7387 fx，\u5219\u5224\u65ad\u89c4\u5219\u5982\u4e0b：
- \u76ee\u6807\u622a\u6b62\u9891\u7387: {target_freq}Hz（\u5982\u9700\u6c42\u4e2d\u672a\u660e\u786e，\u8bf7\u5ffd\u7565\u6b64\u884c）
- \u5408\u683c\u8303\u56f4: \u76ee\u6807\u503c\u7684 80% ~ 120%（\u5373 {range_str}）
- \u5224\u5b9a\u903b\u8f91: \u5b9e\u6d4b\u503c\u5728 {range_str} \u8303\u56f4\u5185 → \u901a\u8fc7；\u4e0d\u5728\u8303\u56f4\u5185 → \u4e0d\u901a\u8fc7
- \u6ce8\u610f：\u53ea\u8981\u5728\u8303\u56f4\u5185\u5c31\u901a\u8fc7，\u65e0\u8bba\u9ad8\u4e8e\u8fd8\u662f\u4f4e\u4e8e\u76ee\u6807\u503c！

【\u4f4e\u901a\u6ee4\u6ce2\u5668\u4f18\u5316\u89c4\u5219】
- \u622a\u6b62\u9891\u7387\u516c\u5f0f：fc = 1 / (2π × √(R1×R2×C1×C2))
- \u5982\u679c fc \u592a\u4f4e → \u51cf\u5c0f R \u6216 C \u503c
- \u5982\u679c fc \u592a\u9ad8 → \u589e\u5927 R \u6216 C \u503c
- \u5efa\u8bae：\u6bcf\u6b21\u8c03\u6574\u5e45\u5ea6\u4e3a 20%-50%

【\u8f93\u51fa\u683c\u5f0f】
{{
  "passed": true\u6216false,
  "reason": "\u5224\u51b3\u539f\u56e0（\u4e00\u53e5\u8bdd）",
  "feedback": "\u5177\u4f53\u8c03\u6574\u5efa\u8bae，\u4f8b\u5982：'\u622a\u6b62\u9891\u7387100Hz\u592a\u4f4e，\u76ee\u68071kHz。\u8bf7\u5c06R1\u548cR2\u4ece10k\u51cf\u5c0f\u52305k，\u6216\u5c06C1\u548cC2\u4ece100nF\u51cf\u5c0f\u523020nF'"
}}"""

        user_prompt = f"【\u539f\u59cb\u8bbe\u8ba1\u9700\u6c42】:\n{requirement}\n\n【\u5b9e\u6d4b\u4eff\u771f\u6570\u636e】:\n{metrics_str}\n\n\u8bf7\u5224\u51b3\u5e76\u7ed9\u51fa\u4f18\u5316\u5efa\u8bae："

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        \u786c\u9608\u503c\u5224\u51b3（\u4e0d\u4f7f\u7528 LLM）

        \u7528\u4e8e G3 (No_Metric) \u6d88\u878d\u5b9e\u9a8c。
        \u622a\u6b62\u9891\u7387\u5224\u65ad\u89c4\u5219：\u76ee\u6807\u503c\u7684 80% ~ 120% \u4e3a\u901a\u8fc7
        """
        # \u4f18\u5148\u4f7f\u7528 set_targets() \u6ce8\u5165\u7684\u76ee\u6807\u503c
        target_freq = self._target_cutoff_hz
        if target_freq is None:
            match = re.search(r'(\d+(?:\.\d+)?)\s*([kK]?)Hz', requirement, re.IGNORECASE)
            if match:
                target_freq = float(match.group(1))
                if match.group(2).lower() == 'k':
                    target_freq *= 1000
            if not target_freq:
                match = re.search(r'\u622a\u6b62\u9891\u7387.*?(\d+(?:\.\d+)?)', requirement)
                if match:
                    target_freq = float(match.group(1))

        # \u4ece metrics \u4e2d\u63d0\u53d6\u5b9e\u9645\u622a\u6b62\u9891\u7387
        actual_cutoff = metrics.get('cutoff_freq_hz')
        if not actual_cutoff:
            return False, "\u65e0\u6cd5\u4ece\u4eff\u771f\u6570\u636e\u4e2d\u63d0\u53d6\u622a\u6b62\u9891\u7387"

        # \u5982\u679c\u6ca1\u6709\u76ee\u6807\u9891\u7387，\u5219\u65e0\u6cd5\u5224\u65ad
        if not target_freq:
            return True, "\u9700\u6c42\u4e2d\u672a\u6307\u5b9a\u76ee\u6807\u622a\u6b62\u9891\u7387，\u9ed8\u8ba4\u901a\u8fc7"

        # \u786c\u9608\u503c\u5224\u65ad：90% ~ 110% (G3: \u6bd4 LLM judge \u66f4\u4e25\u683c)
        min_freq = target_freq * 0.9
        max_freq = target_freq * 1.1

        if min_freq <= actual_cutoff <= max_freq:
            return True, f"\u622a\u6b62\u9891\u7387 {actual_cutoff:.0f}Hz \u5728\u76ee\u6807\u8303\u56f4 {min_freq:.0f}-{max_freq:.0f}Hz \u5185"
        else:
            if actual_cutoff < min_freq:
                feedback = f"\u622a\u6b62\u9891\u7387 {actual_cutoff:.0f}Hz \u592a\u4f4e（\u76ee\u6807 {target_freq:.0f}Hz），\u9700\u8981\u51cf\u5c0f R \u6216 C \u503c"
            else:
                feedback = f"\u622a\u6b62\u9891\u7387 {actual_cutoff:.0f}Hz \u592a\u9ad8（\u76ee\u6807 {target_freq:.0f}Hz），\u9700\u8981\u589e\u5927 R \u6216 C \u503c"
            return False, feedback
