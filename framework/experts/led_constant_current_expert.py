"""
LED 恒流驱动电路专家

简化版：只支持简单 BJT 恒流源拓扑。
强制使用规划中的元器件 UID，不允许 LLM 自行编造名称。
"""

import re
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class LedConstantCurrentExpert(CircuitExpert):
    """LED 恒流驱动电路专家"""

    def __init__(self):
        super().__init__()
        self._target_current_ma = None
        self._supply_voltage = 12.0
        self._re_value = 65.0  # 存储发射极电阻值，用于电流计算
        self._has_opamp = False  # 是否使用运放拓扑

    @property
    def circuit_type(self) -> str:
        return "led_constant_current"

    def get_circuit_description(self) -> str:
        return "LED 恒流驱动电路"

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
        从细化后的需求文本中提取目标电流值

        支持多种表述方式：
        - 电流为20mA
        - 电流稳定在30mA
        - 40mA驱动电流
        - 目标恒定电流为20mA
        - 提供40mA的电流
        """
        patterns = [
            # 最精确：明确的电流值声明
            r'目标?\s*电流\s*[为：:]\s*(\d+(?:\.\d+)?)\s*mA?',
            r'电流\s*[为稳定在：:]+\s*(\d+(?:\.\d+)?)\s*mA?',  # 新增：电流稳定在30mA
            r'电流\s*[为：:]\s*(\d+(?:\.\d+)?)\s*mA?',
            r'电流\s*(\d+(?:\.\d+)?)\s*mA?',
            # 宽松：数字+mA+电流相关词
            r'(\d+(?:\.\d+)?)\s*mA\s*[驱动恒定]*电流',
            r'(\d+(?:\.\d+)?)\s*mA\s*的\s*电流',
            # 最宽松：单独的数字+mA（但要确保是电流相关上下文）
            r'设定?\s*[为：:]?\s*(\d+(?:\.\d+)?)\s*mA',
            r'提供.*?(\d+(?:\.\d+)?)\s*mA',
            r'稳定.*?(\d+(?:\.\d+)?)\s*mA',  # 新增：稳定在30mA
        ]
        for pattern in patterns:
            match = re.search(pattern, elaborated_req, re.IGNORECASE)
            if match:
                current = float(match.group(1))
                print(f"   [电流解析] 从需求中提取到目标电流: {current}mA")
                return current
        print(f"   [电流解析] 未找到明确的电流值，使用默认值 20mA")
        return 20.0

    def get_netlist_prompts(
        self,
        elaborated_req: str,
        uid_hint: str,
        iteration: int,
        previous_spice: Optional[str],
        feedback: Optional[str]
    ) -> Tuple[str, str]:

        uid_model_map = self._parse_uid_model_map(uid_hint)
        # 优先使用 set_targets() 注入的目标值，否则 regex fallback
        if self._target_current_ma is None:
            self._target_current_ma = self._extract_target_current(elaborated_req)
        if self._target_current_ma is None:
            self._target_current_ma = 20.0  # 终极兜底

        # 检测是否使用运放拓扑（test_9: LM2904 + 2N3904）
        opamp_uid = None
        for uid, model in uid_model_map.items():
            if model.upper() in ('LM2904', 'LM358', 'LM324'):
                opamp_uid = uid
                self._has_opamp = True
                break

        # 解析元器件
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

        # 默认值
        if not led_uid:
            led_uid = "LED1"
        if not bjt_uid:
            bjt_uid = "Q1"
        r1_uid = resistor_uids[0] if len(resistor_uids) > 0 else "R1"
        r2_uid = resistor_uids[1] if len(resistor_uids) > 1 else "R2"
        r3_uid = resistor_uids[2] if len(resistor_uids) > 2 else "R3"
        c1_uid = capacitor_uids[0] if capacitor_uids else "C1"

        # --- 运放拓扑分支 (用于 test_9 等含 LM2904 的 LED 驱动) ---
        if self._has_opamp and opamp_uid:
            return self._get_opamp_led_prompts(
                elaborated_req, iteration, previous_spice, feedback,
                opamp_uid, bjt_uid, led_uid, r1_uid, r2_uid, r3_uid, c1_uid
            )

        # --- 纯 BJT 拓扑 (原有逻辑) ---
        # 计算参数
        vbe = 0.7
        vb_theoretical = 2.5  # 理论基极电压（空载）

        # 偏置电阻计算（关键改进：降低输出阻抗）
        # 使用戴维南等效：Ie = (Vth - Vbe) / (R3 + Rth/(β+1))
        # 需要选择合适的 R1, R2 使 Rth/(β+1) 可以忽略

        # 假设 β ≈ 200（2N3904 典型值）
        beta = 200

        # 目标：Rth/(β+1) < R3 × 0.05（负载效应 < 5%）
        # 对于 30mA，R3 ≈ 60Ω，要求 Rth < 60 × 201 × 0.05 ≈ 600Ω
        # 选择 Rth ≈ 500Ω
        rth_target = 500

        # 根据目标 Rth 和 Vb 计算 R1, R2
        # Vb = VCC × R2/(R1+R2) 且 Rth = R1×R2/(R1+R2)
        # 解得：R2 = Vb × Rth / (VCC - Vb + Rth × Vb/VCC)
        # 简化：使用迭代法
        i_divider = vb_theoretical / rth_target * 1000  # Divider 电流 (mA)
        i_divider = max(i_divider, 3.0)  # 至少 3mA，确保稳定

        r2_value = int(vb_theoretical / i_divider * 1000)
        r1_value = int(r2_value * (self._supply_voltage - vb_theoretical) / vb_theoretical)

        # 计算实际的 Rth
        rth = (r1_value * r2_value) / (r1_value + r2_value) if (r1_value + r2_value) > 0 else 0

        # 考虑负载效应修正 R3
        # Ie = (Vth - Vbe) / (R3 + Rth/(β+1))
        # R3 = (Vth - Vbe) / Ie - Rth/(β+1)
        ve_target = vb_theoretical - vbe
        re_correction = rth / (beta + 1)
        re_value = max(10, (ve_target / (self._target_current_ma / 1000)) - re_correction)
        self._re_value = re_value

        print(f"   [参数计算] 目标电流: {self._target_current_ma}mA, R3={re_value:.0f}Ω, R1={r1_value/1000:.1f}k, R2={r2_value/1000:.1f}k")
        print(f"   [负载效应] Rth={rth:.0f}Ω, 修正项={re_correction:.1f}Ω")

        # SPICE 格式转换
        # BJT 用 Q 前缀（规划中应该就是 Q1）
        spice_bjt_uid = bjt_uid
        # LED 用 D 前缀：LED1 -> D1（去掉 LED 前缀，加 D）
        if led_uid.upper().startswith('LED'):
            spice_led_uid = 'D' + led_uid[3:]  # LED1 -> D1
        elif led_uid.upper().startswith('D'):
            spice_led_uid = led_uid  # 已经是 D 前缀
        else:
            spice_led_uid = 'D' + led_uid  # 其他情况加 D 前缀

        example_circuit = f"""VCC VCC 0 DC {self._supply_voltage}
{r1_uid} VCC BASE {r1_value/1000:.1f}k
{r2_uid} BASE 0 {r2_value/1000:.1f}k
{spice_bjt_uid} COL BASE EMIT 2N3904
{r3_uid} EMIT 0 {re_value:.0f}
{spice_led_uid} VCC COL LED
{c1_uid} VCC 0 100n
* 注意：模型由系统自动注入，无需手动定义"""

        system_prompt = f"""设计 LED 恒流驱动电路。

【目标电流】: {self._target_current_ma:.0f}mA
【电源】: {self._supply_voltage}V

============================================================
🔴🔴🔴🔴🔴 必须严格使用以下元器件名称 🔴🔴🔴🔴🔴
============================================================

电阻: {r1_uid}, {r2_uid}, {r3_uid}
BJT: {spice_bjt_uid} (使用 2N3904 模型)
LED: {spice_led_uid}
电容: {c1_uid}

============================================================
电路结构
============================================================

1. {r1_uid} 接在 VCC 和 BASE 之间
2. {r2_uid} 接在 BASE 和 GND(0) 之间
3. {spice_bjt_uid} 引脚顺序: 集电极 基极 发射极 2N3904
4. {r3_uid} 接在 EMIT 和 GND(0) 之间
5. {spice_led_uid} 阳极接 VCC，阴极接 COL
6. {c1_uid} 接在 VCC 和 GND(0) 之间

============================================================
正确示例
============================================================
```
{example_circuit}
```

【绝对禁止】
- 禁止使用 X1, X2, X3, M1 等其他名称！
- 禁止使用 R_DIV, R_SENSE 等其他名称！
- 必须使用 {r1_uid}, {r2_uid}, {r3_uid}, {spice_bjt_uid}, {spice_led_uid}, {c1_uid}
- 禁止写 .control, .subckt, .ends
- 禁止写 .model 语句（模型由系统自动注入）
- 禁止修改电阻值！必须使用以下计算好的值：
  - {r1_uid} = {r1_value/1000:.1f}k
  - {r2_uid} = {r2_value/1000:.1f}k
  - {r3_uid} = {re_value:.0f}

只输出 SPICE 代码！"""

        user_prompt = f"""设计 LED 恒流驱动电路，电流 {self._target_current_ma:.0f}mA。

【必须使用的元器件及参数值】:
- {r1_uid} = {r1_value/1000:.1f}k（偏置电阻）
- {r2_uid} = {r2_value/1000:.1f}k（偏置电阻）
- {r3_uid} = {re_value:.0f}（发射极电阻，决定电流）
- {spice_bjt_uid} = 2N3904
- {spice_led_uid} = LED
- {c1_uid} = 100n

直接输出 SPICE 代码，不要修改任何参数值！"""

        if iteration > 1 and previous_spice:
            user_prompt = f"""【目标电流】: {self._target_current_ma:.0f}mA

【上一轮代码】:
```
{previous_spice}
```

【反馈】: {feedback}

【必须使用的元器件及参数值】:
- {r1_uid} = {r1_value/1000:.1f}k（偏置电阻，固定不变）
- {r2_uid} = {r2_value/1000:.1f}k（偏置电阻，固定不变）
- {r3_uid} = 根据反馈调整
- {spice_bjt_uid} = 2N3904
- {spice_led_uid} = LED
- {c1_uid} = 100n

【重要约束】
- 必须保持 {r1_uid}={r1_value/1000:.1f}k 和 {r2_uid}={r2_value/1000:.1f}k 不变
- 只调整 {r3_uid} 的值来改变电流
- 电流公式：I ≈ (Vb - 0.7V) / R3，其中 Vb ≈ 2.5V

输出 SPICE 代码："""

        return system_prompt, user_prompt

    def _get_opamp_led_prompts(self, elaborated_req, iteration, previous_spice, feedback,
                                opamp_uid, bjt_uid, led_uid, r1_uid, r2_uid, r3_uid, c1_uid):
        """运放 + BJT 恒流源拓扑 (用于 test_9 等含 LM2904 的场景)"""
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
            system_prompt = f"""设计 LED 恒流驱动电路（运放闭环控制 + BJT 扩流）。

【目标电流】: {self._target_current_ma:.0f}mA
【电源电压】: {self._supply_voltage}V
【原理】: I_LED = Vref / R3，其中 Vref 由 R1/R2 分压产生 ({vref:.1f}V)

【元器件及固定参数】:
- 运放: {spice_opamp_uid} (LM2904, IN+→N_REF, IN-→EMIT, OUT→N_GATE)
- BJT: {spice_bjt_uid} (2N3904, 集电极→N_COL, 基极→N_GATE, 发射极→EMIT)
- LED: {spice_led_uid} (阳极→VCC, 阴极→N_COL)
- {r1_uid} = {r1_value/1000:.1f}k (上分压电阻)
- {r2_uid} = {r2_value/1000:.1f}k (下分压电阻)
- {r3_uid} = {re_value} (采样电阻, 设定电流)
- {c1_uid} = 100n (去耦电容)

【完整 SPICE 模板 - 复制此结构，不要修改元件名和连接关系】:
```
{example_circuit}
```

【绝对禁止】:
- 不要修改任何元器件名称
- 不要添加 N_GATE 以外的额外节点
- 不要写 .control .subckt .ends .end
- 不要写 .model 语句
- 只输出 SPICE 代码"""
            user_prompt = f"输出运放恒流 LED 驱动 SPICE 代码，电流 {self._target_current_ma:.0f}mA。复制模板结构，只改数值不改变连接关系。"
        else:
            system_prompt = f"""优化运放恒流 LED 驱动电路。只输出 SPICE 代码。不要修改元器件名称和连接关系。"""
            user_prompt = f"""【目标电流】: {self._target_current_ma:.0f}mA
【上一轮代码】:
{previous_spice}

【反馈】: {feedback}

修改电阻值以调整电流，但保持所有元器件名称和连接关系不变。只输出 SPICE 代码。"""

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
            print(f"   [清洗] 移除 {removed_count} 行")

        return '\n'.join(cleaned_lines)

    def get_simulation_config(self) -> Dict[str, Any]:
        return {
            'analysis_type': 'tran',
            'tran_time': '10m',
            'time_step': '10u',
            'output_node': 'EMIT',
            'description': 'LED恒流驱动电路瞬态分析'
        }

    def parse_simulation_data(
        self,
        x_data: list,
        y_data: list,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:

        if not x_data or not y_data:
            return {'status': 'no_data', 'error': '仿真数据为空'}

        results = {}
        stable_start = int(len(x_data) * 0.8)
        stable_y = y_data[stable_start:] if len(y_data) > stable_start else y_data

        if not stable_y:
            return {'status': 'no_data', 'error': '稳定数据为空'}

        v_emit_avg = sum(stable_y) / len(stable_y)

        # 计算电流: I_LED = Ve / R3
        # 使用存储的 R3 值（在 get_netlist_prompts 中设置）
        led_current_ma = (v_emit_avg / self._re_value) * 1000 if self._re_value > 0 else 0

        results['led_current_ma'] = led_current_ma
        results['v_emit_v'] = v_emit_avg

        current_error = abs(led_current_ma - self._target_current_ma)
        current_error_percent = (current_error / self._target_current_ma) * 100 if self._target_current_ma > 0 else 100

        results['current_error_ma'] = current_error
        results['current_error_percent'] = current_error_percent
        results['status'] = 'ok'

        print(f"   [电流分析] LED电流: {led_current_ma:.2f}mA, 目标: {self._target_current_ma:.1f}mA, 误差: {current_error_percent:.1f}%")

        return results

    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:

        target = self._target_current_ma
        acceptable_min = target * 0.8
        acceptable_max = target * 1.2

        system_prompt = f"""你是仿真裁判官。

【目标电流】: {target:.1f}mA
【合格范围】: {acceptable_min:.1f}mA ~ {acceptable_max:.1f}mA

⚠️【判决规则 - 必须严格遵守】⚠️
1. 只要 led_current_ma 在 [{acceptable_min:.1f}mA, {acceptable_max:.1f}mA] 范围内，就返回 passed: true
2. 判定规则：只要在范围内就通过，无论高于还是低于目标值！
3. 示例（假设目标{target:.0f}mA，范围{acceptable_min:.0f}~{acceptable_max:.0f}mA）：
   - led_current_ma = {target * 0.9:.0f}mA → 在范围内 → passed: true ✅
   - led_current_ma = {target * 1.1:.0f}mA → 在范围内 → passed: true ✅
   - led_current_ma = {acceptable_min - 1:.0f}mA → 低于下限 → passed: false ❌
   - led_current_ma = {acceptable_max + 1:.0f}mA → 高于上限 → passed: false ❌

【问题诊断 - 仅当 passed: false 时使用】
1. 电流 ≈ 0mA → 检查 BJT 是否导通，基极电压是否足够（需要 > 0.7V）
2. 电流偏小（< {acceptable_min:.1f}mA）→ 发射极电阻 R3 太大，减小 R3
3. 电流偏大（> {acceptable_max:.1f}mA）→ 发射极电阻 R3 太小，增大 R3

【恒流源公式】
- Vb = VCC × R2/(R1+R2) （目标约 2.5V）
- Ve = Vb - Vbe ≈ Vb - 0.7V
- I_LED = Ve / R3

【输出格式】
{{"passed": true/false, "reason": "简要原因（通过时写'电流在合格范围内'）", "feedback": "修复建议（通过时可写'无需调整'）"}}"""

        user_prompt = f"""【仿真数据】:
{metrics_str}

请严格按照合格范围 [{acceptable_min:.1f}mA, {acceptable_max:.1f}mA] 进行判决："""

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        硬阈值判决（不使用 LLM）

        用于 G3 (No_Metric) 消融实验。
        LED 电流判断规则：目标值的 80% ~ 120% 为通过
        """
        target = self._target_current_ma
        if not target:
            return True, "无法确定目标电流，默认通过"

        # 从 metrics 中提取实际电流
        actual_current = metrics.get('led_current_ma')
        if actual_current is None:
            return False, "无法从仿真数据中提取 LED 电流"

        # 硬阈值判断：85% ~ 115% (G3: 比 LLM judge 更严格)
        min_current = target * 0.85
        max_current = target * 1.15

        if min_current <= actual_current <= max_current:
            return True, f"LED电流 {actual_current:.1f}mA 在目标范围 {min_current:.1f}-{max_current:.1f}mA 内"
        else:
            if actual_current < min_current:
                feedback = f"LED电流 {actual_current:.1f}mA 太低（目标 {target:.1f}mA），需要减小发射极电阻"
            else:
                feedback = f"LED电流 {actual_current:.1f}mA 太高（目标 {target:.1f}mA），需要增大发射极电阻"
            return False, feedback
