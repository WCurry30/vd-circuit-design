import json
import re
import ast
import os
from typing import List, Dict, Any, Optional
from openai import OpenAI
from sentence_transformers import SentenceTransformer, util

API_KEY = (
    os.environ.get("EDA_API_KEY")
    or os.environ.get("SILICONFLOW_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or ""
)
BASE_URL = os.environ.get("EDA_BASE_URL", "")
MODEL_NAME = os.environ.get("EDA_MODEL_NAME", "deepseek-ai/DeepSeek-V3.2")


class CircuitTypeDetector:
    """
    电路类型自动识别器

    从 ngspice_critic.py 迁移至此，用于在规划阶段识别电路类型。
    """

    KEYWORDS = {
        'filter': [
            '滤波', 'filter', '截止频率', 'cutoff', '低通', '高通', '带通', '带阻',
            'sallen', 'butterworth', 'chebyshev', 'rc滤波', 'lc滤波'
        ],
        'audio_amplifier': [
            '对讲机', '音频放大', 'audio amplifier', '功放', '扬声器', 'speaker',
            '麦克风', 'microphone', '话筒', '音响', '音响放大', '语音放大',
            '耳机放大', '音频功率', '音频前置', '话音放大'
        ],
        'amplifier': [
            '放大', 'amplifier', '增益', 'gain', '功率放大', '前置放大', 'preamp'
        ],
        'power_supply': [
            '电源', 'power supply', '稳压', 'regulator', 'ldo', 'dc-dc',
            '开关电源', '线性电源', 'buck', 'boost', '变换器', '适配器',
            '充电', 'charger', '电池供电'
        ],
        'oscillator': [
            '振荡', 'oscillator', '时钟', 'clock', '晶振', 'crystal',
            '方波', '正弦波', '信号发生', 'pwm', '555', '多谐振荡'
        ],
        'led_blinker': [
            'led', '闪烁', '呼吸灯', '跑马灯', '555定时器', '多谐振荡',
            'blinker', 'astable', 'led控制', '闪烁灯', '流水灯', '闪灯'
        ],
        'bjt_amplifier': [
            '共射', '三极管放大', '2n3904', '分立元件放大', '单管放大',
            'bjt', 'common emitter', 'ce放大', '晶体管放大',
            '共射放大', 'ce放大器', '分压偏置', '集电极'
        ],
        'rectifier': [
            '整流', '桥式', 'ac-dc', '纹波', '滤波电源', 'bridge rectifier', '直流电源'
        ],
        'zener_regulator': [
            '稳压二极管', '齐纳二极管', 'zener', '并联稳压', 'shunt regulator',
            '1n4733', '1n4742', '稳压管', '基准电压', '电压钳位', '过压保护',
            '简单稳压', '齐纳稳压', '二极管稳压'
        ],
        'opamp_amplifier': [
            '运放放大', '运算放大', '运算器', '同相放大', '反相放大', 'lm358', 'lm2904',
            'op-amp', 'opamp amplifier', '运放电路', '电压放大器',
            'opamp', '运放增益', '比例放大', '运放', '运算放大器'
        ],
        'led_constant_current': [
            'led恒流', 'led驱动', '恒流驱动', 'led电流', '恒流源', 'constant current',
            'led供电', 'led电源', '恒流电路', '电流源', 'led偏置'
        ]
    }

    # 特殊关键词优先级（出现这些关键词直接返回对应类型）
    PRIORITY_KEYWORDS = {
        'opamp_amplifier': ['lm2904', 'lm358', '同相放大', '反相放大', '运放放大', '运算放大器', '运算放大', '运算器', 'op-amp', 'opamp'],
        'zener_regulator': ['稳压二极管', '齐纳二极管', 'zener', '并联稳压'],
        'bjt_amplifier': ['共射', '三极管放大', '单管放大', 'bjt'],
        'rectifier': ['整流', '桥式', 'ac-dc', 'bridge rectifier'],
        'led_constant_current': ['led恒流', '恒流驱动', 'led驱动', '恒流源', 'constant current'],
    }

    @classmethod
    def detect(cls, requirement: str) -> str:
        """根据需求文本自动识别电路类型"""
        req_lower = requirement.lower()

        # 优先检查特殊关键词
        for circuit_type, priority_kws in cls.PRIORITY_KEYWORDS.items():
            for kw in priority_kws:
                if kw in req_lower:
                    return circuit_type

        # 普通关键词评分
        scores = {}
        for circuit_type, keywords in cls.KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in req_lower)
            scores[circuit_type] = score

        # 返回得分最高的类型，默认为 filter
        best_type = max(scores, key=scores.get)
        if scores[best_type] == 0:
            return 'filter'  # 默认
        return best_type


class CircuitPlannerFinal:
    def __init__(self):
        print(f"🔌 连接 LLM API ({BASE_URL})...")
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        
        print("⏳ 正在加载 PRM 评估模型 (BAAI/bge-small-zh-v1.5)...")
        try:
            self.prm_model = SentenceTransformer('BAAI/bge-small-zh-v1.5')
            print("✅ PRM 模型加载完成。")
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            self.prm_model = None

        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self):
        return """
你是一个资深的电子硬件架构师。你的任务是将用户的自然语言需求转化为**结构化的元器件物料清单 (BOM)**，用于后续在 KiCad 8 中进行原理图设计。

【重要规则】
1. **输出格式**：必须是严格的 **JSON** 格式。包含 "circuit_name" 和 "components" 两个字段。所有键名(Keys)必须加双引号。
2. **纯净输出**：绝对不要输出 "connections" 连线信息！当前阶段只需要规划出需要的元器件。不要使用 Markdown 代码块，直接输出 JSON 字符串。
3. **语言强制要求**：JSON 中的 `search_query` 字段必须且只能使用**通用英文专业术语或经典芯片型号**（例如 "Resistor", "Capacitor", "LM2904", "LED", "Microphone"），绝对不要输出中文！
4. **指定元器件（最高优先级）**：如果电路设计中需要用到运算放大器 (Op-Amp) 或音频放大功能，请**强制使用 "LM2904"** 作为 `search_query`，绝对不可使用 LM13700、LM386 或其他型号。注意 LM2904 是双运放，可以处理两级放大信号。

【Sallen-Key 滤波器专用规则】
对于低通滤波器电路：
- 只需要 R1, R2（滤波电阻）和 C1, C2（滤波电容）
- 运放使用**单位增益配置**（输出直接连接反相输入端），**不需要 R3, R4 或任何反馈电阻！**
- 可以包含输入耦合电容（C_in）和电源去耦电容（C_dec）
- **绝对禁止规划 R3, R4 或任何反馈网络电阻！**

【LED 恒流驱动电路专用规则】
对于 LED 恒流驱动电路：
- **必须使用简单的 BJT 恒流源拓扑**，禁止使用运放闭环拓扑！
- 只需要：1个 BJT（2N3904），1个 LED，3个电阻，1个去耦电容
- BJT 使用 2N3904 或 BC547，**禁止使用 MOSFET**
- **禁止规划运放（LM2904）**，禁止规划电位器，禁止规划多个二极管
- 元器件列表固定格式：
  - Q1: BJT (2N3904)
  - LED1: LED
  - R1, R2, R3: 电阻（R1,R2 用于分压偏置，R3 用于设定电流）
  - C1: 去耦电容

【示例 - LED 恒流驱动电路】
{
  "circuit_name": "LED_Constant_Current",
  "components": [
    { "uid": "Q1", "search_query": "2N3904", "parameters": { "value": "2N3904" } },
    { "uid": "LED1", "search_query": "LED", "parameters": { "value": "LED" } },
    { "uid": "R1", "search_query": "Resistor", "parameters": { "value": "10k" } },
    { "uid": "R2", "search_query": "Resistor", "parameters": { "value": "2k" } },
    { "uid": "R3", "search_query": "Resistor", "parameters": { "value": "65" } },
    { "uid": "C1", "search_query": "Capacitor", "parameters": { "value": "100nF" } }
  ]
}

【示例 - Sallen-Key 低通滤波器】
{
  "circuit_name": "Sallen_Key_LPF",
  "components": [
    { "uid": "U1", "search_query": "LM2904", "parameters": { "value": "LM2904" } },
    { "uid": "R1", "search_query": "Resistor", "parameters": { "value": "11.3k" } },
    { "uid": "R2", "search_query": "Resistor", "parameters": { "value": "11.3k" } },
    { "uid": "C1", "search_query": "Capacitor", "parameters": { "value": "10nF" } },
    { "uid": "C2", "search_query": "Capacitor", "parameters": { "value": "20nF" } },
    { "uid": "C3", "search_query": "Capacitor", "parameters": { "value": "100nF" } }
  ]
}
"""

    def _elaborate_requirement(self, user_req: str) -> str:
        print("\n💡 正在使用大模型细化用户的自然语言需求 (Query Expansion)...")
        prompt = f"""你是一个高级电子工程师。用户有一个简短的电路设计需求：“{user_req}”。
请将这个需求扩展成一段详细的、专业的电路设计方案描述。

【约束条件】
1. 目标平台是 KiCad 8，因此请尽量选择通用、基础、经典的元器件（如 NE555, LM2904, 2N3904, 1N4148，基础阻容等），避免使用过于冷门或复杂的专用芯片。
2. 描述中必须明确包含具体的元器件类型（如运放、电容类型、电阻用途）、输入输出外设及其在电路中的具体功能分工。
3. 只需要输出一段纯文本的描述，不要包含任何格式化代码、不要 JSON，也不要描述具体的引脚连线细节。"""
        
        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, # 使用较低的 temperature 保证专业且稳定的描述
                max_tokens=800
            )
            elaborated_text = response.choices[0].message.content.strip()
            print(f"   [细化后的设计方案]: \n   {elaborated_text[:150]}...\n")
            return elaborated_text
        except Exception as e:
            print(f"❌ 需求细化失败: {e}")
            return user_req 

    def semantic_prm_score(self, elaborated_req: str, plan_json_str: str) -> float:
        if not self.prm_model: return 0.5
        try:
            # 去除 JSON 符号，提取纯元件关键词用于对比打分
            clean_plan_text = re.sub(r'[{}\[\]":,\n]', ' ', plan_json_str) 
            clean_plan_text = re.sub(r'\s+', ' ', clean_plan_text).strip()

            emb_task = self.prm_model.encode(elaborated_req, convert_to_tensor=True)
            emb_plan = self.prm_model.encode(clean_plan_text, convert_to_tensor=True)
            return max(0.0, min(1.0, util.cos_sim(emb_task, emb_plan).item()))
        except Exception as e:
            print(f" PRM评估异常: {e}")
            return 0.0

    def _generate_candidate(self, user_req: str, temperature: float) -> Optional[str]:
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
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"❌ API Error: {e}")
            return None

    def _clean_and_repair_json(self, text: str) -> str:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = text.replace("```json", "").replace("```", "").strip()
        text = re.sub(r'(?<!:)//.*', '', text)
        text = re.sub(r'(?<!")\b([a-zA-Z0-9_]+)\s*:', r'"\1":', text)
        text = re.sub(r':\s*([0-9]+[a-zA-Z]+)\s*(?=[,}])', r': "\1"', text)
        text = re.sub(r',\s*([\]}])', r'\1', text)
        return text

    def generate_plan(self, user_requirement: str, num_candidates: int = 6) -> Optional[Dict]:
        print(f"\n🧠 任务规划器启动 (deepseek) | 需求: '{user_requirement}'")

        # 1. 扩写需求，不仅用于打分，后续还要传递给网表生成器
        elaborated_req = self._elaborate_requirement(user_requirement)

        # 2. 识别电路类型
        circuit_type = CircuitTypeDetector.detect(user_requirement)
        print(f"   🔍 识别电路类型: {circuit_type}")

        print(f"   策略: 生成 {num_candidates} 个方案并评估...")
        candidates = []

        for i in range(num_candidates):
            temp = 0.1 + (i * 0.1)
            print(f"   [尝试 {i+1}] 生成中 (temp={temp:.2f})...", end="", flush=True)
            
            # 使用扩写后的详细需求来指导大模型挑选更精准的元器件
            raw = self._generate_candidate(elaborated_req, temp)
            if not raw:
                print(" 失败 (API错误)")
                continue

            cleaned = self._clean_and_repair_json(raw)
            plan = None
            
            try:
                plan = json.loads(cleaned)
            except json.JSONDecodeError:
                try:
                    py_str = cleaned.replace("true", "True").replace("false", "False").replace("null", "None")
                    plan = ast.literal_eval(py_str)
                    print(" [AST修复]", end="")
                except:
                    print(f" 失败 (格式错误)")
                    continue

            # 现在的格式只有 components，没有 connections 了
            if "components" not in plan:
                print(f" 失败 (字段缺失)")
                continue
            
            try:
                # 2. 语义打分
                semantic_score = self.semantic_prm_score(elaborated_req, cleaned)
                
                # 3. 基础元件奖励逻辑 (保持不变，鼓励基础电路规范)
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

                # 将细化后的需求存入 JSON，留给网表生成器 (NetlistGenerator) 用！
                plan["elaborated_requirement"] = elaborated_req
                # 将电路类型存入 JSON，用于后续加载对应的专家模块
                plan["circuit_type"] = circuit_type
                
                candidates.append({ "data": plan, "score": final_score, "id": i+1 })
                print(f" ✅ 成功! 总分: {final_score:.4f} (语义分: {semantic_score:.4f}, 附加分: {bonus:.2f})")
            except Exception as e:
                print(f" 打分失败: {e}")

        if not candidates:
            print("\n❌ 所有方案生成均失败。")
            return None

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        print(f"\n🏆 最终优选方案 (来自尝试 {best['id']}, 得分 {best['score']:.4f})")
        print(f"   电路名称: {best['data'].get('circuit_name')}")
        return best['data']

# ================= 主程序入口 =================
if __name__ == "__main__":
    planner = CircuitPlannerFinal()
    req = "设计一个对讲机放大电路，每个元器件要有相应的值"
    
    plan = planner.generate_plan(req, num_candidates=3)
    
    if plan:
        target_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "experiment_results", "new_runs", "planning")
        )
        target_file = "planning_result4.json"
        
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
                print(f"📁 已自动创建文件夹: {target_dir}")
            except Exception as e:
                print(f"❌ 创建文件夹失败: {e}")
                target_dir = "." 
        
        full_path = os.path.join(target_dir, target_file)
        
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
            
        print(f"\n💾 方案已成功保存至: {full_path}")
