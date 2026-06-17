"""
Plan模块对比实验 - 基础智能体接口
================================
定义统一的智能体接口，用于对比不同智能体框架的规划能力
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import json


class BasePlanAgent(ABC):
    """Plan智能体的基类，定义统一接口"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.system_prompt = self._build_system_prompt()

    @abstractmethod
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        pass

    @abstractmethod
    def generate_plan(self, user_requirement: str) -> Optional[Dict]:
        """
        生成电路规划方案

        Args:
            user_requirement: 用户需求

        Returns:
            规划方案字典，包含 components 等字段
        """
        pass

    @abstractmethod
    def get_agent_name(self) -> str:
        """返回智能体名称"""
        pass

    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """解析 JSON 响应"""
        import re
        import ast

        # 清理响应
        text = response
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


# ================= 统一的系统提示词模板 =================
# 与 CircuitPlannerFinal 保持一致
PLAN_SYSTEM_PROMPT = """
你是一个资深的电子硬件架构师。你的任务是将用户的自然语言需求转化为**结构化的元器件物料清单 (BOM)**，用于后续在 KiCad 8 中进行原理图设计。

【重要规则】
1. **输出格式**：必须是严格的 **JSON** 格式。包含 "circuit_name"、"circuit_type" 和 "components" 三个字段。所有键名(Keys)必须加双引号。
2. **纯净输出**：绝对不要输出 "connections" 连线信息！当前阶段只需要规划出需要的元器件。不要使用 Markdown 代码块，直接输出 JSON 字符串。
3. **语言强制要求**：JSON 中的 `search_query` 字段必须且只能使用**通用英文专业术语或经典芯片型号**（例如 "Resistor", "Capacitor", "LM2904", "LED", "Microphone", "VCC", "GND", "Power Supply"），绝对不要输出中文！
4. **circuit_type**：必须是以下之一: filter, opamp_amplifier, bjt_amplifier, led_blinker, led_constant_current, zener_regulator, rectifier。根据用户需求选择，不要用 "general"。

【必须包含的元器件类型】
- 核心芯片/功能器件
- 被动元件：电阻、电容、电感
- 电源相关：VCC (电源正)、GND (地线)、Power Supply (电源)
- 输入输出：连接器、开关、传感器
- 保护元件：二极管、TVS管

【示例】
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

# 无 CoT 版本
PLAN_SYSTEM_PROMPT_NO_COT = """
你是一个电子硬件架构师。将用户的自然语言需求转化为电路设计方案。

【重要规则】
1. 输出必须是严格的 JSON 格式。
2. 必须包含 "circuit_type" 字段（filter/opamp_amplifier/bjt_amplifier/led_blinker/led_constant_current/zener_regulator/rectifier 之一，不要用 "general"）。
3. 必须包含所有类型的元器件：核心芯片、被动元件、电容、电阻、电感、电源(VCC)、地线(GND)、连接器等。

【示例】
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