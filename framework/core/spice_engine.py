"""
\u901a\u7528\u4eff\u771f\u8bc4\u4f30\u5f15\u64ce

\u6838\u5fc3\u5f15\u64ce，\u8d1f\u8d23\u8fd0\u884c Ngspice \u4eff\u771f\u5e76\u8bc4\u4f30\u7ed3\u679c。
\u5177\u4f53\u7684\u4eff\u771f\u914d\u7f6e\u548c\u6570\u636e\u89e3\u6790\u59d4\u6258\u7ed9\u4e13\u5bb6\u6a21\u5757\u5904\u7406。
"""

import os
import subprocess
import json
import re
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from openai import OpenAI

from experts.base_expert import CircuitExpert

# ================= \u914d\u7f6e\u533a\u57df =================
FRAMEWORK_DIR = Path(__file__).resolve().parents[1]
API_KEY = (
    os.environ.get("EDA_API_KEY")
    or os.environ.get("SILICONFLOW_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or ""
)
BASE_URL = os.environ.get("EDA_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = os.environ.get("EDA_MODEL_NAME", "deepseek-ai/DeepSeek-V3.2")
THINKING_ENABLED = False
EXPLICIT_DISABLE_THINKING = False
SPICE_MODELS_DIR = Path(os.environ.get("EDA_SPICE_MODELS_DIR", FRAMEWORK_DIR / "spice_models"))
# ===========================================


class SpiceEngine:
    """\u901a\u7528\u4eff\u771f\u8bc4\u4f30\u5f15\u64ce"""

    def __init__(self, ngspice_path: str = None):
        self.ngspice_path = ngspice_path or os.environ.get("NGSPICE_PATH", r"d:\Spice64\bin\ngspice_con.exe")
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

        # \u6269\u5c55\u7684\u6a21\u578b\u5e93
        self.TIER2_MODELS = {
            # NPN \u6676\u4f53\u7ba1
            "2N3904": ".model 2N3904 NPN(Is=6.734f Xti=3 Eg=1.11 Vaf=74.03 Bf=416.4 Ne=1.259 Ise=6.734 Vjc=.75 Mjc=.3085 Vje=.75 Mje=.2593 Tr=239.5n Tf=301.2p Itf=.4 Vtf=4 Xtf=2 Rb=10)",
            "2N2222": ".model 2N2222 NPN(Is=14.34f Xti=3 Eg=1.11 Vaf=128.2 Bf=255.9 Ne=1.307 Ise=14.34f Ikf=.2847 Xtb=1.5 Br=6.092 Nc=2 Isc=0 Ikr=0 Rc=1 Cjc=7.306p Mjc=.3416 Vjc=.75 Fc=.5 Cje=22.01p Mje=.377 Vje=.75 Tr=46.91n Tf=411.1p Itf=.6 Vtf=1.7 Xtf=3 Rb=10)",
            "2N2219": ".model 2N2219 NPN(Is=14.34f Xti=3 Eg=1.11 Vaf=128.2 Bf=255.9 Ne=1.307 Ise=14.34f Ikf=.2847 Xtb=1.5 Br=6.092 Nc=2 Isc=0 Ikr=0 Rc=1 Cjc=7.306p Mjc=.3416 Vjc=.75 Fc=.5 Cje=22.01p Mje=.377 Vje=.75 Tr=46.91n Tf=411.1p Itf=.6 Vtf=1.7 Xtf=3 Rb=10)",
            "BC547": ".model BC547 NPN(Is=1.8f Xti=3 Eg=1.11 Vaf=100 Bf=400 Ne=1.3 Ise=50f Ikf=80m Xtb=1.5 Br=6.5 Nc=2 Isc=0 Ikr=0 Rc=1 Cjc=4p Mjc=.33 Vjc=.75 Fc=.5 Cje=8p Mje=.34 Vje=.75 Tr=10n Tf=300p Itf=.4 Vtf=4 Xtf=6 Rb=10)",

            # PNP \u6676\u4f53\u7ba1
            "2N3906": ".model 2N3906 PNP(Is=1.41f Xti=3 Eg=1.11 Vaf=18.7 Bf=259.5 Ne=1.5 Ise=0 IKF=80m Xtb=1.5 Br=9.627 Nc=2 Isc=0 Ikr=0 Rc=2.5 Cjc=9.728p Mjc=.5776 Vjc=.75 Fc=.5 Cje=8.063p Mje=.3677 Vje=.75 Tr=33.42n Tf=179.3p Itf=.4 Vtf=4 Xtf=6 Rb=10)",

            # \u4e8c\u6781\u7ba1
            "1N4148": ".model 1N4148 D(Is=2.52n Rs=.568 N=1.752 Cjo=4p M=.4 tt=20n)",
            "1N4001": ".model 1N4001 D(Is=14.11n Rs=33.89m N=1.984 Cjo=25.87p M=.38 tt=5.7u)",
            "1N4007": ".model 1N4007 D(Is=14.11n Rs=33.89m N=1.984 Cjo=25.87p M=.38 tt=5.7u BV=1000)",

            # LED
            "LED": ".model LED D(Is=1e-20 N=2 Eg=2.2 Cjo=50p M=.5)",

            # MOSFET
            "IRF540": ".model IRF540 NMOS(Vto=4 Rd=0.044 Rg=3 Rs=0.01 Vds=100 Vgs=20)",

            # \u5916\u8bbe\u6a21\u578b
            "Speaker": ".subckt Speaker 1 2\nR_spk 1 2 8\n.ends",
            "Microphone": ".subckt Microphone 1 2\nR_mic 1 2 1k\n.ends",

            # \u7a33\u538b\u4e8c\u6781\u7ba1 (Zener Diodes) - 1N47xx \u7cfb\u5217
            # BV = \u7a33\u538b\u503c, Is = \u53cd\u5411\u9971\u548c\u7535\u6d41
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
            # \u65e0 A \u540e\u7f00\u7684\u578b\u53f7\u522b\u540d（\u517c\u5bb9\u6027）
            "1N4733": ".model 1N4733 D(Is=1n N=1 BV=5.1 IBV=49m Cjo=550p)",
            "1N4742": ".model 1N4742 D(Is=1n N=1 BV=12 IBV=21m Cjo=550p)",

            # \u884c\u4e3a\u7ea7 78xx \u7a33\u538b\u5668\u6a21\u578b (1=IN, 2=GND, 3=OUT)
            # \u652f\u6301\u591a\u79cd\u8f93\u51fa\u7535\u538b\u7248\u672c
            "LM7805": ".SUBCKT LM7805 1 2 3\nB1 3 2 V=V(1,2)>7 ? 5 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7806": ".SUBCKT LM7806 1 2 3\nB1 3 2 V=V(1,2)>8 ? 6 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7808": ".SUBCKT LM7808 1 2 3\nB1 3 2 V=V(1,2)>10 ? 8 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7809": ".SUBCKT LM7809 1 2 3\nB1 3 2 V=V(1,2)>11 ? 9 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7810": ".SUBCKT LM7810 1 2 3\nB1 3 2 V=V(1,2)>12 ? 10 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7812": ".SUBCKT LM7812 1 2 3\nB1 3 2 V=V(1,2)>14 ? 12 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7815": ".SUBCKT LM7815 1 2 3\nB1 3 2 V=V(1,2)>17 ? 15 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7818": ".SUBCKT LM7818 1 2 3\nB1 3 2 V=V(1,2)>20 ? 18 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7824": ".SUBCKT LM7824 1 2 3\nB1 3 2 V=V(1,2)>26 ? 24 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            # TO-220 \u5c01\u88c5\u53d8\u4f53（\u4e0e\u57fa\u672c\u578b\u53f7\u529f\u80fd\u76f8\u540c）
            "LM7805_TO220": ".SUBCKT LM7805_TO220 1 2 3\nB1 3 2 V=V(1,2)>7 ? 5 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            "LM7812_TO220": ".SUBCKT LM7812_TO220 1 2 3\nB1 3 2 V=V(1,2)>14 ? 12 : V(1,2)-2\nR1 3 2 1k\n.ENDS",
            # \u8d34\u7247\u7248\u672c\u522b\u540d
            "MC78L05_SO8": ".SUBCKT MC78L05_SO8 1 2 3\nB1 3 2 V=V(1,2)>7 ? 5 : V(1,2)-2\nR1 3 2 1k\n.ENDS"
        }

        # \u8fd0\u653e\u7b49 IC \u5fc5\u987b\u4f7f\u7528 .include \u5f15\u7528 .SUBCKT \u6587\u4ef6
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
        \u4f7f\u7528\u4e13\u5bb6\u6a21\u5757\u8fdb\u884c\u4eff\u771f\u8bc4\u4f30

        Args:
            spice_code: SPICE \u7f51\u8868\u4ee3\u7801
            plan_data: \u89c4\u5212\u6570\u636e
            expert: \u7535\u8def\u4e13\u5bb6\u5b9e\u4f8b
            workspace_dir: \u5de5\u4f5c\u76ee\u5f55
            iteration: \u5f53\u524d\u8fed\u4ee3\u6b21\u6570
            use_hard_threshold: \u662f\u5426\u4f7f\u7528\u786c\u9608\u503c\u5224\u51b3（\u4e0d\u4f7f\u7528 LLM）

        Returns:
            Tuple[bool, str, dict]: (\u662f\u5426\u901a\u8fc7, \u53cd\u9988\u4fe1\u606f, \u5b9e\u6d4b\u6307\u6807dict)
        """
        print(f"\n🔎 [Ngspice Critic] \u6b63\u5728\u7ec4\u88c5\u6d4b\u8bd5\u5e73\u53f0\u5e76\u542f\u52a8\u7269\u7406\u4eff\u771f...")

        requirement = plan_data.get("elaborated_requirement", "")

        # \u4ece\u4e13\u5bb6\u83b7\u53d6\u4eff\u771f\u914d\u7f6e
        config = expert.get_simulation_config()
        print(f"   🔍 \u8bc6\u522b\u7535\u8def\u7c7b\u578b: {expert.get_circuit_description()} ({expert.circuit_type})")

        # \u51c6\u5907\u4eff\u771f\u6587\u4ef6
        cir_file = os.path.join(workspace_dir, f"sim_v{iteration}.cir")

        # \u6ce8\u5165\u6a21\u578b
        retrieved_path = os.path.join(workspace_dir, "retrieved.json")
        with open(retrieved_path, 'r', encoding='utf-8') as f:
            retrieved_data = json.load(f)

        injected_models = "* --- \u52a8\u6001\u6a21\u578b\u6302\u8f7d\u533a ---\n"
        added_models = set()  # \u53bb\u91cd\u96c6\u5408，\u9632\u6b62\u91cd\u590d\u6dfb\u52a0\u540c\u4e00\u6a21\u578b
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
            # 🔧 \u65b0\u589e：\u901a\u7528\u7b26\u53f7\u6620\u5c04 - \u5f53 lib_id \u662f\u901a\u7528\u7b26\u53f7\u65f6，\u6ce8\u5165\u5bf9\u5e94\u7684\u9ed8\u8ba4\u6a21\u578b
            elif lib_id == "D":
                # \u901a\u7528\u4e8c\u6781\u7ba1\u7b26\u53f7，\u6ce8\u5165 1N4001 \u4f5c\u4e3a\u9ed8\u8ba4\u6a21\u578b
                if "1N4001" not in added_models:
                    injected_models += self.TIER2_MODELS["1N4001"] + "\n"
                    added_models.add("1N4001")
                # \u540c\u65f6\u6ce8\u5165 1N4148 \u5e38\u7528\u6a21\u578b
                if "1N4148" not in added_models:
                    injected_models += self.TIER2_MODELS["1N4148"] + "\n"
                    added_models.add("1N4148")
            elif lib_id == "Q_NPN":
                # \u901a\u7528 NPN \u6676\u4f53\u7ba1\u7b26\u53f7，\u6ce8\u5165 2N3904 \u4f5c\u4e3a\u9ed8\u8ba4\u6a21\u578b
                if "2N3904" not in added_models:
                    injected_models += self.TIER2_MODELS["2N3904"] + "\n"
                    added_models.add("2N3904")
            elif lib_id == "Q_PNP":
                # \u901a\u7528 PNP \u6676\u4f53\u7ba1\u7b26\u53f7，\u6ce8\u5165 2N3906 \u4f5c\u4e3a\u9ed8\u8ba4\u6a21\u578b
                if "2N3906" not in added_models:
                    injected_models += self.TIER2_MODELS["2N3906"] + "\n"
                    added_models.add("2N3906")

        # 🔧 \u65b0\u589e：\u626b\u63cf SPICE \u4ee3\u7801\u4e2d\u4f7f\u7528\u7684\u6a21\u578b\u540d，\u81ea\u52a8\u6ce8\u5165\u7f3a\u5931\u7684\u6a21\u578b
        # \u68c0\u6d4b\u4e8c\u6781\u7ba1\u6a21\u578b (Dxxx node node MODEL_NAME)
        diode_models = re.findall(r'^D\w+\s+\S+\s+\S+\s+(\w+)', spice_code, re.MULTILINE)
        for model_name in set(diode_models):
            model_upper = model_name.upper()
            if model_upper in self.TIER2_MODELS and model_upper not in added_models:
                injected_models += self.TIER2_MODELS[model_upper] + "\n"
                added_models.add(model_upper)
                print(f"   [\u6a21\u578b\u6ce8\u5165] \u68c0\u6d4b\u5230\u4e8c\u6781\u7ba1\u6a21\u578b '{model_upper}'，\u5df2\u81ea\u52a8\u6ce8\u5165")

        # \u68c0\u6d4b\u6676\u4f53\u7ba1\u6a21\u578b (Qxxx node node node MODEL_NAME)
        bjt_models = re.findall(r'^Q\w+\s+\S+\s+\S+\s+\S+\s+(\w+)', spice_code, re.MULTILINE)
        for model_name in set(bjt_models):
            model_upper = model_name.upper()
            if model_upper in self.TIER2_MODELS and model_upper not in added_models:
                injected_models += self.TIER2_MODELS[model_upper] + "\n"
                added_models.add(model_upper)
                print(f"   [\u6a21\u578b\u6ce8\u5165] \u68c0\u6d4b\u5230\u6676\u4f53\u7ba1\u6a21\u578b '{model_upper}'，\u5df2\u81ea\u52a8\u6ce8\u5165")

        # \u6784\u5efa\u63a7\u5236\u5757
        output_node = config.get('output_node', 'OUT')
        control_block, output_file = self._build_control_block(
            config, workspace_dir, iteration, output_node
        )

        # \u6e05\u7406 LLM \u53ef\u80fd\u751f\u6210\u7684\u6b8b\u7f3a\u63a7\u5236\u5757\u548c .end
        spice_core = re.sub(r'\.control.*?\.endc', '', spice_code, flags=re.DOTALL | re.IGNORECASE)
        spice_core = re.sub(r'^\.end\s*$', '', spice_core, flags=re.MULTILINE)
        spice_core = re.sub(r'\.end\s*$', '', spice_core, flags=re.DOTALL)
        spice_core = re.sub(r'\.SUBCKT\s+LM2904.*?\.ENDS.*?\n', '', spice_core, flags=re.DOTALL | re.IGNORECASE)
        spice_core = re.sub(r'\.SUBCKT\s+LM358.*?\.ENDS.*?\n', '', spice_core, flags=re.DOTALL | re.IGNORECASE)
        spice_core = re.sub(r'\.MODEL\s+LM2904.*?\n', '', spice_core, flags=re.IGNORECASE)
        spice_core = re.sub(r'\.MODEL\s+LM358.*?\n', '', spice_core, flags=re.IGNORECASE)

        # ===== \u65b0\u589e：\u6e05\u7406 LLM \u5e7b\u89c9\u7684\u4e0d\u652f\u6301\u5143\u4ef6 =====
        # 1. \u5f00\u5173 (SWxxx) - \u66ff\u6362\u4e3a 0.1Ω \u7535\u963b（\u8fd1\u4f3c\u76f4\u901a）
        spice_core = re.sub(r'^(SW\d*)\s+(\S+)\s+(\S+)\s+(\S+)', r'R\1 \2 \3 0.1', spice_core, flags=re.MULTILINE | re.IGNORECASE)

        # 2. \u4fdd\u9669\u4e1d (Fxxx) - \u66ff\u6362\u4e3a 0.01Ω \u7535\u963b（\u8fd1\u4f3c\u76f4\u901a）
        spice_core = re.sub(r'^(F\d*)\s+(\S+)\s+(\S+)\s+([\d.]+[a-zA-Z]?)', r'R\1 \2 \3 0.01', spice_core, flags=re.MULTILINE | re.IGNORECASE)

        # 3. \u7ee7\u7535\u5668 (Kxxx) - \u79fb\u9664（Ngspice \u4e0d\u652f\u6301\u7ee7\u7535\u5668\u6a21\u578b）
        spice_core = re.sub(r'^K\d+.*$', '', spice_core, flags=re.MULTILINE | re.IGNORECASE)

        # 4. \u53d8\u538b\u5668 (Txxx) - \u66ff\u6362\u4e3a\u7406\u60f3\u8026\u5408\u7535\u611f（\u7b80\u5316\u5904\u7406）
        # \u6682\u65f6\u79fb\u9664\u590d\u6742\u7684\u53d8\u538b\u5668，\u66ff\u6362\u4e3a\u7b80\u5355\u7535\u963b
        spice_core = re.sub(r'^T\d+.*$', '* Txxx removed (unsupported)', spice_core, flags=re.MULTILINE | re.IGNORECASE)

        # \u6e05\u7406\u7a7a\u884c
        spice_core = re.sub(r'\n{3,}', '\n\n', spice_core)

        full_spice = f"* LLM Universal Testbench\n{injected_models}\n{spice_core}\n{control_block}\n.end\n"

        with open(cir_file, 'w', encoding='utf-8') as f:
            f.write(full_spice)

        # \u8fd0\u884c\u4eff\u771f
        try:
            result = subprocess.run(
                [self.ngspice_path, '-b', cir_file],
                capture_output=True, text=True, errors='ignore'
            )
        except Exception as e:
            return False, f"❌ Ngspice \u8c03\u7528\u73af\u5883\u5f02\u5e38: {e}", {}

        # \u89e3\u6790\u4eff\u771f\u7ed3\u679c
        if not os.path.exists(output_file):
            # \u68c0\u67e5 SPICE \u4ee3\u7801\u4e2d\u662f\u5426\u6709\u6b63\u786e\u7684 OUT \u8282\u70b9
            if output_node == 'OUT' and 'OUT' not in spice_core.upper():
                return False, f"❌ [\u81f4\u547d\u9519\u8bef] \u4eff\u771f\u672a\u80fd\u4ea7\u751f\u8f93\u51fa\u6570\u636e\u6587\u4ef6！\n【\u5173\u952e\u95ee\u9898】SPICE \u4ee3\u7801\u4e2d\u6ca1\u6709\u540d\u4e3a 'OUT' \u7684\u8282\u70b9！\n\u8bf7\u68c0\u67e5：\n1. \u8f93\u51fa\u8282\u70b9\u5fc5\u987b\u547d\u540d\u4e3a OUT（\u4e0d\u662f\u6570\u5b57\u5982 1, 2, 3）\n2. \u793a\u4f8b：R1 IN OUT 220, D_Z OUT 0 1N4733A\n3. \u786e\u4fdd\u6240\u6709\u5143\u4ef6\u6b63\u786e\u8fde\u63a5\n\u8bf7\u91cd\u65b0\u751f\u6210\u6b63\u786e\u7684 SPICE \u7f51\u8868！", {}
            return False, f"❌ [\u81f4\u547d\u9519\u8bef] \u4eff\u771f\u672a\u80fd\u4ea7\u751f\u8f93\u51fa\u6570\u636e\u6587\u4ef6！\u8bf7\u68c0\u67e5：1. \u8f93\u51fa\u8282\u70b9\u662f\u5426\u547d\u540d\u4e3a OUT；2. \u662f\u5426\u6b63\u786e\u63a5\u4e86VCC\u548cGND；3. \u7a33\u538b\u4e8c\u6781\u7ba1\u662f\u5426\u53cd\u5411\u504f\u7f6e（\u9634\u6781\u63a5OUT，\u9633\u6781\u63a5GND）。\u8bf7\u91cd\u65b0\u8c03\u6574 SPICE \u7f51\u8868！", {}

        # \u8bfb\u53d6\u4eff\u771f\u6570\u636e
        x_data, y_data = self._read_simulation_output(output_file)

        if not x_data:
            return False, "❌ [\u6570\u636e\u63d0\u53d6\u5931\u8d25] \u4eff\u771f\u66f2\u7ebf\u4e3a\u7a7a，\u8fd9\u8bf4\u660e\u7535\u8def\u8f93\u51fa\u8282\u70b9\u6ca1\u6709\u4fe1\u53f7。\u8bf7\u68c0\u67e5\u8fde\u7ebf！", {}

        # \u4f7f\u7528\u4e13\u5bb6\u89e3\u6790\u6570\u636e
        metrics = expert.parse_simulation_data(x_data, y_data, config)

        if not metrics:
            return False, "❌ [\u6307\u6807\u89e3\u6790\u5931\u8d25] \u65e0\u6cd5\u4ece\u4eff\u771f\u6570\u636e\u4e2d\u63d0\u53d6\u6709\u6548\u6307\u6807。", {}

        # \u6d4b\u91cf DC \u529f\u8017
        power_mw = self._measure_dc_power(full_spice, workspace_dir, iteration)
        if power_mw is not None:
            metrics['power_consumption_mw'] = power_mw

        # \u683c\u5f0f\u5316\u6307\u6807
        metrics_str = self._format_metrics(metrics)
        print(f"   📈 {metrics_str.replace(chr(10), ' | ')}")

        # \u6839\u636e\u914d\u7f6e\u9009\u62e9\u5224\u51b3\u65b9\u5f0f
        if use_hard_threshold:
            # \u786c\u9608\u503c\u5224\u51b3（\u4e0d\u4f7f\u7528 LLM）
            print("   ⚖️ \u4f7f\u7528\u786c\u9608\u503c\u5224\u51b3（\u65e0 LLM）...")
            passed, feedback = expert.hard_threshold_judge(requirement, metrics)
            return passed, feedback, metrics
        else:
            # LLM \u5224\u51b3（\u9ed8\u8ba4\u65b9\u5f0f）
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
        """\u6839\u636e\u4eff\u771f\u914d\u7f6e\u751f\u6210\u63a7\u5236\u5757"""

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
            # \u9ed8\u8ba4 AC \u5206\u6790
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
        """\u8bfb\u53d6\u4eff\u771f\u8f93\u51fa\u6587\u4ef6"""
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
            print(f"   ⚠️ [\u8bfb\u53d6\u9519\u8bef] {e}")

        return x_data, y_data

    def _measure_dc_power(self, spice_code: str, workspace_dir: str, iteration: int) -> Optional[float]:
        """\u8fd0\u884c .op \u5206\u6790\u6d4b\u91cf DC \u529f\u8017 (mW)"""
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
        """\u683c\u5f0f\u5316\u6307\u6807\u63cf\u8ff0"""
        lines = []
        for key, value in metrics.items():
            if isinstance(value, float):
                # \u6ce8\u610f：gain \u76f8\u5173\u7684 key \u53ef\u80fd\u5305\u542b freq（\u5982 mid_freq_gain_db）
                # \u6240\u4ee5\u8981\u5148\u5224\u65ad gain，\u518d\u5224\u65ad freq
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
        """LLM \u5224\u51b3"""
        print("   ⚖️ \u6b63\u5728\u53ec\u5524\u5927\u6a21\u578b\u88c1\u5224\u5b98\u8bc4\u4f30\u6d4b\u91cf\u6570\u636e...")

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

            # \u9632\u5f39\u7ea7 JSON \u63d0\u53d6
            match = re.search(r'```json\s*(.*?)\s*```', raw, flags=re.DOTALL | re.IGNORECASE)
            if match:
                clean_json = match.group(1).strip()
            else:
                clean_json = raw[raw.find('{'):raw.rfind('}')+1]

            data = json.loads(clean_json)

            if data['passed']:
                print(f"   ✅ [\u5224\u51b3\u901a\u8fc7] {data['reason']}")
            else:
                print(f"   ⚠️ [\u5224\u51b3\u4e0d\u8fbe\u6807] {data['reason']}")

            return data['passed'], data.get('feedback', '')

        except Exception as e:
            return False, f"❌ \u88c1\u5224\u5b98\u89e3\u6790\u5f02\u5e38: {e}"
