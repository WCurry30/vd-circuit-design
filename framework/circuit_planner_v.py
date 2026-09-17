import json
import re
import ast
import os  # \u7528\u4e8e\u5904\u7406\u6587\u4ef6\u8def\u5f84
from typing import List, Dict, Any, Optional
from openai import OpenAI
from sentence_transformers import SentenceTransformer, util

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
DISABLE_THINKING = os.environ.get("EDA_DISABLE_THINKING", "0") == "1"


def _thinking_kwargs() -> Dict[str, Any]:
    return {"extra_body": {"thinking": {"type": "disabled"}}} if DISABLE_THINKING else {}
# ===========================================


class CircuitTypeDetector:
    """
    \u7535\u8def\u7c7b\u578b\u81ea\u52a8\u8bc6\u522b\u5668

    \u4ece ngspice_critic.py \u8fc1\u79fb\u81f3\u6b64，\u7528\u4e8e\u5728\u89c4\u5212\u9636\u6bb5\u8bc6\u522b\u7535\u8def\u7c7b\u578b。
    """

    KEYWORDS = {
        'filter': [
            '\u6ee4\u6ce2', 'filter', '\u622a\u6b62\u9891\u7387', 'cutoff', '\u4f4e\u901a', '\u9ad8\u901a', '\u5e26\u901a', '\u5e26\u963b',
            'sallen', 'butterworth', 'chebyshev', 'rc\u6ee4\u6ce2', 'lc\u6ee4\u6ce2'
        ],
        'audio_amplifier': [
            '\u5bf9\u8bb2\u673a', '\u97f3\u9891\u653e\u5927', 'audio amplifier', '\u529f\u653e', '\u626c\u58f0\u5668', 'speaker',
            '\u9ea6\u514b\u98ce', 'microphone', '\u8bdd\u7b52', '\u97f3\u54cd', '\u97f3\u54cd\u653e\u5927', '\u8bed\u97f3\u653e\u5927',
            '\u8033\u673a\u653e\u5927', '\u97f3\u9891\u529f\u7387', '\u97f3\u9891\u524d\u7f6e', '\u8bdd\u97f3\u653e\u5927'
        ],
        'amplifier': [
            '\u653e\u5927', 'amplifier', '\u589e\u76ca', 'gain', '\u529f\u7387\u653e\u5927', '\u524d\u7f6e\u653e\u5927', 'preamp'
        ],
        'power_supply': [
            '\u7535\u6e90', 'power supply', '\u7a33\u538b', 'regulator', 'ldo', 'dc-dc',
            '\u5f00\u5173\u7535\u6e90', '\u7ebf\u6027\u7535\u6e90', 'buck', 'boost', '\u53d8\u6362\u5668', '\u9002\u914d\u5668',
            '\u5145\u7535', 'charger', '\u7535\u6c60\u4f9b\u7535'
        ],
        'oscillator': [
            '\u632f\u8361', 'oscillator', '\u65f6\u949f', 'clock', '\u6676\u632f', 'crystal',
            '\u65b9\u6ce2', '\u6b63\u5f26\u6ce2', '\u4fe1\u53f7\u53d1\u751f', 'pwm', '555', '\u591a\u8c10\u632f\u8361'
        ],
        'led_blinker': [
            'led', '\u95ea\u70c1', '\u547c\u5438\u706f', '\u8dd1\u9a6c\u706f', '555\u5b9a\u65f6\u5668', '\u591a\u8c10\u632f\u8361',
            'blinker', 'astable', 'led\u63a7\u5236', '\u95ea\u70c1\u706f', '\u6d41\u6c34\u706f', '\u95ea\u706f'
        ],
        'bjt_amplifier': [
            '\u5171\u5c04', '\u4e09\u6781\u7ba1\u653e\u5927', '2n3904', '\u5206\u7acb\u5143\u4ef6\u653e\u5927', '\u5355\u7ba1\u653e\u5927',
            'bjt', 'common emitter', 'ce\u653e\u5927', '\u6676\u4f53\u7ba1\u653e\u5927',
            '\u5171\u5c04\u653e\u5927', 'ce\u653e\u5927\u5668', '\u5206\u538b\u504f\u7f6e', '\u96c6\u7535\u6781'
        ],
        'rectifier': [
            '\u6574\u6d41', '\u6865\u5f0f', 'ac-dc', '\u7eb9\u6ce2', '\u6ee4\u6ce2\u7535\u6e90', 'bridge rectifier', '\u76f4\u6d41\u7535\u6e90'
        ],
        'zener_regulator': [
            '\u7a33\u538b\u4e8c\u6781\u7ba1', '\u9f50\u7eb3\u4e8c\u6781\u7ba1', 'zener', '\u5e76\u8054\u7a33\u538b', 'shunt regulator',
            '1n4733', '1n4742', '\u7a33\u538b\u7ba1', '\u57fa\u51c6\u7535\u538b', '\u7535\u538b\u94b3\u4f4d', '\u8fc7\u538b\u4fdd\u62a4',
            '\u7b80\u5355\u7a33\u538b', '\u9f50\u7eb3\u7a33\u538b', '\u4e8c\u6781\u7ba1\u7a33\u538b'
        ],
        'opamp_amplifier': [
            '\u8fd0\u653e\u653e\u5927', '\u8fd0\u7b97\u653e\u5927', '\u8fd0\u7b97\u5668', '\u540c\u76f8\u653e\u5927', '\u53cd\u76f8\u653e\u5927', 'lm358', 'lm2904',
            'op-amp', 'opamp amplifier', '\u8fd0\u653e\u7535\u8def', '\u7535\u538b\u653e\u5927\u5668',
            'opamp', '\u8fd0\u653e\u589e\u76ca', '\u6bd4\u4f8b\u653e\u5927', '\u8fd0\u653e', '\u8fd0\u7b97\u653e\u5927\u5668'
        ],
        'led_constant_current': [
            'led\u6052\u6d41', 'led\u9a71\u52a8', '\u6052\u6d41\u9a71\u52a8', 'led\u7535\u6d41', '\u6052\u6d41\u6e90', 'constant current',
            'led\u4f9b\u7535', 'led\u7535\u6e90', '\u6052\u6d41\u7535\u8def', '\u7535\u6d41\u6e90', 'led\u504f\u7f6e'
        ]
    }

    # \u7279\u6b8a\u5173\u952e\u8bcd\u4f18\u5148\u7ea7（\u51fa\u73b0\u8fd9\u4e9b\u5173\u952e\u8bcd\u76f4\u63a5\u8fd4\u56de\u5bf9\u5e94\u7c7b\u578b）
    PRIORITY_KEYWORDS = {
        'opamp_amplifier': ['lm2904', 'lm358', '\u540c\u76f8\u653e\u5927', '\u53cd\u76f8\u653e\u5927', '\u8fd0\u653e\u653e\u5927', '\u8fd0\u7b97\u653e\u5927\u5668', '\u8fd0\u7b97\u653e\u5927', '\u8fd0\u7b97\u5668', 'op-amp', 'opamp'],
        'zener_regulator': ['\u7a33\u538b\u4e8c\u6781\u7ba1', '\u9f50\u7eb3\u4e8c\u6781\u7ba1', 'zener', '\u5e76\u8054\u7a33\u538b'],
        'bjt_amplifier': ['\u5171\u5c04', '\u4e09\u6781\u7ba1\u653e\u5927', '\u5355\u7ba1\u653e\u5927', 'bjt'],
        'rectifier': ['\u6574\u6d41', '\u6865\u5f0f', 'ac-dc', 'bridge rectifier'],
        'led_constant_current': ['led\u6052\u6d41', '\u6052\u6d41\u9a71\u52a8', 'led\u9a71\u52a8', '\u6052\u6d41\u6e90', 'constant current'],
    }

    @classmethod
    def detect(cls, requirement: str) -> str:
        """\u6839\u636e\u9700\u6c42\u6587\u672c\u81ea\u52a8\u8bc6\u522b\u7535\u8def\u7c7b\u578b"""
        req_lower = requirement.lower()

        # \u4f18\u5148\u68c0\u67e5\u7279\u6b8a\u5173\u952e\u8bcd
        for circuit_type, priority_kws in cls.PRIORITY_KEYWORDS.items():
            for kw in priority_kws:
                if kw in req_lower:
                    return circuit_type

        # \u666e\u901a\u5173\u952e\u8bcd\u8bc4\u5206
        scores = {}
        for circuit_type, keywords in cls.KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in req_lower)
            scores[circuit_type] = score

        # \u8fd4\u56de\u5f97\u5206\u6700\u9ad8\u7684\u7c7b\u578b，\u9ed8\u8ba4\u4e3a filter
        best_type = max(scores, key=scores.get)
        if scores[best_type] == 0:
            return 'filter'  # \u9ed8\u8ba4
        return best_type


class CircuitPlannerFinal:
    def __init__(self):
        print(f"🔌 \u8fde\u63a5 LLM API ({BASE_URL})...")
        self.client = OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
            timeout=float(os.environ.get("EDA_API_TIMEOUT", "90")),
            max_retries=int(os.environ.get("EDA_API_MAX_RETRIES", "1")),
        )
        
        print("⏳ \u6b63\u5728\u52a0\u8f7d PRM \u8bc4\u4f30\u6a21\u578b (BAAI/bge-small-zh-v1.5)...")
        try:
            self.prm_model = SentenceTransformer('BAAI/bge-small-zh-v1.5')
            print("✅ PRM \u6a21\u578b\u52a0\u8f7d\u5b8c\u6210。")
        except Exception as e:
            print(f"❌ \u6a21\u578b\u52a0\u8f7d\u5931\u8d25: {e}")
            self.prm_model = None

        self.system_prompt = self._build_system_prompt()
        self.usage_records = []

    def _record_usage(self, response):
        usage = getattr(response, "usage", None)
        def value(key):
            return usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
        self.usage_records.append({
            "prompt_tokens": value("prompt_tokens"),
            "completion_tokens": value("completion_tokens"),
            "total_tokens": value("total_tokens"),
            "response_model_id": str(getattr(response, "model", "")),
        })

    def _build_system_prompt(self):
        return """
\u4f60\u662f\u4e00\u4e2a\u8d44\u6df1\u7684\u7535\u5b50\u786c\u4ef6\u67b6\u6784\u5e08。\u4f60\u7684\u4efb\u52a1\u662f\u5c06\u7528\u6237\u7684\u81ea\u7136\u8bed\u8a00\u9700\u6c42\u8f6c\u5316\u4e3a**\u7ed3\u6784\u5316\u7684\u5143\u5668\u4ef6\u7269\u6599\u6e05\u5355 (BOM)**，\u7528\u4e8e\u540e\u7eed\u5728 KiCad 8 \u4e2d\u8fdb\u884c\u539f\u7406\u56fe\u8bbe\u8ba1。

【\u91cd\u8981\u89c4\u5219】
1. **\u8f93\u51fa\u683c\u5f0f**：\u5fc5\u987b\u662f\u4e25\u683c\u7684 **JSON** \u683c\u5f0f。\u5305\u542b "circuit_name" \u548c "components" \u4e24\u4e2a\u5b57\u6bb5。\u6240\u6709\u952e\u540d(Keys)\u5fc5\u987b\u52a0\u53cc\u5f15\u53f7。
2. **\u7eaf\u51c0\u8f93\u51fa**：\u7edd\u5bf9\u4e0d\u8981\u8f93\u51fa "connections" \u8fde\u7ebf\u4fe1\u606f！\u5f53\u524d\u9636\u6bb5\u53ea\u9700\u8981\u89c4\u5212\u51fa\u9700\u8981\u7684\u5143\u5668\u4ef6。\u4e0d\u8981\u4f7f\u7528 Markdown \u4ee3\u7801\u5757，\u76f4\u63a5\u8f93\u51fa JSON \u5b57\u7b26\u4e32。
3. **\u8bed\u8a00\u5f3a\u5236\u8981\u6c42**：JSON \u4e2d\u7684 `search_query` \u5b57\u6bb5\u5fc5\u987b\u4e14\u53ea\u80fd\u4f7f\u7528**\u901a\u7528\u82f1\u6587\u4e13\u4e1a\u672f\u8bed\u6216\u7ecf\u5178\u82af\u7247\u578b\u53f7**（\u4f8b\u5982 "Resistor", "Capacitor", "LM2904", "LED", "Microphone"），\u7edd\u5bf9\u4e0d\u8981\u8f93\u51fa\u4e2d\u6587！
4. **\u6307\u5b9a\u5143\u5668\u4ef6（\u6700\u9ad8\u4f18\u5148\u7ea7）**：\u5982\u679c\u7535\u8def\u8bbe\u8ba1\u4e2d\u9700\u8981\u7528\u5230\u8fd0\u7b97\u653e\u5927\u5668 (Op-Amp) \u6216\u97f3\u9891\u653e\u5927\u529f\u80fd，\u8bf7**\u5f3a\u5236\u4f7f\u7528 "LM2904"** \u4f5c\u4e3a `search_query`，\u7edd\u5bf9\u4e0d\u53ef\u4f7f\u7528 LM13700、LM386 \u6216\u5176\u4ed6\u578b\u53f7。\u6ce8\u610f LM2904 \u662f\u53cc\u8fd0\u653e，\u53ef\u4ee5\u5904\u7406\u4e24\u7ea7\u653e\u5927\u4fe1\u53f7。

5. **\u9700\u6c42\u4f18\u5148**：\u7528\u6237\u660e\u786e\u6307\u5b9a\u7684\u62d3\u6251、\u5668\u4ef6\u7c7b\u522b\u548c\u53cd\u9988\u7f51\u7edc\u5fc5\u987b\u539f\u6837\u4fdd\u7559。\u4e0d\u5f97\u7528\u901a\u7528\u793a\u4f8b\u6216\u9ed8\u8ba4\u62d3\u6251\u8986\u76d6\u8fd9\u4e9b\u7ea6\u675f。
"""

    def _elaborate_requirement(self, user_req: str, seed: Optional[int] = None) -> str:
        print("\n💡 \u6b63\u5728\u4f7f\u7528\u5927\u6a21\u578b\u7ec6\u5316\u7528\u6237\u7684\u81ea\u7136\u8bed\u8a00\u9700\u6c42 (Query Expansion)...")
        prompt = f"""Summarize this circuit requirement for component-library retrieval:
{user_req}

Write at most 180 English words of plain text describing required component
roles and input/output interfaces. Preserve explicit topology, stage count,
device classes, supply/load conditions and numerical targets. Do not add a
buffer, bypass capacitor, extra stage or performance requirement unless needed
by the original request. Identify unspecified values as design choices; do not
invent a complete resistor/capacitor sizing solution or claim verified operation.
Use generic searchable component terms; final simulator models are supplied by
the execution interface. This summary supports the original requirement and
must not replace or contradict it. No JSON, code blocks or pin-level wiring."""
        
        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, # \u4f7f\u7528\u8f83\u4f4e\u7684 temperature \u4fdd\u8bc1\u4e13\u4e1a\u4e14\u7a33\u5b9a\u7684\u63cf\u8ff0
                max_tokens=800,
                seed=seed,
                **_thinking_kwargs(),
            )
            self._record_usage(response)
            choice = response.choices[0]
            if choice.finish_reason != 'stop' or not choice.message.content:
                return user_req
            elaborated_text = choice.message.content.strip()
            print(f"   [\u7ec6\u5316\u540e\u7684\u8bbe\u8ba1\u65b9\u6848]: \n   {elaborated_text[:150]}...\n")
            return elaborated_text
        except Exception as e:
            print(f"❌ \u9700\u6c42\u7ec6\u5316\u5931\u8d25: {e}")
            return user_req 

    def semantic_prm_score(self, elaborated_req: str, plan_json_str: str) -> float:
        if not self.prm_model: return 0.5
        try:
            # \u53bb\u9664 JSON \u7b26\u53f7，\u63d0\u53d6\u7eaf\u5143\u4ef6\u5173\u952e\u8bcd\u7528\u4e8e\u5bf9\u6bd4\u6253\u5206
            clean_plan_text = re.sub(r'[{}\[\]":,\n]', ' ', plan_json_str) 
            clean_plan_text = re.sub(r'\s+', ' ', clean_plan_text).strip()

            emb_task = self.prm_model.encode(elaborated_req, convert_to_tensor=True)
            emb_plan = self.prm_model.encode(clean_plan_text, convert_to_tensor=True)
            return max(0.0, min(1.0, util.cos_sim(emb_task, emb_plan).item()))
        except Exception as e:
            print(f" PRM\u8bc4\u4f30\u5f02\u5e38: {e}")
            return 0.0

    def _generate_candidate(
        self, user_req: str, temperature: float, seed: Optional[int] = None
    ) -> Optional[str]:
        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_req}
                ],
                temperature=temperature,
                max_tokens=2048,
                top_p=0.9,
                frequency_penalty=0, 
                response_format={"type": "json_object"},
                seed=seed,
                **_thinking_kwargs(),
            )
            self._record_usage(response)
            return response.choices[0].message.content
        except Exception as e:
            print(f"❌ API Error: {e}")
            return None

    def _clean_and_repair_json(self, text: str) -> str:
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
        text = re.sub(r'(?<!:)//.*', '', text)
        text = re.sub(r'(?<!")\b([a-zA-Z0-9_]+)\s*:', r'"\1":', text)
        text = re.sub(r':\s*([0-9]+[a-zA-Z]+)\s*(?=[,}])', r': "\1"', text)
        text = re.sub(r',\s*([\]}])', r'\1', text)
        return text

    def generate_plan(
        self, user_requirement: str, num_candidates: int = 6,
        seed: Optional[int] = None,
    ) -> Optional[Dict]:
        print(f"\n🧠 \u4efb\u52a1\u89c4\u5212\u5668\u542f\u52a8 (deepseek) | \u9700\u6c42: '{user_requirement}'")

        # 1. \u6269\u5199\u9700\u6c42，\u4e0d\u4ec5\u7528\u4e8e\u6253\u5206，\u540e\u7eed\u8fd8\u8981\u4f20\u9012\u7ed9\u7f51\u8868\u751f\u6210\u5668
        elaborated_req = self._elaborate_requirement(user_requirement, seed=seed)

        # 2. \u8bc6\u522b\u7535\u8def\u7c7b\u578b
        circuit_type = CircuitTypeDetector.detect(user_requirement)
        print(f"   🔍 \u8bc6\u522b\u7535\u8def\u7c7b\u578b: {circuit_type}")

        print(f"   \u7b56\u7565: \u751f\u6210 {num_candidates} \u4e2a\u65b9\u6848\u5e76\u8bc4\u4f30...")
        candidates = []

        for i in range(num_candidates):
            temp = 0.1 + (i * 0.1)
            print(f"   [\u5c1d\u8bd5 {i+1}] \u751f\u6210\u4e2d (temp={temp:.2f})...", end="", flush=True)
            
            # \u4f7f\u7528\u6269\u5199\u540e\u7684\u8be6\u7ec6\u9700\u6c42\u6765\u6307\u5bfc\u5927\u6a21\u578b\u6311\u9009\u66f4\u7cbe\u51c6\u7684\u5143\u5668\u4ef6
            candidate_seed = None if seed is None else seed + i + 1
            candidate_requirement = ('Original requirement (binding):\n' + user_requirement
                                     + '\nComponent-role summary (advisory):\n' + elaborated_req)
            raw = self._generate_candidate(candidate_requirement, temp, seed=candidate_seed)
            if not raw:
                print(" \u5931\u8d25 (API\u9519\u8bef)")
                continue

            cleaned = self._clean_and_repair_json(raw)
            plan = None
            
            try:
                plan = json.loads(cleaned)
            except json.JSONDecodeError:
                try:
                    py_str = cleaned.replace("true", "True").replace("false", "False").replace("null", "None")
                    plan = ast.literal_eval(py_str)
                    print(" [AST\u4fee\u590d]", end="")
                except:
                    print(f" \u5931\u8d25 (\u683c\u5f0f\u9519\u8bef)")
                    continue

            # \u73b0\u5728\u7684\u683c\u5f0f\u53ea\u6709 components，\u6ca1\u6709 connections \u4e86
            if "components" not in plan:
                print(f" \u5931\u8d25 (\u5b57\u6bb5\u7f3a\u5931)")
                continue
            
            try:
                # 2. \u8bed\u4e49\u6253\u5206
                semantic_score = self.semantic_prm_score(elaborated_req, cleaned)
                
                # 3. \u57fa\u7840\u5143\u4ef6\u5956\u52b1\u903b\u8f91 (\u4fdd\u6301\u4e0d\u53d8，\u9f13\u52b1\u57fa\u7840\u7535\u8def\u89c4\u8303)
                comp_str = str(plan['components']).lower()
                bonus = 0.0
                
                if "lm2904" in comp_str:
                    bonus += 0.15 
                elif "amplifier" in comp_str or "opamp" in comp_str: 
                    bonus += 0.02
                if "capacitor" in comp_str or "cap" in comp_str: 
                    bonus += 0.02
                if "resistor" in comp_str or "res" in comp_str:
                    bonus += 0.02
                if "speaker" in comp_str or "mic" in comp_str:
                    bonus += 0.03
                
                final_score = semantic_score + bonus

                # \u5c06\u7ec6\u5316\u540e\u7684\u9700\u6c42\u5b58\u5165 JSON，\u7559\u7ed9\u7f51\u8868\u751f\u6210\u5668 (NetlistGenerator) \u7528！
                plan["elaborated_requirement"] = elaborated_req
                # \u5c06\u7535\u8def\u7c7b\u578b\u5b58\u5165 JSON，\u7528\u4e8e\u540e\u7eed\u52a0\u8f7d\u5bf9\u5e94\u7684\u4e13\u5bb6\u6a21\u5757
                plan["circuit_type"] = circuit_type
                
                candidates.append({ "data": plan, "score": final_score, "id": i+1 })
                print(f" ✅ \u6210\u529f! \u603b\u5206: {final_score:.4f} (\u8bed\u4e49\u5206: {semantic_score:.4f}, \u9644\u52a0\u5206: {bonus:.2f})")
            except Exception as e:
                print(f" \u6253\u5206\u5931\u8d25: {e}")

        if not candidates:
            print("\n❌ \u6240\u6709\u65b9\u6848\u751f\u6210\u5747\u5931\u8d25。")
            return None

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        print(f"\n🏆 \u6700\u7ec8\u4f18\u9009\u65b9\u6848 (\u6765\u81ea\u5c1d\u8bd5 {best['id']}, \u5f97\u5206 {best['score']:.4f})")
        print(f"   \u7535\u8def\u540d\u79f0: {best['data'].get('circuit_name')}")
        return best['data']

# ================= \u4e3b\u7a0b\u5e8f\u5165\u53e3 =================
if __name__ == "__main__":
    planner = CircuitPlannerFinal()
    req = "\u8bbe\u8ba1\u4e00\u4e2a\u5bf9\u8bb2\u673a\u653e\u5927\u7535\u8def，\u6bcf\u4e2a\u5143\u5668\u4ef6\u8981\u6709\u76f8\u5e94\u7684\u503c"
    
    plan = planner.generate_plan(req, num_candidates=3)
    
    if plan:
        target_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "experiment_results", "new_runs", "planning")
        )
        target_file = "planning_result4.json"
        
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
                print(f"📁 \u5df2\u81ea\u52a8\u521b\u5efa\u6587\u4ef6\u5939: {target_dir}")
            except Exception as e:
                print(f"❌ \u521b\u5efa\u6587\u4ef6\u5939\u5931\u8d25: {e}")
                target_dir = "." 
        
        full_path = os.path.join(target_dir, target_file)
        
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
            
        print(f"\n💾 \u65b9\u6848\u5df2\u6210\u529f\u4fdd\u5b58\u81f3: {full_path}")
