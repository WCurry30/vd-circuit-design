"""
稳压二极管并联稳压电路专家

专门处理 Zener Diode Shunt Regulator 电路。
涉及时域（Tran 瞬态分析），验证输出电压稳定性和纹波抑制能力。
"""

import re
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class ZenerRegulatorExpert(CircuitExpert):
    """稳压二极管并联稳压电路专家"""

    def __init__(self):
        super().__init__()
        self._zener_model = "1N4733A"
        self._zener_voltage = 5.1

    def set_targets(self, targets: Optional[Dict] = None):
        super().set_targets(targets)
        if targets and targets.get("metric") == "v_out_avg_v":
            self._zener_voltage = targets.get("value")  # 覆盖模型查找值

    @property
    def circuit_type(self) -> str:
        return "zener_regulator"

    def get_circuit_description(self) -> str:
        return "稳压二极管并联稳压电路"

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

        uid_model_map = self._parse_uid_model_map(uid_hint)

        # 解析元器件角色映射
        zener_uid = None
        zener_model = "1N4733A"
        resistor_uid = None
        capacitor_uids = []

        for uid, model in uid_model_map.items():
            model_upper = model.upper()
            if '1N47' in model_upper or 'ZENER' in model_upper:
                zener_uid = uid
                zener_model = model
            elif model == 'R':
                resistor_uid = uid
            elif model == 'C':
                capacitor_uids.append(uid)

        # 提取稳压值
        vz = self._extract_zener_voltage(zener_model)

        # 保存到实例变量，供判决时使用
        self._zener_model = zener_model
        self._zener_voltage = vz

        # 构建示例代码，使用实际的 UID
        zener_line = f"{zener_uid} 0 OUT {zener_model}" if zener_uid else "D1 0 OUT 1N4733A"
        resistor_line = f"{resistor_uid} IN1 OUT 330" if resistor_uid else "R1 IN1 OUT 330"
        cap_lines = ""
        for i, cap_uid in enumerate(capacitor_uids[:2]):
            if i == 0:
                cap_lines += f"{cap_uid} OUT 0 100u\n"
            else:
                cap_lines += f"{cap_uid} OUT 0 0.1u\n"

        example_circuit = f"""VIN IN 0 DC 12
{zener_line}
{resistor_line}
{cap_lines}R_LOAD OUT 0 1k"""

        if iteration == 1:
            system_prompt = f"""你是一个模拟电路设计工程师。设计一个稳压二极管并联稳压电路。

【必须使用的元器件 UID】：{uid_hint}

【关键：元器件 UID 映射】
- 稳压二极管 UID: {zener_uid} (型号 {zener_model}, 稳压值 {vz}V)
- 电阻 UID: {resistor_uid}
- 电容 UID: {', '.join(capacitor_uids) if capacitor_uids else '无'}

============================================================
🔴🔴🔴 核心规则 - 必须严格遵守 🔴🔴🔴
============================================================

【规则1：必须使用提供的元器件 UID】
- 必须使用 {zener_uid} 作为稳压二极管名称（不能改成 D_Z 或其他名字！）
- 必须使用 {resistor_uid} 作为电阻名称
- 必须使用提供的电容 UID

【规则2：稳压二极管必须反向偏置】
- SPICE 语法：D<name> <阳极节点> <阴极节点> <模型名>
- 阳极接 GND（节点0），阴极接 OUT
- 正确写法：{zener_uid} 0 OUT {zener_model}
- 错误写法：{zener_uid} OUT 0 {zener_model} （这会正向偏置，压降只有0.7V！）

【规则3：输出节点必须叫 OUT】

【规则4：禁止使用晶体管！】
- 基础并联稳压电路不需要晶体管
- 不要写任何以 Q 开头的元件

============================================================
✅ 使用你提供的 UID 的正确示例
============================================================
```
{example_circuit}```

【不要写 .control、.end、.SUBCKT 定义】
【只输出 SPICE 代码！】"""

            user_prompt = f"【设计需求】:\n{elaborated_req}\n"
            user_prompt += f"\n【元器件 UID 列表】: {uid_hint}\n"
            user_prompt += f"\n请使用上面列出的 UID 设计电路。稳压二极管 {zener_uid} 阳极接GND(0)，阴极接OUT。输出 SPICE 代码。\n"

        else:
            system_prompt = f"""你是一个SPICE电路优化专家。根据仿真反馈修复电路问题。

【必须使用的元器件 UID】：{uid_hint}

【关键：元器件 UID 映射】
- 稳压二极管 UID: {zener_uid} (型号 {zener_model}, 稳压值 {vz}V)
- 电阻 UID: {resistor_uid}
- 电容 UID: {', '.join(capacitor_uids) if capacitor_uids else '无'}

============================================================
🔴 根据仿真反馈修复问题
============================================================

【问题类型判断】
1. 输出电压偏低（如0.几V）但不是0V或0.7V：
   → 可能是稳压管没直接接在OUT节点，被分压电阻分走了
   → 解决：确保稳压管 {zener_uid} 直接并联在 OUT 节点和 GND 之间

2. 输出电压约0.7V：
   → 稳压管正向偏置（极性接反）
   → 解决：{zener_uid} 0 OUT {zener_model}（阳极接GND，阴极接OUT）

3. 输出电压为0V：
   → 电路断路或稳压管短路
   → 检查所有连接

4. 纹波过大：
   → 增大输出电容值

【正确电路结构 - 稳压管必须直接接OUT节点】
```
{example_circuit}```

【只输出 SPICE 代码！】"""

            user_prompt = f"【设计需求】:\n{elaborated_req}\n"
            user_prompt += f"\n【上一轮代码】:\n```\n{previous_spice}\n```\n"
            user_prompt += f"\n【仿真反馈】:\n{feedback}\n"
            user_prompt += f"\n请根据上述反馈修复电路。关键：稳压管 {zener_uid} 必须直接接在 OUT 节点，不能接在其他中间节点！\n"

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
                skip_message = f"[控制块] {line_stripped}"
            elif re.match(r'^\.endc\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[控制块] {line_stripped}"
            elif re.match(r'^\.model\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[模型定义] {line_stripped}"
            elif re.match(r'^\.subckt\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[子电路] {line_stripped}"
            # 自动移除晶体管 - 基础并联稳压电路不需要晶体管
            elif re.match(r'^Q\d+\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[自动移除晶体管] {line_stripped} - 基础并联稳压电路不需要晶体管"
            # 移除与晶体管相关的电阻 R_B
            elif re.match(r'^R_B\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[自动移除晶体管相关电阻] {line_stripped}"
            # 🔧 修复：将保险丝转换为小电阻 (SPICE 不支持 FUSE 元件类型)
            # 匹配: FUSE, F1, F2, F_FUSE, F_PROTECT 等（F开头，后跟数字或下划线或字母的保险丝命名）
            elif re.match(r'^F(USE|[0-9]+|_[A-Za-z0-9]+)\s+', line_stripped, re.IGNORECASE):
                parts = line_stripped.split()
                if len(parts) >= 3:
                    # Fuse node1 node2 [value] -> R_Fuse node1 node2 0.01
                    orig_name = parts[0]
                    node1, node2 = parts[1], parts[2]
                    replacement_line = f"R_{orig_name} {node1} {node2} 0.01"
                    print(f"   [SPICE修复] {orig_name} -> R_{orig_name} (0.01Ω 等效电阻，SPICE不支持FUSE)")
                should_remove = True

            if should_remove:
                removed_count += 1
                if skip_message:
                    print(f"   [自动清洗] {skip_message}")
            else:
                cleaned_lines.append(line)

            # 添加替换行（在移除原行后）
            if replacement_line:
                cleaned_lines.append(replacement_line)

        if removed_count > 0:
            print(f"   警告：LLM 生成了 {removed_count} 个错误行，已自动移除")

        return '\n'.join(cleaned_lines)

    def get_simulation_config(self) -> Dict[str, Any]:
        return {
            'analysis_type': 'tran',
            'tran_time': '100m',
            'time_step': '100u',
            'output_node': 'OUT',
            'description': '并联稳压电路瞬态分析'
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

        steady_y = []
        for i, t in enumerate(x_data):
            if t > 0.02:
                steady_y.append(y_data[i])

        if not steady_y:
            results['status'] = 'sim_error'
            print(f"   ⚠️ 稳态数据为空！")
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
        print(f"   [电压分析] 平均输出: {v_avg:.2f}V, 纹波: {v_ripple:.3f}V ({results['ripple_percent']:.1f}%)")

        # 输出电压偏离度百分比
        if self._zener_voltage and v_avg > 0:
            results['voltage_error_percent'] = abs(v_avg - self._zener_voltage) / self._zener_voltage * 100

        return results

    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:

        # 使用实例中保存的稳压值
        zv = self._zener_voltage
        # 计算容差范围 (±10%)
        min_v = zv * 0.9
        max_v = zv * 1.1

        system_prompt = f"""你是一个SPICE仿真裁判官。

【判决准则】
1. 输出电压应在稳压值附近（当前稳压管 {self._zener_model} 标称值 = {zv}V，允许误差 ±10%）
   - 合格范围：{min_v:.2f}V ~ {max_v:.2f}V
   - 判定规则：只要 v_out_avg 在 {min_v:.2f}~{max_v:.2f}V 范围内就通过，无论高于还是低于目标值！
2. 输出电压接近0V或0.7V = 稳压二极管极性错误或电路拓扑错误
3. 纹波应小于输出电压的5%

【常见问题诊断】
- 输出电压偏低但稳压管两端电压正常 → 稳压管没直接接在OUT节点，被分压了
- 输出电压约0.7V → 稳压管正向偏置（极性接反）
- 输出电压为0V → 稳压管或电阻未正确连接

【输出格式】
{{
  "passed": true或false,
  "reason": "判决原因",
  "feedback": "具体修复建议（必须明确指出如何修改SPICE代码）"
}}"""

        user_prompt = f"【设计需求】:\n{requirement}\n\n【仿真数据】:\n{metrics_str}\n\n请判决："

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        硬阈值判决（不使用 LLM）

        用于 G3 (No_Metric) 消融实验。
        稳压输出判断规则：目标值的 90% ~ 110% 为通过
        """
        zv = self._zener_voltage
        if not zv:
            return True, "无法确定稳压目标值，默认通过"

        # 从 metrics 中提取实际输出电压
        actual_voltage = metrics.get('v_out_avg_v')
        if actual_voltage is None:
            return False, "无法从仿真数据中提取输出电压"

        # 硬阈值判断：95% ~ 105% (G3: 比 LLM judge 更严格)
        min_v = zv * 0.95
        max_v = zv * 1.05

        if min_v <= actual_voltage <= max_v:
            return True, f"输出电压 {actual_voltage:.2f}V 在目标范围 {min_v:.2f}-{max_v:.2f}V 内"
        else:
            if actual_voltage < min_v:
                feedback = f"输出电压 {actual_voltage:.2f}V 太低（目标 {zv:.2f}V），可能是稳压管极性接反或未正确连接"
            else:
                feedback = f"输出电压 {actual_voltage:.2f}V 太高（目标 {zv:.2f}V），可能是负载太轻或稳压管型号不匹配"
            return False, feedback
