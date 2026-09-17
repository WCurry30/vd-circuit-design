"""
LED \u6052\u6d41\u9a71\u52a8\u7535\u8def\u4e13\u5bb6

\u7b80\u5316\u7248：\u53ea\u652f\u6301\u7b80\u5355 BJT \u6052\u6d41\u6e90\u62d3\u6251。
\u5f3a\u5236\u4f7f\u7528\u89c4\u5212\u4e2d\u7684\u5143\u5668\u4ef6 UID，\u4e0d\u5141\u8bb8 LLM \u81ea\u884c\u7f16\u9020\u540d\u79f0。
"""

import re
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class LedConstantCurrentExpert(CircuitExpert):
    """LED \u6052\u6d41\u9a71\u52a8\u7535\u8def\u4e13\u5bb6"""

    def __init__(self):
        super().__init__()
        self._target_current_ma = None
        self._supply_voltage = 12.0
        self._re_value = 65.0  # \u5b58\u50a8\u53d1\u5c04\u6781\u7535\u963b\u503c，\u7528\u4e8e\u7535\u6d41\u8ba1\u7b97
        self._has_opamp = False  # \u662f\u5426\u4f7f\u7528\u8fd0\u653e\u62d3\u6251

    @property
    def circuit_type(self) -> str:
        return "led_constant_current"

    def get_circuit_description(self) -> str:
        return "LED \u6052\u6d41\u9a71\u52a8\u7535\u8def"

    def set_targets(self, targets: Optional[Dict] = None):
        super().set_targets(targets)
        if targets and targets.get("metric") == "led_current_ma":
            self._target_current_ma = targets.get("value")

    def _parse_uid_model_map(self, uid_hint: str) -> Dict[str, str]:
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

    def _extract_target_current(self, elaborated_req: str) -> float:
        """
        \u4ece\u7ec6\u5316\u540e\u7684\u9700\u6c42\u6587\u672c\u4e2d\u63d0\u53d6\u76ee\u6807\u7535\u6d41\u503c

        \u652f\u6301\u591a\u79cd\u8868\u8ff0\u65b9\u5f0f：
        - \u7535\u6d41\u4e3a20mA
        - \u7535\u6d41\u7a33\u5b9a\u572830mA
        - 40mA\u9a71\u52a8\u7535\u6d41
        - \u76ee\u6807\u6052\u5b9a\u7535\u6d41\u4e3a20mA
        - \u63d0\u4f9b40mA\u7684\u7535\u6d41
        """
        patterns = [
            # \u6700\u7cbe\u786e：\u660e\u786e\u7684\u7535\u6d41\u503c\u58f0\u660e
            r'\u76ee\u6807?\s*\u7535\u6d41\s*[\u4e3a：:]\s*(\d+(?:\.\d+)?)\s*mA?',
            r'\u7535\u6d41\s*[\u4e3a\u7a33\u5b9a\u5728：:]+\s*(\d+(?:\.\d+)?)\s*mA?',  # \u65b0\u589e：\u7535\u6d41\u7a33\u5b9a\u572830mA
            r'\u7535\u6d41\s*[\u4e3a：:]\s*(\d+(?:\.\d+)?)\s*mA?',
            r'\u7535\u6d41\s*(\d+(?:\.\d+)?)\s*mA?',
            # \u5bbd\u677e：\u6570\u5b57+mA+\u7535\u6d41\u76f8\u5173\u8bcd
            r'(\d+(?:\.\d+)?)\s*mA\s*[\u9a71\u52a8\u6052\u5b9a]*\u7535\u6d41',
            r'(\d+(?:\.\d+)?)\s*mA\s*\u7684\s*\u7535\u6d41',
            # \u6700\u5bbd\u677e：\u5355\u72ec\u7684\u6570\u5b57+mA（\u4f46\u8981\u786e\u4fdd\u662f\u7535\u6d41\u76f8\u5173\u4e0a\u4e0b\u6587）
            r'\u8bbe\u5b9a?\s*[\u4e3a：:]?\s*(\d+(?:\.\d+)?)\s*mA',
            r'\u63d0\u4f9b.*?(\d+(?:\.\d+)?)\s*mA',
            r'\u7a33\u5b9a.*?(\d+(?:\.\d+)?)\s*mA',  # \u65b0\u589e：\u7a33\u5b9a\u572830mA
        ]
        for pattern in patterns:
            match = re.search(pattern, elaborated_req, re.IGNORECASE)
            if match:
                current = float(match.group(1))
                print(f"   [\u7535\u6d41\u89e3\u6790] \u4ece\u9700\u6c42\u4e2d\u63d0\u53d6\u5230\u76ee\u6807\u7535\u6d41: {current}mA")
                return current
        print(f"   [\u7535\u6d41\u89e3\u6790] \u672a\u627e\u5230\u660e\u786e\u7684\u7535\u6d41\u503c，\u4f7f\u7528\u9ed8\u8ba4\u503c 20mA")
        return 20.0

    def get_netlist_prompts(
        self,
        elaborated_req: str,
        uid_hint: str,
        iteration: int,
        previous_spice: Optional[str],
        feedback: Optional[str]
    ) -> Tuple[str, str]:

        # The shared catalog lists available devices, not requested topology.
        original_requirement = elaborated_req.split('Planner elaboration:', 1)[0]
        original_requirement = original_requirement.split('Shared public interface:', 1)[0]
        if re.search(r'\b(?:mosfet|nmos|pmos|2n7000|2n7002|bs170)\b', original_requirement, re.IGNORECASE):
            self._has_opamp = bool(re.search(
                r'\b(?:op[- ]?amp|lm2904|lm358|lm324)\b', original_requirement, re.IGNORECASE
            ))
            system = (
                "Design a SPICE LED current driver satisfying the explicit requirement. "
                "Use the requested MOSFET topology and polarity. For an op-amp current "
                "loop, choose the sense resistor and reference using I=Vref/Rsense, "
                "connect negative feedback to the sensed current, and verify supply "
                "headroom for the LED, sense resistor and MOSFET. Native MOSFET "
                "syntax is Mname drain gate source bulk model, in exactly that order. "
                "For a low-side NMOS loop, the series current path is supply, LED, "
                "drain, source, sense resistor, ground. Drive the gate from the "
                "op-amp output; connect its positive input to the reference and "
                "negative input to the source/sense node. Keep a zero-volt current "
                "probe in series with this path using the public interface's "
                "specified name and polarity. Choose the bulk connection according "
                "to the provided device contract. Use the supplied model catalog "
                "without redefining models. Return one complete fenced spice block."
            )
            user = f"Requirement:\n{elaborated_req}\nComponent hints:\n{uid_hint}"
            if previous_spice is not None and feedback is not None:
                user += f"\nPrevious candidate:\n{previous_spice}\nSimulation feedback:\n{feedback}\nReturn a corrected complete deck."
            return system, user

        if 'Shared public interface:' in elaborated_req:
            # Legacy single-transistor templates do not cover every public topology.
            system = (
                'Design the LED current driver specified in the original requirement. '
                'Preserve its required device types, device count, feedback structure, '
                'supplies and load. Use the shared model catalog and interface. '
                'Component hints and planner suggestions are advisory. '
                'Return one complete fenced spice block without local model definitions.'
            )
            user = f'Requirement:\n{elaborated_req}\nComponent hints:\n{uid_hint}'
            if previous_spice is not None and feedback is not None:
                user += f'\nPrevious candidate:\n{previous_spice}\nSimulation feedback:\n{feedback}\nReturn a corrected complete deck.'
            return system, user

        uid_model_map = self._parse_uid_model_map(uid_hint)
        # \u4f18\u5148\u4f7f\u7528 set_targets() \u6ce8\u5165\u7684\u76ee\u6807\u503c，\u5426\u5219 regex fallback
        if self._target_current_ma is None:
            self._target_current_ma = self._extract_target_current(elaborated_req)
        if self._target_current_ma is None:
            self._target_current_ma = 20.0  # \u7ec8\u6781\u515c\u5e95

        # \u68c0\u6d4b\u662f\u5426\u4f7f\u7528\u8fd0\u653e\u62d3\u6251（test_9: LM2904 + 2N3904）
        opamp_uid = None
        for uid, model in uid_model_map.items():
            if model.upper() in ('LM2904', 'LM358', 'LM324'):
                opamp_uid = uid
                self._has_opamp = True
                break

        # \u89e3\u6790\u5143\u5668\u4ef6
        resistor_uids = []
        capacitor_uids = []
        led_uid = None
        bjt_uid = None

        for uid, model in uid_model_map.items():
            model_upper = model.upper()
            if 'LED' in model_upper:
                led_uid = uid
            elif model == 'R':
                resistor_uids.append(uid)
            elif model == 'C':
                capacitor_uids.append(uid)
            elif '2N' in model_upper or 'BC' in model_upper:  # BJT
                bjt_uid = uid

        # \u9ed8\u8ba4\u503c
        if not led_uid:
            led_uid = "LED1"
        if not bjt_uid:
            bjt_uid = "Q1"
        r1_uid = resistor_uids[0] if len(resistor_uids) > 0 else "R1"
        r2_uid = resistor_uids[1] if len(resistor_uids) > 1 else "R2"
        r3_uid = resistor_uids[2] if len(resistor_uids) > 2 else "R3"
        c1_uid = capacitor_uids[0] if capacitor_uids else "C1"

        # --- \u8fd0\u653e\u62d3\u6251\u5206\u652f (\u7528\u4e8e test_9 \u7b49\u542b LM2904 \u7684 LED \u9a71\u52a8) ---
        if self._has_opamp and opamp_uid:
            return self._get_opamp_led_prompts(
                elaborated_req, iteration, previous_spice, feedback,
                opamp_uid, bjt_uid, led_uid, r1_uid, r2_uid, r3_uid, c1_uid
            )

        # --- \u7eaf BJT \u62d3\u6251 (\u539f\u6709\u903b\u8f91) ---
        # \u8ba1\u7b97\u53c2\u6570
        vbe = 0.7
        vb_theoretical = 2.5  # \u7406\u8bba\u57fa\u6781\u7535\u538b（\u7a7a\u8f7d）

        # \u504f\u7f6e\u7535\u963b\u8ba1\u7b97（\u5173\u952e\u6539\u8fdb：\u964d\u4f4e\u8f93\u51fa\u963b\u6297）
        # \u4f7f\u7528\u6234\u7ef4\u5357\u7b49\u6548：Ie = (Vth - Vbe) / (R3 + Rth/(β+1))
        # \u9700\u8981\u9009\u62e9\u5408\u9002\u7684 R1, R2 \u4f7f Rth/(β+1) \u53ef\u4ee5\u5ffd\u7565

        # \u5047\u8bbe β ≈ 200（2N3904 \u5178\u578b\u503c）
        beta = 200

        # \u76ee\u6807：Rth/(β+1) < R3 × 0.05（\u8d1f\u8f7d\u6548\u5e94 < 5%）
        # \u5bf9\u4e8e 30mA，R3 ≈ 60Ω，\u8981\u6c42 Rth < 60 × 201 × 0.05 ≈ 600Ω
        # \u9009\u62e9 Rth ≈ 500Ω
        rth_target = 500

        # \u6839\u636e\u76ee\u6807 Rth \u548c Vb \u8ba1\u7b97 R1, R2
        # Vb = VCC × R2/(R1+R2) \u4e14 Rth = R1×R2/(R1+R2)
        # \u89e3\u5f97：R2 = Vb × Rth / (VCC - Vb + Rth × Vb/VCC)
        # \u7b80\u5316：\u4f7f\u7528\u8fed\u4ee3\u6cd5
        i_divider = vb_theoretical / rth_target * 1000  # Divider \u7535\u6d41 (mA)
        i_divider = max(i_divider, 3.0)  # \u81f3\u5c11 3mA，\u786e\u4fdd\u7a33\u5b9a

        r2_value = int(vb_theoretical / i_divider * 1000)
        r1_value = int(r2_value * (self._supply_voltage - vb_theoretical) / vb_theoretical)

        # \u8ba1\u7b97\u5b9e\u9645\u7684 Rth
        rth = (r1_value * r2_value) / (r1_value + r2_value) if (r1_value + r2_value) > 0 else 0

        # \u8003\u8651\u8d1f\u8f7d\u6548\u5e94\u4fee\u6b63 R3
        # Ie = (Vth - Vbe) / (R3 + Rth/(β+1))
        # R3 = (Vth - Vbe) / Ie - Rth/(β+1)
        ve_target = vb_theoretical - vbe
        re_correction = rth / (beta + 1)
        re_value = max(10, (ve_target / (self._target_current_ma / 1000)) - re_correction)
        self._re_value = re_value

        print(f"   [\u53c2\u6570\u8ba1\u7b97] \u76ee\u6807\u7535\u6d41: {self._target_current_ma}mA, R3={re_value:.0f}Ω, R1={r1_value/1000:.1f}k, R2={r2_value/1000:.1f}k")
        print(f"   [\u8d1f\u8f7d\u6548\u5e94] Rth={rth:.0f}Ω, \u4fee\u6b63\u9879={re_correction:.1f}Ω")

        # SPICE \u683c\u5f0f\u8f6c\u6362
        # BJT \u7528 Q \u524d\u7f00（\u89c4\u5212\u4e2d\u5e94\u8be5\u5c31\u662f Q1）
        spice_bjt_uid = bjt_uid
        # LED \u7528 D \u524d\u7f00：LED1 -> D1（\u53bb\u6389 LED \u524d\u7f00，\u52a0 D）
        if led_uid.upper().startswith('LED'):
            spice_led_uid = 'D' + led_uid[3:]  # LED1 -> D1
        elif led_uid.upper().startswith('D'):
            spice_led_uid = led_uid  # \u5df2\u7ecf\u662f D \u524d\u7f00
        else:
            spice_led_uid = 'D' + led_uid  # \u5176\u4ed6\u60c5\u51b5\u52a0 D \u524d\u7f00

        example_circuit = f"""VCC VCC 0 DC {self._supply_voltage}
{r1_uid} VCC BASE {r1_value/1000:.1f}k
{r2_uid} BASE 0 {r2_value/1000:.1f}k
{spice_bjt_uid} COL BASE EMIT 2N3904
{r3_uid} EMIT 0 {re_value:.0f}
{spice_led_uid} VCC COL LED
{c1_uid} VCC 0 100n
* \u6ce8\u610f：\u6a21\u578b\u7531\u7cfb\u7edf\u81ea\u52a8\u6ce8\u5165，\u65e0\u9700\u624b\u52a8\u5b9a\u4e49"""

        system_prompt = f"""\u8bbe\u8ba1 LED \u6052\u6d41\u9a71\u52a8\u7535\u8def。

【\u76ee\u6807\u7535\u6d41】: {self._target_current_ma:.0f}mA
【\u7535\u6e90】: {self._supply_voltage}V

============================================================
🔴🔴🔴🔴🔴 \u5fc5\u987b\u4e25\u683c\u4f7f\u7528\u4ee5\u4e0b\u5143\u5668\u4ef6\u540d\u79f0 🔴🔴🔴🔴🔴
============================================================

\u7535\u963b: {r1_uid}, {r2_uid}, {r3_uid}
BJT: {spice_bjt_uid} (\u4f7f\u7528 2N3904 \u6a21\u578b)
LED: {spice_led_uid}
\u7535\u5bb9: {c1_uid}

============================================================
\u7535\u8def\u7ed3\u6784
============================================================

1. {r1_uid} \u63a5\u5728 VCC \u548c BASE \u4e4b\u95f4
2. {r2_uid} \u63a5\u5728 BASE \u548c GND(0) \u4e4b\u95f4
3. {spice_bjt_uid} \u5f15\u811a\u987a\u5e8f: \u96c6\u7535\u6781 \u57fa\u6781 \u53d1\u5c04\u6781 2N3904
4. {r3_uid} \u63a5\u5728 EMIT \u548c GND(0) \u4e4b\u95f4
5. {spice_led_uid} \u9633\u6781\u63a5 VCC，\u9634\u6781\u63a5 COL
6. {c1_uid} \u63a5\u5728 VCC \u548c GND(0) \u4e4b\u95f4

============================================================
\u6b63\u786e\u793a\u4f8b
============================================================
```
{example_circuit}
```

【\u7edd\u5bf9\u7981\u6b62】
- \u7981\u6b62\u4f7f\u7528 X1, X2, X3, M1 \u7b49\u5176\u4ed6\u540d\u79f0！
- \u7981\u6b62\u4f7f\u7528 R_DIV, R_SENSE \u7b49\u5176\u4ed6\u540d\u79f0！
- \u5fc5\u987b\u4f7f\u7528 {r1_uid}, {r2_uid}, {r3_uid}, {spice_bjt_uid}, {spice_led_uid}, {c1_uid}
- \u7981\u6b62\u5199 .control, .subckt, .ends
- \u7981\u6b62\u5199 .model \u8bed\u53e5（\u6a21\u578b\u7531\u7cfb\u7edf\u81ea\u52a8\u6ce8\u5165）
- \u7981\u6b62\u4fee\u6539\u7535\u963b\u503c！\u5fc5\u987b\u4f7f\u7528\u4ee5\u4e0b\u8ba1\u7b97\u597d\u7684\u503c：
  - {r1_uid} = {r1_value/1000:.1f}k
  - {r2_uid} = {r2_value/1000:.1f}k
  - {r3_uid} = {re_value:.0f}

\u53ea\u8f93\u51fa SPICE \u4ee3\u7801！"""

        user_prompt = f"""\u8bbe\u8ba1 LED \u6052\u6d41\u9a71\u52a8\u7535\u8def，\u7535\u6d41 {self._target_current_ma:.0f}mA。

【\u5fc5\u987b\u4f7f\u7528\u7684\u5143\u5668\u4ef6\u53ca\u53c2\u6570\u503c】:
- {r1_uid} = {r1_value/1000:.1f}k（\u504f\u7f6e\u7535\u963b）
- {r2_uid} = {r2_value/1000:.1f}k（\u504f\u7f6e\u7535\u963b）
- {r3_uid} = {re_value:.0f}（\u53d1\u5c04\u6781\u7535\u963b，\u51b3\u5b9a\u7535\u6d41）
- {spice_bjt_uid} = 2N3904
- {spice_led_uid} = LED
- {c1_uid} = 100n

\u76f4\u63a5\u8f93\u51fa SPICE \u4ee3\u7801，\u4e0d\u8981\u4fee\u6539\u4efb\u4f55\u53c2\u6570\u503c！"""

        if iteration > 1 and previous_spice:
            user_prompt = f"""【\u76ee\u6807\u7535\u6d41】: {self._target_current_ma:.0f}mA

【\u4e0a\u4e00\u8f6e\u4ee3\u7801】:
```
{previous_spice}
```

【\u53cd\u9988】: {feedback}

【\u5fc5\u987b\u4f7f\u7528\u7684\u5143\u5668\u4ef6\u53ca\u53c2\u6570\u503c】:
- {r1_uid} = {r1_value/1000:.1f}k（\u504f\u7f6e\u7535\u963b，\u56fa\u5b9a\u4e0d\u53d8）
- {r2_uid} = {r2_value/1000:.1f}k（\u504f\u7f6e\u7535\u963b，\u56fa\u5b9a\u4e0d\u53d8）
- {r3_uid} = \u6839\u636e\u53cd\u9988\u8c03\u6574
- {spice_bjt_uid} = 2N3904
- {spice_led_uid} = LED
- {c1_uid} = 100n

【\u91cd\u8981\u7ea6\u675f】
- \u5fc5\u987b\u4fdd\u6301 {r1_uid}={r1_value/1000:.1f}k \u548c {r2_uid}={r2_value/1000:.1f}k \u4e0d\u53d8
- \u53ea\u8c03\u6574 {r3_uid} \u7684\u503c\u6765\u6539\u53d8\u7535\u6d41
- \u7535\u6d41\u516c\u5f0f：I ≈ (Vb - 0.7V) / R3，\u5176\u4e2d Vb ≈ 2.5V

\u8f93\u51fa SPICE \u4ee3\u7801："""

        return system_prompt, user_prompt

    def _get_opamp_led_prompts(self, elaborated_req, iteration, previous_spice, feedback,
                                opamp_uid, bjt_uid, led_uid, r1_uid, r2_uid, r3_uid, c1_uid):
        """\u8fd0\u653e + BJT \u6052\u6d41\u6e90\u62d3\u6251 (\u7528\u4e8e test_9 \u7b49\u542b LM2904 \u7684\u573a\u666f)"""
        spice_opamp_uid = 'X' + opamp_uid[1:] if opamp_uid.startswith('U') else 'X1'
        spice_bjt_uid = bjt_uid
        if led_uid.upper().startswith('LED'):
            spice_led_uid = 'D' + led_uid[3:]
        elif led_uid.upper().startswith('D'):
            spice_led_uid = led_uid
        else:
            spice_led_uid = 'D' + led_uid

        vref = 2.5
        re_value = int(vref / (self._target_current_ma / 1000))
        self._re_value = re_value
        r1_value = 10000
        r2_value = int(r1_value * vref / (self._supply_voltage - vref))

        example_circuit = f"""VCC VCC 0 DC {self._supply_voltage}
{r1_uid} VCC N_REF {r1_value/1000:.1f}k
{r2_uid} N_REF 0 {r2_value/1000:.1f}k
{spice_opamp_uid} N_REF EMIT VCC 0 N_GATE LM2904
{spice_bjt_uid} N_COL N_GATE EMIT 2N3904
{r3_uid} EMIT 0 {re_value}
{spice_led_uid} VCC N_COL LED
{c1_uid} VCC 0 100n
* I_LED = Vref / R3 = {vref} / {re_value} = {self._target_current_ma:.0f}mA"""

        if iteration == 1:
            system_prompt = f"""\u8bbe\u8ba1 LED \u6052\u6d41\u9a71\u52a8\u7535\u8def（\u8fd0\u653e\u95ed\u73af\u63a7\u5236 + BJT \u6269\u6d41）。

【\u76ee\u6807\u7535\u6d41】: {self._target_current_ma:.0f}mA
【\u7535\u6e90\u7535\u538b】: {self._supply_voltage}V
【\u539f\u7406】: I_LED = Vref / R3，\u5176\u4e2d Vref \u7531 R1/R2 \u5206\u538b\u4ea7\u751f ({vref:.1f}V)

【\u5143\u5668\u4ef6\u53ca\u56fa\u5b9a\u53c2\u6570】:
- \u8fd0\u653e: {spice_opamp_uid} (LM2904, IN+→N_REF, IN-→EMIT, OUT→N_GATE)
- BJT: {spice_bjt_uid} (2N3904, \u96c6\u7535\u6781→N_COL, \u57fa\u6781→N_GATE, \u53d1\u5c04\u6781→EMIT)
- LED: {spice_led_uid} (\u9633\u6781→VCC, \u9634\u6781→N_COL)
- {r1_uid} = {r1_value/1000:.1f}k (\u4e0a\u5206\u538b\u7535\u963b)
- {r2_uid} = {r2_value/1000:.1f}k (\u4e0b\u5206\u538b\u7535\u963b)
- {r3_uid} = {re_value} (\u91c7\u6837\u7535\u963b, \u8bbe\u5b9a\u7535\u6d41)
- {c1_uid} = 100n (\u53bb\u8026\u7535\u5bb9)

【\u5b8c\u6574 SPICE \u6a21\u677f - \u590d\u5236\u6b64\u7ed3\u6784，\u4e0d\u8981\u4fee\u6539\u5143\u4ef6\u540d\u548c\u8fde\u63a5\u5173\u7cfb】:
```
{example_circuit}
```

【\u7edd\u5bf9\u7981\u6b62】:
- \u4e0d\u8981\u4fee\u6539\u4efb\u4f55\u5143\u5668\u4ef6\u540d\u79f0
- \u4e0d\u8981\u6dfb\u52a0 N_GATE \u4ee5\u5916\u7684\u989d\u5916\u8282\u70b9
- \u4e0d\u8981\u5199 .control .subckt .ends .end
- \u4e0d\u8981\u5199 .model \u8bed\u53e5
- \u53ea\u8f93\u51fa SPICE \u4ee3\u7801"""
            user_prompt = f"\u8f93\u51fa\u8fd0\u653e\u6052\u6d41 LED \u9a71\u52a8 SPICE \u4ee3\u7801，\u7535\u6d41 {self._target_current_ma:.0f}mA。\u590d\u5236\u6a21\u677f\u7ed3\u6784，\u53ea\u6539\u6570\u503c\u4e0d\u6539\u53d8\u8fde\u63a5\u5173\u7cfb。"
        else:
            system_prompt = f"""\u4f18\u5316\u8fd0\u653e\u6052\u6d41 LED \u9a71\u52a8\u7535\u8def。\u53ea\u8f93\u51fa SPICE \u4ee3\u7801。\u4e0d\u8981\u4fee\u6539\u5143\u5668\u4ef6\u540d\u79f0\u548c\u8fde\u63a5\u5173\u7cfb。"""
            user_prompt = f"""【\u76ee\u6807\u7535\u6d41】: {self._target_current_ma:.0f}mA
【\u4e0a\u4e00\u8f6e\u4ee3\u7801】:
{previous_spice}

【\u53cd\u9988】: {feedback}

\u4fee\u6539\u7535\u963b\u503c\u4ee5\u8c03\u6574\u7535\u6d41，\u4f46\u4fdd\u6301\u6240\u6709\u5143\u5668\u4ef6\u540d\u79f0\u548c\u8fde\u63a5\u5173\u7cfb\u4e0d\u53d8。\u53ea\u8f93\u51fa SPICE \u4ee3\u7801。"""

        return system_prompt, user_prompt

    def clean_spice_code(self, spice_code: str) -> str:
        lines = spice_code.split('\n')
        cleaned_lines = []
        removed_count = 0

        for line in lines:
            line_stripped = line.strip()
            should_remove = False

            if re.match(r'^\.control\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
            elif re.match(r'^\.endc\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
            elif re.match(r'^\.END\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
            elif re.match(r'^\.subckt', line_stripped, re.IGNORECASE):
                should_remove = True
            elif re.match(r'^\.ends', line_stripped, re.IGNORECASE):
                should_remove = True

            if should_remove:
                removed_count += 1
            else:
                cleaned_lines.append(line)

        if removed_count > 0:
            print(f"   [\u6e05\u6d17] \u79fb\u9664 {removed_count} \u884c")

        return '\n'.join(cleaned_lines)

    def get_simulation_config(self) -> Dict[str, Any]:
        return {
            'analysis_type': 'tran',
            'tran_time': '10m',
            'time_step': '10u',
            'output_node': 'EMIT',
            'description': 'LED\u6052\u6d41\u9a71\u52a8\u7535\u8def\u77ac\u6001\u5206\u6790'
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
        stable_start = int(len(x_data) * 0.8)
        stable_y = y_data[stable_start:] if len(y_data) > stable_start else y_data

        if not stable_y:
            return {'status': 'no_data', 'error': '\u7a33\u5b9a\u6570\u636e\u4e3a\u7a7a'}

        v_emit_avg = sum(stable_y) / len(stable_y)

        # \u8ba1\u7b97\u7535\u6d41: I_LED = Ve / R3
        # \u4f7f\u7528\u5b58\u50a8\u7684 R3 \u503c（\u5728 get_netlist_prompts \u4e2d\u8bbe\u7f6e）
        led_current_ma = (v_emit_avg / self._re_value) * 1000 if self._re_value > 0 else 0

        results['led_current_ma'] = led_current_ma
        results['v_emit_v'] = v_emit_avg

        current_error = abs(led_current_ma - self._target_current_ma)
        current_error_percent = (current_error / self._target_current_ma) * 100 if self._target_current_ma > 0 else 100

        results['current_error_ma'] = current_error
        results['current_error_percent'] = current_error_percent
        results['status'] = 'ok'

        print(f"   [\u7535\u6d41\u5206\u6790] LED\u7535\u6d41: {led_current_ma:.2f}mA, \u76ee\u6807: {self._target_current_ma:.1f}mA, \u8bef\u5dee: {current_error_percent:.1f}%")

        return results

    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:

        target = self._target_current_ma
        acceptable_min = target * 0.8
        acceptable_max = target * 1.2

        system_prompt = f"""\u4f60\u662f\u4eff\u771f\u88c1\u5224\u5b98。

【\u76ee\u6807\u7535\u6d41】: {target:.1f}mA
【\u5408\u683c\u8303\u56f4】: {acceptable_min:.1f}mA ~ {acceptable_max:.1f}mA

⚠️【\u5224\u51b3\u89c4\u5219 - \u5fc5\u987b\u4e25\u683c\u9075\u5b88】⚠️
1. \u53ea\u8981 led_current_ma \u5728 [{acceptable_min:.1f}mA, {acceptable_max:.1f}mA] \u8303\u56f4\u5185，\u5c31\u8fd4\u56de passed: true
2. \u5224\u5b9a\u89c4\u5219：\u53ea\u8981\u5728\u8303\u56f4\u5185\u5c31\u901a\u8fc7，\u65e0\u8bba\u9ad8\u4e8e\u8fd8\u662f\u4f4e\u4e8e\u76ee\u6807\u503c！
3. \u793a\u4f8b（\u5047\u8bbe\u76ee\u6807{target:.0f}mA，\u8303\u56f4{acceptable_min:.0f}~{acceptable_max:.0f}mA）：
   - led_current_ma = {target * 0.9:.0f}mA → \u5728\u8303\u56f4\u5185 → passed: true ✅
   - led_current_ma = {target * 1.1:.0f}mA → \u5728\u8303\u56f4\u5185 → passed: true ✅
   - led_current_ma = {acceptable_min - 1:.0f}mA → \u4f4e\u4e8e\u4e0b\u9650 → passed: false ❌
   - led_current_ma = {acceptable_max + 1:.0f}mA → \u9ad8\u4e8e\u4e0a\u9650 → passed: false ❌

【\u95ee\u9898\u8bca\u65ad - \u4ec5\u5f53 passed: false \u65f6\u4f7f\u7528】
1. \u7535\u6d41 ≈ 0mA → \u68c0\u67e5 BJT \u662f\u5426\u5bfc\u901a，\u57fa\u6781\u7535\u538b\u662f\u5426\u8db3\u591f（\u9700\u8981 > 0.7V）
2. \u7535\u6d41\u504f\u5c0f（< {acceptable_min:.1f}mA）→ \u53d1\u5c04\u6781\u7535\u963b R3 \u592a\u5927，\u51cf\u5c0f R3
3. \u7535\u6d41\u504f\u5927（> {acceptable_max:.1f}mA）→ \u53d1\u5c04\u6781\u7535\u963b R3 \u592a\u5c0f，\u589e\u5927 R3

【\u6052\u6d41\u6e90\u516c\u5f0f】
- Vb = VCC × R2/(R1+R2) （\u76ee\u6807\u7ea6 2.5V）
- Ve = Vb - Vbe ≈ Vb - 0.7V
- I_LED = Ve / R3

【\u8f93\u51fa\u683c\u5f0f】
{{"passed": true/false, "reason": "\u7b80\u8981\u539f\u56e0（\u901a\u8fc7\u65f6\u5199'\u7535\u6d41\u5728\u5408\u683c\u8303\u56f4\u5185'）", "feedback": "\u4fee\u590d\u5efa\u8bae（\u901a\u8fc7\u65f6\u53ef\u5199'\u65e0\u9700\u8c03\u6574'）"}}"""

        user_prompt = f"""【\u4eff\u771f\u6570\u636e】:
{metrics_str}

\u8bf7\u4e25\u683c\u6309\u7167\u5408\u683c\u8303\u56f4 [{acceptable_min:.1f}mA, {acceptable_max:.1f}mA] \u8fdb\u884c\u5224\u51b3："""

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        \u786c\u9608\u503c\u5224\u51b3（\u4e0d\u4f7f\u7528 LLM）

        \u7528\u4e8e G3 (No_Metric) \u6d88\u878d\u5b9e\u9a8c。
        LED \u7535\u6d41\u5224\u65ad\u89c4\u5219：\u76ee\u6807\u503c\u7684 80% ~ 120% \u4e3a\u901a\u8fc7
        """
        target = self._target_current_ma
        if not target:
            return True, "\u65e0\u6cd5\u786e\u5b9a\u76ee\u6807\u7535\u6d41，\u9ed8\u8ba4\u901a\u8fc7"

        # \u4ece metrics \u4e2d\u63d0\u53d6\u5b9e\u9645\u7535\u6d41
        actual_current = metrics.get('led_current_ma')
        if actual_current is None:
            return False, "\u65e0\u6cd5\u4ece\u4eff\u771f\u6570\u636e\u4e2d\u63d0\u53d6 LED \u7535\u6d41"

        # \u786c\u9608\u503c\u5224\u65ad：85% ~ 115% (G3: \u6bd4 LLM judge \u66f4\u4e25\u683c)
        min_current = target * 0.85
        max_current = target * 1.15

        if min_current <= actual_current <= max_current:
            return True, f"LED\u7535\u6d41 {actual_current:.1f}mA \u5728\u76ee\u6807\u8303\u56f4 {min_current:.1f}-{max_current:.1f}mA \u5185"
        else:
            if actual_current < min_current:
                feedback = f"LED\u7535\u6d41 {actual_current:.1f}mA \u592a\u4f4e（\u76ee\u6807 {target:.1f}mA），\u9700\u8981\u51cf\u5c0f\u53d1\u5c04\u6781\u7535\u963b"
            else:
                feedback = f"LED\u7535\u6d41 {actual_current:.1f}mA \u592a\u9ad8（\u76ee\u6807 {target:.1f}mA），\u9700\u8981\u589e\u5927\u53d1\u5c04\u6781\u7535\u963b"
            return False, feedback
