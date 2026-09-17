"""
\u7a33\u538b\u4e8c\u6781\u7ba1\u5e76\u8054\u7a33\u538b\u7535\u8def\u4e13\u5bb6

\u4e13\u95e8\u5904\u7406 Zener Diode Shunt Regulator \u7535\u8def。
\u6d89\u53ca\u65f6\u57df（Tran \u77ac\u6001\u5206\u6790），\u9a8c\u8bc1\u8f93\u51fa\u7535\u538b\u7a33\u5b9a\u6027\u548c\u7eb9\u6ce2\u6291\u5236\u80fd\u529b。
"""

import re
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class ZenerRegulatorExpert(CircuitExpert):
    """\u7a33\u538b\u4e8c\u6781\u7ba1\u5e76\u8054\u7a33\u538b\u7535\u8def\u4e13\u5bb6"""

    def __init__(self):
        super().__init__()
        self._zener_model = "1N4733A"
        self._zener_voltage = 5.1

    def set_targets(self, targets: Optional[Dict] = None):
        super().set_targets(targets)
        if targets and targets.get("metric") == "v_out_avg_v":
            self._zener_voltage = targets.get("value")  # \u8986\u76d6\u6a21\u578b\u67e5\u627e\u503c

    @property
    def circuit_type(self) -> str:
        return "zener_regulator"

    def get_circuit_description(self) -> str:
        return "\u7a33\u538b\u4e8c\u6781\u7ba1\u5e76\u8054\u7a33\u538b\u7535\u8def"

    def _parse_uid_model_map(self, uid_hint: str) -> Dict[str, str]:
        uid_model_map = {}
        parts = uid_hint.split('、')
        for part in parts:
            match = re.match(r'(\w+)\(([^)]+)\)', part.strip())
            if match:
                uid = match.group(1)
                model = match.group(2)
                uid_model_map[uid] = model
        return uid_model_map

    def _extract_zener_voltage(self, model: str) -> float:
        zener_voltages = {
            '1N4728': 3.3, '1N4728A': 3.3,
            '1N4729': 3.6, '1N4729A': 3.6,
            '1N4730': 3.9, '1N4730A': 3.9,
            '1N4731': 4.3, '1N4731A': 4.3,
            '1N4732': 4.7, '1N4732A': 4.7,
            '1N4733': 5.1, '1N4733A': 5.1,
            '1N4734': 5.6, '1N4734A': 5.6,
            '1N4735': 6.2, '1N4735A': 6.2,
            '1N4736': 6.8, '1N4736A': 6.8,
            '1N4737': 7.5, '1N4737A': 7.5,
            '1N4738': 8.2, '1N4738A': 8.2,
            '1N4739': 9.1, '1N4739A': 9.1,
            '1N4740': 10.0, '1N4740A': 10.0,
            '1N4741': 11.0, '1N4741A': 11.0,
            '1N4742': 12.0, '1N4742A': 12.0,
            '1N4743': 13.0, '1N4743A': 13.0,
            '1N4744': 15.0, '1N4744A': 15.0,
            '1N4745': 16.0, '1N4745A': 16.0,
            '1N4746': 18.0, '1N4746A': 18.0,
            '1N4747': 20.0, '1N4747A': 20.0,
            '1N4748': 22.0, '1N4748A': 22.0,
            '1N4749': 24.0, '1N4749A': 24.0,
            '1N4750': 27.0, '1N4750A': 27.0,
            '1N4751': 30.0, '1N4751A': 30.0,
        }
        model_upper = model.upper()
        return zener_voltages.get(model_upper, 5.1)

    def get_netlist_prompts(
        self,
        elaborated_req: str,
        uid_hint: str,
        iteration: int,
        previous_spice: Optional[str],
        feedback: Optional[str]
    ) -> Tuple[str, str]:
        """Generate supply-connected shunt or buffered regulator guidance."""
        system_prompt = f"""Design the Zener regulator specified in the requirement.
Return one complete SPICE deck without surrounding prose.
Use the provided component identifiers: {uid_hint}.
The public interface determines input/output nodes, supply and load names,
device models, targets and test conditions. Component-library hints do not
override that interface. Include an explicit nonzero DC supply and every
required load. A node label alone is not a power source.

For a shunt regulator, connect the feed resistor from the powered supply node
to the regulated node, the Zener cathode to that node and anode to ground,
and the load from that node to ground. Check that the feed resistor actually
shares a node with the supply; do not use a disconnected input alias.
At minimum input and maximum load, require
(Vin_min - Vz)/Rfeed > Iload_max + Iz_min.
At maximum input and minimum load, check Zener and resistor dissipation.
Use the provided model and simulate its loaded operating point; the nominal
Zener voltage alone does not establish regulation.

Include a buffer only when requested. For an NPN emitter follower, connect the
collector to the supply, base to the biased Zener node and emitter to OUT.
Account for base current and Vout approximately Vz - Vbe. The Zener node and
OUT are distinct in this topology. For an explicitly requested op-amp buffer,
provide its supply rails and negative feedback from its own output.
Do not add a buffer to an unbuffered shunt requirement.
Use native device terminal ordering and the supplied model catalog.

On repair, first resolve parsing and connectivity errors, then verify supply,
load, bias current and voltage under each requested condition. Change values
or incorrect connections as needed while retaining the requested topology.
Planner values are initial suggestions and may be revised when simulation
shows that they do not satisfy the original requirement."""
        user_prompt = f"Requirement:\n{elaborated_req}\nComponent identifiers: {uid_hint}"
        if iteration > 1:
            user_prompt += f"\nPrevious deck:\n{previous_spice}\nEvaluation feedback:\n{feedback}"
        return system_prompt, user_prompt

    def clean_spice_code(self, spice_code: str) -> str:
        lines = spice_code.split('\n')
        cleaned_lines = []
        removed_count = 0

        for line in lines:
            line_stripped = line.strip()
            should_remove = False
            skip_message = None
            replacement_line = None

            if re.match(r'^\.control\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[\u63a7\u5236\u5757] {line_stripped}"
            elif re.match(r'^\.endc\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[\u63a7\u5236\u5757] {line_stripped}"
            elif re.match(r'^\.model\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[\u6a21\u578b\u5b9a\u4e49] {line_stripped}"
            elif re.match(r'^\.subckt\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[\u5b50\u7535\u8def] {line_stripped}"
            # 🔧 \u4fee\u590d：\u5c06\u4fdd\u9669\u4e1d\u8f6c\u6362\u4e3a\u5c0f\u7535\u963b (SPICE \u4e0d\u652f\u6301 FUSE \u5143\u4ef6\u7c7b\u578b)
            # \u5339\u914d: FUSE, F1, F2, F_FUSE, F_PROTECT \u7b49（F\u5f00\u5934，\u540e\u8ddf\u6570\u5b57\u6216\u4e0b\u5212\u7ebf\u6216\u5b57\u6bcd\u7684\u4fdd\u9669\u4e1d\u547d\u540d）
            elif re.match(r'^F(USE|[0-9]+|_[A-Za-z0-9]+)\s+', line_stripped, re.IGNORECASE):
                parts = line_stripped.split()
                if len(parts) >= 3:
                    # Fuse node1 node2 [value] -> R_Fuse node1 node2 0.01
                    orig_name = parts[0]
                    node1, node2 = parts[1], parts[2]
                    replacement_line = f"R_{orig_name} {node1} {node2} 0.01"
                    print(f"   [SPICE\u4fee\u590d] {orig_name} -> R_{orig_name} (0.01Ω \u7b49\u6548\u7535\u963b，SPICE\u4e0d\u652f\u6301FUSE)")
                should_remove = True

            if should_remove:
                removed_count += 1
                if skip_message:
                    print(f"   [\u81ea\u52a8\u6e05\u6d17] {skip_message}")
            else:
                cleaned_lines.append(line)

            # \u6dfb\u52a0\u66ff\u6362\u884c（\u5728\u79fb\u9664\u539f\u884c\u540e）
            if replacement_line:
                cleaned_lines.append(replacement_line)

        if removed_count > 0:
            print(f"   \u8b66\u544a：LLM \u751f\u6210\u4e86 {removed_count} \u4e2a\u9519\u8bef\u884c，\u5df2\u81ea\u52a8\u79fb\u9664")

        return '\n'.join(cleaned_lines)

    def get_simulation_config(self) -> Dict[str, Any]:
        return {
            'analysis_type': 'tran',
            'tran_time': '100m',
            'time_step': '100u',
            'output_node': 'OUT',
            'description': '\u5e76\u8054\u7a33\u538b\u7535\u8def\u77ac\u6001\u5206\u6790'
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

        steady_y = []
        for i, t in enumerate(x_data):
            if t > 0.02:
                steady_y.append(y_data[i])

        if not steady_y:
            results['status'] = 'sim_error'
            print(f"   ⚠️ \u7a33\u6001\u6570\u636e\u4e3a\u7a7a！")
            return results

        v_max = max(steady_y)
        v_min = min(steady_y)
        v_ripple = v_max - v_min
        v_avg = sum(steady_y) / len(steady_y)

        results['v_out_avg_v'] = v_avg
        results['v_max_v'] = v_max
        results['v_min_v'] = v_min
        results['v_ripple_v'] = v_ripple

        if v_avg > 0:
            ripple_percent = (v_ripple / v_avg) * 100
            results['ripple_percent'] = ripple_percent
        else:
            results['ripple_percent'] = 100.0

        results['status'] = 'ok'
        print(f"   [\u7535\u538b\u5206\u6790] \u5e73\u5747\u8f93\u51fa: {v_avg:.2f}V, \u7eb9\u6ce2: {v_ripple:.3f}V ({results['ripple_percent']:.1f}%)")

        # \u8f93\u51fa\u7535\u538b\u504f\u79bb\u5ea6\u767e\u5206\u6bd4
        if self._zener_voltage and v_avg > 0:
            results['voltage_error_percent'] = abs(v_avg - self._zener_voltage) / self._zener_voltage * 100

        return results

    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:

        # \u4f7f\u7528\u5b9e\u4f8b\u4e2d\u4fdd\u5b58\u7684\u7a33\u538b\u503c
        zv = self._zener_voltage
        # \u8ba1\u7b97\u5bb9\u5dee\u8303\u56f4 (±10%)
        min_v = zv * 0.9
        max_v = zv * 1.1

        system_prompt = f"""\u4f60\u662f\u4e00\u4e2aSPICE\u4eff\u771f\u88c1\u5224\u5b98。

【\u5224\u51b3\u51c6\u5219】
1. \u8f93\u51fa\u7535\u538b\u5e94\u5728\u7a33\u538b\u503c\u9644\u8fd1（\u5f53\u524d\u7a33\u538b\u7ba1 {self._zener_model} \u6807\u79f0\u503c = {zv}V，\u5141\u8bb8\u8bef\u5dee ±10%）
   - \u5408\u683c\u8303\u56f4：{min_v:.2f}V ~ {max_v:.2f}V
   - \u5224\u5b9a\u89c4\u5219：\u53ea\u8981 v_out_avg \u5728 {min_v:.2f}~{max_v:.2f}V \u8303\u56f4\u5185\u5c31\u901a\u8fc7，\u65e0\u8bba\u9ad8\u4e8e\u8fd8\u662f\u4f4e\u4e8e\u76ee\u6807\u503c！
2. \u8f93\u51fa\u7535\u538b\u63a5\u8fd10V\u62160.7V = \u7a33\u538b\u4e8c\u6781\u7ba1\u6781\u6027\u9519\u8bef\u6216\u7535\u8def\u62d3\u6251\u9519\u8bef
3. \u7eb9\u6ce2\u5e94\u5c0f\u4e8e\u8f93\u51fa\u7535\u538b\u76845%

【\u5e38\u89c1\u95ee\u9898\u8bca\u65ad】
- \u8f93\u51fa\u7535\u538b\u504f\u4f4e\u4f46\u7a33\u538b\u7ba1\u4e24\u7aef\u7535\u538b\u6b63\u5e38 → \u7a33\u538b\u7ba1\u6ca1\u76f4\u63a5\u63a5\u5728OUT\u8282\u70b9，\u88ab\u5206\u538b\u4e86
- \u8f93\u51fa\u7535\u538b\u7ea60.7V → \u7a33\u538b\u7ba1\u6b63\u5411\u504f\u7f6e（\u6781\u6027\u63a5\u53cd）
- \u8f93\u51fa\u7535\u538b\u4e3a0V → \u7a33\u538b\u7ba1\u6216\u7535\u963b\u672a\u6b63\u786e\u8fde\u63a5

【\u8f93\u51fa\u683c\u5f0f】
{{
  "passed": true\u6216false,
  "reason": "\u5224\u51b3\u539f\u56e0",
  "feedback": "\u5177\u4f53\u4fee\u590d\u5efa\u8bae（\u5fc5\u987b\u660e\u786e\u6307\u51fa\u5982\u4f55\u4fee\u6539SPICE\u4ee3\u7801）"
}}"""

        user_prompt = f"【\u8bbe\u8ba1\u9700\u6c42】:\n{requirement}\n\n【\u4eff\u771f\u6570\u636e】:\n{metrics_str}\n\n\u8bf7\u5224\u51b3："

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        \u786c\u9608\u503c\u5224\u51b3（\u4e0d\u4f7f\u7528 LLM）

        \u7528\u4e8e G3 (No_Metric) \u6d88\u878d\u5b9e\u9a8c。
        \u7a33\u538b\u8f93\u51fa\u5224\u65ad\u89c4\u5219：\u76ee\u6807\u503c\u7684 90% ~ 110% \u4e3a\u901a\u8fc7
        """
        zv = self._zener_voltage
        if not zv:
            return True, "\u65e0\u6cd5\u786e\u5b9a\u7a33\u538b\u76ee\u6807\u503c，\u9ed8\u8ba4\u901a\u8fc7"

        # \u4ece metrics \u4e2d\u63d0\u53d6\u5b9e\u9645\u8f93\u51fa\u7535\u538b
        actual_voltage = metrics.get('v_out_avg_v')
        if actual_voltage is None:
            return False, "\u65e0\u6cd5\u4ece\u4eff\u771f\u6570\u636e\u4e2d\u63d0\u53d6\u8f93\u51fa\u7535\u538b"

        # \u786c\u9608\u503c\u5224\u65ad：95% ~ 105% (G3: \u6bd4 LLM judge \u66f4\u4e25\u683c)
        min_v = zv * 0.95
        max_v = zv * 1.05

        if min_v <= actual_voltage <= max_v:
            return True, f"\u8f93\u51fa\u7535\u538b {actual_voltage:.2f}V \u5728\u76ee\u6807\u8303\u56f4 {min_v:.2f}-{max_v:.2f}V \u5185"
        else:
            if actual_voltage < min_v:
                feedback = f"\u8f93\u51fa\u7535\u538b {actual_voltage:.2f}V \u592a\u4f4e（\u76ee\u6807 {zv:.2f}V），\u53ef\u80fd\u662f\u7a33\u538b\u7ba1\u6781\u6027\u63a5\u53cd\u6216\u672a\u6b63\u786e\u8fde\u63a5"
            else:
                feedback = f"\u8f93\u51fa\u7535\u538b {actual_voltage:.2f}V \u592a\u9ad8（\u76ee\u6807 {zv:.2f}V），\u53ef\u80fd\u662f\u8d1f\u8f7d\u592a\u8f7b\u6216\u7a33\u538b\u7ba1\u578b\u53f7\u4e0d\u5339\u914d"
            return False, feedback
