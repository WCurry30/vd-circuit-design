"""
电路专家抽象基类

定义了所有电路专家必须实现的接口，用于支持插件化架构。
每个具体电路类型（滤波器、放大器、电源等）需要继承此类并实现所有抽象方法。
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional


class CircuitExpert(ABC):
    """电路专家抽象基类"""

    _external_targets: Optional[Dict[str, Any]] = None

    def set_targets(self, targets: Optional[Dict[str, Any]] = None):
        """从 test_cases_v3 注入目标值，子类重写以提取自己关心的 metric"""
        self._external_targets = targets

    @property
    @abstractmethod
    def circuit_type(self) -> str:
        """
        返回电路类型标识符

        例如: 'filter', 'audio_amplifier', 'power_supply', 'oscillator'
        """
        pass

    @abstractmethod
    def get_netlist_prompts(
        self,
        elaborated_req: str,
        uid_hint: str,
        iteration: int,
        previous_spice: Optional[str],
        feedback: Optional[str]
    ) -> Tuple[str, str]:
        """
        生成网表生成所需的 Prompt

        Args:
            elaborated_req: 细化后的设计需求
            uid_hint: 可用的元器件 UID 列表（逗号分隔）
            iteration: 当前迭代次数（1 表示首轮）
            previous_spice: 上一轮的 SPICE 代码（迭代轮次使用）
            feedback: 上一轮的仿真反馈（迭代轮次使用）

        Returns:
            Tuple[str, str]: (system_prompt, user_prompt)
        """
        pass

    @abstractmethod
    def clean_spice_code(self, spice_code: str) -> str:
        """
        清洗 LLM 生成的 SPICE 代码

        移除多余的、不符合规范的元件，修正常见的 LLM 错误。

        Args:
            spice_code: 原始 SPICE 代码

        Returns:
            str: 清洗后的 SPICE 代码
        """
        pass

    @abstractmethod
    def get_simulation_config(self) -> Dict[str, Any]:
        """
        返回仿真配置

        Returns:
            Dict[str, Any]: 包含以下键的配置字典:
                - analysis_type: 'ac' | 'tran' | 'mixed'
                - frequency_range: (f_start, f_end) 频率范围
                - output_node: 输出节点名
                - 其他类型特定参数
        """
        pass

    @abstractmethod
    def parse_simulation_data(
        self,
        x_data: list,
        y_data: list,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        解析仿真数据，提取关键指标

        Args:
            x_data: X 轴数据（通常是频率或时间）
            y_data: Y 轴数据（通常是增益或电压）
            config: 仿真配置

        Returns:
            Dict[str, Any]: 指标字典，例如:
                - 滤波器: {'cutoff_freq_hz': 1000, 'passband_gain_db': 0, ...}
                - 放大器: {'gain_db': 20, 'bandwidth_hz': 10000, ...}
        """
        pass

    @abstractmethod
    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:
        """
        生成 LLM 判决所需的 Prompt

        Args:
            requirement: 设计需求
            metrics_str: 格式化后的仿真指标字符串

        Returns:
            Tuple[str, str]: (system_prompt, user_prompt)
        """

    @abstractmethod
    def hard_threshold_judge(
        self,
        requirement: str,
        metrics: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        硬阈值判决（不使用 LLM）

        用于消融实验 G3 (No_Metric)，完全移除 LLM 判决，改用硬阈值规则。
        子类需要实现具体的阈值判断逻辑。

        Args:
            requirement: 设计需求
            metrics: 仿真指标字典（来自 parse_simulation_data）

        Returns:
            Tuple[bool, str]: (是否通过, 判决理由)
        """
        pass

    def get_circuit_description(self) -> str:
        """
        返回电路类型的中文描述

        可选实现，用于日志输出
        """
        return self.circuit_type
