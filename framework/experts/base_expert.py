"""
\u7535\u8def\u4e13\u5bb6\u62bd\u8c61\u57fa\u7c7b

\u5b9a\u4e49\u4e86\u6240\u6709\u7535\u8def\u4e13\u5bb6\u5fc5\u987b\u5b9e\u73b0\u7684\u63a5\u53e3，\u7528\u4e8e\u652f\u6301\u63d2\u4ef6\u5316\u67b6\u6784。
\u6bcf\u4e2a\u5177\u4f53\u7535\u8def\u7c7b\u578b（\u6ee4\u6ce2\u5668、\u653e\u5927\u5668、\u7535\u6e90\u7b49）\u9700\u8981\u7ee7\u627f\u6b64\u7c7b\u5e76\u5b9e\u73b0\u6240\u6709\u62bd\u8c61\u65b9\u6cd5。
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional


class CircuitExpert(ABC):
    """\u7535\u8def\u4e13\u5bb6\u62bd\u8c61\u57fa\u7c7b"""

    _external_targets: Optional[Dict[str, Any]] = None

    def set_targets(self, targets: Optional[Dict[str, Any]] = None):
        """\u4ece test_cases_v3 \u6ce8\u5165\u76ee\u6807\u503c，\u5b50\u7c7b\u91cd\u5199\u4ee5\u63d0\u53d6\u81ea\u5df1\u5173\u5fc3\u7684 metric"""
        self._external_targets = targets

    @property
    @abstractmethod
    def circuit_type(self) -> str:
        """
        \u8fd4\u56de\u7535\u8def\u7c7b\u578b\u6807\u8bc6\u7b26

        \u4f8b\u5982: 'filter', 'audio_amplifier', 'power_supply', 'oscillator'
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
        \u751f\u6210\u7f51\u8868\u751f\u6210\u6240\u9700\u7684 Prompt

        Args:
            elaborated_req: \u7ec6\u5316\u540e\u7684\u8bbe\u8ba1\u9700\u6c42
            uid_hint: \u53ef\u7528\u7684\u5143\u5668\u4ef6 UID \u5217\u8868（\u9017\u53f7\u5206\u9694）
            iteration: \u5f53\u524d\u8fed\u4ee3\u6b21\u6570（1 \u8868\u793a\u9996\u8f6e）
            previous_spice: \u4e0a\u4e00\u8f6e\u7684 SPICE \u4ee3\u7801（\u8fed\u4ee3\u8f6e\u6b21\u4f7f\u7528）
            feedback: \u4e0a\u4e00\u8f6e\u7684\u4eff\u771f\u53cd\u9988（\u8fed\u4ee3\u8f6e\u6b21\u4f7f\u7528）

        Returns:
            Tuple[str, str]: (system_prompt, user_prompt)
        """
        pass

    @abstractmethod
    def clean_spice_code(self, spice_code: str) -> str:
        """
        \u6e05\u6d17 LLM \u751f\u6210\u7684 SPICE \u4ee3\u7801

        \u79fb\u9664\u591a\u4f59\u7684、\u4e0d\u7b26\u5408\u89c4\u8303\u7684\u5143\u4ef6，\u4fee\u6b63\u5e38\u89c1\u7684 LLM \u9519\u8bef。

        Args:
            spice_code: \u539f\u59cb SPICE \u4ee3\u7801

        Returns:
            str: \u6e05\u6d17\u540e\u7684 SPICE \u4ee3\u7801
        """
        pass

    @abstractmethod
    def get_simulation_config(self) -> Dict[str, Any]:
        """
        \u8fd4\u56de\u4eff\u771f\u914d\u7f6e

        Returns:
            Dict[str, Any]: \u5305\u542b\u4ee5\u4e0b\u952e\u7684\u914d\u7f6e\u5b57\u5178:
                - analysis_type: 'ac' | 'tran' | 'mixed'
                - frequency_range: (f_start, f_end) \u9891\u7387\u8303\u56f4
                - output_node: \u8f93\u51fa\u8282\u70b9\u540d
                - \u5176\u4ed6\u7c7b\u578b\u7279\u5b9a\u53c2\u6570
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
        \u89e3\u6790\u4eff\u771f\u6570\u636e，\u63d0\u53d6\u5173\u952e\u6307\u6807

        Args:
            x_data: X \u8f74\u6570\u636e（\u901a\u5e38\u662f\u9891\u7387\u6216\u65f6\u95f4）
            y_data: Y \u8f74\u6570\u636e（\u901a\u5e38\u662f\u589e\u76ca\u6216\u7535\u538b）
            config: \u4eff\u771f\u914d\u7f6e

        Returns:
            Dict[str, Any]: \u6307\u6807\u5b57\u5178，\u4f8b\u5982:
                - \u6ee4\u6ce2\u5668: {'cutoff_freq_hz': 1000, 'passband_gain_db': 0, ...}
                - \u653e\u5927\u5668: {'gain_db': 20, 'bandwidth_hz': 10000, ...}
        """
        pass

    @abstractmethod
    def get_judgment_prompts(
        self,
        requirement: str,
        metrics_str: str
    ) -> Tuple[str, str]:
        """
        \u751f\u6210 LLM \u5224\u51b3\u6240\u9700\u7684 Prompt

        Args:
            requirement: \u8bbe\u8ba1\u9700\u6c42
            metrics_str: \u683c\u5f0f\u5316\u540e\u7684\u4eff\u771f\u6307\u6807\u5b57\u7b26\u4e32

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
        \u786c\u9608\u503c\u5224\u51b3（\u4e0d\u4f7f\u7528 LLM）

        \u7528\u4e8e\u6d88\u878d\u5b9e\u9a8c G3 (No_Metric)，\u5b8c\u5168\u79fb\u9664 LLM \u5224\u51b3，\u6539\u7528\u786c\u9608\u503c\u89c4\u5219。
        \u5b50\u7c7b\u9700\u8981\u5b9e\u73b0\u5177\u4f53\u7684\u9608\u503c\u5224\u65ad\u903b\u8f91。

        Args:
            requirement: \u8bbe\u8ba1\u9700\u6c42
            metrics: \u4eff\u771f\u6307\u6807\u5b57\u5178（\u6765\u81ea parse_simulation_data）

        Returns:
            Tuple[bool, str]: (\u662f\u5426\u901a\u8fc7, \u5224\u51b3\u7406\u7531)
        """
        pass

    def get_circuit_description(self) -> str:
        """
        \u8fd4\u56de\u7535\u8def\u7c7b\u578b\u7684\u4e2d\u6587\u63cf\u8ff0

        \u53ef\u9009\u5b9e\u73b0，\u7528\u4e8e\u65e5\u5fd7\u8f93\u51fa
        """
        return self.circuit_type
