"""
滤波器电路专家

专门处理 Sallen-Key 低通滤波器等滤波电路的网表生成、仿真配置和评估。
所有滤波器相关的硬编码逻辑都从 ngspice_critic.py 和 netlist_generator.py 迁移至此。
"""

import re
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class FilterExpert(CircuitExpert):
    """Sallen-Key 低通滤波器专家"""

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
        return "滤波电路"

    def get_netlist_prompts(
        self,
        elaborated_req: str,
        uid_hint: str,
        iteration: int,
        previous_spice: Optional[str],
        feedback: Optional[str]
    ) -> Tuple[str, str]:
        """
        生成滤波器网表生成所需的 Prompt

        从 netlist_generator.py 第24-86行迁移
        """

        # 第一轮：给出清晰的 Sallen-Key 模板
        if iteration == 1:
            system_prompt = f"""你是一个SPICE网表生成器。生成一个标准的二阶 Sallen-Key 低通滤波器。

【必须使用的元器件 UID】（大小写必须一致）：{uid_hint}

【标准模板 - 必须严格遵循】
```
VCC VCC 0 DC 9V
V1 IN 0 DC 0 AC 1
R1 IN N1 <计算值>
C1 N1 0 <计算值>
R2 N1 N2 <计算值>
C2 N2 OUT <计算值>
X1 N2 OUT VCC 0 OUT LM2904
C_dec VCC 0 100nF
```

【关键规则 - 拓扑必须正确】
1. **信号源 V1 必须直接接到 R1！**
   - 正确：V1 IN 0 ... 然后 R1 IN N1 ...
   - 错误：V1 接到其他地方，或者 R1 接到其他节点
2. **R1 必须是第一个接到输入信号的元件！**
3. **禁止添加任何输入耦合电容到地！这会阻断直流信号！**
4. **只使用模板中的元件！不要添加 R3, R4, R_in, C_in, C3 等额外元件！**
5. **禁止添加任何从运放输出端到地的电阻！这会破坏单位增益配置！**
6. 运放调用：`X1 N2 OUT VCC 0 OUT LM2904`
   - IN+ (第1参数) = N2
   - IN- (第2参数) = OUT（单位增益反馈）
   - 这两个参数绝对不能改！
7. 截止频率公式：fc = 1 / (2pi * sqrt(R1*R2*C1*C2))
8. 不要写 .control、.end、.SUBCKT
9. 只输出 SPICE 代码！

【绝对禁止】
- 禁止添加 R3, R4, R_feedback 等任何额外电阻
- 禁止在 OUT 节点和地之间添加任何元件
- 禁止将LM2904的Pin2和Pin3相连
- 禁止将LM2904的Pin3和Pin6接地
- 禁止在 N2 节点和地之间添加任何元件
- 禁止添加输入端到地的电阻或电容（会阻断信号）"""

            user_prompt = f"【设计需求】:\n{elaborated_req}\n"
            user_prompt += f"\n【元器件 UID 列表】: {uid_hint}\n"
            user_prompt += "\n请计算合适的 R、C 值，输出 SPICE 代码。记住：只使用 R1, R2, C1, C2，不要添加任何额外元件！\n"

        # 后续迭代：根据反馈进行优化
        else:
            system_prompt = f"""你是一个SPICE电路优化专家。只调整参数值，不改变拓扑。

【必须使用的元器件 UID】：{uid_hint}

【优化规则】
1. 截止频率公式：fc = 1 / (2pi * sqrt(R1*R2*C1*C2))
2. 如果 fc 太低，减小 R 或 C
3. 如果 fc 太高，增大 R 或 C
4. **不要添加新的电阻或电容！只修改 R1, R2, C1, C2 的值！**
5. **保持运放连接：X1 N2 OUT VCC 0 OUT LM2904（绝对不变）**
6. **禁止添加 R3, R4 或任何额外元件！**
7. 不要写 .control、.end、.SUBCKT
8. 只输出 SPICE 代码！"""

            user_prompt = f"【设计需求】:\n{elaborated_req}\n"
            user_prompt += f"\n【元器件 UID 列表】: {uid_hint}\n"
            user_prompt += f"\n【你上一轮的代码】:\n```\n{previous_spice}\n```\n"
            user_prompt += f"\n【仿真反馈】:\n{feedback}\n"
            user_prompt += "\n请只调整 R1, R2, C1, C2 的值，不要添加新的元件（特别是 R3, R4），不要改变运放的连接方式。输出修改后的 SPICE 代码。\n"

        return system_prompt, user_prompt

    def clean_spice_code(self, spice_code: str) -> str:
        """
        清洗 SPICE 代码，移除 LLM 错误添加的多余元件

        从 netlist_generator.py 第94-143行迁移
        """
        # 这些元件会破坏 Sallen-Key 单位增益配置
        forbidden_patterns = [
            r'^R3\s+.*$',           # 移除 R3
            r'^R4\s+.*$',           # 移除 R4
            r'^R_feedback\s+.*$',   # 移除 R_feedback
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
                    skip_message = f"[禁止元件] {line_stripped}"
                    break

            # 检测两端都接地的元件（电气短路，无意义）
            if not should_remove:
                # 匹配 Cxxx 0 0 value 或 Rxxx 0 0 value
                short_circuit_match = re.match(r'^([RC]\w+)\s+0\s+0\s+', line_stripped, re.IGNORECASE)
                if short_circuit_match:
                    should_remove = True
                    skip_message = f"[短路错误] {line_stripped} - 两端都接地，无意义"

            # 检测重复的去耦电容（只保留一个）
            if not should_remove:
                # 匹配去耦电容 C_decxxx VCC 0 或 C_decxxx 0 VCC
                decap_match = re.match(r'^(C_dec\d*)\s+(VCC|0)\s+(0|VCC)\s+', line_stripped, re.IGNORECASE)
                if decap_match:
                    # 检查是否已经有去耦电容了
                    if any('C_dec' in l and ('VCC' in l.upper() or '0' in l.split()) for l in cleaned_lines):
                        should_remove = True
                        skip_message = f"[重复去耦] {line_stripped} - 已有去耦电容，移除重复"

            if should_remove:
                removed_count += 1
                print(f"   [自动清洗] {skip_message}")
            else:
                cleaned_lines.append(line)

        if removed_count > 0:
            print(f"   警告：LLM 生成了 {removed_count} 个错误元件，已自动移除")

        return '\n'.join(cleaned_lines)

    def get_simulation_config(self) -> Dict[str, Any]:
        """
        返回滤波器仿真配置

        从 ngspice_critic.py SimulationConfig['filter'] 迁移
        """
        return {
            'analysis_type': 'ac',
            'metrics': ['cutoff_freq', 'passband_gain', 'roll_off'],
            'frequency_range': (1, 1e6),
            'output_node': 'OUT',
            'points_per_decade': 50,
            'description': '滤波电路'
        }

    def parse_simulation_data(
        self,
        x_data: list,
        y_data: list,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        解析滤波器仿真数据，计算关键指标

        从 ngspice_critic.py 第297-436行迁移
        重点：计算截止频率（-3dB 点）、通带增益等
        """
        if not x_data:
            return None

        results = {}

        # AC 分析指标
        # 找到真正的通带区域（增益最大的区域）
        # 使用滑动窗口找到增益最平稳的区域作为通带参考

        # 先找到最大增益点及其附近作为通带参考
        max_gain = max(y_data)
        max_idx = y_data.index(max_gain)
        results['max_gain_db'] = max_gain

        # 以最大增益附近（±1个 decade）的增益作为通带增益
        # 这样可以避免高频衰减区拉低平均值
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

        # 截止频率检测 - 对于低通滤波器，从低频往高频搜索
        # 截止频率：增益下降到通带增益 -3dB 的频率点
        threshold = passband_gain - 3.0

        # 从低频往高频搜索，找到增益第一次低于 threshold 的点
        # 这是低通滤波器的正确检测方式
        cutoff_freq = None
        for i in range(len(x_data)):
            if y_data[i] <= threshold:
                # 找到精确的截止频率点（线性插值）
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
            # 如果整个频段都没有低于 threshold，说明截止频率超出了仿真范围
            # 此时取最高频率点作为参考
            results['cutoff_freq_hz'] = x_data[-1]
            print(f"   ⚠️ 截止频率超出仿真范围，上限 {x_data[-1]:.0f} Hz")

        # 带宽（如果有截止频率）
        if 'cutoff_freq_hz' in results:
            results['bandwidth_hz'] = results['cutoff_freq_hz']

        # 截止频率偏离度百分比
        if self._target_cutoff_hz and results.get('cutoff_freq_hz'):
            results['cutoff_deviation_pct'] = abs(results['cutoff_freq_hz'] - self._target_cutoff_hz) / self._target_cutoff_hz * 100

        return results

    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:
        """
        生成滤波器判决所需的 Prompt

        从 ngspice_critic.py 第457-520行迁移
        """
        # 优先使用 set_targets() 注入的目标值
        target_freq = self._target_cutoff_hz
        if target_freq is None:
            # fallback: 从需求中提取目标截止频率（单位：Hz）
            match = re.search(r'(\d+(?:\.\d+)?)\s*([kK]?)Hz', requirement, re.IGNORECASE)
            if match:
                target_freq = float(match.group(1))
                if match.group(2).lower() == 'k':
                    target_freq *= 1000
            if not target_freq:
                match = re.search(r'截止频率.*?(\d+(?:\.\d+)?)', requirement)
                if match:
                    target_freq = float(match.group(1))

        # 计算容差范围 (±20%)
        if target_freq:
            min_freq = target_freq * 0.8
            max_freq = target_freq * 1.2
            range_str = f"{min_freq:.0f}Hz ~ {max_freq:.0f}Hz"
        else:
            range_str = "未知目标值，请根据需求自行判断合理范围"

        system_prompt = f"""你是一个专业的 SPICE 仿真裁判官和电路优化顾问。

【电路类型】: 滤波电路

【判决准则】截止频率判断规则
如果需求中明确了目标截止频率 fx，则判断规则如下：
- 目标截止频率: {target_freq}Hz（如需求中未明确，请忽略此行）
- 合格范围: 目标值的 80% ~ 120%（即 {range_str}）
- 判定逻辑: 实测值在 {range_str} 范围内 → 通过；不在范围内 → 不通过
- 注意：只要在范围内就通过，无论高于还是低于目标值！

【低通滤波器优化规则】
- 截止频率公式：fc = 1 / (2π × √(R1×R2×C1×C2))
- 如果 fc 太低 → 减小 R 或 C 值
- 如果 fc 太高 → 增大 R 或 C 值
- 建议：每次调整幅度为 20%-50%

【输出格式】
{{
  "passed": true或false,
  "reason": "判决原因（一句话）",
  "feedback": "具体调整建议，例如：'截止频率100Hz太低，目标1kHz。请将R1和R2从10k减小到5k，或将C1和C2从100nF减小到20nF'"
}}"""

        user_prompt = f"【原始设计需求】:\n{requirement}\n\n【实测仿真数据】:\n{metrics_str}\n\n请判决并给出优化建议："

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        硬阈值判决（不使用 LLM）

        用于 G3 (No_Metric) 消融实验。
        截止频率判断规则：目标值的 80% ~ 120% 为通过
        """
        # 优先使用 set_targets() 注入的目标值
        target_freq = self._target_cutoff_hz
        if target_freq is None:
            match = re.search(r'(\d+(?:\.\d+)?)\s*([kK]?)Hz', requirement, re.IGNORECASE)
            if match:
                target_freq = float(match.group(1))
                if match.group(2).lower() == 'k':
                    target_freq *= 1000
            if not target_freq:
                match = re.search(r'截止频率.*?(\d+(?:\.\d+)?)', requirement)
                if match:
                    target_freq = float(match.group(1))

        # 从 metrics 中提取实际截止频率
        actual_cutoff = metrics.get('cutoff_freq_hz')
        if not actual_cutoff:
            return False, "无法从仿真数据中提取截止频率"

        # 如果没有目标频率，则无法判断
        if not target_freq:
            return True, "需求中未指定目标截止频率，默认通过"

        # 硬阈值判断：90% ~ 110% (G3: 比 LLM judge 更严格)
        min_freq = target_freq * 0.9
        max_freq = target_freq * 1.1

        if min_freq <= actual_cutoff <= max_freq:
            return True, f"截止频率 {actual_cutoff:.0f}Hz 在目标范围 {min_freq:.0f}-{max_freq:.0f}Hz 内"
        else:
            if actual_cutoff < min_freq:
                feedback = f"截止频率 {actual_cutoff:.0f}Hz 太低（目标 {target_freq:.0f}Hz），需要减小 R 或 C 值"
            else:
                feedback = f"截止频率 {actual_cutoff:.0f}Hz 太高（目标 {target_freq:.0f}Hz），需要增大 R 或 C 值"
            return False, feedback
