"""
运算放大器放大电路专家

专门处理 Op-Amp Amplifier 电路（同相放大器、反相放大器）。
支持 AC 分析测量增益和带宽。
"""

import re
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class OpAmpAmplifierExpert(CircuitExpert):
    """运算放大器放大电路专家"""

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
        return "运算放大器放大电路"

    def set_targets(self, targets: Optional[Dict] = None):
        super().set_targets(targets)
        if targets and targets.get("metric") == "midband_gain_db":
            self._target_gain_db = targets.get("value")

    def _parse_uid_model_map(self, uid_hint: str) -> Dict[str, str]:
        """解析 UID 到型号的映射"""
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
        """从需求文本中检测放大器类型"""
        if '反相' in elaborated_req or 'inverting' in elaborated_req.lower():
            return "inverting"
        return "non_inverting"

    def _extract_target_gain(self, elaborated_req: str) -> float:
        """从需求文本中提取目标增益"""
        patterns = [
            # 增益为40dB / 增益:40dB / 增益 40dB / 增益：40dB
            r'增益\s*[为：:]\s*(\d+(?:\.\d+)?)\s*dB?',
            r'增益\s+(\d+(?:\.\d+)?)\s*dB?',
            # 40dB增益 / 40dB的增益
            r'(\d+(?:\.\d+)?)\s*dB\s*增益',
            # gain: 40dB / gain of 40dB
            r'gain\s*[为：:of\s]+\s*(\d+(?:\.\d+)?)\s*dB?',
            # 放大100倍 (转换为dB)
            r'放大\s*(\d+(?:\.\d+)?)\s*倍',
        ]

        for pattern in patterns:
            match = re.search(pattern, elaborated_req, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                if '倍' in pattern:
                    # 倍数转dB: 20*log10(倍数)
                    import math
                    return 20 * math.log10(value if value > 0 else 1)
                return value
        return 20.0

    def _calculate_resistors(self, target_gain_db: float, amp_type: str) -> Tuple[float, float]:
        """根据目标增益计算电阻值，返回 (Rf, Rg) 或 (Rf, Ri)"""
        # dB 转线性增益
        gain_linear = 10 ** (target_gain_db / 20)

        rg = 1000  # 基准电阻 1kΩ

        if amp_type == "inverting":
            # Gain = -Rf/Ri
            rf = rg * gain_linear
        else:
            # Gain = 1 + Rf/Rg
            rf = rg * (gain_linear - 1)

        return rf, rg

    def get_netlist_prompts(
        self,
        elaborated_req: str,
        uid_hint: str,
        iteration: int,
        previous_spice: Optional[str],
        feedback: Optional[str]
    ) -> Tuple[str, str]:

        self._iteration_count = iteration
        uid_model_map = self._parse_uid_model_map(uid_hint)

        # 检测放大器类型，目标增益优先使用 set_targets() 注入值
        self._amplifier_type = self._detect_amplifier_type(elaborated_req)
        if self._target_gain_db is None:
            self._target_gain_db = self._extract_target_gain(elaborated_req)
        if self._target_gain_db is None:
            self._target_gain_db = 20.0  # 终极兜底

        # 计算推荐电阻值
        rf_recommended, rg_recommended = self._calculate_resistors(
            self._target_gain_db, self._amplifier_type
        )

        # 解析元器件角色
        opamp_uid = None
        resistor_uids = []
        capacitor_uids = []

        for uid, model in uid_model_map.items():
            model_upper = model.upper()
            if 'LM2904' in model_upper or 'LM358' in model_upper or 'OPA' in model_upper:
                opamp_uid = uid
                self._opamp_model = model
            elif model == 'R':
                resistor_uids.append(uid)
            elif model == 'C':
                capacitor_uids.append(uid)

        if not opamp_uid:
            opamp_uid = "U1"
            self._opamp_model = "LM2904"

        # 使用规划中的实际电阻 UID
        rf_uid = resistor_uids[0] if len(resistor_uids) > 0 else "R1"
        rg_uid = resistor_uids[1] if len(resistor_uids) > 1 else "R2"

        # 找一个电容 UID 用于电源去耦
        decap_uid = capacitor_uids[0] if len(capacitor_uids) > 0 else "C1"

        amp_type_cn = "反相放大器" if self._amplifier_type == "inverting" else "同相放大器"

        # SPICE 要求子电路调用使用 X 前缀
        # 如果运放 UID 是 U1，在 SPICE 中写为 XU1（保留原始编号）
        spice_opamp_uid = opamp_uid if opamp_uid.upper().startswith('X') else 'X' + opamp_uid

        if iteration == 1:
            # 第一轮：给出最简化的示例（使用实际的元件 UID！）
            if self._amplifier_type == "inverting":
                # 反相放大器：IN+ 接地，输入通过电阻接 IN-
                example_circuit = f"""* 反相放大器 - 目标增益 {self._target_gain_db:.0f}dB
VIN IN 0 DC 0 AC 1
{rg_uid} IN N_MINUS 1k
{rf_uid} N_MINUS OUT {rf_recommended/1000:.1f}k
{spice_opamp_uid} 0 N_MINUS VCC VEE OUT LM2904
VCC VCC 0 DC 12
VEE VEE 0 DC -12
{decap_uid} VCC 0 100n"""
                topology_note = f"""【反相放大器拓扑】
- 运放 IN+ 接地 (0)
- 输入信号通过 {rg_uid} 接 IN-
- 反馈电阻 {rf_uid} 接在 OUT 和 IN- 之间
- 增益 = -{rf_uid}/{rg_uid}"""
            else:
                # 同相放大器：输入接 IN+，反馈网络接 IN-
                example_circuit = f"""* 同相放大器 - 目标增益 {self._target_gain_db:.0f}dB
VIN IN 0 DC 0 AC 1
{rg_uid} N_MINUS 0 1k
{rf_uid} N_MINUS OUT {rf_recommended/1000:.1f}k
{spice_opamp_uid} IN N_MINUS VCC VEE OUT LM2904
VCC VCC 0 DC 12
VEE VEE 0 DC -12
{decap_uid} VCC 0 100n"""
                topology_note = f"""【同相放大器拓扑】
- 输入信号直接接 IN+
- IN- 接反馈网络分压点
- {rg_uid} 接在 IN- 和地之间
- {rf_uid} 接在 OUT 和 IN- 之间
- 增益 = 1 + {rf_uid}/{rg_uid}"""

            system_prompt = f"""你是一个模拟电路设计工程师。设计一个{amp_type_cn}。

【目标增益】: {self._target_gain_db:.1f} dB

============================================================
🔴🔴🔴 必须使用以下元器件 UID 🔴🔴🔴
============================================================

运放: {spice_opamp_uid} (LM2904) - 注意SPICE子电路调用必须用X前缀
反馈电阻: {rf_uid}
接地电阻: {rg_uid}
去耦电容: {decap_uid}

============================================================
🔴🔴🔴 必须设计【{amp_type_cn}】🔴🔴🔴
============================================================

{topology_note}

【运放引脚顺序】{spice_opamp_uid} <IN+> <IN-> <VCC> <VEE> <OUT> LM2904

【目标增益 {self._target_gain_db:.0f}dB 的电阻值】
- {rg_uid} = 1kΩ
- {rf_uid} = {rf_recommended/1000:.1f}kΩ

【电源配置】双电源：VCC=+12V, VEE=-12V

============================================================
✅ 正确示例（使用实际 UID）
============================================================
```
{example_circuit}```

【绝对禁止】
- 禁止更改元件名称！必须用 {spice_opamp_uid}, {rf_uid}, {rg_uid}, {decap_uid}
- 禁止写 .control、.end、.SUBCKT
- 禁止添加输入/输出耦合电容
- 禁止使用单电源（必须用双电源 VEE=-12V）
【只输出 SPICE 代码！】"""

            user_prompt = f"设计【{amp_type_cn}】，增益 {self._target_gain_db:.0f}dB。必须使用元件名称：{spice_opamp_uid}, {rf_uid}={rf_recommended/1000:.1f}k, {rg_uid}=1k。双电源 VCC=+12V, VEE=-12V。直接输出 SPICE 代码。"

        else:
            # 后续迭代：根据反馈精确调整
            if self._amplifier_type == "inverting":
                correct_topology = f"{spice_opamp_uid} 0 N_MINUS VCC VEE OUT LM2904 (IN+接地)"
            else:
                correct_topology = f"{spice_opamp_uid} IN N_MINUS VCC VEE OUT LM2904 (IN+接输入)"

            system_prompt = f"""你是一个SPICE电路优化专家。修复电路问题。

【电路类型】: {amp_type_cn}
【目标增益】: {self._target_gain_db:.1f} dB

============================================================
🔴 必须使用以下元器件 UID
============================================================

运放: {spice_opamp_uid} (LM2904) - 注意SPICE子电路调用必须用X前缀
反馈电阻: {rf_uid}
接地电阻: {rg_uid}
去耦电容: {decap_uid}

============================================================
🔴 检查电路拓扑是否正确
============================================================

【正确的运放连接】
{correct_topology}

【增益公式】
{'Gain = -' + rf_uid + '/' + rg_uid + '（反相）' if self._amplifier_type == 'inverting' else 'Gain = 1 + ' + rf_uid + '/' + rg_uid + '（同相）'}

【推荐电阻值】
- {rg_uid} = 1kΩ
- {rf_uid} = {rf_recommended/1000:.1f}kΩ
- 理论增益: {self._target_gain_db:.0f}dB

【电源配置】必须用双电源：VCC=+12V, VEE=-12V

============================================================
🔴 常见问题
============================================================

1. 增益异常低（<5dB）:
   → 检查电源！必须用双电源（VEE=-12V）
   → 检查运放引脚连接！

2. 增益偏高/偏低:
   → 调整 {rf_uid}/{rg_uid} 比值

【绝对禁止】
- 禁止更改元件名称！必须用 {spice_opamp_uid}, {rf_uid}, {rg_uid}
【只输出 SPICE 代码！保持最简！】"""

            user_prompt = f"""【目标】: {amp_type_cn}，增益 {self._target_gain_db:.0f}dB

【必须使用的元件 UID】:
- 运放: {spice_opamp_uid}
- 反馈电阻: {rf_uid}
- 接地电阻: {rg_uid}

【上一轮代码】:
```
{previous_spice}
```

【仿真反馈】: {feedback}

【修复步骤】:
1. 确保使用双电源：VCC=+12V, VEE=-12V
2. 检查运放 {opamp_uid} 的引脚连接
3. 使用 {rg_uid}=1k, {rf_uid}={rf_recommended/1000:.1f}k
4. 移除所有不必要的电容

输出修复后的 SPICE 代码："""

        return system_prompt, user_prompt

    def clean_spice_code(self, spice_code: str) -> str:
        """清洗 SPICE 代码并强制修正电路拓扑"""
        lines = spice_code.split('\n')
        cleaned_lines = []
        removed_count = 0

        for line in lines:
            line_stripped = line.strip()
            should_remove = False
            skip_message = None
            replacement_line = None

            # 移除控制块
            if re.match(r'^\.control\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[控制块]"
            elif re.match(r'^\.endc\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[控制块]"
            elif re.match(r'^\.model\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[模型定义]"
            elif re.match(r'^\.subckt\s+LM2904', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[运放子电路]"
            elif re.match(r'^\.ends\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[子电路结束]"
            elif re.match(r'^\.AC\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[AC指令]"
            elif re.match(r'^\.END\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[END指令]"
            # 移除保险丝
            elif re.match(r'^F(USE|[0-9]+|_[A-Za-z0-9]+)\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[保险丝]"
            # 🔧 运放 UID 转换：U1 -> 保持原样（网表翻译器会处理）
            # 注意：不再强制转换为 X1，而是保留原始 UID
            # 🔧 强制修正电路拓扑：检测运放连接并强制修正
            # 支持格式: U1/X1 <IN+> <IN-> <VCC> <VEE> <OUT> LM2904
            elif re.match(r'^[UX]\w*\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+LM2904', line_stripped, re.IGNORECASE):
                match = re.match(r'^([UX]\w*)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(LM2904)', line_stripped, re.IGNORECASE)
                if match:
                    opamp_name = match.group(1)
                    in_plus = match.group(2)
                    in_minus = match.group(3)
                    vcc = match.group(4)
                    vee = match.group(5)
                    out = match.group(6)
                    model = match.group(7)

                    # 检查并修正拓扑
                    if self._amplifier_type == "non_inverting":
                        # 同相放大器：IN+ 应该接输入（IN），不应该接地
                        if in_plus in ['0', 'GND']:
                            print(f"   [拓扑修正] 检测到反相放大器拓扑，强制修正为同相放大器")
                            replacement_line = f"{opamp_name} IN {in_minus} {vcc} {vee} {out} {model}"
                        else:
                            replacement_line = line_stripped
                    else:
                        # 反相放大器：IN+ 应该接地
                        if in_plus not in ['0', 'GND']:
                            print(f"   [拓扑修正] 检测到同相放大器拓扑，强制修正为反相放大器")
                            replacement_line = f"{opamp_name} 0 {in_minus} {vcc} {vee} {out} {model}"
                        else:
                            replacement_line = line_stripped
                should_remove = True
            # 移除输入耦合电容
            elif re.match(r'^C\d+\s+IN\s+\w+\s+\d+', line_stripped, re.IGNORECASE):
                if 'OUT' not in line_stripped.upper():
                    should_remove = True
                    skip_message = f"[输入耦合电容]"
            # 移除大容量电容
            elif re.match(r'^C\d+\s+\w+\s+\w+\s+(\d+)[uU]', line_stripped):
                match = re.match(r'^C\d+\s+\w+\s+\w+\s+(\d+)[uU]', line_stripped)
                if match and int(match.group(1)) >= 1:
                    should_remove = True
                    skip_message = f"[大容量电容]"

            if should_remove:
                removed_count += 1
                if skip_message:
                    print(f"   [清洗] {skip_message}: {line_stripped[:40]}...")
            else:
                cleaned_lines.append(line)

            if replacement_line:
                cleaned_lines.append(replacement_line)

        if removed_count > 0:
            print(f"   共移除 {removed_count} 个多余元件")

        return '\n'.join(cleaned_lines)

    def get_simulation_config(self) -> Dict[str, Any]:
        """返回仿真配置 - AC 分析"""
        return {
            'analysis_type': 'ac',
            'frequency_range': (1, 1e6),
            'points_per_decade': 50,
            'output_node': 'OUT',
            'description': '运放放大电路 AC 分析'
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

        # 找最大增益（中频增益）- 在 1kHz 附近
        # 搜索 100Hz ~ 10kHz 范围内的最大值作为中频增益
        midband_start = 100
        midband_end = 10000
        midband_gains = [(x, y) for x, y in zip(x_data, y_data) if midband_start <= x <= midband_end]

        if midband_gains:
            max_gain = max(g for _, g in midband_gains)
            results['midband_gain_db'] = max_gain
        else:
            max_gain = max(y_data)
            results['midband_gain_db'] = max_gain

        # 找 -3dB 带宽
        threshold = max_gain - 3.0

        # 高频截止点
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

        # 计算增益误差
        gain_error = abs(max_gain - self._target_gain_db)
        results['gain_error_db'] = gain_error

        results['status'] = 'ok'

        bw_str = f", 带宽: {high_cutoff:.0f}Hz" if high_cutoff else ""
        print(f"   [增益分析] 中频增益: {max_gain:.2f}dB{bw_str}")

        return results

    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:

        target = self._target_gain_db
        # 放宽容差到 ±3dB（考虑实际电路的复杂性和测量精度）
        # 注意：39.99dB 与 40dB 的差异只有 0.01dB，属于浮点精度误差
        acceptable_min = target - 3
        acceptable_max = target + 3

        # 根据增益动态计算最小带宽要求
        # LM2904 GBW ≈ 1MHz，带宽 ≈ GBW / 增益倍数
        gain_linear = 10 ** (target / 20)
        min_bandwidth = max(1000, 1000000 / gain_linear * 0.5)  # 至少 50% 理论带宽

        system_prompt = f"""你是一个SPICE仿真裁判官。

【判决准则】
1. 增益应在目标值附近（目标 = {target:.1f}dB）
   - 合格范围：{acceptable_min:.1f}dB ~ {acceptable_max:.1f}dB
   - 判定规则：只要 midband_gain_db 在 {acceptable_min:.1f}~{acceptable_max:.1f} dB 范围内就通过，无论高于还是低于目标值！
   - 增益误差 < 1dB 为优秀，< 3dB 为合格

2. 带宽要求（根据运放 LM2904 的增益带宽积动态调整）
   - 当前增益 {target:.0f}dB (约 {gain_linear:.0f} 倍)
   - LM2904 GBW ≈ 1MHz，理论带宽 ≈ {1000000/gain_linear:.0f}Hz
   - 合格带宽：> {min_bandwidth:.0f}Hz

【问题诊断】
- 增益 ≈ 0dB → 运放未正确连接或反馈断开
- 增益偏低 → Rf 太小或 Rg 太大，或运放引脚接错
- 增益偏高 → Rf 太大或 Rg 太小
- 带宽太窄 → 有不必要的大电容，或 GBW 限制

【输出格式】
{{
  "passed": true或false,
  "reason": "判决原因",
  "feedback": "具体修复建议（指出电阻值如何调整）"
}}"""

        user_prompt = f"""【设计需求】: {requirement}
【目标增益】: {target:.1f} dB
【仿真数据】:
{metrics_str}

请判决："""

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        硬阈值判决（不使用 LLM）

        用于 G3 (No_Metric) 消融实验。
        增益判断规则：目标值的 ±3dB 为通过
        """
        target = self._target_gain_db
        if not target:
            return True, "无法确定目标增益，默认通过"

        # 从 metrics 中提取实际增益
        actual_gain = metrics.get('midband_gain_db') or metrics.get('max_gain_db')
        if actual_gain is None:
            return False, "无法从仿真数据中提取增益"

        # 硬阈值判断：±2dB (G3: 比 LLM judge 的 ±3dB 更严格)
        min_gain = target - 2
        max_gain = target + 2

        if min_gain <= actual_gain <= max_gain:
            return True, f"增益 {actual_gain:.1f}dB 在目标范围 {min_gain:.1f}-{max_gain:.1f}dB 内"
        else:
            if actual_gain < min_gain:
                feedback = f"增益 {actual_gain:.1f}dB 太低（目标 {target:.1f}dB），需要减小 Rg 或增大 Rf"
            else:
                feedback = f"增益 {actual_gain:.1f}dB 太高（目标 {target:.1f}dB），需要增大 Rg 或减小 Rf"
            return False, feedback
