"""
Plan Method Implementations
============================
Five plan methods for comparison experiment:

P0: Ours - CircuitPlannerFinal (domain prompt + PRM + elaboration)
P1: CoT - Chain-of-Thought (step reasoning, no domain rules, no PRM, no elaboration)
P2: Self-Reflection - OpenAI agent with JSON reflection retry loop
P3: ToT - Tree of Thoughts (breadth search + LLM self-evaluation + depth expansion)
P4: AutoGen - Multi-agent conversation (Designer + Reviewer)
"""

import json
import os
import sys
import types
import random
import io
from typing import Dict, Any, Optional, List
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except (AttributeError, OSError):
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_DIR = PROJECT_ROOT / "framework"
for path in (FRAMEWORK_DIR, Path(__file__).resolve().parent):
    sys.path.insert(0, str(path))

import circuit_planner_v as planner_module

# ================= API Config =================
API_KEY = (
    os.environ.get("EDA_API_KEY")
    or os.environ.get("SILICONFLOW_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or ""
)
BASE_URL = os.environ.get("EDA_BASE_URL", "")
MODEL_NAME = os.environ.get("EDA_MODEL_NAME", "deepseek-ai/DeepSeek-V3.2")

# Ensure module-level config is set
planner_module.API_KEY = API_KEY
planner_module.BASE_URL = BASE_URL
planner_module.MODEL_NAME = MODEL_NAME

# ================= Prompt Templates =================

# P1: CoT - Generic step-by-step, NO domain-specific rules
COT_SYSTEM_PROMPT = """
You are an electronic hardware architect. Your task is to convert user requirements into a structured BOM for KiCad 8 schematic design.

[Important Rules]
1. Output format: strict JSON with "circuit_name", "circuit_type", and "components" fields. All keys must be double-quoted.
2. Pure output: no "connections" info, no Markdown code blocks. Output JSON directly.
3. Language: search_query fields must use English terminology or classic chip model numbers (e.g. "Resistor", "Capacitor", "LM2904", "LED").
4. **CRITICAL**: Generate ONLY essential components. A typical analog circuit needs 5-8 components total. Do NOT add redundant, unnecessary, or decorative components. Every component must serve a clear purpose in the circuit.
5. **circuit_type**: Must be one of: filter, opamp_amplifier, bjt_amplifier, led_blinker, led_constant_current, zener_regulator, rectifier. Choose based on the user's requirement. Do NOT use "general".

[Required Component Types]
- Core chips/functional devices
- Passive components: resistors, capacitors, inductors
- Power: VCC, GND, Power Supply
- Input/Output: connectors, switches, sensors
- Protection: diodes, TVS

[Design Steps - Chain of Thought]
Step 1: Analyze user requirements, identify circuit functional modules
Step 2: Select core chips/components for each functional module
Step 3: Configure necessary peripheral circuits (power, decoupling, biasing)
Step 4: Add power supply (VCC) and ground (GND) connections
Step 5: Add passive components (resistors, capacitors, inductors)
Step 6: Add input/output connectors and protection components
Step 7: Output the final BOM as JSON

[Example]
{
  "circuit_name": "Demo",
  "circuit_type": "filter",
  "components": [
    { "uid": "U1", "search_query": "NE555", "parameters": { "value": "NE555" } },
    { "uid": "R1", "search_query": "Resistor", "parameters": { "value": "10k" } },
    { "uid": "C1", "search_query": "Capacitor", "parameters": { "value": "100nF" } },
    { "uid": "VCC", "search_query": "VCC", "parameters": { "value": "5V" } },
    { "uid": "GND", "search_query": "GND", "parameters": { "value": "0V" } }
  ]
}
"""

# P3: ToT - Evaluation prompt for scoring candidates
TOT_EVALUATION_PROMPT = """You are a senior circuit design reviewer. Evaluate the following circuit plan on three criteria:

1. Relevance (1-10): Does the plan match the user's requirements? Are the right components selected?
2. Completeness (1-10): Are all necessary components included? (power, ground, passives, protection)
3. Feasibility (1-10): Can this circuit actually work? Are component choices practical?

User requirement: {requirement}

Circuit Plan:
{plan_json}

Output ONLY a JSON object with three numeric scores:
{{"relevance": <1-10>, "completeness": <1-10>, "feasibility": <1-10>, "total": <sum>}}"""

TOT_EXPAND_PROMPT = """You are a circuit designer. The following circuit plan needs refinement.
Please expand and improve it by:
1. Adding any missing components (power, ground, decoupling capacitors, protection)
2. Ensuring component values are reasonable for the application
3. Making the plan more complete and practical

Original plan:
{plan_json}

User requirement: {requirement}

Output the improved plan as a JSON object with "circuit_name" and "components" fields."""

# P4: AutoGen - Reviewer critique prompt
AUTOGEN_REVIEWER_PROMPT = """You are a circuit verification engineer. Review the following circuit plan and provide constructive feedback.

User requirement: {requirement}

Circuit Plan:
{plan_json}

Check for:
1. Missing essential components (power, ground, decoupling, protection)
2. Inappropriate component selection for the application
3. Missing passive components (resistors, capacitors)
4. Overall completeness and feasibility

Provide specific, actionable feedback. Output as JSON:
{{"issues": ["issue1", "issue2", ...], "severity": "low|medium|high", "suggestions": ["fix1", "fix2", ...]}}"""

AUTOGEN_REVISE_PROMPT = """You are a circuit designer. Revise your circuit plan based on the reviewer's feedback.

Original plan:
{plan_json}

Reviewer feedback: {feedback}

Output the revised plan as a JSON object with "circuit_name" and "components" fields."""


# ================= Circuit Type Inference =================

VALID_CIRCUIT_TYPES = [
    "filter", "opamp_amplifier", "bjt_amplifier",
    "led_blinker", "led_constant_current", "zener_regulator", "rectifier"
]

def _infer_circuit_type(user_requirement: str) -> str:
    """Infer circuit_type from user requirement using keyword matching. Used as fallback."""
    req = user_requirement.lower()
    if any(kw in req for kw in ['滤波', 'filter']):
        return 'filter'
    if any(kw in req for kw in ['led', '发光']):
        if any(kw in req for kw in ['恒流', 'constant current', '驱动']):
            return 'led_constant_current'
        return 'led_blinker'
    if any(kw in req for kw in ['稳压', 'zener', 'regulator', '基准', '电源']):
        return 'zener_regulator'
    if any(kw in req for kw in ['bjt', '晶体管', '共射', '2n3904']) and \
       any(kw in req for kw in ['放大', 'amplifier', 'gain', '增益']):
        return 'bjt_amplifier'
    if any(kw in req for kw in ['运放', 'opamp', 'lm2904', 'lm358', '同相', '反相']):
        return 'opamp_amplifier'
    if any(kw in req for kw in ['整流', 'rectifier']):
        return 'rectifier'
    if any(kw in req for kw in ['放大', 'amplifier']):
        return 'opamp_amplifier'
    return 'filter'


# ================= Base Wrapper =================

class BasePlanWrapper:
    """Base class for all plan methods."""

    def get_name(self) -> str:
        raise NotImplementedError

    def generate_plan(self, user_requirement: str) -> Optional[Dict]:
        raise NotImplementedError

    def _call_llm(self, system_prompt: str, user_message: str, temperature: float = 0.3) -> Optional[str]:
        """Direct LLM call using OpenAI client."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=temperature,
                max_tokens=2048,
                top_p=0.9,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"   [LLM Error]: {e}")
            return None

    def _parse_json(self, text: str) -> Optional[Dict]:
        """Robust JSON parsing."""
        import re
        import ast

        if not text:
            return None

        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = text.replace("```json", "").replace("```", "").strip()
        text = re.sub(r'(?<!")\b([a-zA-Z0-9_]+)\s*:', r'"\1":', text)
        text = re.sub(r':\s*([0-9]+[a-zA-Z]+)\s*(?=[,}])', r': "\1"', text)
        text = re.sub(r',\s*([\]}])', r'\1', text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                py_str = text.replace("true", "True").replace("false", "False").replace("null", "None")
                return ast.literal_eval(py_str)
            except:
                return None

    @staticmethod
    def _normalize_circuit_type(plan: Dict, user_requirement: str) -> Dict:
        """Ensure plan has a valid circuit_type. Fall back to inference if missing or 'general'."""
        ct = plan.get("circuit_type", "general")
        if ct in ("general", "unknown") or ct not in VALID_CIRCUIT_TYPES:
            plan["circuit_type"] = _infer_circuit_type(user_requirement)
        return plan


# ================= P0: Ours =================

class OursPlanMethod(BasePlanWrapper):
    """CircuitPlannerFinal: domain prompt + PRM + elaboration + VCC/GND enforcement."""

    def __init__(self):
        self.planner = planner_module.CircuitPlannerFinal()

        # Inject VCC/GND enforcement into the system prompt
        vcc_gnd_rule = """
【电源与接地强制规则】
- 每个电路方案必须包含 VCC（电源正）和 GND（地线）两个元器件
- search_query 分别使用 "VCC" 和 "GND"
- 这是强制要求，无例外
"""
        self.planner.system_prompt = self.planner.system_prompt + vcc_gnd_rule

    def get_name(self) -> str:
        return "Ours (CircuitPlanner)"

    def generate_plan(self, user_requirement: str) -> Optional[Dict]:
        return self.planner.generate_plan(
            user_requirement,
            num_candidates=3,
            use_prm_selection=True
        )


# ================= P1: CoT =================

class CoTPlanMethod(BasePlanWrapper):
    """
    Chain-of-Thought baseline.
    - CoT step-by-step reasoning in prompt
    - NO domain-specific rules (no Sallen-Key rules, no LED rules, no LM2904 forced binding)
    - NO PRM selection (random choice among candidates)
    - NO requirement elaboration
    """

    def __init__(self):
        self.planner = planner_module.CircuitPlannerFinal()

        # Patch elaboration to no-op
        self.planner._elaborate_requirement = types.MethodType(
            lambda self, req: req, self.planner
        )

        # Replace system prompt with CoT version (no domain rules)
        self.planner.system_prompt = COT_SYSTEM_PROMPT

        # Also patch _generate_candidate to not use response_format json_object
        # (deepseek may not support it)
        self.planner._generate_candidate = types.MethodType(
            self._patched_generate_candidate, self.planner
        )

    def get_name(self) -> str:
        return "CoT (Chain-of-Thought)"

    def _patched_generate_candidate(self, self_, user_req: str, temperature: float) -> Optional[str]:
        try:
            response = self_.client.chat.completions.create(
                model=planner_module.MODEL_NAME,
                messages=[
                    {"role": "system", "content": self_.system_prompt},
                    {"role": "user", "content": user_req}
                ],
                temperature=temperature,
                max_tokens=2048,
                top_p=0.9,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"   [CoT API Error]: {e}")
            return None

    def generate_plan(self, user_requirement: str) -> Optional[Dict]:
        # Use PRM-selection disabled (= random choice) from CircuitPlannerFinal
        return self.planner.generate_plan(
            user_requirement,
            num_candidates=3,
            use_prm_selection=False  # Random selection, not PRM
        )


# ================= P2: Self-Reflection =================

class SelfReflectionPlanMethod(BasePlanWrapper):
    """
    Self-Reflection baseline using OpenAI agent pattern.
    Generic prompt + JSON retry loop with reflection on failure.
    Uses the existing openai_agent module.
    """

    def __init__(self):
        from openai_agent import OpenAIAgentPlanAgent

        config = {
            "api_key": API_KEY,
            "base_url": BASE_URL,
            "model_name": MODEL_NAME,
            "max_iterations": 2,
        }
        self.agent = OpenAIAgentPlanAgent(config)

    def get_name(self) -> str:
        return "Self-Reflection (OpenAI Agent)"

    def generate_plan(self, user_requirement: str) -> Optional[Dict]:
        return self.agent.generate_plan(user_requirement)


# ================= P3: ToT (Tree of Thoughts) =================

class ToTPlanMethod(BasePlanWrapper):
    """
    Tree of Thoughts baseline.
    - Breadth b=3: Generate 3 candidate plans with different temperatures
    - Evaluation: LLM self-evaluates each on relevance/completeness/feasibility
    - Depth: Take top 2, expand/refine each
    - Selection: Pick best from 5 candidates (3 original + 2 refined)
    """

    def __init__(self, breadth: int = 3, depth_expand: int = 2):
        self.breadth = breadth
        self.depth_expand = depth_expand

    def get_name(self) -> str:
        return "ToT (Tree of Thoughts)"

    def generate_plan(self, user_requirement: str) -> Optional[Dict]:
        # Phase 1: Generate breadth candidates (no PRM, use CoT prompt)
        print(f"   [ToT] Phase 1: Generating {self.breadth} candidates...")
        candidates = []

        for i in range(self.breadth):
            temp = 0.2 + (i * 0.2)  # 0.2, 0.4, 0.6
            raw = self._call_llm(COT_SYSTEM_PROMPT, user_requirement, temperature=temp)
            if not raw:
                continue

            plan = self._parse_json(raw)
            if plan and "components" in plan:
                self._normalize_circuit_type(plan, user_requirement)
                plan["elaborated_requirement"] = user_requirement
                candidates.append({"plan": plan, "raw": raw, "id": i + 1})
                print(f"      Candidate {i+1}: {len(plan.get('components', []))} components")

        if not candidates:
            print("   [ToT] No valid candidates generated")
            return None

        # Phase 2: LLM self-evaluation
        print(f"   [ToT] Phase 2: LLM self-evaluation of {len(candidates)} candidates...")
        for cand in candidates:
            plan_str = json.dumps(cand["plan"], indent=2, ensure_ascii=False)
            eval_prompt = TOT_EVALUATION_PROMPT.format(
                requirement=user_requirement,
                plan_json=plan_str
            )
            eval_raw = self._call_llm(
                "You are a circuit design evaluator. Output ONLY valid JSON.",
                eval_prompt,
                temperature=0.1
            )
            if eval_raw:
                eval_data = self._parse_json(eval_raw)
                if eval_data:
                    cand["scores"] = eval_data
                    cand["total"] = eval_data.get("total", 0)
                    print(f"      Candidate {cand['id']}: total={cand['total']}")
                else:
                    cand["scores"] = {}
                    cand["total"] = 0
            else:
                cand["scores"] = {}
                cand["total"] = 0

        # Sort by total score
        candidates.sort(key=lambda x: x["total"], reverse=True)

        # Phase 3: Expand top candidates (depth)
        top_n = min(self.depth_expand, len(candidates))
        refined_candidates = []

        for i in range(top_n):
            cand = candidates[i]
            plan_str = json.dumps(cand["plan"], indent=2, ensure_ascii=False)
            expand_prompt = TOT_EXPAND_PROMPT.format(
                requirement=user_requirement,
                plan_json=plan_str
            )
            print(f"   [ToT] Phase 3: Expanding candidate {cand['id']}...")
            refined_raw = self._call_llm(COT_SYSTEM_PROMPT, expand_prompt, temperature=0.3)
            if refined_raw:
                refined_plan = self._parse_json(refined_raw)
                if refined_plan and "components" in refined_plan:
                    self._normalize_circuit_type(refined_plan, user_requirement)
                    refined_plan["elaborated_requirement"] = user_requirement
                    refined_candidates.append(refined_plan)
                    print(f"      Refined: {len(refined_plan.get('components', []))} components")

        # Phase 4: Select best - use the top-scored original if no refinements
        all_final = [c["plan"] for c in candidates] + refined_candidates
        if not all_final:
            return candidates[0]["plan"] if candidates else None

        # Pick the one with most components as heuristic (LLM selection is expensive)
        # But prefer refined plans if they exist
        if refined_candidates:
            best = max(refined_candidates, key=lambda p: len(p.get("components", [])))
        else:
            best = candidates[0]["plan"]

        print(f"   [ToT] Selected plan with {len(best.get('components', []))} components")
        return best


# ================= P4: AutoGen Multi-Agent =================

class AutoGenPlanMethod(BasePlanWrapper):
    """
    AutoGen Multi-Agent baseline.
    Two agents: CircuitDesigner + VerificationEngineer
    Multi-turn: Designer proposes → Reviewer critiques → Designer revises → Final output
    """

    def __init__(self, max_rounds: int = 2):
        self.max_rounds = max_rounds

    def get_name(self) -> str:
        return "AutoGen (Multi-Agent)"

    def generate_plan(self, user_requirement: str) -> Optional[Dict]:
        # Round 1: Designer generates initial plan
        print(f"   [AutoGen] Round 1: Designer generating initial plan...")
        initial_plan = self._parse_json(
            self._call_llm(COT_SYSTEM_PROMPT, user_requirement, temperature=0.3)
        )

        if not initial_plan or "components" not in initial_plan:
            print("   [AutoGen] Initial plan generation failed")
            return initial_plan

        self._normalize_circuit_type(initial_plan, user_requirement)
        initial_plan["elaborated_requirement"] = user_requirement

        current_plan = initial_plan
        for round_num in range(1, self.max_rounds + 1):
            # Reviewer critiques
            print(f"   [AutoGen] Round {round_num}: Reviewer critiquing...")
            plan_str = json.dumps(current_plan, indent=2, ensure_ascii=False)
            review_prompt = AUTOGEN_REVIEWER_PROMPT.format(
                requirement=user_requirement,
                plan_json=plan_str
            )
            review_raw = self._call_llm(
                "You are a circuit verification engineer. Output ONLY valid JSON.",
                review_prompt,
                temperature=0.2
            )
            review_data = self._parse_json(review_raw)

            if not review_data or not review_data.get("issues"):
                print("   [AutoGen] No issues found, plan accepted")
                break

            issues = review_data.get("issues", [])
            severity = review_data.get("severity", "low")
            suggestions = review_data.get("suggestions", [])
            print(f"      Issues ({severity}): {len(issues)}")

            if severity == "low" and len(issues) <= 1:
                print("   [AutoGen] Minor issues only, accepting plan")
                break

            # Designer revises
            print(f"   [AutoGen] Round {round_num}: Designer revising...")
            feedback_str = "\n".join(issues + suggestions)
            revise_prompt = AUTOGEN_REVISE_PROMPT.format(
                plan_json=plan_str,
                feedback=feedback_str
            )
            revised_raw = self._call_llm(COT_SYSTEM_PROMPT, revise_prompt, temperature=0.3)
            revised_plan = self._parse_json(revised_raw)

            if revised_plan and "components" in revised_plan:
                self._normalize_circuit_type(revised_plan, user_requirement)
                revised_plan["elaborated_requirement"] = user_requirement
                print(f"      Revised: {len(revised_plan.get('components', []))} components")
                current_plan = revised_plan
            else:
                print("   [AutoGen] Revision failed, keeping current plan")
                break

        return current_plan


# ================= Factory =================

def create_plan_method(method_type: str) -> BasePlanWrapper:
    """Factory function for plan methods."""
    methods = {
        "Ours": OursPlanMethod,
        "CoT": CoTPlanMethod,
        "SelfReflection": SelfReflectionPlanMethod,
        "ToT": ToTPlanMethod,
        "AutoGen": AutoGenPlanMethod,
    }

    if method_type not in methods:
        raise ValueError(f"Unknown plan method: {method_type}. Available: {list(methods.keys())}")

    return methods[method_type]()
