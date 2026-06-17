"""
通用网表生成引擎

核心引擎，负责调用 LLM 生成 SPICE 网表。
具体的 Prompt 和清洗逻辑委托给专家模块处理。
"""

import os
import json
import re
from typing import Optional
from openai import OpenAI

from experts.base_expert import CircuitExpert

API_KEY = (
    os.environ.get("EDA_API_KEY")
    or os.environ.get("SILICONFLOW_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or ""
)
BASE_URL = os.environ.get("EDA_BASE_URL", "")
MODEL_NAME = os.environ.get("EDA_MODEL_NAME", "deepseek-ai/DeepSeek-V3.2")
THINKING_ENABLED = False
EXPLICIT_DISABLE_THINKING = False


class NetlistEngine:
    """通用网表生成引擎"""

    def __init__(self):
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    def generate_spice(
        self,
        plan_data: dict,
        expert: CircuitExpert,
        iteration: int = 1,
        previous_spice: Optional[str] = None,
        feedback: Optional[str] = None,
        retrieved_path: Optional[str] = None,
        temperature: float = 0.1
    ) -> str:
        """
        使用专家模块生成 SPICE 网表

        Args:
            plan_data: 规划数据（包含 components, elaborated_requirement 等）
            expert: 电路专家实例
            iteration: 当前迭代次数
            previous_spice: 上一轮的 SPICE 代码
            feedback: 上一轮的仿真反馈
            retrieved_path: 检索结果文件路径（用于获取实际型号）

        Returns:
            str: 生成的 SPICE 代码
        """
        elaborated_req = plan_data.get("elaborated_requirement", "")

        # 提取元器件 UID 列表和型号映射
        components = plan_data.get("components", [])
        uid_list = [comp.get("uid") for comp in components if comp.get("uid")]

        # 构建 uid_hint，包含型号信息
        uid_model_map = {}
        if retrieved_path and os.path.exists(retrieved_path):
            try:
                with open(retrieved_path, 'r', encoding='utf-8') as f:
                    retrieved_data = json.load(f)
                for uid, info in retrieved_data.items():
                    if info and 'lib_id' in info:
                        uid_model_map[uid] = info['lib_id']
            except Exception as e:
                print(f"   [警告] 无法读取检索结果: {e}")

        # 格式化 uid_hint，包含型号信息
        uid_hint_parts = []
        for uid in uid_list:
            if uid in uid_model_map:
                uid_hint_parts.append(f"{uid}({uid_model_map[uid]})")
            else:
                uid_hint_parts.append(uid)
        uid_hint = "、".join(uid_hint_parts)

        # 从专家获取 Prompt
        system_prompt, user_prompt = expert.get_netlist_prompts(
            elaborated_req, uid_hint, iteration, previous_spice, feedback
        )

        # 调用 LLM 生成
        kwargs = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }
        if THINKING_ENABLED:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        elif EXPLICIT_DISABLE_THINKING:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = self.client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content

        # 提取 SPICE 代码块
        match = re.search(r'```spice\s*(.*?)\s*```', raw, flags=re.DOTALL | re.IGNORECASE)
        spice_code = match.group(1).strip() if match else raw.replace("```", "").strip()

        # 调用专家的专有清洗逻辑
        spice_code = expert.clean_spice_code(spice_code)

        # --- 🛡️ 框架级全局防弹护盾：自动修复重复的元件名 ---
        cleaned_spice_lines = []
        seen_components = set()
        for line in spice_code.split('\n'):
            line_strip = line.strip()
            if not line_strip or line_strip.startswith('*') or line_strip.startswith('.'):
                cleaned_spice_lines.append(line)
                continue
            
            parts = line_strip.split()
            if not parts:
                cleaned_spice_lines.append(line)
                continue
            
            comp_name = parts[0].upper()
            if comp_name in seen_components:
                # 发现重复的元件名，自动加后缀重命名
                new_name = f"{comp_name}_DUP{len(seen_components)}"
                print(f"   [全局护盾] 拦截到 LLM 幻觉：重复元件名 {comp_name}，已自动重命名为 {new_name}")
                parts[0] = new_name
                seen_components.add(new_name)
                cleaned_spice_lines.append(" ".join(parts))
            else:
                seen_components.add(comp_name)
                cleaned_spice_lines.append(line)
        
        spice_code = '\n'.join(cleaned_spice_lines)

        return spice_code

    def translate_to_json(
        self,
        spice_code: str,
        retrieved_path: str,
        output_path: str
    ) -> str:
        """
        将 SPICE 网表翻译为画图引擎所需的 JSON 格式

        这是通用逻辑，不依赖专家模块。
        从 netlist_generator.py 第145-522行迁移。
        """
        print("\n[翻译] 正在将优化后的 SPICE 网表翻译为画图引擎所需的 JSON 格式...")
        with open(retrieved_path, 'r', encoding='utf-8') as f:
            retrieved_data = json.load(f)

        # 过滤掉检索失败的元件（值为 None 的条目）
        valid_uids = [uid for uid, info in retrieved_data.items() if info is not None]
        print(f"   检索到 {len(valid_uids)} 个有效元器件: {valid_uids}")

        # 从 SPICE 代码中提取优化后的元件值
        print(f"   正在从 SPICE 代码提取优化后的元件值...")
        optimized_values = {}

        for line in spice_code.split('\n'):
            line = line.strip()
            # 匹配电阻：Rxxx node1 node2 value（支持 R1, R2, Ri, Rf, R_load 等格式）
            r_match = re.match(r'^(R[A-Za-z0-9_]*)\s+\S+\s+\S+\s+([\d.]+[kKmMuUnNpPgGtT]?)', line, re.IGNORECASE)
            if r_match:
                uid = r_match.group(1).upper()
                value = r_match.group(2)
                optimized_values[uid] = value
                print(f"      提取 {uid} = {value}")
                continue

            # 匹配电容：Cxxx node1 node2 value（支持 C1, C_in, C_out 等格式）
            c_match = re.match(r'^(C[A-Za-z0-9_]*)\s+\S+\s+\S+\s+([\d.]+[kKmMuUnNpPgGtT]?F?)', line, re.IGNORECASE)
            if c_match:
                uid = c_match.group(1).upper()
                value = c_match.group(2)
                value = re.sub(r'F$', '', value, flags=re.IGNORECASE)
                optimized_values[uid] = value
                print(f"      提取 {uid} = {value}")
                continue

        # 更新 retrieved_data 中的元件值
        for uid in valid_uids:
            if uid.upper() in optimized_values:
                new_value = optimized_values[uid.upper()]
                if uid in retrieved_data and retrieved_data[uid]:
                    old_value = retrieved_data[uid].get('planned_value', '')
                    if old_value != new_value:
                        print(f"      更新 {uid}: {old_value} -> {new_value}")
                        retrieved_data[uid]['planned_value'] = new_value

        # 动态组装"元件引脚说明书"
        comp_context = "## 系统当前加载的物理元器件与可用引脚清单 (动态 Datasheet)\n"
        for uid, info in retrieved_data.items():
            if not info:
                continue
            lib_id = info.get('lib_id', 'Unknown')
            pin_desc = []
            for p in info.get('pins', []):
                p_num = p.get('num')
                p_type = p.get('type', 'passive')
                pin_desc.append(f"引脚{p_num}({p_type})")
            comp_context += f"- UID: `{uid}` (型号: {lib_id}) | 拥有可用物理引脚: [{', '.join(pin_desc)}]\n"

        # 万能跨域映射法则
        system_prompt = """你是一个顶级的硬件翻译引擎。你的任务是将 SPICE 网表翻译为我自定义的 JSON 格式。

【关键规则】

1. **常见芯片引脚映射**：
   - **LM2904/LM358**: 引脚 3(IN+), 2(IN-), 8(V+), 4(V-/GND), 1(OUT)
   - **NE555**: 引脚 1(GND), 2(TR), 3(OUT), 4(RST), 5(CV), 6(THR), 7(DIS), 8(VCC)
   在 SPICE 中：`X1 1脚 2脚 3脚 4脚 5脚 6脚 7脚 8脚 芯片名`，请严格按照位置对应到上述物理引脚号！

2. **【最重要】每个元器件的所有物理引脚都必须出现在 JSON 中，绝不允许漏写！**
   - 电阻 R、电容 C、二极管 D 都有 2 个引脚（1, 2），两个都必须出现！
   - **开关/保险丝/端子**：即使在 SPICE 中用 0.001 欧姆代替了，也必须映射回真实器件的 2 个引脚（1, 2）。
   - **变压器 (T/Transformer)**：必须有 4 个引脚。1, 2 脚为初级网络；3, 4 脚为次级网络（接整流桥的 AC 输入端）。
   - **贴片稳压器 (U/MC78L05_SO8等 8 脚 IC)**：引脚 8=IN，引脚 1=OUT。引脚 2, 3, 6, 7 全部为 GND，**你必须把 2, 3, 6, 7 这四个引脚全部加入到 0(GND) 网络中**，绝不能让它们悬空！

3. **网络必须至少有 2 个引脚**

4. **【运放防短路绝对禁令】（必须严格遵守）**：
   - 对于运放类器件，绝对禁止将 2号(IN-) 和 3号(IN+) 引脚连在同一个网络里！
   - 绝对禁止将 1号(OUT)、2号(IN-) 或 3号(IN+) 接入 GND 或 0 网络！

【输出格式】
```json
{
  "nets": {
    "网络名": ["UID:引脚号", "UID:引脚号"]
  }
}
```

【示例】SPICE 代码 `R1 N1 N2 10k` 表示 R1 的引脚1接N1，引脚2接N2。
翻译为：
- N1 网络包含 "R1:1"
- N2 网络包含 "R1:2"
R1 的两个引脚都出现了！"""

        user_prompt = f"【已验证通过的 SPICE 网表】:\n{spice_code}\n\n{comp_context}\n\n请严格基于上述法则，输出完美的 JSON："

        kwargs = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1
        }
        if THINKING_ENABLED:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        elif EXPLICIT_DISABLE_THINKING:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = self.client.chat.completions.create(**kwargs)

        # 提取干净的 JSON
        raw_output = response.choices[0].message.content
        print(f"   [调试] LLM 返回内容长度: {len(raw_output)} 字符")

        match = re.search(r'```json\s*(.*?)\s*```', raw_output, flags=re.DOTALL | re.IGNORECASE)
        if match:
            clean_json = match.group(1).strip()
        else:
            start_idx = raw_output.find('{')
            end_idx = raw_output.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                clean_json = raw_output[start_idx:end_idx]
            else:
                print(f"   [错误] 无法从 LLM 输出中提取 JSON")
                clean_json = "{}"

        try:
            data = json.loads(clean_json)
        except json.JSONDecodeError as e:
            print(f"   [错误] JSON 解析失败: {e}")
            data = {"nets": {}}

        # 多格式兼容性处理
        if isinstance(data, list):
            merged_nets = {}
            for item in data:
                if isinstance(item, dict):
                    if "nets" in item:
                        merged_nets.update(item["nets"])
                    else:
                        merged_nets.update(item)
            data = {"nets": merged_nets}

        if "nets" in data and isinstance(data["nets"], list):
            converted_nets = {}
            for item in data["nets"]:
                if isinstance(item, dict):
                    net_name = item.get("name") or item.get("net_name")
                    pins = item.get("connections") or item.get("pins") or item.get("pins_list")
                    if net_name and isinstance(pins, list):
                        converted_nets[net_name] = pins
            data["nets"] = converted_nets

        elif "nets" not in data:
            if all(isinstance(v, list) for v in data.values() if v is not None):
                data = {"nets": data}

        print(f"   解析到 {len(data.get('nets', {}))} 个网络")

        # 构建 UID 映射表
        uid_mapping = {}
        for valid_uid in valid_uids:
            uid_mapping[valid_uid.upper()] = valid_uid
            # 处理运放 UID: U1 -> XU1 和 X1 映射
            if valid_uid.upper().startswith('U'):
                # U1 -> XU1 (SPICE 子电路调用格式)
                xu_equiv = 'X' + valid_uid
                uid_mapping[xu_equiv.upper()] = valid_uid
                # U1 -> X1 (旧格式兼容)
                x_equiv = 'X' + valid_uid[1:]
                uid_mapping[x_equiv.upper()] = valid_uid
            # 处理 LED UID: LED1 -> D1 映射
            if valid_uid.upper().startswith('LED'):
                # LED1 -> D1
                d_equiv = 'D' + valid_uid[3:]
                uid_mapping[d_equiv.upper()] = valid_uid
                # LED1 -> DLED1
                uid_mapping['D' + valid_uid.upper()] = valid_uid
            # 处理 BJT UID: Q1 在 SPICE 中就是 Q1，但也可能被写成 M1（MOSFET 格式）
            if valid_uid.upper().startswith('Q'):
                uid_mapping[valid_uid.upper()] = valid_uid
            uid_mapping[valid_uid] = valid_uid

        # Python 级别强制清洗
        sanitized_nets = {}
        total_pins = 0
        dropped_pins = 0
        used_pins = set()

        for net_name, pins in data.get("nets", {}).items():
            if not isinstance(pins, list):
                continue

            clean_pins = []
            for pin in pins:
                total_pins += 1
                if not isinstance(pin, str):
                    dropped_pins += 1
                    continue

                pin_clean = pin.strip()
                pin_clean = re.sub(r'[.\-()]', ':', pin_clean)

                if ':' in pin_clean:
                    uid_raw = pin_clean.split(':')[0]
                    pin_num = pin_clean.split(':')[1]

                    matched_uid = uid_mapping.get(uid_raw.upper())
                    normalized_pin = f"{matched_uid}:{pin_num}" if matched_uid else None

                    if matched_uid:
                        if normalized_pin in used_pins:
                            dropped_pins += 1
                            continue
                        clean_pins.append(normalized_pin)
                        used_pins.add(normalized_pin)
                    else:
                        dropped_pins += 1
                else:
                    dropped_pins += 1

            if clean_pins:
                sanitized_nets[net_name] = clean_pins
                print(f"   网络 '{net_name}': {len(clean_pins)} 个有效引脚")

        # 运放防短路硬拦截护盾
        for uid in valid_uids:
            if "LM2904" in retrieved_data.get(uid, {}).get("lib_id", "").upper():
                for gnd_net in ['GND', '0', '0V', 'VSS']:
                    if gnd_net in sanitized_nets:
                        sanitized_nets[gnd_net] = [p for p in sanitized_nets[gnd_net]
                                                   if p not in [f"{uid}:1", f"{uid}:2", f"{uid}:3"]]

                for net_name, pins in sanitized_nets.items():
                    if f"{uid}:2" in pins and f"{uid}:3" in pins:
                        pins.remove(f"{uid}:2")
                        print(f"   [护盾触发] 已强制解绑 {uid} 的 2脚和3脚，防止输入端短路！")

        # --- 🛡️ 双引脚无源器件漏引脚兜底机制 ---
        # 强行从原始 SPICE 代码中找回被 LLM 幻觉吃掉的引脚
        for uid in valid_uids:
            # 支持 R1, R2, Ri, Rf, R_load, C_in, C_out 等多种格式
            if re.match(r'^[RCDL][A-Za-z0-9_]*$', uid, re.IGNORECASE):
                pin1_found = any(f"{uid}:1" in nets for nets in sanitized_nets.values())
                pin2_found = any(f"{uid}:2" in nets for nets in sanitized_nets.values())

                if not pin1_found or not pin2_found:
                    match = re.search(rf'^{uid}\s+(\S+)\s+(\S+)', spice_code, re.IGNORECASE | re.MULTILINE)
                    if match:
                        node1, node2 = match.group(1), match.group(2)
                        if not pin1_found:
                            if node1 not in sanitized_nets: sanitized_nets[node1] = []
                            sanitized_nets[node1].append(f"{uid}:1")
                            used_pins.add(f"{uid}:1")  # 🔧 关键修复：更新 used_pins
                            print(f"   [兜底修复] 强行将漏掉的 {uid}:1 补回到网络 {node1}")
                        if not pin2_found:
                            if node2 not in sanitized_nets: sanitized_nets[node2] = []
                            sanitized_nets[node2].append(f"{uid}:2")
                            used_pins.add(f"{uid}:2")  # 🔧 关键修复：更新 used_pins
                            print(f"   [兜底修复] 强行将漏掉的 {uid}:2 补回到网络 {node2}")

        # 引脚连接验证
        print(f"\n   [引脚验证] 检查每个元器件的引脚完整性...")

        component_pins = {}
        for uid, info in retrieved_data.items():
            if not info:
                continue
            pins = info.get('pins', [])
            component_pins[uid] = {p.get('num') for p in pins if p.get('num')}

        unconnected_pins = []
        for uid in valid_uids:
            expected_pins = component_pins.get(uid, set())
            connected_pins = set()
            for pin in used_pins:
                if pin.startswith(f"{uid}:"):
                    connected_pins.add(pin.split(':')[1])

            missing_pins = expected_pins - connected_pins
            if missing_pins:
                for pin_num in missing_pins:
                    unconnected_pins.append(f"{uid}:{pin_num}")
                print(f"   {uid} 有未连接引脚: {missing_pins}")

        # 移除完全未使用的元器件
        used_uids = set()
        for pin in used_pins:
            uid = pin.split(':')[0]
            used_uids.add(uid)

        unused_uids = set(valid_uids) - used_uids
        if unused_uids:
            print(f"\n   移除未使用的元器件: {unused_uids}")
            valid_uids = [uid for uid in valid_uids if uid in used_uids]

        # 处理单引脚网络
        single_pin_nets = [name for name, pins in sanitized_nets.items() if len(pins) < 2]
        power_nodes = {'VCC', 'VEE', 'VIN', 'IN', 'OUT', 'VDD', 'VSS', 'AVCC', 'DVCC', 'N_IN', 'N_OUT', 'INPUT', 'OUTPUT'}
        ground_nodes = {'0', 'GND', 'AGND', 'DGND', 'GND_PWR'}

        if single_pin_nets:
            print(f"   发现 {len(single_pin_nets)} 个单引脚网络: {single_pin_nets}")

            for net_name in single_pin_nets[:]:
                pins = sanitized_nets[net_name]

                if net_name.upper() in [n.upper() for n in power_nodes]:
                    continue

                if net_name.upper() in [n.upper() for n in ground_nodes]:
                    continue

                del sanitized_nets[net_name]

        # 智能接地处理
        print(f"\n   [智能接地] 处理未使用的引脚...")

        pin_type_map = {}
        for uid, info in retrieved_data.items():
            if not info:
                continue
            pin_type_map[uid] = {}
            for p in info.get('pins', []):
                p_num = p.get('num')
                p_type = p.get('type', 'passive').lower()
                pin_type_map[uid][p_num] = p_type

        input_pin_types = {'input', 'in', 'in+', 'in-', 'non-inverting', 'inverting',
                          'clk', 'data', 'enable', 'reset', 'set'}

        auto_ground_pins = []

        for uid in valid_uids:
            expected_pins = component_pins.get(uid, set())
            connected_pins = set()
            for pin in used_pins:
                if pin.startswith(f"{uid}:"):
                    connected_pins.add(pin.split(':')[1])

            missing_pins = expected_pins - connected_pins

            if not missing_pins:
                continue

            lib_id = retrieved_data.get(uid, {}).get('lib_id', '').upper()

            if 'LM2904' in lib_id or 'LM358' in lib_id or 'OPA' in lib_id or 'OPAMP' in lib_id:
                opamp_a_pins = {'1', '2', '3'}
                opamp_a_used = bool(connected_pins & opamp_a_pins)

                opamp_b_pins = {'5', '6', '7'}
                opamp_b_used = bool(connected_pins & opamp_b_pins)

                if opamp_a_used and not opamp_b_used:
                    for pin_num in ['5', '6']:
                        if pin_num in missing_pins:
                            auto_ground_pins.append(f"{uid}:{pin_num}")
                            print(f"      {uid} 引脚 {pin_num} (未使用运放B输入) -> 自动接地")

                elif opamp_b_used and not opamp_a_used:
                    for pin_num in ['2', '3']:
                        if pin_num in missing_pins:
                            auto_ground_pins.append(f"{uid}:{pin_num}")
                            print(f"      {uid} 引脚 {pin_num} (未使用运放A输入) -> 自动接地")

            else:
                for pin_num in missing_pins:
                    pin_type = pin_type_map.get(uid, {}).get(pin_num, 'passive').lower()
                    if pin_type in input_pin_types or 'input' in pin_type:
                        auto_ground_pins.append(f"{uid}:{pin_num}")
                        print(f"      {uid} 引脚 {pin_num} (类型: {pin_type}) -> 自动接地")

        if auto_ground_pins:
            if 'GND' not in sanitized_nets:
                sanitized_nets['GND'] = []
            sanitized_nets['GND'].extend(auto_ground_pins)
            print(f"\n   已将 {len(auto_ground_pins)} 个未使用输入引脚自动接地")

        data["nets"] = sanitized_nets
        data["components"] = [{"uid": uid} for uid in valid_uids]

        # 保存更新后的 retrieved_data
        updated_retrieved_path = output_path.replace('.json', '_updated_retrieved.json')
        with open(updated_retrieved_path, 'w', encoding='utf-8') as f:
            json.dump(retrieved_data, f, indent=2, ensure_ascii=False)
        print(f"      已保存更新后的元件数据: {updated_retrieved_path}")

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        print(f"\n   [网表翻译完成]")
        print(f"      - 有效网络数: {len(sanitized_nets)}")
        print(f"      - 总引脚数: {total_pins}, 丢弃: {dropped_pins}")
        print(f"      - 元器件数: {len(valid_uids)}")
        print(f"      - 自动接地引脚: {len(auto_ground_pins)}")
        print(f"      - 输出文件: {output_path}")

        return output_path
