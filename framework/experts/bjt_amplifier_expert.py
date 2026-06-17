"""
三极管共射极放大电路专家

专门处理 BJT Common Emitter Amplifier 电路。
采用 SPICE 原生三极管模型（2N3904），稳定性极高，适合进行交流（AC）增益寻优。
"""

import re
import math
from typing import Tuple, Dict, Any, Optional
from .base_expert import CircuitExpert


class BjtAmplifierExpert(CircuitExpert):
    """三极管共射极放大电路专家"""

    def __init__(self):
        super().__init__()
        self._target_gain_db = None

    @property
    def circuit_type(self) -> str:
        return "bjt_amplifier"

    def get_circuit_description(self) -> str:
        return "三极管共射极放大电路"

    def set_targets(self, targets: Optional[Dict] = None):
        super().set_targets(targets)
        if targets and targets.get("metric") == "max_gain_db":
            self._target_gain_db = targets.get("value")

    def _extract_target_gain(self, requirement: str) -> float:
        """
        从需求中提取目标增益（dB）

        支持格式：
        - "增益为40dB" -> 40
        - "增益20dB" -> 20
        - "100倍放大" -> 40 (20*log10(100))
        - "10倍增益" -> 20
        """
        # 尝试匹配 dB 值
        db_match = re.search(r'(\d+(?:\.\d+)?)\s*dB', requirement, re.IGNORECASE)
        if db_match:
            return float(db_match.group(1))

        # 尝试匹配倍数
        times_match = re.search(r'(\d+(?:\.\d+)?)\s*倍', requirement)
        if times_match:
            times = float(times_match.group(1))
            return 20 * math.log10(times) if times > 0 else 40

        # 默认 40dB (100倍)
        return 40.0

    def get_netlist_prompts(
        self,
        elaborated_req: str,
        uid_hint: str,
        iteration: int,
        previous_spice: Optional[str],
        feedback: Optional[str]
    ) -> Tuple[str, str]:
        """
        生成三极管共射放大器网表所需的 Prompt

        采用分压偏置共射放大器拓扑，只使用 SPICE 原生三极管模型（2N3904）。
        """

        # 优先使用 set_targets() 注入的目标值，否则 regex fallback
        target_gain_db = self._target_gain_db or self._extract_target_gain(elaborated_req)
        target_gain_linear = 10 ** (target_gain_db / 20)

        # 第一轮：提供标准的分压偏置共射放大器模板
        if iteration == 1:
            system_prompt = f"""你是一个SPICE网表生成器。你的任务是根据设计需求生成SPICE网表代码。

【输出格式要求 - 极其重要】
1. **只输出纯 SPICE 代码**，不要有任何解释、分析或说明文字
2. 不要使用 markdown 代码块标记（如 ```spice）
3. 不要输出中文或英文的分析文本
4. 每行只能是一个有效的 SPICE 语句

【必须使用的元器件 UID】（大小写必须一致）：{uid_hint}

【目标增益】
- 目标增益：{target_gain_db:.1f} dB（约 {target_gain_linear:.0f} 倍）
- 容差范围：{target_gain_db * 0.85:.1f} dB ~ {target_gain_db * 1.15:.1f} dB
- 注意：单级共射放大器实际增益上限约 40-50 dB

【标准拓扑结构 - 必须严格遵守】
```
VCC VCC 0 DC 12V
VIN IN 0 DC 0 AC 1
<R1_UID> VCC N_BASE <R1值，典型8.2k-47k>
<R2_UID> N_BASE 0 <R2值，典型2.2k-10k>
<RC_UID> VCC N_COLLECTOR <RC值，根据增益计算>
<RE_UID> N_EMITTER 0 <RE值，典型100-1k>
<CIN_UID> IN N_BASE 1u
<COUT_UID> N_COLLECTOR OUT 1u
<CE_UID> N_EMITTER 0 47u
<Q1_UID> N_COLLECTOR N_BASE N_EMITTER 2N3904
<RL_UID> OUT 0 10k
```

【关键：正确的偏置设计方法】
**步骤1：确定静态工作点**
- 目标：Vce ≈ VCC/2 = 6V（保证最大输出动态范围）
- 目标：Ic ≈ 1-2mA（典型工作电流）

**步骤2：计算发射极电阻 RE**
- Ve ≈ 1V（提供稳定的直流负反馈）
- RE = Ve / Ie ≈ 1V / 1mA = 1kΩ

**步骤3：计算基极偏置电阻**
- Vb = Ve + Vbe ≈ 1V + 0.65V = 1.65V
- R2 电流取 I_R2 = 10×Ib ≈ 0.1mA（稳定偏置）
- R2 = Vb / I_R2 ≈ 1.65V / 0.1mA = 16.5kΩ（取 15k-18k）
- R1 = (VCC - Vb) / (I_R2 + Ib) ≈ (12-1.65) / 0.11mA ≈ 94kΩ（取 82k-100k）

**步骤4：根据增益计算 RC**
- 增益公式：Au ≈ RC / re，其中 re ≈ 26mV/Ie ≈ 26Ω（当 Ie=1mA）
- 目标增益 {target_gain_linear:.0f} 倍 → RC ≈ {target_gain_linear:.0f} × 26Ω ≈ {target_gain_linear * 26:.0f}Ω
- **验证**：RC × Ic 必须小于 (VCC - Ve) = 11V，否则饱和！
- 如果 RC × Ic > 11V，需要减小 RC 或增大 RE（牺牲增益换取稳定）

【安全设计约束 - 必须满足】
1. **RC × Ic < VCC - Ve - 2V**（防止饱和，留2V余量）
2. **RE ≥ 100Ω**（保证工作点稳定）
3. **Vb = VCC × R2/(R1+R2) 在 1.2V-2.5V 范围**
4. **Ic = (Vb-0.65)/RE 在 0.5mA-3mA 范围**

【电容处理规则】
- 只使用列表中已有的电容 UID
- CE 连接：`<CE_UID> N_EMITTER 0 47u`（并联旁路）
- 不要添加额外的 C_comp 或补偿电容！

【阻值格式】
- 电阻：使用 k 或 无单位（如 10k, 4.7k, 220）
- 电容：使用 u/n/p（如 47u, 100n, 10p）

【绝对禁止】
- 禁止输出任何非 SPICE 语句的文字！
- 禁止使用 N_E_AC 等中间节点！（会导致直流悬浮）
- 禁止将电容连接在集电极和基极之间！（密勒效应）
- 禁止设计让三极管饱和的偏置！"""

            user_prompt = f"【设计需求】: {elaborated_req}\n【元器件 UID 列表】: {uid_hint}\n\n请输出 SPICE 代码："

        # 后续迭代：根据反馈进行优化
        else:
            system_prompt = f"""你是一个SPICE电路优化专家。只调整参数值，不改变拓扑。

【输出格式要求 - 极其重要】
1. **只输出纯 SPICE 代码**，不要有任何解释、分析或说明文字
2. 不要使用 markdown 代码块标记
3. 不要输出中文或英文的分析文本

【必须使用的元器件 UID】：{uid_hint}

【目标增益】
- 目标增益：{target_gain_db:.1f} dB（约 {target_gain_linear:.0f} 倍）
- 容差范围：{target_gain_db * 0.85:.1f} dB ~ {target_gain_db * 1.15:.1f} dB

【标准拓扑结构 - 必须遵守】
```
<R1_UID> VCC N_BASE <值>
<R2_UID> N_BASE 0 <值>
<RC_UID> VCC N_COLLECTOR <值>
<RE_UID> N_EMITTER 0 <值>
<CE_UID> N_EMITTER 0 47u
```
注意：CE 直接并联在 RE 两端，不使用 N_E_AC 等中间节点！

【优化规则】
1. **增益公式**：Au ≈ RC / re（re ≈ 26mV/Ie，约 26Ω@1mA）
2. **增益调整**：
   - 增益太低 → 增大 RC 或减小 RE（提高 Ie 减小 re）
   - 增益太高 → 减小 RC 或增大 RE

3. **饱和问题诊断**（增益远低于预期时）：
   - 检查：RC × Ic 是否 > (VCC - Ve)？
   - 如果饱和：增大 R1、减小 R2 或增大 RE

4. **截止问题诊断**（增益为负值时）：
   - 检查：Vb 是否过低？
   - 如果截止：减小 R1 或增大 R2

【安全约束 - 必须满足】
- RC × Ic < VCC - Ve - 2V（防止饱和）
- Ic = (Vb - 0.65V) / RE，应在 0.5-3mA 范围
- Vb = 12V × R2/(R1+R2)，应在 1.2-2.5V 范围

【常见错误修复】
1. **使用了 N_E_AC 节点**：直接改为 RE 接地，CE 并联在 RE 上
2. **电容值用电阻单位**：10Meg → 10u, 1k → 1u
3. **三极管饱和**：增大 R1 或 RE，确保 Vc > Ve + 2V

【绝对禁止】
- 禁止输出任何非 SPICE 语句的文字！
- 禁止使用 N_E_AC 等中间节点！
- 禁止将电容连接在集电极和基极之间！"""

            user_prompt = f"【设计需求】: {elaborated_req}\n【元器件 UID 列表】: {uid_hint}\n\n【你上一轮的代码】:\n{previous_spice}\n\n【仿真反馈】:\n{feedback}\n\n请只调整参数值，输出修改后的 SPICE 代码："

        return system_prompt, user_prompt

    def clean_spice_code(self, spice_code: str) -> str:
        """
        清洗 SPICE 代码，移除 LLM 错误添加的分析文本和无效语句

        确保只使用 SPICE 原生三极管调用方式（Q1 ... 2N3904）
        """
        lines = spice_code.split('\n')
        cleaned_lines = []
        removed_count = 0

        # 有效的 SPICE 语句开头模式
        valid_spice_patterns = [
            r'^[VIRCLDQX]\w*\s+\S+',  # 元件语句：Vxxx, Ixxx, Rxxx, Cxxx, Lxxx, Dxxx, Qxxx, Xxxx 后跟节点
            r'^\.\w+',                 # 点命令：.model, .subckt, .ends, .end
            r'^\s*$',                  # 空行
        ]

        for line in lines:
            line_stripped = line.strip()
            should_remove = False
            skip_message = None

            # 跳过包含中文字符的行（LLM 分析文本）
            if re.search(r'[\u4e00-\u9fff]', line_stripped):
                should_remove = True
                skip_message = f"[中文文本] {line_stripped[:30]}..."

            # 跳过 markdown 格式行
            if not should_remove and re.match(r'^\*{1,2}|\*{1,2}$|^-_|^#', line_stripped):
                should_remove = True
                skip_message = f"[Markdown格式] {line_stripped[:30]}..."

            # 跳过以 - 开头的列表项
            if not should_remove and re.match(r'^-\s*_?DUP', line_stripped):
                should_remove = True
                skip_message = f"[列表项] {line_stripped[:30]}..."

            # 检查是否是有效的 SPICE 语句
            if not should_remove:
                is_valid_spice = False
                for pattern in valid_spice_patterns:
                    if re.match(pattern, line_stripped, re.IGNORECASE):
                        is_valid_spice = True
                        break

                # 单独处理注释行（以 * 开头，但不是 markdown）
                if line_stripped.startswith('*') and not line_stripped.startswith('**'):
                    is_valid_spice = True

                if not is_valid_spice:
                    should_remove = True
                    skip_message = f"[非SPICE语句] {line_stripped[:30]}..."

            # 移除 .control 和 .endc 块
            if not should_remove and re.match(r'^\.control\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[控制块] {line_stripped}"
            elif not should_remove and re.match(r'^\.endc\s*$', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[控制块] {line_stripped}"

            # 移除 .model 语句（由 spice_engine 统一注入）
            if not should_remove and re.match(r'^\.model\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[模型定义] {line_stripped}"

            # 移除 .SUBCKT 定义
            if not should_remove and re.match(r'^\.subckt\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[子电路] {line_stripped}"

            # 移除 .include 和 .lib 语句
            if not should_remove and re.match(r'^\.include\s+|^\.lib\s+', line_stripped, re.IGNORECASE):
                should_remove = True
                skip_message = f"[禁止外部模型] {line_stripped}"

            # 检测两端都接地的元件（电气短路，无意义）
            if not should_remove:
                short_circuit_match = re.match(r'^([RC]\w+)\s+0\s+0\s+', line_stripped, re.IGNORECASE)
                if short_circuit_match:
                    should_remove = True
                    skip_message = f"[短路错误] {line_stripped}"

            # 检测电容值格式错误（使用电阻单位 k/M/Meg）
            if not should_remove:
                cap_match = re.match(r'^C\w+\s+\S+\s+\S+\s+(\S+)', line_stripped, re.IGNORECASE)
                if cap_match:
                    cap_value = cap_match.group(1).upper()
                    # 检测错误的单位
                    if re.search(r'[KMG]|MEG', cap_value):
                        should_remove = True
                        skip_message = f"[电容值格式错误] {line_stripped} - 电容值不能使用 k/M/Meg 单位！"

            # 检测 C_comp 错误连接在集电极和基极之间（形成密勒负反馈）
            if not should_remove:
                # 匹配 C_comp N_COLLECTOR N_BASE 或类似模式
                comp_feedback = re.match(r'^C\w*\s+N_COLLECTOR\s+N_BASE', line_stripped, re.IGNORECASE)
                if comp_feedback:
                    should_remove = True
                    skip_message = f"[密勒负反馈] {line_stripped} - C_comp连接在集电极和基极之间会导致增益归零！"

            # 检测 N_E_AC 节点（会导致直流悬浮）
            if not should_remove:
                # 匹配连接到 N_E_AC 节点的元件
                neac_match = re.match(r'^[RC]\w*\s+\S+\s+N_E_AC\s+', line_stripped, re.IGNORECASE)
                if neac_match:
                    print(f"   [警告] 检测到 N_E_AC 节点！这会导致直流悬浮，建议改为 RE 直接接地、CE 并联在 RE 上")
                    # 不删除，只警告，让 LLM 在下一轮修正

            if should_remove:
                removed_count += 1
            else:
                cleaned_lines.append(line)

        if removed_count > 0:
            print(f"   [清洗统计] 移除 {removed_count} 行无效内容")

        return '\n'.join(cleaned_lines)

    def get_simulation_config(self) -> Dict[str, Any]:
        """
        返回三极管放大电路仿真配置

        使用交流分析（AC）测量频率响应和中频增益
        """
        return {
            'analysis_type': 'ac',
            'frequency_range': (10, 100000),  # 10Hz ~ 100kHz
            'points_per_decade': 10,
            'output_node': 'OUT',
            'description': '三极管放大电路交流分析'
        }

    def parse_simulation_data(
        self,
        x_data: list,
        y_data: list,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        解析交流仿真数据，计算中频增益

        因为输入是 AC 1V，所以输出电压的大小直接等于线性增益。
        """
        if not x_data or not y_data:
            return {'status': 'no_data', 'error': '仿真数据为空'}

        results = {}

        # 求出最大输出电压（即最大线性增益）
        max_gain_db = max(y_data)
        results['max_gain_db'] = max_gain_db

        # 计算线性增益
        max_gain_v = 10 ** (max_gain_db / 20)
        results['max_gain_v'] = max_gain_v

        # 找到最大增益对应的频率
        max_idx = y_data.index(max_gain_db)
        if max_idx < len(x_data):
            results['peak_freq_hz'] = x_data[max_idx]

        # 计算增益平坦度（用于判断是否正常工作）
        # 正常放大器应该在中频有平坦增益，低频滚降
        low_freq_gains = y_data[:5]  # 前5个点（低频）
        mid_freq_gains = y_data[len(y_data)//3:2*len(y_data)//3]  # 中间三分之一（中频）

        avg_low_gain = sum(low_freq_gains) / len(low_freq_gains) if low_freq_gains else 0
        avg_mid_gain = sum(mid_freq_gains) / len(mid_freq_gains) if mid_freq_gains else 0
        gain_rise = avg_mid_gain - avg_low_gain

        results['low_freq_gain_db'] = avg_low_gain
        results['mid_freq_gain_db'] = avg_mid_gain
        results['gain_rise_db'] = gain_rise

        # 检查电路工作状态
        if max_gain_db < -100:
            # 极端情况：电路几乎无输出
            results['status'] = 'circuit_error'
            print(f"   [严重错误] 电路结构异常！最大增益仅 {max_gain_db:.2f} dB")
            print(f"   可能原因：1) 使用了N_E_AC悬浮节点 2) 电容值格式错误 3) 元件连接错误")
        elif max_gain_db < 0:
            # 负增益：可能是有源器件截止或密勒负反馈
            results['status'] = 'negative_feedback_or_cutoff'
            print(f"   [增益异常] 增益为负值 {max_gain_db:.2f} dB！")
            print(f"   可能原因：1) C_comp连接在集电极-基极之间 2) 三极管截止 3) 使用了悬浮节点")
        elif max_gain_db < 10:
            # 增益极低：可能是三极管饱和
            results['status'] = 'low_gain_possible_saturation'
            print(f"   [增益过低] 中频增益仅 {max_gain_db:.2f} dB，可能三极管已饱和！")
            print(f"   建议：检查 RC×Ic 是否 > (VCC-Ve)，增大R1或增大RE以减小集电极电流")
        elif gain_rise < 5 and max_gain_db < 20:
            # 增益平坦且低：可能是旁路电容未起作用或拓扑错误
            results['status'] = 'flat_low_gain'
            print(f"   [增益平坦] 中频增益 {max_gain_db:.2f} dB，低频增益 {avg_low_gain:.2f} dB")
            print(f"   可能原因：CE未正确旁路，或三极管工作点异常")
        else:
            results['status'] = 'ok'
            print(f"   [增益测量] 中频增益: {max_gain_db:.2f} dB（线性: {max_gain_v:.2f}）")

        # 增益偏离度 (dB)
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
        生成三极管放大电路判决所需的 Prompt
        """

        # 优先使用 set_targets() 注入的目标值
        target_gain_db = self._target_gain_db or self._extract_target_gain(requirement)
        lower_bound = target_gain_db * 0.85
        upper_bound = target_gain_db * 1.15

        system_prompt = f"""你是一个专业的 SPICE 仿真裁判官和模拟电路优化顾问。

【电路类型】: 三极管共射放大电路

【目标增益与容差】
- 目标增益：{target_gain_db:.1f} dB
- 容差范围：{lower_bound:.1f} dB ~ {upper_bound:.1f} dB（±15%）
- 判定规则：只要 max_gain_db 在 {lower_bound:.1f}~{upper_bound:.1f} dB 范围内就通过，无论高于还是低于目标值！
- 注意：单级共射放大器实际增益上限约 40-50 dB

【关键：判决依据】
- 必须使用 max_gain_db（峰值增益）进行判决
- 忽略 mid_freq_gain_db、low_freq_gain_db 等辅助数据

【增益公式】
- 开环增益：Au ≈ RC / re（re ≈ 26mV/Ie）
- 当 Ie = 1mA 时，re ≈ 26Ω

【故障诊断与解决】
1. **增益极低（< 0dB 或远低于目标）**：
   - 最可能原因：三极管饱和！检查 RC × Ic 是否 > (VCC - Ve - 2V)
   - 解决：增大 R1 或增大 RE，减小集电极电流

2. **增益为负值（< 0dB）**：
   - 可能原因1：补偿电容 C_comp 错误连接在集电极和基极之间
   - 可能原因2：使用了 N_E_AC 等悬浮节点
   - 解决：删除 C_comp，将 RE 直接接地、CE 并联在 RE 上

3. **电容值格式错误**：
   - 错误：`C_xxx NODE1 NODE2 10Meg`（使用了电阻单位 Meg）
   - 正确：`C_xxx NODE1 NODE2 10u`（使用法拉单位 p/n/u/m）

4. **增益略低**：增大 RC 或减小 RE
5. **增益略高**：减小 RC 或增大 RE

【饱和诊断公式】
- Vb = 12V × R2/(R1+R2)
- Ic ≈ (Vb - 0.65V) / RE
- 如果 RC × Ic > 10V，则三极管可能饱和

【输出格式】
{{
  "passed": true或false,
  "reason": "判决原因（一句话）",
  "feedback": "具体调整建议"
}}"""

        user_prompt = f"【原始设计需求】:\n{requirement}\n\n【实测仿真数据】:\n{metrics_str}\n\n【目标增益】: {target_gain_db:.1f} dB，容差范围：{lower_bound:.1f} dB ~ {upper_bound:.1f} dB\n\n请使用 max_gain_db 进行判决，并给出优化建议："

        return system_prompt, user_prompt

    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        硬阈值判决（不使用 LLM）

        用于 G3 (No_Metric) 消融实验。
        增益判断规则：目标值的 85% ~ 115% 为通过
        """
        # 提取目标增益
        # 优先使用 set_targets() 注入的目标值
        target_gain = self._target_gain_db or self._extract_target_gain(requirement)

        if not target_gain:
            return True, "需求中未指定目标增益，默认通过"

        # 从 metrics 中提取实际增益
        actual_gain = metrics.get('max_gain_db')
        if actual_gain is None:
            return False, "无法从仿真数据中提取增益"

        # 硬阈值判断：85% ~ 115%
        # 硬阈值判断：90% ~ 110% (G3: 比 LLM judge 更严格)
        min_gain = target_gain * 0.9
        max_gain = target_gain * 1.1

        if min_gain <= actual_gain <= max_gain:
            return True, f"增益 {actual_gain:.1f}dB 在目标范围 {min_gain:.1f}-{max_gain:.1f}dB 内"
        else:
            if actual_gain < min_gain:
                feedback = f"增益 {actual_gain:.1f}dB 太低（目标 {target_gain:.1f}dB），需要增大 Rc 或减小 Re"
            else:
                feedback = f"增益 {actual_gain:.1f}dB 太高（目标 {target_gain:.1f}dB），需要减小 Rc 或增大 Re"
            return False, feedback
