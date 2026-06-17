"""
OpenAI Agents SDK 风格智能体适配器 (v2)
=====================================
模拟 OpenAI Agents SDK 的使用模式
支持元器件池注入
"""

import os
import sys
import json
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from base_agent import BasePlanAgent, PLAN_SYSTEM_PROMPT


# 全局元器件池
COMPONENT_POOL: List[str] = []


def set_component_pool(pool: List[str]):
    """设置全局元器件池"""
    global COMPONENT_POOL
    COMPONENT_POOL = pool


class OpenAIAgentPlanAgent(BasePlanAgent):
    """
    OpenAI Agents SDK 风格的电路规划智能体
    特性：反思循环 + Function Calling（模拟）
    """

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        super().__init__(config)

        self.api_key = (
            config.get("api_key")
            or os.environ.get("EDA_API_KEY")
            or os.environ.get("SILICONFLOW_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )
        self.base_url = config.get("base_url") or os.environ.get("EDA_BASE_URL", "")
        self.model_name = config.get("model_name") or os.environ.get("EDA_MODEL_NAME", "deepseek-ai/DeepSeek-V3.2")

        # 最大反思迭代次数
        self.max_iterations = config.get("max_iterations", 2)

        # 初始化 OpenAI 客户端
        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _build_full_prompt(self) -> str:
        """构建完整的 system_prompt（包含元器件池）"""
        prompt = PLAN_SYSTEM_PROMPT

        # 注入元器件池
        if COMPONENT_POOL:
            pool_str = ", ".join(COMPONENT_POOL)
            pool_instruction = f"""
【重要约束 - 元器件选择】
你只能从以下元器件池中选择元器件，禁止使用元器件池之外的元器件：
{pool_str}

"""
            prompt = pool_instruction + prompt

        return prompt

    def _build_system_prompt(self) -> str:
        return PLAN_SYSTEM_PROMPT

    def get_agent_name(self) -> str:
        return "OpenAI-Agent"

    @staticmethod
    def _infer_circuit_type(user_requirement: str) -> str:
        """Infer circuit_type from user requirement using keyword matching."""
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

    def _call_llm(self, messages: List[Dict], temperature: float = 0.3) -> Optional[str]:
        """调用 LLM"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=2048,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"   LLM 调用失败: {e}")
            return None

    def generate_plan(self, user_requirement: str) -> Optional[Dict]:
        """使用反思循环生成电路规划方案"""

        # 构建完整的 system prompt
        full_system_prompt = self._build_full_prompt()

        # 构建消息列表
        messages = [
            {"role": "system", "content": full_system_prompt},
            {"role": "user", "content": user_requirement}
        ]

        # 迭代反思生成
        for iteration in range(self.max_iterations):
            # 调用 LLM
            response = self._call_llm(messages)

            if not response:
                return None

            # 解析 JSON
            plan = self._parse_json_response(response)

            # 检查是否有效
            if plan and "components" in plan:
                ct = plan.get("circuit_type", "general")
                if ct in ("general", "unknown"):
                    plan["circuit_type"] = self._infer_circuit_type(user_requirement)
                plan["elaborated_requirement"] = user_requirement
                return plan

            # 如果无效，添加反思提示
            反思提示 = """上一次的输出无法解析为有效的 JSON 格式。请重新生成。

要求：
1. 直接输出 JSON，不要有 Markdown 代码块标记
2. 必须包含 "circuit_name" 和 "components" 字段
3. components 是元器件数组，每个元器件需要 uid 和 search_query
"""
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": 反思提示})

        return None


if __name__ == "__main__":
    # 测试
    set_component_pool(["NE555", "LED", "R", "C", "VCC", "GND"])
    agent = OpenAIAgentPlanAgent()
    test_req = "设计一个LED闪烁电路，使用555定时器"
    result = agent.generate_plan(test_req)
    print(json.dumps(result, indent=2, ensure_ascii=False) if result else "失败")
