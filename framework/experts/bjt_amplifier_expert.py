"""
\u4e09\u6781\u7ba1\u5171\u5c04\u6781\u653e\u5927\u7535\u8def\u4e13\u5bb6

\u4e13\u95e8\u5904\u7406 BJT Common Emitter Amplifier \u7535\u8def。
\u91c7\u7528 SPICE \u539f\u751f\u4e09\u6781\u7ba1\u6a21\u578b（2N3904），\u7a33\u5b9a\u6027\u6781\u9ad8，\u9002\u5408\u8fdb\u884c\u4ea4\u6d41（AC）\u589e\u76ca\u5bfb\u4f18。
"""

import re
import math
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class BjtAmplifierExpert(CircuitExpert):
    """\u4e09\u6781\u7ba1\u5171\u5c04\u6781\u653e\u5927\u7535\u8def\u4e13\u5bb6"""

    def __init__(self):
        super().__init__()
        self._target_gain_db = None

    @property
    def circuit_type(self) -> str:
        return "bjt_amplifier"

    def get_circuit_description(self) -> str:
        return "\u4e09\u6781\u7ba1\u5171\u5c04\u6781\u653e\u5927\u7535\u8def"

    def set_targets(self, targets: Optional[Dict] = None):
        super().set_targets(targets)
        if targets and targets.get("metric") == "max_gain_db":
            self._target_gain_db = targets.get("value")

    def _extract_target_gain(self, requirement: str) -> float:
        """
        \u4ece\u9700\u6c42\u4e2d\u63d0\u53d6\u76ee\u6807\u589e\u76ca（dB）

        \u652f\u6301\u683c\u5f0f：
        - "\u589e\u76ca\u4e3a40dB" -> 40
        - "\u589e\u76ca20dB" -> 20
        - "100\u500d\u653e\u5927" -> 40 (20*log10(100))
        - "10\u500d\u589e\u76ca" -> 20
        """
        # \u5c1d\u8bd5\u5339\u914d dB \u503c
        db_match = re.search(r'(\d+(?:\.\d+)?)\s*dB', requirement, re.IGNORECASE)
        if db_match:
            return float(db_match.group(1))

        # \u5c1d\u8bd5\u5339\u914d\u500d\u6570
        times_match = re.search(r'(\d+(?:\.\d+)?)\s*\u500d', requirement)
        if times_match:
            times = float(times_match.group(1))
            return 20 * math.log10(times) if times > 0 else 40

        # \u9ed8\u8ba4 40dB (100\u500d)
        return 40.0

    def get_netlist_prompts(
        self,
        elaborated_req: str,
        uid_hint: str,
        iteration: int,
        previous_spice: Optional[str],
        feedback: Optional[str]
    ) -> Tuple[str, str]:
        """Generate request-specific common-emitter design and repair guidance."""
        system_prompt = f"""You design BJT amplifier SPICE circuits.
Return only the complete SPICE deck, without Markdown or explanations.
Use the provided component identifiers: {uid_hint}.
The requirement and public interface determine supply, load, gain, frequency,
allowed device models and stage count. Use native Q references in C B E order;
use the supplied NPN model (2N2222 under the shared catalog), without defining
or importing substitute models. Do not invent a target or tolerance.

Design guidance:
- Choose a forward-active DC operating point with collector-emitter headroom.
  Account for base current loading of the bias divider. Check Ve, Vb, Vc and Ic.
  Estimate Vb = VCC*Rbottom/(Rtop+Rbottom), Ie = (Vb-0.65)/RE_DC,
  and Vc = VCC-Ic*RC, then include divider loading and check Vc > Vb.
  A computed collector voltage at or below the base voltage indicates saturation;
  change bias current or collector resistance before attempting gain adjustment.
- At midband, a common-emitter stage has signed gain approximately
  Av = -(RC || RL_effective) / (re + RE_unbypassed), with re approximately
  26mV/Ie at room temperature. The next stage also loads the collector.
- Select RC from DC headroom and current, then choose emitter degeneration
  to obtain the requested loaded gain. Recheck bias after changing values.
- A negative signed gain is normal phase inversion, not evidence of cutoff.
  When gain is reported in dB, interpret it as 20*log10(abs(Av)).
- Include emitter bypass only when allowed by the requirement. Partial bypass
  may use split emitter resistors with a continuous resistive DC path to ground.
  An unbypassed stage must retain its emitter degeneration at the test frequency.
  Do not combine an RC/RE gain estimate with a capacitor that shorts RE at the
  measurement frequency. An optional planner-proposed full bypass can be omitted
  when emitter degeneration is needed for the requested moderate gain.
- Choose coupling and bypass capacitors using their effective resistances and
  the specified measurement frequency; account for attenuation away from midband.
  Every capacitively isolated input/output node needs a resistive DC return.
  Put OUT on the load side of the output coupling capacitor, with a load or
  bias-return resistor to ground. Use the specified load when present; otherwise
  select an explicit finite load and include it in the gain calculation.
- Respect a requested multistage topology. Account for interstage loading,
  overall gain sign and the product of the individual stage gains.

When feedback is supplied, diagnose simulator errors first, then topology and
DC bias, then numerical gain. Repair incorrect wiring where needed while
preserving the requested topology and public interface. Do not infer cutoff
or saturation solely from gain sign. Output the entire revised deck."""
        user_prompt = f"Requirement: {elaborated_req}\nComponent identifiers: {uid_hint}"
        if iteration > 1:
            user_prompt += f"\nPrevious deck:\n{previous_spice}\nEvaluation feedback:\n{feedback}"
        return system_prompt, user_prompt

    def clean_spice_code(self, spice_code: str) -> str:
        """
        \u6e05\u6d17 SPICE \u4ee3\u7801，\u79fb\u9664 LLM \u9519\u8bef\u6dfb\u52a0\u7684\u5206\u6790\u6587\u672c\u548c\u65e0\u6548\u8bed\u53e5

        \u786e\u4fdd\u53ea\u4f7f\u7528 SPICE \u539f\u751f\u4e09\u6781\u7ba1\u8c03\u7528\u65b9\u5f0f（Q1 ... 2N3904）
        """
        lines = spice_code.split('\n')
        cleaned_lines = []
        removed_count = 0

        # \u6709\u6548\u7684 SPICE \u8bed\u53e5\u5f00\u5934\u6a21\u5f0f
        valid_spice_patterns = [
            r'^[VIRCLDQX]\w*\s+\S+',  # \u5143\u4ef6\u8bed\u53e5：Vxxx, Ixxx, Rxxx, Cxxx, Lxxx, Dxxx, Qxxx, Xxxx \u540e\u8ddf\u8282\u70b9
            r'^\.\w+',                 # \u70b9\u547d\u4ee4：.model, .subckt, .ends, .end
            r'^\s*$',                  # \u7a7a\u884c
        ]

        for line in lines:
            line_stripped = line.strip()
            should_remove = False
            skip_message = None

            # \u8df3\u8fc7\u5305\u542b\u4e2d\u6587\u5b57\u7b26\u7684\u884c（LLM \u5206\u6790\u6587\u672c）
            if re.search(r'[\u4e00-\u9fff]', line_stripped):
                should_remove = True
                skip_message = f"[\u4e2d\u6587\u6587\u672c] {line_stripped[:30]}..."

            # \u8df3\u8fc7 markdown \u683c\u5f0f\u884c
            if not should_remove and re.match(r'^\*{1,2}|\*{1,2}$|^-_|^#', line_stripped):
                should_remove = True
                skip_message = f"[Markdown\u683c\u5f0f] {line_stripped[:30]}..."

            # \u8df3\u8fc7\u4ee5 - \u5f00\u5934\u7684\u5217\u8868\u9879
            if not should_remove and re.match(r'^-\s*_?DUP', line_stripped):
                should_remove = True
                skip_message = f"[\u5217\u8868\u9879] {line_stripped[:30]}..."

            # \u68c0\u67e5\u662f\u5426\u662f\u6709\u6548\u7684 SPICE \u8bed\u53e5
            if not should_remove:
                is_valid_spice = False
                for pattern in valid_spice_patterns:
                    if re.match(pattern, line_stripped, re.IGNORECASE):
                        is_valid_spice = True
                        break

                # \u5355\u72ec\u5904\u7406\u6ce8\u91ca\u884c（\u4ee5 * \u5f00\u5934，\u4f46\u4e0d\u662f markdown）
                if line_stripped.startswith('*') and not line_stripped.startswith('**'):
                    is_valid_spice = True

                if not is_valid_spice:
                    should_remove = True
                    skip_message = f"[\u975eSPICE\u8bed\u53e5] {line_stripped[:30]}..."

            # \u79fb\u9664 .control \u548c .endc \u5757
            if not should_remove and re.match(r'^\.control\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[\u63a7\u5236\u5757] {line_stripped}"
            elif not should_remove and re.match(r'^\.endc\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[\u63a7\u5236\u5757] {line_stripped}"

            # \u79fb\u9664 .model \u8bed\u53e5（\u7531 spice_engine \u7edf\u4e00\u6ce8\u5165）
            if not should_remove and re.match(r'^\.model\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[\u6a21\u578b\u5b9a\u4e49] {line_stripped}"

            # \u79fb\u9664 .SUBCKT \u5b9a\u4e49
            if not should_remove and re.match(r'^\.subckt\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[\u5b50\u7535\u8def] {line_stripped}"

            # \u79fb\u9664 .include \u548c .lib \u8bed\u53e5
            if not should_remove and re.match(r'^\.include\s+|^\.lib\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[\u7981\u6b62\u5916\u90e8\u6a21\u578b] {line_stripped}"

            # \u68c0\u6d4b\u4e24\u7aef\u90fd\u63a5\u5730\u7684\u5143\u4ef6（\u7535\u6c14\u77ed\u8def，\u65e0\u610f\u4e49）
            if not should_remove:
                short_circuit_match = re.match(r'^([RC]\w+)\s+0\s+0\s+', line_stripped, re.IGNORECASE)
                if short_circuit_match:
                    should_remove = True
                    skip_message = f"[\u77ed\u8def\u9519\u8bef] {line_stripped}"

            # \u68c0\u6d4b\u7535\u5bb9\u503c\u683c\u5f0f\u9519\u8bef（\u4f7f\u7528\u7535\u963b\u5355\u4f4d k/M/Meg）
            if not should_remove:
                cap_match = re.match(r'^C\w+\s+\S+\s+\S+\s+(\S+)', line_stripped, re.IGNORECASE)
                if cap_match:
                    cap_value = cap_match.group(1).upper()
                    # \u68c0\u6d4b\u9519\u8bef\u7684\u5355\u4f4d
                    if re.search(r'[KMG]|MEG', cap_value):
                        should_remove = True
                        skip_message = f"[\u7535\u5bb9\u503c\u683c\u5f0f\u9519\u8bef] {line_stripped} - \u7535\u5bb9\u503c\u4e0d\u80fd\u4f7f\u7528 k/M/Meg \u5355\u4f4d！"

            # \u68c0\u6d4b C_comp \u9519\u8bef\u8fde\u63a5\u5728\u96c6\u7535\u6781\u548c\u57fa\u6781\u4e4b\u95f4（\u5f62\u6210\u5bc6\u52d2\u8d1f\u53cd\u9988）
            if not should_remove:
                # \u5339\u914d C_comp N_COLLECTOR N_BASE \u6216\u7c7b\u4f3c\u6a21\u5f0f
                comp_feedback = re.match(r'^C\w*\s+N_COLLECTOR\s+N_BASE', line_stripped, re.IGNORECASE)
                if comp_feedback:
                    should_remove = True
                    skip_message = f"[\u5bc6\u52d2\u8d1f\u53cd\u9988] {line_stripped} - C_comp\u8fde\u63a5\u5728\u96c6\u7535\u6781\u548c\u57fa\u6781\u4e4b\u95f4\u4f1a\u5bfc\u81f4\u589e\u76ca\u5f52\u96f6！"

            # \u68c0\u6d4b N_E_AC \u8282\u70b9（\u4f1a\u5bfc\u81f4\u76f4\u6d41\u60ac\u6d6e）
            if not should_remove:
                # \u5339\u914d\u8fde\u63a5\u5230 N_E_AC \u8282\u70b9\u7684\u5143\u4ef6
                neac_match = re.match(r'^[RC]\w*\s+\S+\s+N_E_AC\s+', line_stripped, re.IGNORECASE)
                if neac_match:
                    print(f"   [\u8b66\u544a] \u68c0\u6d4b\u5230 N_E_AC \u8282\u70b9！\u8fd9\u4f1a\u5bfc\u81f4\u76f4\u6d41\u60ac\u6d6e，\u5efa\u8bae\u6539\u4e3a RE \u76f4\u63a5\u63a5\u5730、CE \u5e76\u8054\u5728 RE \u4e0a")
                    # \u4e0d\u5220\u9664，\u53ea\u8b66\u544a，\u8ba9 LLM \u5728\u4e0b\u4e00\u8f6e\u4fee\u6b63

            if should_remove:
                removed_count += 1
            else:
                cleaned_lines.append(line)

        if removed_count > 0:
            print(f"   [\u6e05\u6d17\u7edf\u8ba1] \u79fb\u9664 {removed_count} \u884c\u65e0\u6548\u5185\u5bb9")

        return '\n'.join(cleaned_lines)

    def get_simulation_config(self) -> Dict[str, Any]:
        """
        \u8fd4\u56de\u4e09\u6781\u7ba1\u653e\u5927\u7535\u8def\u4eff\u771f\u914d\u7f6e

        \u4f7f\u7528\u4ea4\u6d41\u5206\u6790（AC）\u6d4b\u91cf\u9891\u7387\u54cd\u5e94\u548c\u4e2d\u9891\u589e\u76ca
        """
        return {
            'analysis_type': 'ac',
            'frequency_range': (10, 100000),  # 10Hz ~ 100kHz
            'points_per_decade': 10,
            'output_node': 'OUT',
            'description': '\u4e09\u6781\u7ba1\u653e\u5927\u7535\u8def\u4ea4\u6d41\u5206\u6790'
        }

    def parse_simulation_data(
        self,
        x_data: list,
        y_data: list,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        \u89e3\u6790\u4ea4\u6d41\u4eff\u771f\u6570\u636e，\u8ba1\u7b97\u4e2d\u9891\u589e\u76ca

        \u56e0\u4e3a\u8f93\u5165\u662f AC 1V，\u6240\u4ee5\u8f93\u51fa\u7535\u538b\u7684\u5927\u5c0f\u76f4\u63a5\u7b49\u4e8e\u7ebf\u6027\u589e\u76ca。
        """
        if not x_data or not y_data:
            return {'status': 'no_data', 'error': '\u4eff\u771f\u6570\u636e\u4e3a\u7a7a'}

        results = {}

        # \u6c42\u51fa\u6700\u5927\u8f93\u51fa\u7535\u538b（\u5373\u6700\u5927\u7ebf\u6027\u589e\u76ca）
        max_gain_db = max(y_data)
        results['max_gain_db'] = max_gain_db

        # \u8ba1\u7b97\u7ebf\u6027\u589e\u76ca
        max_gain_v = 10 ** (max_gain_db / 20)
        results['max_gain_v'] = max_gain_v

        # \u627e\u5230\u6700\u5927\u589e\u76ca\u5bf9\u5e94\u7684\u9891\u7387
        max_idx = y_data.index(max_gain_db)
        if max_idx < len(x_data):
            results['peak_freq_hz'] = x_data[max_idx]

        # \u8ba1\u7b97\u589e\u76ca\u5e73\u5766\u5ea6（\u7528\u4e8e\u5224\u65ad\u662f\u5426\u6b63\u5e38\u5de5\u4f5c）
        # \u6b63\u5e38\u653e\u5927\u5668\u5e94\u8be5\u5728\u4e2d\u9891\u6709\u5e73\u5766\u589e\u76ca，\u4f4e\u9891\u6eda\u964d
        low_freq_gains = y_data[:5]  # \u524d5\u4e2a\u70b9（\u4f4e\u9891）
        mid_freq_gains = y_data[len(y_data)//3:2*len(y_data)//3]  # \u4e2d\u95f4\u4e09\u5206\u4e4b\u4e00（\u4e2d\u9891）

        avg_low_gain = sum(low_freq_gains) / len(low_freq_gains) if low_freq_gains else 0
        avg_mid_gain = sum(mid_freq_gains) / len(mid_freq_gains) if mid_freq_gains else 0
        gain_rise = avg_mid_gain - avg_low_gain

        results['low_freq_gain_db'] = avg_low_gain
        results['mid_freq_gain_db'] = avg_mid_gain
        results['gain_rise_db'] = gain_rise

        # \u68c0\u67e5\u7535\u8def\u5de5\u4f5c\u72b6\u6001
        if max_gain_db < -100:
            # \u6781\u7aef\u60c5\u51b5：\u7535\u8def\u51e0\u4e4e\u65e0\u8f93\u51fa
            results['status'] = 'circuit_error'
            print(f"   [\u4e25\u91cd\u9519\u8bef] \u7535\u8def\u7ed3\u6784\u5f02\u5e38！\u6700\u5927\u589e\u76ca\u4ec5 {max_gain_db:.2f} dB")
            print(f"   \u53ef\u80fd\u539f\u56e0：1) \u4f7f\u7528\u4e86N_E_AC\u60ac\u6d6e\u8282\u70b9 2) \u7535\u5bb9\u503c\u683c\u5f0f\u9519\u8bef 3) \u5143\u4ef6\u8fde\u63a5\u9519\u8bef")
        elif max_gain_db < 0:
            # \u8d1f\u589e\u76ca：\u53ef\u80fd\u662f\u6709\u6e90\u5668\u4ef6\u622a\u6b62\u6216\u5bc6\u52d2\u8d1f\u53cd\u9988
            results['status'] = 'negative_feedback_or_cutoff'
            print(f"   [\u589e\u76ca\u5f02\u5e38] \u589e\u76ca\u4e3a\u8d1f\u503c {max_gain_db:.2f} dB！")
            print(f"   \u53ef\u80fd\u539f\u56e0：1) C_comp\u8fde\u63a5\u5728\u96c6\u7535\u6781-\u57fa\u6781\u4e4b\u95f4 2) \u4e09\u6781\u7ba1\u622a\u6b62 3) \u4f7f\u7528\u4e86\u60ac\u6d6e\u8282\u70b9")
        elif max_gain_db < 10:
            # \u589e\u76ca\u6781\u4f4e：\u53ef\u80fd\u662f\u4e09\u6781\u7ba1\u9971\u548c
            results['status'] = 'low_gain_possible_saturation'
            print(f"   [\u589e\u76ca\u8fc7\u4f4e] \u4e2d\u9891\u589e\u76ca\u4ec5 {max_gain_db:.2f} dB，\u53ef\u80fd\u4e09\u6781\u7ba1\u5df2\u9971\u548c！")
            print(f"   \u5efa\u8bae：\u68c0\u67e5 RC×Ic \u662f\u5426 > (VCC-Ve)，\u589e\u5927R1\u6216\u589e\u5927RE\u4ee5\u51cf\u5c0f\u96c6\u7535\u6781\u7535\u6d41")
        elif gain_rise < 5 and max_gain_db < 20:
            # \u589e\u76ca\u5e73\u5766\u4e14\u4f4e：\u53ef\u80fd\u662f\u65c1\u8def\u7535\u5bb9\u672a\u8d77\u4f5c\u7528\u6216\u62d3\u6251\u9519\u8bef
            results['status'] = 'flat_low_gain'
            print(f"   [\u589e\u76ca\u5e73\u5766] \u4e2d\u9891\u589e\u76ca {max_gain_db:.2f} dB，\u4f4e\u9891\u589e\u76ca {avg_low_gain:.2f} dB")
            print(f"   \u53ef\u80fd\u539f\u56e0：CE\u672a\u6b63\u786e\u65c1\u8def，\u6216\u4e09\u6781\u7ba1\u5de5\u4f5c\u70b9\u5f02\u5e38")
        else:
            results['status'] = 'ok'
            print(f"   [\u589e\u76ca\u6d4b\u91cf] \u4e2d\u9891\u589e\u76ca: {max_gain_db:.2f} dB（\u7ebf\u6027: {max_gain_v:.2f}）")

        # \u589e\u76ca\u504f\u79bb\u5ea6 (dB)
        if self._target_gain_db is not None:
            results['gain_error_db'] = abs(max_gain_db - self._target_gain_db)
            results['gain_deviation_pct'] = results['gain_error_db'] / self._target_gain_db * 100

        return results

    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:
        """
        \u751f\u6210\u4e09\u6781\u7ba1\u653e\u5927\u7535\u8def\u5224\u51b3\u6240\u9700\u7684 Prompt
        """

        # \u4f18\u5148\u4f7f\u7528 set_targets() \u6ce8\u5165\u7684\u76ee\u6807\u503c
        target_gain_db = self._target_gain_db or self._extract_target_gain(requirement)
        lower_bound = target_gain_db * 0.85
        upper_bound = target_gain_db * 1.15

        system_prompt = f"""\u4f60\u662f\u4e00\u4e2a\u4e13\u4e1a\u7684 SPICE \u4eff\u771f\u88c1\u5224\u5b98\u548c\u6a21\u62df\u7535\u8def\u4f18\u5316\u987e\u95ee。

【\u7535\u8def\u7c7b\u578b】: \u4e09\u6781\u7ba1\u5171\u5c04\u653e\u5927\u7535\u8def

【\u76ee\u6807\u589e\u76ca\u4e0e\u5bb9\u5dee】
- \u76ee\u6807\u589e\u76ca：{target_gain_db:.1f} dB
- \u5bb9\u5dee\u8303\u56f4：{lower_bound:.1f} dB ~ {upper_bound:.1f} dB（±15%）
- \u5224\u5b9a\u89c4\u5219：\u53ea\u8981 max_gain_db \u5728 {lower_bound:.1f}~{upper_bound:.1f} dB \u8303\u56f4\u5185\u5c31\u901a\u8fc7，\u65e0\u8bba\u9ad8\u4e8e\u8fd8\u662f\u4f4e\u4e8e\u76ee\u6807\u503c！
- \u6ce8\u610f：\u5355\u7ea7\u5171\u5c04\u653e\u5927\u5668\u5b9e\u9645\u589e\u76ca\u4e0a\u9650\u7ea6 40-50 dB

【\u5173\u952e：\u5224\u51b3\u4f9d\u636e】
- \u5fc5\u987b\u4f7f\u7528 max_gain_db（\u5cf0\u503c\u589e\u76ca）\u8fdb\u884c\u5224\u51b3
- \u5ffd\u7565 mid_freq_gain_db、low_freq_gain_db \u7b49\u8f85\u52a9\u6570\u636e

【\u589e\u76ca\u516c\u5f0f】
- \u5f00\u73af\u589e\u76ca：Au ≈ RC / re（re ≈ 26mV/Ie）
- \u5f53 Ie = 1mA \u65f6，re ≈ 26Ω

【\u6545\u969c\u8bca\u65ad\u4e0e\u89e3\u51b3】
1. **\u589e\u76ca\u6781\u4f4e（< 0dB \u6216\u8fdc\u4f4e\u4e8e\u76ee\u6807）**：
   - \u6700\u53ef\u80fd\u539f\u56e0：\u4e09\u6781\u7ba1\u9971\u548c！\u68c0\u67e5 RC × Ic \u662f\u5426 > (VCC - Ve - 2V)
   - \u89e3\u51b3：\u589e\u5927 R1 \u6216\u589e\u5927 RE，\u51cf\u5c0f\u96c6\u7535\u6781\u7535\u6d41

2. **\u589e\u76ca\u4e3a\u8d1f\u503c（< 0dB）**：
   - \u53ef\u80fd\u539f\u56e01：\u8865\u507f\u7535\u5bb9 C_comp \u9519\u8bef\u8fde\u63a5\u5728\u96c6\u7535\u6781\u548c\u57fa\u6781\u4e4b\u95f4
   - \u53ef\u80fd\u539f\u56e02：\u4f7f\u7528\u4e86 N_E_AC \u7b49\u60ac\u6d6e\u8282\u70b9
   - \u89e3\u51b3：\u5220\u9664 C_comp，\u5c06 RE \u76f4\u63a5\u63a5\u5730、CE \u5e76\u8054\u5728 RE \u4e0a

3. **\u7535\u5bb9\u503c\u683c\u5f0f\u9519\u8bef**：
   - \u9519\u8bef：`C_xxx NODE1 NODE2 10Meg`（\u4f7f\u7528\u4e86\u7535\u963b\u5355\u4f4d Meg）
   - \u6b63\u786e：`C_xxx NODE1 NODE2 10u`（\u4f7f\u7528\u6cd5\u62c9\u5355\u4f4d p/n/u/m）

4. **\u589e\u76ca\u7565\u4f4e**：\u589e\u5927 RC \u6216\u51cf\u5c0f RE
5. **\u589e\u76ca\u7565\u9ad8**：\u51cf\u5c0f RC \u6216\u589e\u5927 RE

【\u9971\u548c\u8bca\u65ad\u516c\u5f0f】
- Vb = 12V × R2/(R1+R2)
- Ic ≈ (Vb - 0.65V) / RE
- \u5982\u679c RC × Ic > 10V，\u5219\u4e09\u6781\u7ba1\u53ef\u80fd\u9971\u548c

【\u8f93\u51fa\u683c\u5f0f】
{{
  "passed": true\u6216false,
  "reason": "\u5224\u51b3\u539f\u56e0（\u4e00\u53e5\u8bdd）",
  "feedback": "\u5177\u4f53\u8c03\u6574\u5efa\u8bae"
}}"""

        user_prompt = f"【\u539f\u59cb\u8bbe\u8ba1\u9700\u6c42】:\n{requirement}\n\n【\u5b9e\u6d4b\u4eff\u771f\u6570\u636e】:\n{metrics_str}\n\n【\u76ee\u6807\u589e\u76ca】: {target_gain_db:.1f} dB，\u5bb9\u5dee\u8303\u56f4：{lower_bound:.1f} dB ~ {upper_bound:.1f} dB\n\n\u8bf7\u4f7f\u7528 max_gain_db \u8fdb\u884c\u5224\u51b3，\u5e76\u7ed9\u51fa\u4f18\u5316\u5efa\u8bae："

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        \u786c\u9608\u503c\u5224\u51b3（\u4e0d\u4f7f\u7528 LLM）

        \u7528\u4e8e G3 (No_Metric) \u6d88\u878d\u5b9e\u9a8c。
        \u589e\u76ca\u5224\u65ad\u89c4\u5219：\u76ee\u6807\u503c\u7684 85% ~ 115% \u4e3a\u901a\u8fc7
        """
        # \u63d0\u53d6\u76ee\u6807\u589e\u76ca
        # \u4f18\u5148\u4f7f\u7528 set_targets() \u6ce8\u5165\u7684\u76ee\u6807\u503c
        target_gain = self._target_gain_db or self._extract_target_gain(requirement)

        if not target_gain:
            return True, "\u9700\u6c42\u4e2d\u672a\u6307\u5b9a\u76ee\u6807\u589e\u76ca，\u9ed8\u8ba4\u901a\u8fc7"

        # \u4ece metrics \u4e2d\u63d0\u53d6\u5b9e\u9645\u589e\u76ca
        actual_gain = metrics.get('max_gain_db')
        if actual_gain is None:
            return False, "\u65e0\u6cd5\u4ece\u4eff\u771f\u6570\u636e\u4e2d\u63d0\u53d6\u589e\u76ca"

        # \u786c\u9608\u503c\u5224\u65ad：85% ~ 115%
        # \u786c\u9608\u503c\u5224\u65ad：90% ~ 110% (G3: \u6bd4 LLM judge \u66f4\u4e25\u683c)
        min_gain = target_gain * 0.9
        max_gain = target_gain * 1.1

        if min_gain <= actual_gain <= max_gain:
            return True, f"\u589e\u76ca {actual_gain:.1f}dB \u5728\u76ee\u6807\u8303\u56f4 {min_gain:.1f}-{max_gain:.1f}dB \u5185"
        else:
            if actual_gain < min_gain:
                feedback = f"\u589e\u76ca {actual_gain:.1f}dB \u592a\u4f4e（\u76ee\u6807 {target_gain:.1f}dB），\u9700\u8981\u589e\u5927 Rc \u6216\u51cf\u5c0f Re"
            else:
                feedback = f"\u589e\u76ca {actual_gain:.1f}dB \u592a\u9ad8（\u76ee\u6807 {target_gain:.1f}dB），\u9700\u8981\u51cf\u5c0f Rc \u6216\u589e\u5927 Re"
            return False, feedback

    def _extract_target_gain(self, requirement: str) -> Optional[float]:
        """\u4ece\u9700\u6c42\u4e2d\u63d0\u53d6\u76ee\u6807\u589e\u76ca（\u5355\u4f4d：dB）"""
        # \u5339\u914d "\u589e\u76ca\u4e3a40db", "\u589e\u76ca40dB", "\u589e\u76ca40db" \u7b49\u683c\u5f0f
        match = re.search(r'\u589e\u76ca.*?(\d+(?:\.\d+)?)\s*dB', requirement, re.IGNORECASE)
        if match:
            return float(match.group(1))
        # \u5339\u914d "\u589e\u76ca\u4e3a40"（\u5047\u8bbe\u5355\u4f4d\u662f dB）
        match = re.search(r'\u589e\u76ca.*?(\d+(?:\.\d+)?)(?!\s*dB)', requirement)
        if match:
            return float(match.group(1))
        return None
