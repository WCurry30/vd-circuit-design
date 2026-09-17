"""
\u901a\u7528\u7f51\u8868\u751f\u6210\u5f15\u64ce

\u6838\u5fc3\u5f15\u64ce，\u8d1f\u8d23\u8c03\u7528 LLM \u751f\u6210 SPICE \u7f51\u8868。
\u5177\u4f53\u7684 Prompt \u548c\u6e05\u6d17\u903b\u8f91\u59d4\u6258\u7ed9\u4e13\u5bb6\u6a21\u5757\u5904\u7406。
"""

import os
import json
import re
from typing import Any, Optional
from openai import OpenAI
from spice_contract import component_bindings, clean_preserving_definitions, extract_spice_deck

# ================= \u914d\u7f6e\u533a\u57df =================
API_KEY = (
    os.environ.get("EDA_API_KEY")
    or os.environ.get("SILICONFLOW_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or ""
)
BASE_URL = os.environ.get("EDA_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = os.environ.get("EDA_MODEL_NAME", "model-not-configured")
THINKING_ENABLED = False
EXPLICIT_DISABLE_THINKING = False
# ===========================================


class NetlistEngine:
    """\u901a\u7528\u7f51\u8868\u751f\u6210\u5f15\u64ce"""

    cleanup_enabled = True

    def __init__(self):
        self.client = OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
            timeout=float(os.environ.get("EDA_API_TIMEOUT", "90")),
            max_retries=int(os.environ.get("EDA_API_MAX_RETRIES", "1")),
        )
        self.last_usage = {}
        self.last_request = None
        self.last_response = None

    def generate_spice(
        self,
        plan_data: dict,
        expert: Any,
        iteration: int = 1,
        previous_spice: Optional[str] = None,
        feedback: Optional[str] = None,
        retrieved_path: Optional[str] = None,
        temperature: float = 0.1,
        seed: Optional[int] = None,
    ) -> str:
        """
        \u4f7f\u7528\u4e13\u5bb6\u6a21\u5757\u751f\u6210 SPICE \u7f51\u8868

        Args:
            plan_data: \u89c4\u5212\u6570\u636e（\u5305\u542b components, elaborated_requirement \u7b49）
            expert: \u7535\u8def\u4e13\u5bb6\u5b9e\u4f8b
            iteration: \u5f53\u524d\u8fed\u4ee3\u6b21\u6570
            previous_spice: \u4e0a\u4e00\u8f6e\u7684 SPICE \u4ee3\u7801
            feedback: \u4e0a\u4e00\u8f6e\u7684\u4eff\u771f\u53cd\u9988
            retrieved_path: \u68c0\u7d22\u7ed3\u679c\u6587\u4ef6\u8def\u5f84（\u7528\u4e8e\u83b7\u53d6\u5b9e\u9645\u578b\u53f7）

        Returns:
            str: \u751f\u6210\u7684 SPICE \u4ee3\u7801
        """
        self.last_response = None
        self.last_usage = {}
        elaborated_req = plan_data.get("elaborated_requirement", "")

        # \u63d0\u53d6\u5143\u5668\u4ef6 UID \u5217\u8868\u548c\u578b\u53f7\u6620\u5c04
        components = plan_data.get("components", [])
        uid_list = [comp.get("uid") for comp in components if comp.get("uid")]

        # \u6784\u5efa uid_hint，\u5305\u542b\u578b\u53f7\u4fe1\u606f
        uid_model_map = {}
        retrieved_data = {}
        if retrieved_path and os.path.exists(retrieved_path):
            try:
                with open(retrieved_path, 'r', encoding='utf-8') as f:
                    retrieved_data = json.load(f)
                for uid, info in retrieved_data.items():
                    if info and 'lib_id' in info:
                        uid_model_map[uid] = info['lib_id']
            except Exception as e:
                print(f"   [\u8b66\u544a] \u65e0\u6cd5\u8bfb\u53d6\u68c0\u7d22\u7ed3\u679c: {e}")

        # \u683c\u5f0f\u5316 uid_hint，\u5305\u542b\u578b\u53f7\u4fe1\u606f
        self.last_component_bindings = component_bindings(components, retrieved_data)
        uid_hint_parts = []
        for binding in self.last_component_bindings:
            reference = binding['spice_reference']
            if reference:
                library_id = binding['library_id']
                uid_hint_parts.append(f"{reference}({library_id})" if library_id else reference)
        uid_hint = "、".join(uid_hint_parts)

        # \u4ece\u4e13\u5bb6\u83b7\u53d6 Prompt
        system_prompt, user_prompt = expert.get_netlist_prompts(
            elaborated_req, uid_hint, iteration, previous_spice, feedback
        )
        system_prompt += (
            '\nDesign authority: the original user requirement and public interface '
            'are constraints. Planner elaboration and proposed component values are '
            'unverified design suggestions. Resolve conflicts in favor of the original '
            'requirement, physical circuit equations and measured feedback. You may '
            'omit optional planner-added parts or revise their values/connections when '
            'needed; preserve component identifiers for parts retained. Do not omit '
            'components or topology explicitly required by the original request.'
            ' The planner BOM is not an exhaustive component-count constraint. '
            'You may add supporting passive components needed for bias, DC return, '
            'coupling or decoupling, using unique SPICE identifiers. Planner-only '
            'prohibitions on additional parts are not requirements. Respect any '
            'component counts and topology restrictions explicitly stated in the '
            'original request; do not add active stages to evade them.'
        )
        system_prompt += ('\nShared execution contract, overriding template model assumptions:\n'
                          + plan_data['model_contract']) if plan_data.get('model_contract') else (
            "\nThe explicit user requirement determines the circuit topology. "
            "Library identifiers describe physical symbols, not executable SPICE models. "
            "Use valid SPICE device prefixes and include all required device model "
            "and subcircuit definitions in the deck; no external include files. "
            "This self-contained model requirement supersedes any template assumption "
            "that device models are injected by another simulator."
        )
        user_prompt += "\nPhysical-to-SPICE bindings:\n" + json.dumps(
            self.last_component_bindings, ensure_ascii=False
        )

        # \u8c03\u7528 LLM \u751f\u6210
        kwargs = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }
        if seed is not None:
            kwargs["seed"] = seed
        if THINKING_ENABLED:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        elif EXPLICIT_DISABLE_THINKING:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        self.last_request = kwargs
        if getattr(self, 'sizing_enabled', False):
            from sizing_conversation import generate_with_sizing
            response = generate_with_sizing(self.client.chat.completions.create, kwargs,
                                           remaining_calls=self.remaining_calls,
                                           events=self.sizing_events)
        else:
            response = self.client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content
        self.last_response = raw
        usage = getattr(response, "usage", None)
        def _usage_value(key: str):
            if isinstance(usage, dict):
                return usage.get(key)
            return getattr(usage, key, None)

        self.last_usage = {
            key: _usage_value(key)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if _usage_value(key) is not None
        }
        self.last_usage["response_model_id"] = str(getattr(response, "model", ""))

        # \u63d0\u53d6 SPICE \u4ee3\u7801\u5757
        spice_code = extract_spice_deck(raw)

        if not self.cleanup_enabled:
            return spice_code

        # \u8c03\u7528\u4e13\u5bb6\u7684\u4e13\u6709\u6e05\u6d17\u903b\u8f91
        spice_code = clean_preserving_definitions(spice_code, expert.clean_spice_code)

        # --- 🛡️ \u6846\u67b6\u7ea7\u5168\u5c40\u9632\u5f39\u62a4\u76fe：\u81ea\u52a8\u4fee\u590d\u91cd\u590d\u7684\u5143\u4ef6\u540d ---
        cleaned_spice_lines = []
        seen_components = set()
        component_scopes = []
        for line in spice_code.split('\n'):
            line_strip = line.strip()
            if re.match(r'^\.subckt\b', line_strip, re.IGNORECASE):
                component_scopes.append(seen_components)
                seen_components = set()
            elif re.match(r'^\.ends\b', line_strip, re.IGNORECASE):
                if not component_scopes:
                    raise ValueError('unmatched subcircuit end')
                seen_components = component_scopes.pop()
            if not line_strip or line_strip.startswith(('*', '.', '+')):
                cleaned_spice_lines.append(line)
                continue
            
            parts = line_strip.split()
            if not parts:
                cleaned_spice_lines.append(line)
                continue
            
            comp_name = parts[0].upper()
            if comp_name in seen_components:
                # \u53d1\u73b0\u91cd\u590d\u7684\u5143\u4ef6\u540d，\u81ea\u52a8\u52a0\u540e\u7f00\u91cd\u547d\u540d
                new_name = f"{comp_name}_DUP{len(seen_components)}"
                print(f"   [\u5168\u5c40\u62a4\u76fe] \u62e6\u622a\u5230 LLM \u5e7b\u89c9：\u91cd\u590d\u5143\u4ef6\u540d {comp_name}，\u5df2\u81ea\u52a8\u91cd\u547d\u540d\u4e3a {new_name}")
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
        \u5c06 SPICE \u7f51\u8868\u7ffb\u8bd1\u4e3a\u753b\u56fe\u5f15\u64ce\u6240\u9700\u7684 JSON \u683c\u5f0f

        \u8fd9\u662f\u901a\u7528\u903b\u8f91，\u4e0d\u4f9d\u8d56\u4e13\u5bb6\u6a21\u5757。
        \u4ece netlist_generator.py \u7b2c145-522\u884c\u8fc1\u79fb。
        """
        print("\n[\u7ffb\u8bd1] \u6b63\u5728\u5c06\u4f18\u5316\u540e\u7684 SPICE \u7f51\u8868\u7ffb\u8bd1\u4e3a\u753b\u56fe\u5f15\u64ce\u6240\u9700\u7684 JSON \u683c\u5f0f...")
        with open(retrieved_path, 'r', encoding='utf-8') as f:
            retrieved_data = json.load(f)

        # \u8fc7\u6ee4\u6389\u68c0\u7d22\u5931\u8d25\u7684\u5143\u4ef6（\u503c\u4e3a None \u7684\u6761\u76ee）
        valid_uids = [uid for uid, info in retrieved_data.items() if info is not None]
        print(f"   \u68c0\u7d22\u5230 {len(valid_uids)} \u4e2a\u6709\u6548\u5143\u5668\u4ef6: {valid_uids}")

        # \u4ece SPICE \u4ee3\u7801\u4e2d\u63d0\u53d6\u4f18\u5316\u540e\u7684\u5143\u4ef6\u503c
        print(f"   \u6b63\u5728\u4ece SPICE \u4ee3\u7801\u63d0\u53d6\u4f18\u5316\u540e\u7684\u5143\u4ef6\u503c...")
        optimized_values = {}

        for line in spice_code.split('\n'):
            line = line.strip()
            # \u5339\u914d\u7535\u963b：Rxxx node1 node2 value（\u652f\u6301 R1, R2, Ri, Rf, R_load \u7b49\u683c\u5f0f）
            r_match = re.match(r'^(R[A-Za-z0-9_]*)\s+\S+\s+\S+\s+([\d.]+[kKmMuUnNpPgGtT]?)', line, re.IGNORECASE)
            if r_match:
                uid = r_match.group(1).upper()
                value = r_match.group(2)
                optimized_values[uid] = value
                print(f"      \u63d0\u53d6 {uid} = {value}")
                continue

            # \u5339\u914d\u7535\u5bb9：Cxxx node1 node2 value（\u652f\u6301 C1, C_in, C_out \u7b49\u683c\u5f0f）
            c_match = re.match(r'^(C[A-Za-z0-9_]*)\s+\S+\s+\S+\s+([\d.]+[kKmMuUnNpPgGtT]?F?)', line, re.IGNORECASE)
            if c_match:
                uid = c_match.group(1).upper()
                value = c_match.group(2)
                value = re.sub(r'F$', '', value, flags=re.IGNORECASE)
                optimized_values[uid] = value
                print(f"      \u63d0\u53d6 {uid} = {value}")
                continue

        # \u66f4\u65b0 retrieved_data \u4e2d\u7684\u5143\u4ef6\u503c
        for uid in valid_uids:
            if uid.upper() in optimized_values:
                new_value = optimized_values[uid.upper()]
                if uid in retrieved_data and retrieved_data[uid]:
                    old_value = retrieved_data[uid].get('planned_value', '')
                    if old_value != new_value:
                        print(f"      \u66f4\u65b0 {uid}: {old_value} -> {new_value}")
                        retrieved_data[uid]['planned_value'] = new_value

        # \u52a8\u6001\u7ec4\u88c5"\u5143\u4ef6\u5f15\u811a\u8bf4\u660e\u4e66"
        comp_context = "## \u7cfb\u7edf\u5f53\u524d\u52a0\u8f7d\u7684\u7269\u7406\u5143\u5668\u4ef6\u4e0e\u53ef\u7528\u5f15\u811a\u6e05\u5355 (\u52a8\u6001 Datasheet)\n"
        for uid, info in retrieved_data.items():
            if not info:
                continue
            lib_id = info.get('lib_id', 'Unknown')
            pin_desc = []
            for p in info.get('pins', []):
                p_num = p.get('num')
                p_type = p.get('type', 'passive')
                pin_desc.append(f"\u5f15\u811a{p_num}({p_type})")
            comp_context += f"- UID: `{uid}` (\u578b\u53f7: {lib_id}) | \u62e5\u6709\u53ef\u7528\u7269\u7406\u5f15\u811a: [{', '.join(pin_desc)}]\n"

        # \u4e07\u80fd\u8de8\u57df\u6620\u5c04\u6cd5\u5219
        system_prompt = """\u4f60\u662f\u4e00\u4e2a\u9876\u7ea7\u7684\u786c\u4ef6\u7ffb\u8bd1\u5f15\u64ce。\u4f60\u7684\u4efb\u52a1\u662f\u5c06 SPICE \u7f51\u8868\u7ffb\u8bd1\u4e3a\u6211\u81ea\u5b9a\u4e49\u7684 JSON \u683c\u5f0f。

【\u5173\u952e\u89c4\u5219】

1. **\u5e38\u89c1\u82af\u7247\u5f15\u811a\u6620\u5c04**：
   - **LM2904/LM358**: \u5f15\u811a 3(IN+), 2(IN-), 8(V+), 4(V-/GND), 1(OUT)
   - **NE555**: \u5f15\u811a 1(GND), 2(TR), 3(OUT), 4(RST), 5(CV), 6(THR), 7(DIS), 8(VCC)
   \u5728 SPICE \u4e2d：`X1 1\u811a 2\u811a 3\u811a 4\u811a 5\u811a 6\u811a 7\u811a 8\u811a \u82af\u7247\u540d`，\u8bf7\u4e25\u683c\u6309\u7167\u4f4d\u7f6e\u5bf9\u5e94\u5230\u4e0a\u8ff0\u7269\u7406\u5f15\u811a\u53f7！

2. **【\u6700\u91cd\u8981】\u6bcf\u4e2a\u5143\u5668\u4ef6\u7684\u6240\u6709\u7269\u7406\u5f15\u811a\u90fd\u5fc5\u987b\u51fa\u73b0\u5728 JSON \u4e2d，\u7edd\u4e0d\u5141\u8bb8\u6f0f\u5199！**
   - \u7535\u963b R、\u7535\u5bb9 C、\u4e8c\u6781\u7ba1 D \u90fd\u6709 2 \u4e2a\u5f15\u811a（1, 2），\u4e24\u4e2a\u90fd\u5fc5\u987b\u51fa\u73b0！
   - **\u5f00\u5173/\u4fdd\u9669\u4e1d/\u7aef\u5b50**：\u5373\u4f7f\u5728 SPICE \u4e2d\u7528 0.001 \u6b27\u59c6\u4ee3\u66ff\u4e86，\u4e5f\u5fc5\u987b\u6620\u5c04\u56de\u771f\u5b9e\u5668\u4ef6\u7684 2 \u4e2a\u5f15\u811a（1, 2）。
   - **\u53d8\u538b\u5668 (T/Transformer)**：\u5fc5\u987b\u6709 4 \u4e2a\u5f15\u811a。1, 2 \u811a\u4e3a\u521d\u7ea7\u7f51\u7edc；3, 4 \u811a\u4e3a\u6b21\u7ea7\u7f51\u7edc（\u63a5\u6574\u6d41\u6865\u7684 AC \u8f93\u5165\u7aef）。
   - **\u8d34\u7247\u7a33\u538b\u5668 (U/MC78L05_SO8\u7b49 8 \u811a IC)**：\u5f15\u811a 8=IN，\u5f15\u811a 1=OUT。\u5f15\u811a 2, 3, 6, 7 \u5168\u90e8\u4e3a GND，**\u4f60\u5fc5\u987b\u628a 2, 3, 6, 7 \u8fd9\u56db\u4e2a\u5f15\u811a\u5168\u90e8\u52a0\u5165\u5230 0(GND) \u7f51\u7edc\u4e2d**，\u7edd\u4e0d\u80fd\u8ba9\u5b83\u4eec\u60ac\u7a7a！

3. **\u7f51\u7edc\u5fc5\u987b\u81f3\u5c11\u6709 2 \u4e2a\u5f15\u811a**

4. **【\u8fd0\u653e\u9632\u77ed\u8def\u7edd\u5bf9\u7981\u4ee4】（\u5fc5\u987b\u4e25\u683c\u9075\u5b88）**：
   - \u5bf9\u4e8e\u8fd0\u653e\u7c7b\u5668\u4ef6，\u7edd\u5bf9\u7981\u6b62\u5c06 2\u53f7(IN-) \u548c 3\u53f7(IN+) \u5f15\u811a\u8fde\u5728\u540c\u4e00\u4e2a\u7f51\u7edc\u91cc！
   - \u7edd\u5bf9\u7981\u6b62\u5c06 1\u53f7(OUT)、2\u53f7(IN-) \u6216 3\u53f7(IN+) \u63a5\u5165 GND \u6216 0 \u7f51\u7edc！

【\u8f93\u51fa\u683c\u5f0f】
```json
{
  "nets": {
    "\u7f51\u7edc\u540d": ["UID:\u5f15\u811a\u53f7", "UID:\u5f15\u811a\u53f7"]
  }
}
```

【\u793a\u4f8b】SPICE \u4ee3\u7801 `R1 N1 N2 10k` \u8868\u793a R1 \u7684\u5f15\u811a1\u63a5N1，\u5f15\u811a2\u63a5N2。
\u7ffb\u8bd1\u4e3a：
- N1 \u7f51\u7edc\u5305\u542b "R1:1"
- N2 \u7f51\u7edc\u5305\u542b "R1:2"
R1 \u7684\u4e24\u4e2a\u5f15\u811a\u90fd\u51fa\u73b0\u4e86！"""

        user_prompt = f"【\u5df2\u9a8c\u8bc1\u901a\u8fc7\u7684 SPICE \u7f51\u8868】:\n{spice_code}\n\n{comp_context}\n\n\u8bf7\u4e25\u683c\u57fa\u4e8e\u4e0a\u8ff0\u6cd5\u5219，\u8f93\u51fa\u5b8c\u7f8e\u7684 JSON："

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

        # \u63d0\u53d6\u5e72\u51c0\u7684 JSON
        raw_output = response.choices[0].message.content
        print(f"   [\u8c03\u8bd5] LLM \u8fd4\u56de\u5185\u5bb9\u957f\u5ea6: {len(raw_output)} \u5b57\u7b26")

        match = re.search(r'```json\s*(.*?)\s*```', raw_output, flags=re.DOTALL | re.IGNORECASE)
        if match:
            clean_json = match.group(1).strip()
        else:
            start_idx = raw_output.find('{')
            end_idx = raw_output.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                clean_json = raw_output[start_idx:end_idx]
            else:
                print(f"   [\u9519\u8bef] \u65e0\u6cd5\u4ece LLM \u8f93\u51fa\u4e2d\u63d0\u53d6 JSON")
                clean_json = "{}"

        try:
            data = json.loads(clean_json)
        except json.JSONDecodeError as e:
            print(f"   [\u9519\u8bef] JSON \u89e3\u6790\u5931\u8d25: {e}")
            data = {"nets": {}}

        # \u591a\u683c\u5f0f\u517c\u5bb9\u6027\u5904\u7406
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

        print(f"   \u89e3\u6790\u5230 {len(data.get('nets', {}))} \u4e2a\u7f51\u7edc")

        # \u6784\u5efa UID \u6620\u5c04\u8868
        uid_mapping = {}
        for valid_uid in valid_uids:
            uid_mapping[valid_uid.upper()] = valid_uid
            # \u5904\u7406\u8fd0\u653e UID: U1 -> XU1 \u548c X1 \u6620\u5c04
            if valid_uid.upper().startswith('U'):
                # U1 -> XU1 (SPICE \u5b50\u7535\u8def\u8c03\u7528\u683c\u5f0f)
                xu_equiv = 'X' + valid_uid
                uid_mapping[xu_equiv.upper()] = valid_uid
                # U1 -> X1 (\u65e7\u683c\u5f0f\u517c\u5bb9)
                x_equiv = 'X' + valid_uid[1:]
                uid_mapping[x_equiv.upper()] = valid_uid
            # \u5904\u7406 LED UID: LED1 -> D1 \u6620\u5c04
            if valid_uid.upper().startswith('LED'):
                # LED1 -> D1
                d_equiv = 'D' + valid_uid[3:]
                uid_mapping[d_equiv.upper()] = valid_uid
                # LED1 -> DLED1
                uid_mapping['D' + valid_uid.upper()] = valid_uid
            # \u5904\u7406 BJT UID: Q1 \u5728 SPICE \u4e2d\u5c31\u662f Q1，\u4f46\u4e5f\u53ef\u80fd\u88ab\u5199\u6210 M1（MOSFET \u683c\u5f0f）
            if valid_uid.upper().startswith('Q'):
                uid_mapping[valid_uid.upper()] = valid_uid
            uid_mapping[valid_uid] = valid_uid

        # Python \u7ea7\u522b\u5f3a\u5236\u6e05\u6d17
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
                print(f"   \u7f51\u7edc '{net_name}': {len(clean_pins)} \u4e2a\u6709\u6548\u5f15\u811a")

        # \u8fd0\u653e\u9632\u77ed\u8def\u786c\u62e6\u622a\u62a4\u76fe
        for uid in valid_uids:
            if "LM2904" in retrieved_data.get(uid, {}).get("lib_id", "").upper():
                for gnd_net in ['GND', '0', '0V', 'VSS']:
                    if gnd_net in sanitized_nets:
                        sanitized_nets[gnd_net] = [p for p in sanitized_nets[gnd_net]
                                                   if p not in [f"{uid}:1", f"{uid}:2", f"{uid}:3"]]

                for net_name, pins in sanitized_nets.items():
                    if f"{uid}:2" in pins and f"{uid}:3" in pins:
                        pins.remove(f"{uid}:2")
                        print(f"   [\u62a4\u76fe\u89e6\u53d1] \u5df2\u5f3a\u5236\u89e3\u7ed1 {uid} \u7684 2\u811a\u548c3\u811a，\u9632\u6b62\u8f93\u5165\u7aef\u77ed\u8def！")

        # --- 🛡️ \u53cc\u5f15\u811a\u65e0\u6e90\u5668\u4ef6\u6f0f\u5f15\u811a\u515c\u5e95\u673a\u5236 ---
        # \u5f3a\u884c\u4ece\u539f\u59cb SPICE \u4ee3\u7801\u4e2d\u627e\u56de\u88ab LLM \u5e7b\u89c9\u5403\u6389\u7684\u5f15\u811a
        for uid in valid_uids:
            # \u652f\u6301 R1, R2, Ri, Rf, R_load, C_in, C_out \u7b49\u591a\u79cd\u683c\u5f0f
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
                            used_pins.add(f"{uid}:1")  # 🔧 \u5173\u952e\u4fee\u590d：\u66f4\u65b0 used_pins
                            print(f"   [\u515c\u5e95\u4fee\u590d] \u5f3a\u884c\u5c06\u6f0f\u6389\u7684 {uid}:1 \u8865\u56de\u5230\u7f51\u7edc {node1}")
                        if not pin2_found:
                            if node2 not in sanitized_nets: sanitized_nets[node2] = []
                            sanitized_nets[node2].append(f"{uid}:2")
                            used_pins.add(f"{uid}:2")  # 🔧 \u5173\u952e\u4fee\u590d：\u66f4\u65b0 used_pins
                            print(f"   [\u515c\u5e95\u4fee\u590d] \u5f3a\u884c\u5c06\u6f0f\u6389\u7684 {uid}:2 \u8865\u56de\u5230\u7f51\u7edc {node2}")

        # \u5f15\u811a\u8fde\u63a5\u9a8c\u8bc1
        print(f"\n   [\u5f15\u811a\u9a8c\u8bc1] \u68c0\u67e5\u6bcf\u4e2a\u5143\u5668\u4ef6\u7684\u5f15\u811a\u5b8c\u6574\u6027...")

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
                print(f"   {uid} \u6709\u672a\u8fde\u63a5\u5f15\u811a: {missing_pins}")

        # \u79fb\u9664\u5b8c\u5168\u672a\u4f7f\u7528\u7684\u5143\u5668\u4ef6
        used_uids = set()
        for pin in used_pins:
            uid = pin.split(':')[0]
            used_uids.add(uid)

        unused_uids = set(valid_uids) - used_uids
        if unused_uids:
            print(f"\n   \u79fb\u9664\u672a\u4f7f\u7528\u7684\u5143\u5668\u4ef6: {unused_uids}")
            valid_uids = [uid for uid in valid_uids if uid in used_uids]

        # \u5904\u7406\u5355\u5f15\u811a\u7f51\u7edc
        single_pin_nets = [name for name, pins in sanitized_nets.items() if len(pins) < 2]
        power_nodes = {'VCC', 'VEE', 'VIN', 'IN', 'OUT', 'VDD', 'VSS', 'AVCC', 'DVCC', 'N_IN', 'N_OUT', 'INPUT', 'OUTPUT'}
        ground_nodes = {'0', 'GND', 'AGND', 'DGND', 'GND_PWR'}

        if single_pin_nets:
            print(f"   \u53d1\u73b0 {len(single_pin_nets)} \u4e2a\u5355\u5f15\u811a\u7f51\u7edc: {single_pin_nets}")

            for net_name in single_pin_nets[:]:
                pins = sanitized_nets[net_name]

                if net_name.upper() in [n.upper() for n in power_nodes]:
                    continue

                if net_name.upper() in [n.upper() for n in ground_nodes]:
                    continue

                del sanitized_nets[net_name]

        # \u667a\u80fd\u63a5\u5730\u5904\u7406
        print(f"\n   [\u667a\u80fd\u63a5\u5730] \u5904\u7406\u672a\u4f7f\u7528\u7684\u5f15\u811a...")

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
                            print(f"      {uid} \u5f15\u811a {pin_num} (\u672a\u4f7f\u7528\u8fd0\u653eB\u8f93\u5165) -> \u81ea\u52a8\u63a5\u5730")

                elif opamp_b_used and not opamp_a_used:
                    for pin_num in ['2', '3']:
                        if pin_num in missing_pins:
                            auto_ground_pins.append(f"{uid}:{pin_num}")
                            print(f"      {uid} \u5f15\u811a {pin_num} (\u672a\u4f7f\u7528\u8fd0\u653eA\u8f93\u5165) -> \u81ea\u52a8\u63a5\u5730")

            else:
                for pin_num in missing_pins:
                    pin_type = pin_type_map.get(uid, {}).get(pin_num, 'passive').lower()
                    if pin_type in input_pin_types or 'input' in pin_type:
                        auto_ground_pins.append(f"{uid}:{pin_num}")
                        print(f"      {uid} \u5f15\u811a {pin_num} (\u7c7b\u578b: {pin_type}) -> \u81ea\u52a8\u63a5\u5730")

        if auto_ground_pins:
            if 'GND' not in sanitized_nets:
                sanitized_nets['GND'] = []
            sanitized_nets['GND'].extend(auto_ground_pins)
            print(f"\n   \u5df2\u5c06 {len(auto_ground_pins)} \u4e2a\u672a\u4f7f\u7528\u8f93\u5165\u5f15\u811a\u81ea\u52a8\u63a5\u5730")

        data["nets"] = sanitized_nets
        data["components"] = [{"uid": uid} for uid in valid_uids]

        # \u4fdd\u5b58\u66f4\u65b0\u540e\u7684 retrieved_data
        updated_retrieved_path = output_path.replace('.json', '_updated_retrieved.json')
        with open(updated_retrieved_path, 'w', encoding='utf-8') as f:
            json.dump(retrieved_data, f, indent=2, ensure_ascii=False)
        print(f"      \u5df2\u4fdd\u5b58\u66f4\u65b0\u540e\u7684\u5143\u4ef6\u6570\u636e: {updated_retrieved_path}")

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        print(f"\n   [\u7f51\u8868\u7ffb\u8bd1\u5b8c\u6210]")
        print(f"      - \u6709\u6548\u7f51\u7edc\u6570: {len(sanitized_nets)}")
        print(f"      - \u603b\u5f15\u811a\u6570: {total_pins}, \u4e22\u5f03: {dropped_pins}")
        print(f"      - \u5143\u5668\u4ef6\u6570: {len(valid_uids)}")
        print(f"      - \u81ea\u52a8\u63a5\u5730\u5f15\u811a: {len(auto_ground_pins)}")
        print(f"      - \u8f93\u51fa\u6587\u4ef6: {output_path}")

        return output_path
