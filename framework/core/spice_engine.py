"""
通用仿真评估引擎

核心引擎，负责运行 Ngspice 仿真并评估结果。
具体的仿真配置和数据解析委托给专家模块处理。
"""

import os
import subprocess
import json
import re
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from openai import OpenAI

from experts.base_expert import CircuitExpert

FRAMEWORK_DIR = Path(__file__).resolve().parents[1]
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
SPICE_MODELS_DIR = Path(os.environ.get("EDA_SPICE_MODELS_DIR", FRAMEWORK_DIR / "spice_models"))


class SpiceEngine:
    """通用仿真评估引擎"""

    def __init__(self, ngspice_path: str = None):
        self.ngspice_path = ngspice_path or os.environ.get("NGSPICE_PATH", "ngspice")
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

        # 扩展的模型库
        self.TIER2_MODELS = {
            # NPN 晶体管
            "2N3904": ".model 2N3904 NPN(Is=6.734f Xti=3 Eg=1.11 Vaf=74.03 Bf=416.4 Ne=1.259 Ise=6.734 Vjc=.75 Mjc=.3085 Vje=.75 Mje=.2593 Tr=239.5n Tf=301.2p Itf=.4 Vtf=4 Xtf=2 Rb=10)",
            "2N2222": ".model 2N2222 NPN(Is=14.34f Xti=3 Eg=1.11 Vaf=128.2 Bf=255.9 Ne=1.307 Ise=14.34f Ikf=.2847 Xtb=1.5 Br=6.092 Nc=2 Isc=0 Ikr=0 Rc=1 Cjc=7.306p Mjc=.3416 Vjc=.75 Fc=.5 Cje=22.01p Mje=.377 Vje=.75 Tr=46.91n Tf=411.1p Itf=.6 Vtf=1.7 Xtf=3 Rb=10)",
            "2N2219": ".model 2N2219 NPN(Is=14.34f Xti=3 Eg=1.11 Vaf=128.2 Bf=255.9 Ne=1.307 Ise=14.34f Ikf=.2847 Xtb=1.5 Br=6.092 Nc=2 Isc=0 Ikr=0 Rc=1 Cjc=7.306p Mjc=.3416 Vjc=.75 Fc=.5 Cje=22.01p Mje=.377 Vje=.75 Tr=46.91n Tf=411.1p Itf=.6 Vtf=1.7 Xtf=3 Rb=10)",
            "BC547": ".model BC547 NPN(Is=1.8f Xti=3 Eg=1.11 Vaf=100 Bf=400 Ne=1.3 Ise=50f Ikf=80m Xtb=1.5 Br=6.5 Nc=2 Isc=0 Ikr=0 Rc=1 Cjc=4p Mjc=.33 Vjc=.75 Fc=.5 Cje=8p Mje=.34 Vje=.75 Tr=10n Tf=300p Itf=.4 Vtf=4 Xtf=6 Rb=10)",

            # PNP 晶体管
            "2N3906": ".model 2N3906 PNP(Is=1.41f Xti=3 Eg=1.11 Vaf=18.7 Bf=259.5 Ne=1.5 Ise=0 IKF=80m Xtb=1.5 Br=9.627 Nc=2 Isc=0 Ikr=0 Rc=2.5 Cjc=9.728p Mjc=.5776 Vjc=.75 Fc=.5 Cje=8.063p Mje=.3677 Vje=.75 Tr=33.42n Tf=179.3p Itf=.4 Vtf=4 Xtf=6 Rb=10)",

            # 二极管
            "1N4148": ".model 1N4148 D(Is=2.52n Rs=.568 N=1.752 Cjo=4p M=.4 tt=20n)",
            "1N4001": ".model 1N4001 D(Is=14.11n Rs=33.89m N=1.984 Cjo=25.87p M=.38 tt=5.7u)",
            "1N4007": ".model 1N4007 D(Is=14.11n Rs=33.89m N=1.984 Cjo=25.87p M=.38 tt=5.7u BV=1000)",

            # LED
            "LED": ".model LED D(Is=1e-20 N=2 Eg=2.2 Cjo=50p M=.5)",

            # MOSFET
            "IRF540": ".model IRF540 NMOS(Vto=4 Rd=0.044 Rg=3 Rs=0.01 Vds=100 Vgs=20)",

            # 外设模型
            "Speaker": ".subckt Speaker 1 2\nR_spk 1 2 8\n.ends",
            "Microphone": ".subckt Microphone 1 2\nR_mic 1 2 1k\n.ends",

            # 稳压二极管 (Zener Diodes) - 1N47xx 系列
            # BV = 稳压值, Is = 反向饱和电流
            "1N4728A": ".model 1N4728A D(Is=1n N=1 BV=3.3 IBV=76m Cjo=550p)",
            "1N4729A": ".model 1N4729A D(Is=1n N=1 BV=3.6 IBV=69m Cjo=550p)",
            "1N4730A": ".model 1N4730A D(Is=1n N=1 BV=3.9 IBV=64m Cjo=550p)",
            "1N4731A": ".model 1N4731A D(Is=1n N=1 BV=4.3 IBV=58m Cjo=550p)",
            "1N4732A": ".model 1N4732A D(Is=1n N=1 BV=4.7 IBV=53m Cjo=550p)",
            "1N4733A": ".model 1N4733A D(Is=1n N=1 BV=5.1 IBV=49m Cjo=550p)",
            "1N4734A": ".model 1N4734A D(Is=1n N=1 BV=5.6 IBV=45m Cjo=550p)",
            "1N4735A": ".model 1N4735A D(Is=1n N=1 BV=6.2 IBV=41m Cjo=550p)",
            "1N4736A": ".model 1N4736A D(Is=1n N=1 BV=6.8 IBV=37m Cjo=550p)",
            "1N4737A": ".model 1N4737A D(Is=1n N=1 BV=7.5 IBV=34m Cjo=550p)",
            "1N4738A": ".model 1N4738A D(Is=1n N=1 BV=8.2 IBV=31m Cjo=550p)",
            "1N4739A": ".model 1N4739A D(Is=1n N=1 BV=9.1 IBV=28m Cjo=550p)",
            "1N4740A": ".model 1N4740A D(Is=1n N=1 BV=10 IBV=25m Cjo=550p)",
            "1N4741A": ".model 1N4741A D(Is=1n N=1 BV=11 IBV=23m Cjo=550p)",
            "1N4742A": ".model 1N4742A D(Is=1n N=1 BV=12 IBV=21m Cjo=550p)",
            "1N4743A": ".model 1N4743A D(Is=1n N=1 BV=13 IBV=19m Cjo=550p)",
            "1N4744A": ".model 1N4744A D(Is=1n N=1 BV=15 IBV=17m Cjo=550p)",
            "1N4745A": ".model 1N4745A D(Is=1n N=1 BV=16 IBV=16m Cjo=550p)",
            "1N4746A": ".model 1N4746A D(Is=1n N=1 BV=18 IBV=14m Cjo=550p)",
            "1N4747A": ".model 1N4747A D(Is=1n N=1 BV=20 IBV=13m Cjo=550p)",
            "1N4748A": ".model 1N4748A D(Is=1n N=1 BV=22 IBV=12m Cjo=550p)",
            "1N4749A": ".model 1N4749A D(Is=1n N=1 BV=24 IBV=11m Cjo=550p)",
            "1N4750A": ".model 1N4750A D(Is=1n N=1 BV=27 IBV=9.3m Cjo=550p)",
            "1N4751A": ".model 1N4751A D(Is=1n N=1 BV=30 IBV=8.3m Cjo=550p)",
            # 无 A 后缀的型号别名（兼容性）
            "1N4733": ".model 1N4733 D(Is=1n N=1 BV=5.1 IBV=49m Cjo=550p)",
            "1N4742": ".model 1N4742 D(Is=1n N=1 BV=12 IBV=21m Cjo=550p)",

            # 行为级 78xx 稳压器模型 (1=IN, 2=GND, 3=OUT)
            # 支持多种输出电压版本
            "LM7805": ".SUBCKT LM7805 1 2 3\nB1 3 2 V=V(1,2)>7 ? 5 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7806": ".SUBCKT LM7806 1 2 3\nB1 3 2 V=V(1,2)>8 ? 6 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7808": ".SUBCKT LM7808 1 2 3\nB1 3 2 V=V(1,2)>10 ? 8 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7809": ".SUBCKT LM7809 1 2 3\nB1 3 2 V=V(1,2)>11 ? 9 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7810": ".SUBCKT LM7810 1 2 3\nB1 3 2 V=V(1,2)>12 ? 10 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7812": ".SUBCKT LM7812 1 2 3\nB1 3 2 V=V(1,2)>14 ? 12 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7815": ".SUBCKT LM7815 1 2 3\nB1 3 2 V=V(1,2)>17 ? 15 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7818": ".SUBCKT LM7818 1 2 3\nB1 3 2 V=V(1,2)>20 ? 18 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7824": ".SUBCKT LM7824 1 2 3\nB1 3 2 V=V(1,2)>26 ? 24 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            # TO-220 封装变体（与基本型号功能相同）
            "LM7805_TO220": ".SUBCKT LM7805_TO220 1 2 3\nB1 3 2 V=V(1,2)>7 ? 5 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7812_TO220": ".SUBCKT LM7812_TO220 1 2 3\nB1 3 2 V=V(1,2)>14 ? 12 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            # 贴片版本别名
            "MC78L05_SO8": ".SUBCKT MC78L05_SO8 1 2 3\nB1 3 2 V=V(1,2)>7 ? 5 : V(1,2)-2\nR1 3 2 1k\n.ENDS"
        }

        # 运放等 IC 必须使用 .include 引用 .SUBCKT 文件
        self.TIER3_LIBS = {
            "LM2904": str(SPICE_MODELS_DIR / "LM2904.lib"),
            "LM358": str(SPICE_MODELS_DIR / "LM2904.lib"),
            "NE555": str(SPICE_MODELS_DIR / "NE555.lib"),
            "NE555D": str(SPICE_MODELS_DIR / "NE555.lib"),
            "TL431": str(SPICE_MODELS_DIR / "TL431.lib")
        }

    def evaluate(
        self,
        spice_code: str,
        plan_data: dict,
        expert: CircuitExpert,
        workspace_dir: str,
        iteration: int = 1,
        use_hard_threshold: bool = False
    ) -> Tuple[bool, str, dict]:
        """
        使用专家模块进行仿真评估

        Args:
            spice_code: SPICE 网表代码
            plan_data: 规划数据
            expert: 电路专家实例
            workspace_dir: 工作目录
            iteration: 当前迭代次数
            use_hard_threshold: 是否使用硬阈值判决（不使用 LLM）

        Returns:
            Tuple[bool, str, dict]: (是否通过, 反馈信息, 实测指标dict)
        """
        print(f"\n🔎 [Ngspice Critic] 正在组装测试平台并启动物理仿真...")

        requirement = plan_data.get("elaborated_requirement", "")

        # 从专家获取仿真配置
        config = expert.get_simulation_config()
        print(f"   🔍 识别电路类型: {expert.get_circuit_description()} ({expert.circuit_type})")

        # 准备仿真文件
        cir_file = os.path.join(workspace_dir, f"sim_v{iteration}.cir")

        # 注入模型
        retrieved_path = os.path.join(workspace_dir, "retrieved.json")
        with open(retrieved_path, 'r', encoding='utf-8') as f:
            retrieved_data = json.load(f)

        injected_models = "* --- 动态模型挂载区 ---\n"
        added_models = set()  # 去重集合，防止重复添加同一模型
        for uid, info in retrieved_data.items():
            if not info:
                continue
            lib_id = info['lib_id']
            if lib_id in self.TIER2_MODELS:
                if lib_id not in added_models:
                    injected_models += self.TIER2_MODELS[lib_id] + "\n"
                    added_models.add(lib_id)
            elif lib_id in self.TIER3_LIBS:
                if lib_id not in added_models:
                    injected_models += f".include \"{self.TIER3_LIBS[lib_id]}\"\n"
                    added_models.add(lib_id)
            # 🔧 新增：通用符号映射 - 当 lib_id 是通用符号时，注入对应的默认模型
            elif lib_id == "D":
                # 通用二极管符号，注入 1N4001 作为默认模型
                if "1N4001" not in added_models:
                    injected_models += self.TIER2_MODELS["1N4001"] + "\n"
                    added_models.add("1N4001")
                # 同时注入 1N4148 常用模型
                if "1N4148" not in added_models:
                    injected_models += self.TIER2_MODELS["1N4148"] + "\n"
                    added_models.add("1N4148")
            elif lib_id == "Q_NPN":
                # 通用 NPN 晶体管符号，注入 2N3904 作为默认模型
                if "2N3904" not in added_models:
                    injected_models += self.TIER2_MODELS["2N3904"] + "\n"
                    added_models.add("2N3904")
            elif lib_id == "Q_PNP":
                # 通用 PNP 晶体管符号，注入 2N3906 作为默认模型
                if "2N3906" not in added_models:
                    injected_models += self.TIER2_MODELS["2N3906"] + "\n"
                    added_models.add("2N3906")

        # 🔧 新增：扫描 SPICE 代码中使用的模型名，自动注入缺失的模型
        # 检测二极管模型 (Dxxx node node MODEL_NAME)
        diode_models = re.findall(r'^D\w+\s+\S+\s+\S+\s+(\w+)', spice_code, re.MULTILINE)
        for model_name in set(diode_models):
            model_upper = model_name.upper()
            if model_upper in self.TIER2_MODELS and model_upper not in added_models:
                injected_models += self.TIER2_MODELS[model_upper] + "\n"
                added_models.add(model_upper)
                print(f"   [模型注入] 检测到二极管模型 '{model_upper}'，已自动注入")

        # 检测晶体管模型 (Qxxx node node node MODEL_NAME)
        bjt_models = re.findall(r'^Q\w+\s+\S+\s+\S+\s+\S+\s+(\w+)', spice_code, re.MULTILINE)
        for model_name in set(bjt_models):
            model_upper = model_name.upper()
            if model_upper in self.TIER2_MODELS and model_upper not in added_models:
                injected_models += self.TIER2_MODELS[model_upper] + "\n"
                added_models.add(model_upper)
                print(f"   [模型注入] 检测到晶体管模型 '{model_upper}'，已自动注入")

        # 构建控制块
        output_node = config.get('output_node', 'OUT')
        control_block, output_file = self._build_control_block(
            config, workspace_dir, iteration, output_node
        )

        # 清理 LLM 可能生成的残缺控制块和 .end
        spice_core = re.sub(r'\.control.*?\.endc', '', spice_code, flags=re.DOTALL | re.IGNORECASE)
        spice_core = re.sub(r'^\.end\s*$', '', spice_core, flags=re.MULTILINE)
        spice_core = re.sub(r'\.end\s*$', '', spice_core, flags=re.DOTALL)
        spice_core = re.sub(r'\.SUBCKT\s+LM2904.*?\.ENDS.*?\n', '', spice_core, flags=re.DOTALL | re.IGNORECASE)
        spice_core = re.sub(r'\.SUBCKT\s+LM358.*?\.ENDS.*?\n', '', spice_core, flags=re.DOTALL | re.IGNORECASE)
        spice_core = re.sub(r'\.MODEL\s+LM2904.*?\n', '', spice_core, flags=re.IGNORECASE)
        spice_core = re.sub(r'\.MODEL\s+LM358.*?\n', '', spice_core, flags=re.IGNORECASE)

        # ===== 新增：清理 LLM 幻觉的不支持元件 =====
        # 1. 开关 (SWxxx) - 替换为 0.1Ω 电阻（近似直通）
        spice_core = re.sub(r'^(SW\d*)\s+(\S+)\s+(\S+)\s+(\S+)', r'R\1 \2 \3 0.1', spice_core, flags=re.MULTILINE | re.IGNORECASE)

        # 2. 保险丝 (Fxxx) - 替换为 0.01Ω 电阻（近似直通）
        spice_core = re.sub(r'^(F\d*)\s+(\S+)\s+(\S+)\s+([\d.]+[a-zA-Z]?)', r'R\1 \2 \3 0.01', spice_core, flags=re.MULTILINE | re.IGNORECASE)

        # 3. 继电器 (Kxxx) - 移除（Ngspice 不支持继电器模型）
        spice_core = re.sub(r'^K\d+.*$', '', spice_core, flags=re.MULTILINE | re.IGNORECASE)

        # 4. 变压器 (Txxx) - 替换为理想耦合电感（简化处理）
        # 暂时移除复杂的变压器，替换为简单电阻
        spice_core = re.sub(r'^T\d+.*$', '* Txxx removed (unsupported)', spice_core, flags=re.MULTILINE | re.IGNORECASE)

        # 清理空行
        spice_core = re.sub(r'\n{3,}', '\n\n', spice_core)

        full_spice = f"* LLM Universal Testbench\n{injected_models}\n{spice_core}\n{control_block}\n.end\n"

        with open(cir_file, 'w', encoding='utf-8') as f:
            f.write(full_spice)

        # 运行仿真
        try:
            result = subprocess.run(
                [self.ngspice_path, '-b', cir_file],
                capture_output=True, text=True, errors='ignore'
            )
        except Exception as e:
            return False, f"❌ Ngspice 调用环境异常: {e}", {}

        # 解析仿真结果
        if not os.path.exists(output_file):
            # 检查 SPICE 代码中是否有正确的 OUT 节点
            if output_node == 'OUT' and 'OUT' not in spice_core.upper():
                return False, f"❌ [致命错误] 仿真未能产生输出数据文件！\n【关键问题】SPICE 代码中没有名为 'OUT' 的节点！\n请检查：\n1. 输出节点必须命名为 OUT（不是数字如 1, 2, 3）\n2. 示例：R1 IN OUT 220, D_Z OUT 0 1N4733A\n3. 确保所有元件正确连接\n请重新生成正确的 SPICE 网表！", {}
            return False, f"❌ [致命错误] 仿真未能产生输出数据文件！请检查：1. 输出节点是否命名为 OUT；2. 是否正确接了VCC和GND；3. 稳压二极管是否反向偏置（阴极接OUT，阳极接GND）。请重新调整 SPICE 网表！", {}

        # 读取仿真数据
        x_data, y_data = self._read_simulation_output(output_file)

        if not x_data:
            return False, "❌ [数据提取失败] 仿真曲线为空，这说明电路输出节点没有信号。请检查连线！", {}

        # 使用专家解析数据
        metrics = expert.parse_simulation_data(x_data, y_data, config)

        if not metrics:
            return False, "❌ [指标解析失败] 无法从仿真数据中提取有效指标。", {}

        # 测量 DC 功耗
        power_mw = self._measure_dc_power(full_spice, workspace_dir, iteration)
        if power_mw is not None:
            metrics['power_consumption_mw'] = power_mw

        # 格式化指标
        metrics_str = self._format_metrics(metrics)
        print(f"   📈 {metrics_str.replace(chr(10), ' | ')}")

        # 根据配置选择判决方式
        if use_hard_threshold:
            # 硬阈值判决（不使用 LLM）
            print("   ⚖️ 使用硬阈值判决（无 LLM）...")
            passed, feedback = expert.hard_threshold_judge(requirement, metrics)
            return passed, feedback, metrics
        else:
            # LLM 判决（默认方式）
            sys_prompt, user_prompt = expert.get_judgment_prompts(requirement, metrics_str)
            passed, feedback = self._llm_judge(sys_prompt, user_prompt)
            return passed, feedback, metrics

    def _build_control_block(
        self,
        config: Dict[str, Any],
        workspace_dir: str,
        iteration: int,
        output_node: str
    ) -> Tuple[str, str]:
        """根据仿真配置生成控制块"""

        analysis_type = config.get('analysis_type', 'ac')
        frequency_range = config.get('frequency_range', (1, 1e6))
        points_per_decade = config.get('points_per_decade', 50)

        if analysis_type == 'ac':
            f_start, f_end = frequency_range
            output_file = os.path.join(workspace_dir, f"ac_out_v{iteration}.txt").replace('\\', '/')
            control_block = f"""
.control
ac dec {points_per_decade} {f_start} {f_end}
wrdata {output_file} vdb({output_node})
quit
.endc
"""
        elif analysis_type == 'tran':
            tran_time = config.get('tran_time', '20m')
            time_step = config.get('time_step', '100u')
            output_file = os.path.join(workspace_dir, f"tran_out_v{iteration}.txt").replace('\\', '/')
            control_block = f"""
.control
tran {time_step} {tran_time} 0 uic
wrdata {output_file} v({output_node})
quit
.endc
"""
        elif analysis_type == 'mixed':
            f_start, f_end = frequency_range
            tran_time = config.get('tran_time', '20m')
            ac_file = os.path.join(workspace_dir, f"ac_out_v{iteration}.txt").replace('\\', '/')
            tran_file = os.path.join(workspace_dir, f"tran_out_v{iteration}.txt").replace('\\', '/')
            output_file = ac_file
            control_block = f"""
.control
ac dec {points_per_decade} {f_start} {f_end}
wrdata {ac_file} vdb({output_node})
tran 10u {tran_time} 0 uic
wrdata {tran_file} v({output_node})
quit
.endc
"""
        else:
            # 默认 AC 分析
            output_file = os.path.join(workspace_dir, f"ac_out_v{iteration}.txt").replace('\\', '/')
            control_block = f"""
.control
ac dec 50 1 1Meg
wrdata {output_file} vdb({output_node})
quit
.endc
"""

        return control_block, output_file

    def _read_simulation_output(self, output_file: str) -> Tuple[list, list]:
        """读取仿真输出文件"""
        x_data, y_data = [], []
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            x_data.append(float(parts[0]))
                            y_data.append(float(parts[1]))
                        except ValueError:
                            continue
        except Exception as e:
            print(f"   ⚠️ [读取错误] {e}")

        return x_data, y_data

    def _measure_dc_power(self, spice_code: str, workspace_dir: str, iteration: int) -> Optional[float]:
        """运行 .op 分析测量 DC 功耗 (mW)"""
        spice_core = re.sub(r'\.control.*?\.endc', '', spice_code, flags=re.DOTALL | re.IGNORECASE)
        spice_core = re.sub(r'^\.end\s*$', '', spice_core, flags=re.MULTILINE)
        spice_core = re.sub(r'\.SUBCKT.*?\.ENDS.*?\n', '', spice_core, flags=re.DOTALL | re.IGNORECASE)

        op_spice = f"* OP Analysis\n{spice_core}\n.op\n.end\n"
        op_file = os.path.join(workspace_dir, f"power_op_v{iteration}.cir")

        with open(op_file, 'w', encoding='utf-8') as f:
            f.write(op_spice)

        try:
            result = subprocess.run(
                [self.ngspice_path, '-b', op_file],
                capture_output=True, text=True, errors='ignore', timeout=30
            )
        except Exception:
            return None

        output = result.stdout + '\n' + result.stderr

        source_voltages = {}
        source_currents = {}
        for line in output.split('\n'):
            vm = re.match(r'^\s*(v\w+)\s*=\s*([\d.+-]+(?:[eE][+-]?\d+)?)', line, re.IGNORECASE)
            if vm and vm.group(1) != 'vcc#branch':
                source_voltages[vm.group(1)] = float(vm.group(2))
            im = re.match(r'^\s*(v\w+)#branch\s*=\s*([\d.+-]+(?:[eE][+-]?\d+)?)', line, re.IGNORECASE)
            if im:
                source_currents[im.group(1)] = float(im.group(2))

        total_power_w = 0.0
        for src in source_voltages:
            if src in source_currents:
                power = abs(source_voltages[src] * source_currents[src])
                total_power_w += power

        if total_power_w > 0:
            return total_power_w * 1000.0
        return None

    def _format_metrics(self, metrics: Dict[str, Any]) -> str:
        """格式化指标描述"""
        lines = []
        for key, value in metrics.items():
            if isinstance(value, float):
                # 注意：gain 相关的 key 可能包含 freq（如 mid_freq_gain_db）
                # 所以要先判断 gain，再判断 freq
                if 'gain' in key:
                    lines.append(f"{key}: {value:.2f} dB")
                elif 'freq' in key or 'bandwidth' in key:
                    lines.append(f"{key}: {value:.2f} Hz")
                elif 'current' in key and 'ma' in key.lower():
                    lines.append(f"{key}: {value:.2f} mA")
                elif 'current' in key and 'percent' in key.lower():
                    lines.append(f"{key}: {value:.1f}%")
                elif 'voltage' in key or 'ripple' in key or 'amplitude' in key or key.startswith('v_'):
                    lines.append(f"{key}: {value:.4f} V")
                else:
                    lines.append(f"{key}: {value:.4f}")
            else:
                lines.append(f"{key}: {value}")

        return "\n".join(lines)

    def _llm_judge(self, system_prompt: str, user_prompt: str) -> Tuple[bool, str]:
        """LLM 判决"""
        print("   ⚖️ 正在召唤大模型裁判官评估测量数据...")

        try:
            kwargs = {
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1,
            }
            if THINKING_ENABLED:
                kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            elif EXPLICIT_DISABLE_THINKING:
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            res = self.client.chat.completions.create(**kwargs)
            raw = res.choices[0].message.content

            # 防弹级 JSON 提取
            match = re.search(r'```json\s*(.*?)\s*```', raw, flags=re.DOTALL | re.IGNORECASE)
            if match:
                clean_json = match.group(1).strip()
            else:
                clean_json = raw[raw.find('{'):raw.rfind('}')+1]

            data = json.loads(clean_json)

            if data['passed']:
                print(f"   ✅ [判决通过] {data['reason']}")
            else:
                print(f"   ⚠️ [判决不达标] {data['reason']}")

            return data['passed'], data.get('feedback', '')

        except Exception as e:
            return False, f"❌ 裁判官解析异常: {e}"
