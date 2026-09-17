import json
import os
import sys
import chromadb
from sentence_transformers import SentenceTransformer, util
import re
from pathlib import Path


FRAMEWORK_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FRAMEWORK_DIR.parent


# ==========================================
# \u7b2c\u4e00\u90e8\u5206：\u5185\u7f6e\u7684\u667a\u80fd\u68c0\u7d22\u5668\u7c7b
# ==========================================
class IntelligentRetriever:
    def __init__(self, persist_directory=None, enable_exact_match=True):
        self.enable_exact_match = enable_exact_match
        if persist_directory is None:
            persist_directory = os.environ.get("EDA_CHROMA_DIR") or str(FRAMEWORK_DIR / "chroma_db")
        if not os.path.exists(persist_directory):
            if os.path.exists("../chroma_db"):
                persist_directory = "../chroma_db"
            elif os.path.exists("D:/EDA/new/chroma_db"):
                persist_directory = "D:/EDA/new/chroma_db"
            else:
                raise FileNotFoundError(f"❌ \u627e\u4e0d\u5230\u5411\u91cf\u6570\u636e\u5e93: {persist_directory}")

        print(f"🔌 \u8fde\u63a5\u6570\u636e\u5e93: {persist_directory}...")
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_collection("electronic_components")

        print("⏳ \u52a0\u8f7d Embedding \u6a21\u578b...")
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

       # ==========================================================
        # 🎯 【\u6700\u9ad8\u4f18\u5148\u7ea7】：\u7cbe\u786e\u9501\u5b9a\u767b\u8bb0\u518c (\u76f4\u63a5\u786c\u67e5 lib_id，\u7ed5\u8fc7\u5411\u91cf\u641c\u7d22)
        # ==========================================================
        self.exact_match_registry = {
            # === \u8fd0\u7b97\u653e\u5927\u5668\u7cfb\u5217 ===
            "opamp": "LM2904",
            "op-amp": "LM2904",
            "operational amplifier": "LM2904",
            "lm358": "LM2904",
            "lm2904": "LM2904",
            "ne5532": "LM2904",
            
            # === \u5fae\u63a7\u5236\u5668\u7cfb\u5217 ===
            "attiny85": "ATtiny25V-10S",
            "mcuattiny85": "ATtiny25V-10S",
            "mcu attiny85": "ATtiny25V-10S",
            
            # === 🔌 \u65b0\u589e：\u8fde\u63a5\u5668/\u8f93\u5165\u8f93\u51fa\u7aef\u5b50\u5f3a\u5236\u7ed1\u5b9a ===
            # \u53ea\u8981\u5927\u6a21\u578b\u7684 search_query \u5305\u542b\u5de6\u8fb9\u7684\u8bcd，\u76f4\u63a5\u65e0\u8111\u63d0\u53d6\u53f3\u8fb9\u7684 lib_id
            "connector": "Conn_01x01",
            "header": "Conn_01x01",
            "pin": "Conn_01x01",
            "input": "Conn_01x01",
            "output": "Conn_01x01",
            "terminal": "Conn_01x01",

            # === \u8fde\u63a5\u5668\u7cfb\u5217 ===
            "dc jack": "Barrel_Jack",
            "dc power jack": "Barrel_Jack",

            # === \u5b9a\u65f6\u5668\u7cfb\u5217 ===
            "ne555": "NE555D",

            # === \u57fa\u7840\u65e0\u6e90\u5668\u4ef6 ===
            "capacitor": "C",
            "resistor": "R",
            "inductor": "L",

            "potentiometer": "R_Potentiometer",
            "spst switch": "SW_SPST",
            "transformer": "Transformer_1P_1S",
            "bnc": "Conn_Coaxial",
            "transistor npn": "2N2219",
            "transistor": "2N2219",
            "transistor fet": "GS66502B",
            "mosfet": "GS66502B"

        }
    def _try_exact_match(self, raw_query):
        q = raw_query.lower().strip()
        target_lib_id = None
        
        for trigger_word, lib_id in self.exact_match_registry.items():
            if trigger_word in q:
                target_lib_id = lib_id
                break
                
        if not target_lib_id:
            return None 
            
        try:
            results = self.collection.get(
                where={"lib_id": target_lib_id},
                include=["metadatas"]
            )
            if results and results['metadatas'] and len(results['metadatas']) > 0:
                print(f"      🎯 [\u7edd\u5bf9\u9501\u5b9a\u6a21\u5757] \u547d\u4e2d\u89c4\u5219 '{trigger_word}' -> \u76f4\u63a5\u63d0\u53d6\u5e93\u5143\u4ef6: {target_lib_id}")
                meta = results['metadatas'][0]
                parsed_data = self._parse_metadata(meta, 1.0, raw_query)
                return {"status": "success", "data": parsed_data}
        except Exception as e:
            print(f"      ⚠️ [\u7edd\u5bf9\u9501\u5b9a\u6a21\u5757] \u8bd5\u56fe\u63d0\u53d6 {target_lib_id} \u5931\u8d25，\u5c06\u9000\u56de\u5e38\u89c4\u641c\u7d22。\u539f\u56e0: {e}")
            
        return None

    def _optimize_query(self, raw_query):
        q = raw_query.lower().strip()
        print(f"      [\u8c03\u8bd5] \u5206\u6790: '{raw_query}'", end="")

        # =========================================================
        # 🔥 \u82af\u7247\u5bb6\u65cf\u667a\u80fd\u6620\u5c04 (\u4f60\u7684\u4e13\u5c5e\u89c4\u5219)
        # =========================================================
        
        # 1. \u62e6\u622a 78/79 \u7cfb\u5217\u7a33\u538b\u5668 (\u5982 78L12, 79L12, 7805, 7905 \u7b49)
        # \u6b63\u5219\u89e3\u91ca：\u5339\u914d 78 \u6216 79 \u5f00\u5934，\u4e2d\u95f4\u53ef\u80fd\u8ddf\u7740\u4e00\u4e2a\u5b57\u6bcd(\u5982L/M)，\u6700\u540e\u662f\u4e24\u4f4d\u6570\u5b57
        # \u91cd\u8981：\u6570\u636e\u5e93\u4e2d\u53ef\u80fd\u6ca1\u6709\u8fd9\u4e9b\u5668\u4ef6，\u4f46\u7cfb\u7edf\u6709 SPICE \u6a21\u578b
        # \u8fd4\u56de\u7279\u6b8a\u6807\u8bb0，\u8ba9\u540e\u7eed\u6d41\u7a0b\u521b\u5efa\u865a\u62df\u5668\u4ef6
        match_78xx = re.search(r'(7[89][a-z]?\d{2})', q)
        if match_78xx:
            original_model = match_78xx.group(1).upper()
            # \u6807\u51c6\u5316\u578b\u53f7\u540d：LM7805, LM7812 \u7b49
            if not original_model.startswith('LM'):
                original_model = 'LM' + original_model
            print(f" -> \u547d\u4e2d\u89c4\u5219: \u5c5e\u4e8e 78/79xx \u7a33\u538b\u5bb6\u65cf，\u4f7f\u7528\u865a\u62df\u5668\u4ef6 '{original_model}'")
            return f"__VIRTUAL_REGULATOR__:{original_model}"

        # 2. 【\u4f18\u5148】\u62e6\u622a\u7a33\u538b\u4e8c\u6781\u7ba1\u5bb6\u65cf (\u5982 1N4733A, 1N4742A, \u6216\u57fa\u7840\u8bcd\u6c47 zener)
        # \u5fc5\u987b\u5728\u666e\u901a\u4e8c\u6781\u7ba1\u89c4\u5219\u4e4b\u524d，\u5426\u5219\u4f1a\u88ab 1n\d{4 \u6b63\u5219\u5148\u5339\u914d
        match_zener = re.search(r'1n47\d{2}[a-z]?', q, re.IGNORECASE)
        if "zener" in q or match_zener:
            if match_zener:
                zener_model = match_zener.group(0).upper()
            else:
                # \u9ed8\u8ba4\u4f7f\u7528 5.1V \u7a33\u538b\u4e8c\u6781\u7ba1
                zener_model = "1N4733A"
            print(f" -> \u547d\u4e2d\u89c4\u5219: \u5c5e\u4e8e\u7a33\u538b\u4e8c\u6781\u7ba1，\u4f7f\u7528\u865a\u62df\u5668\u4ef6 '{zener_model}'")
            return f"__VIRTUAL_ZENER__:{zener_model}"

        # 3. \u62e6\u622a\u4e8c\u6781\u7ba1\u5bb6\u65cf (\u5982 1n4148, 1n4001, 1n4007, \u6216\u57fa\u7840\u8bcd\u6c47 diode)
        # \u6b63\u5219\u89e3\u91ca：\u5339\u914d 1n \u540e\u9762\u8ddf\u7740 4 \u4f4d\u6570\u5b57\u7684\u578b\u53f7
        if "diode" in q or re.search(r'1n\d{4}', q):
            # \u6392\u9664\u53d1\u5149\u4e8c\u6781\u7ba1(LED)\u548c\u7a33\u538b\u4e8c\u6781\u7ba1(Zener)
            if "led" not in q and "zener" not in q:
                print(" -> \u547d\u4e2d\u89c4\u5219: \u5c5e\u4e8e\u57fa\u7840\u4e8c\u6781\u7ba1，\u7edf\u4e00\u6620\u5c04\u4e3a 'D'")
                return "D" 

        if "resistor" in q or q == "r":
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'Resistor'")
            return "Resistor"

        if "resistor" in q or q == "r":
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'Resistor'")
            return "Resistor"
        if "capacitor" in q:
            if "polarized" in q or "electrolytic" in q:
                print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'Capacitor'")
                return "Capacitor"
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'Capacitor'")
            return "Capacitor"
        if "inductor" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'L'")
            return "L"
        if "diode" in q and "led" not in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'D'")
            return "D"
        if "led" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'Light emitting diode'")
            return "Light emitting diode"
        if "crystal" in q or "oscillator" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'Crystal_Small'")
            return "Crystal_Small"
        if "switch" in q and "button" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'SW_Push'")
            return "SW_Push"
        if "stm32" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'STMicroelectronics'")
            return "STMicroelectronics"
        if "opamp" in q or "op-amp" in q or "operational amplifier" in q or "lm2904" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'LM2904 Dual Operational Amplifiers'")
            return "LM2904 Dual Operational Amplifiers"
        if "regulator" in q or "ldo" in q or "1117" in q or "7805" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'Regulator_Linear'")
            return "Regulator_Linear"
        if "mosfet" in q or "nmos" in q or "pmos" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'GS66502B'")
            return "GS66502B"
        if "npn" in q or "pnp" in q or "bjt" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a '2N2219'")
            return "2N2219"
        if "connector" in q or "header" in q or "pin" in q or "input" in q or "output" in q:
            print(" -> \u547d\u4e2d\u89c4\u5219: \u5f3a\u5236\u8f6c\u4e3a 'Conn_01x01' (\u5355\u5f15\u811a\u4fe1\u53f7\u7aef\u5b50)")
            return "Conn_01x01"  # \u5982\u679c\u4f60\u5e93\u91cc\u5355\u5f15\u811a\u53eb\u522b\u7684\u540d\u5b57，\u8bf7\u66ff\u6362\u6210\u4f60\u5e93\u91cc\u7684\u771f\u5b9e\u540d\u5b57

        print(" -> \u65e0\u89c4\u5219，\u4fdd\u6301\u539f\u6837")
        return raw_query

    def search_component(self, query_text, expected_query=None, n_candidates=15, validation_threshold=0.4):
        # 1. \u7cbe\u786e\u9501\u5b9a（\u5f3a\u5236\u6620\u5c04\u89c4\u5219，\u4fdd\u6301\u4e0d\u53d8）
        if self.enable_exact_match:
            exact_match_result = self._try_exact_match(query_text)
            if exact_match_result:
                return exact_match_result

        # 2. \u67e5\u8be2\u4f18\u5316/\u5f3a\u5236\u8f6c\u6362（\u68c0\u67e5\u662f\u5426\u547d\u4e2d\u5f3a\u5236\u8f6c\u6362\u89c4\u5219）
        optimized_query = self._optimize_query(query_text)
        is_forced_conversion = (optimized_query != query_text)

        # 2.5 【\u7279\u6b8a\u5904\u7406】\u865a\u62df\u7a33\u538b\u5668（78xx \u7cfb\u5217\u4e0d\u5728\u6570\u636e\u5e93\u4e2d）
        # \u5fc5\u987b\u5728 _optimize_query \u4e4b\u540e\u68c0\u67e5，\u56e0\u4e3a\u6807\u8bb0\u662f\u7531\u5b83\u8fd4\u56de\u7684
        if optimized_query.startswith("__VIRTUAL_REGULATOR__:"):
            actual_model = optimized_query.split(":")[1]
            # \u63d0\u53d6\u8f93\u51fa\u7535\u538b（\u5982 LM7812 -> 12V）
            voltage_match = re.search(r'LM78(\d+)', actual_model)
            voltage = voltage_match.group(1) if voltage_match else "05"
            print(f"      🔧 [\u865a\u62df\u7a33\u538b\u5668] \u521b\u5efa {actual_model} ({voltage}V) \u865a\u62df\u5668\u4ef6")

            # \u751f\u6210\u7b26\u5408 KiCad \u683c\u5f0f\u7684\u7b26\u53f7\u5b9a\u4e49
            raw_symbol = f'''(symbol "{actual_model}"
\t\t(pin_names hide)
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(property "Reference" "U"
\t\t\t(at 0 5.08 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Value" "{actual_model}"
\t\t\t(at 0 -5.08 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Footprint" "Package_TO_SOT_THT:TO-220-3_Vertical"
\t\t\t(at 0 0 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t\t(hide yes)
\t\t\t)
\t\t)
\t\t(symbol "{actual_model}_0_1"
\t\t\t(rectangle
\t\t\t\t(start -5.08 3.81)
\t\t\t\t(end 5.08 -3.81)
\t\t\t\t(stroke
\t\t\t\t\t(width 0)
\t\t\t\t\t(type default)
\t\t\t\t)
\t\t\t\t(fill
\t\t\t\t\t(type background)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(symbol "{actual_model}_1_1"
\t\t\t(pin input line
\t\t\t\t(at -7.62 0 0)
\t\t\t\t(length 2.54)
\t\t\t\t(name "IN")
\t\t\t\t(number "1")
\t\t\t)
\t\t\t(pin power_in line
\t\t\t\t(at 0 -6.35 90)
\t\t\t\t(length 2.54)
\t\t\t\t(name "GND")
\t\t\t\t(number "2")
\t\t\t)
\t\t\t(pin output line
\t\t\t\t(at 7.62 0 180)
\t\t\t\t(length 2.54)
\t\t\t\t(name "OUT")
\t\t\t\t(number "3")
\t\t\t)
\t\t)
\t)'''

            # \u8fd4\u56de\u4e00\u4e2a\u6807\u51c6\u7684 TO-220 \u5c01\u88c5\u7a33\u538b\u5668\u865a\u62df\u5668\u4ef6
            virtual_data = {
                "lib_id": actual_model,
                "name": actual_model,
                "description": f"Linear Voltage Regulator {voltage}V (Virtual)",
                "keywords": "voltage regulator linear",
                "source_library": "Virtual_Library",
                "pins": [
                    {"num": "1", "name": "IN", "type": "power_in", "x": -7.62, "y": 0, "rot": 0},
                    {"num": "2", "name": "GND", "type": "power_in", "x": 0, "y": -6.35, "rot": 90},
                    {"num": "3", "name": "OUT", "type": "power_out", "x": 7.62, "y": 0, "rot": 180}
                ],
                "footprint": "Package_TO_SOT_THT:TO-220-3_Vertical",
                "raw_symbol_definition": raw_symbol
            }
            return {"status": "success", "data": virtual_data}

        # 2.6 【\u7279\u6b8a\u5904\u7406】\u865a\u62df\u7a33\u538b\u4e8c\u6781\u7ba1（1N47xx \u7cfb\u5217\u4e0d\u5728\u6570\u636e\u5e93\u4e2d）
        if optimized_query.startswith("__VIRTUAL_ZENER__:"):
            actual_model = optimized_query.split(":")[1]

            # \u7a33\u538b\u503c\u6620\u5c04\u8868
            zener_voltages = {
                '1N4728A': 3.3, '1N4729A': 3.6, '1N4730A': 3.9, '1N4731A': 4.3,
                '1N4732A': 4.7, '1N4733A': 5.1, '1N4734A': 5.6, '1N4735A': 6.2,
                '1N4736A': 6.8, '1N4737A': 7.5, '1N4738A': 8.2, '1N4739A': 9.1,
                '1N4740A': 10.0, '1N4741A': 11.0, '1N4742A': 12.0, '1N4743A': 13.0,
                '1N4744A': 15.0, '1N4745A': 16.0, '1N4746A': 18.0, '1N4747A': 20.0,
                '1N4748A': 22.0, '1N4749A': 24.0, '1N4750A': 27.0, '1N4751A': 30.0,
                '1N4733': 5.1, '1N4742': 12.0,  # \u65e0 A \u540e\u7f00\u7684\u517c\u5bb9\u578b\u53f7
            }
            voltage = zener_voltages.get(actual_model, 5.1)
            print(f"      🔧 [\u865a\u62df\u7a33\u538b\u4e8c\u6781\u7ba1] \u521b\u5efa {actual_model} ({voltage}V) \u865a\u62df\u5668\u4ef6")

            # \u751f\u6210\u7b26\u5408 KiCad \u683c\u5f0f\u7684\u7a33\u538b\u4e8c\u6781\u7ba1\u7b26\u53f7\u5b9a\u4e49
            raw_symbol = f'''(symbol "{actual_model}"
\t\t(pin_numbers hide)
\t\t(pin_names (offset 1.016) hide)
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(property "Reference" "D"
\t\t\t(at 0 2.54 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Value" "{actual_model}"
\t\t\t(at 0 -3.81 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Footprint" "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal"
\t\t\t(at 0 0 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t\t(hide yes)
\t\t\t)
\t\t)
\t\t(property "ki_description" "Zener diode {voltage}V"
\t\t\t(at 0 0 0)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t\t(hide yes)
\t\t\t)
\t\t)
\t\t(symbol "{actual_model}_0_1"
\t\t\t(polyline
\t\t\t\t(pts
\t\t\t\t\t(xy 1.27 0) (xy -1.27 0)
\t\t\t\t)
\t\t\t\t(stroke
\t\t\t\t\t(width 0)
\t\t\t\t\t(type default)
\t\t\t\t)
\t\t\t\t(fill
\t\t\t\t\t(type none)
\t\t\t\t)
\t\t\t)
\t\t\t(polyline
\t\t\t\t(pts
\t\t\t\t\t(xy -1.27 -1.27) (xy -1.27 1.27) (xy 1.27 0) (xy -1.27 -1.27)
\t\t\t\t)
\t\t\t\t(stroke
\t\t\t\t\t(width 0.2032)
\t\t\t\t\t(type default)
\t\t\t\t)
\t\t\t\t(fill
\t\t\t\t\t(type outline)
\t\t\t\t)
\t\t\t)
\t\t\t(polyline
\t\t\t\t(pts
\t\t\t\t\t(xy 1.27 1.27) (xy 1.27 -1.27) (xy 0.635 -0.635) (xy 1.27 0)
\t\t\t\t)
\t\t\t\t(stroke
\t\t\t\t\t(width 0.2032)
\t\t\t\t\t(type default)
\t\t\t\t)
\t\t\t\t(fill
\t\t\t\t\t(type outline)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(symbol "{actual_model}_1_1"
\t\t\t(pin passive line
\t\t\t\t(at -3.81 0 0)
\t\t\t\t(length 2.54)
\t\t\t\t(name "K")
\t\t\t\t(number "1")
\t\t\t)
\t\t\t(pin passive line
\t\t\t\t(at 3.81 0 180)
\t\t\t\t(length 2.54)
\t\t\t\t(name "A")
\t\t\t\t(number "2")
\t\t\t)
\t\t)
\t)'''

            virtual_data = {
                "lib_id": actual_model,
                "name": actual_model,
                "description": f"Zener Diode {voltage}V (Virtual)",
                "keywords": "zener diode voltage regulator",
                "source_library": "Virtual_Library",
                "pins": [
                    {"num": "1", "name": "K", "type": "passive", "x": -3.81, "y": 0, "rot": 0},
                    {"num": "2", "name": "A", "type": "passive", "x": 3.81, "y": 0, "rot": 180}
                ],
                "footprint": "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
                "raw_symbol_definition": raw_symbol
            }
            return {"status": "success", "data": virtual_data}

        # 3. \u767d\u540d\u5355\u5143\u5668\u4ef6\u76f4\u63a5\u8fdb\u884c\u5411\u91cf\u68c0\u7d22（\u4fdd\u6301\u539f\u6709\u903b\u8f91）
        whitelist = ["R", "C", "L", "D", "Speaker", "Microphone", "SW_Push", "Capacitor", "Resistor"]
        is_whitelist = query_text in whitelist or optimized_query in whitelist

        # ==================================================
        # 4. 【\u666e\u901a\u68c0\u7d22】\u9996\u5148\u5c1d\u8bd5 lib_id \u7cbe\u786e\u5339\u914d
        # \u53ea\u6709\u975e\u5f3a\u5236\u8f6c\u6362、\u975e\u767d\u540d\u5355\u7684\u5143\u5668\u4ef6\u624d\u8d70\u8fd9\u4e2a\u6d41\u7a0b
        # ==================================================
        if not is_forced_conversion and not is_whitelist:
            try:
                # \u5c1d\u8bd5\u591a\u79cd\u5f62\u5f0f\u7684\u7cbe\u786e\u5339\u914d
                match_attempts = [
                    query_text,                    # \u539f\u59cb\u67e5\u8be2
                    query_text.upper(),            # \u5927\u5199
                    query_text.lower(),            # \u5c0f\u5199
                    query_text.capitalize(),       # \u9996\u5b57\u6bcd\u5927\u5199
                ]
                # \u53bb\u91cd
                match_attempts = list(dict.fromkeys(match_attempts))

                for attempt in match_attempts:
                    direct_results = self.collection.get(
                        where={"lib_id": attempt},
                        include=["metadatas"]
                    )
                    if direct_results and direct_results['metadatas'] and len(direct_results['metadatas']) > 0:
                        print(f"      🎯 [lib_id\u7cbe\u786e\u5339\u914d] \u5143\u4ef6\u540d '{query_text}' -> \u76f4\u63a5\u547d\u4e2d\u5e93\u5143\u4ef6: '{attempt}'")
                        meta = direct_results['metadatas'][0]
                        parsed_data = self._parse_metadata(meta, 1.0, query_text)
                        return {"status": "success", "data": parsed_data}

                print(f"      ℹ️ [lib_id\u7cbe\u786e\u5339\u914d] \u672a\u627e\u5230 '{query_text}'，\u8fdb\u5165\u5411\u91cf\u68c0\u7d22\u6d41\u7a0b...")
            except Exception as e:
                print(f"      ⚠️ [lib_id\u7cbe\u786e\u5339\u914d] \u67e5\u8be2\u51fa\u9519: {e}，\u7ee7\u7eed\u5411\u91cf\u68c0\u7d22...")

        # 5. \u5411\u91cf\u68c0\u7d22\u6d41\u7a0b（\u5f3a\u5236\u8f6c\u6362、\u767d\u540d\u5355、\u6216 lib_id \u7cbe\u786e\u5339\u914d\u5931\u8d25\u540e\u6267\u884c）
        print()
        query_vector = self.model.encode([optimized_query]).tolist()
        results = self.collection.query(
            query_embeddings=query_vector,
            n_results=n_candidates,
            include=["metadatas", "distances"]
        )

        if not results['ids'] or len(results['ids'][0]) == 0:
            return {"status": "not_found", "data": None}

        candidates = []
        for i in range(len(results['ids'][0])):
            meta = results['metadatas'][0][i]
            dist = results['distances'][0][i]
            candidates.append({
                "meta": meta,
                "score": 1 - dist
            })

        # 3. \u5f3a\u529b\u91cd\u6392 (\u5305\u542b\u65b0\u589e\u7684 Keywords \u5339\u914d)
        best_match = self._rerank_results(optimized_query, candidates)
        best_meta = best_match["meta"]
        retrieved_name = best_meta.get("lib_id", "")
        
        # 4. 【\u4fdd\u7559】：\u767d\u540d\u5355\u514d\u68c0
        whitelist = ["R", "C", "L", "D", "Speaker", "Microphone", "SW_Push", "Capacitor", "Resistor"]
        if retrieved_name in whitelist or optimized_query in whitelist:
            print(f"      ✅ \u89e6\u53d1\u767d\u540d\u5355\u8c41\u514d\u6821\u9a8c -> \u91c7\u7eb3: {retrieved_name}")
            parsed_data = self._parse_metadata(best_meta, best_match["score"], query_text)
            return {"status": "success", "data": parsed_data}

        # 5. \u57fa\u4e8e\u529f\u80fd\u7684\u76f8\u4f3c\u5ea6\u6821\u9a8c\u515c\u5e95
        retrieved_desc = best_meta.get("description", "")
        retrieved_func_text = f"{retrieved_name} {retrieved_desc}"
        expected_func_text = expected_query if expected_query else query_text

        v_expected = self.model.encode([expected_func_text])
        v_retrieved = self.model.encode([retrieved_func_text])
        similarity = util.cos_sim(v_expected, v_retrieved)[0][0].item()

        if similarity < validation_threshold:
            print(f"      ⚠️ \u529f\u80fd\u6821\u9a8c\u672a\u901a\u8fc7!")
            print(f"      - \u9884\u671f\u9700\u6c42: '{expected_func_text}'")
            print(f"      - \u5b9e\u9645\u635e\u53d6: '{retrieved_name}' (\u63cf\u8ff0: {retrieved_desc})")
            return {
                "status": "validation_failed", 
                "reason": f"\u68c0\u7d22\u5230\u7684\u5143\u4ef6 '{retrieved_name}' \u529f\u80fd\u4e0d\u5339\u914d",
                "retrieved_name": retrieved_name,
                "data": None
            }
            
        print(f"      ✅ \u529f\u80fd\u6821\u9a8c\u901a\u8fc7 (\u76f8\u4f3c\u5ea6: {similarity:.2f})")
        parsed_data = self._parse_metadata(best_meta, best_match["score"], query_text)
        return {"status": "success", "data": parsed_data}

    def _rerank_results(self, query, candidates):
        """
        🔥 \u6838\u5fc3\u6539\u8fdb：\u5f15\u5165 keywords \u5339\u914d\u6253\u5206\u673a\u5236
        """
        query_clean = query.strip().lower()
        # \u5c06\u67e5\u8be2\u8bcd\u8fdb\u884c\u62c6\u5206，\u65b9\u4fbf\u4e0e keyword \u8fdb\u884c\u4ea4\u53c9\u6bd4\u5bf9
        query_words = set(query_clean.split())
        query_words.add(query_clean) # \u628a\u5b8c\u6574\u77ed\u8bed\u4e5f\u52a0\u8fdb\u53bb

        for item in candidates:
            meta = item["meta"]
            lib_id = meta.get("lib_id", "")
            lib_id_lower = lib_id.lower()
            item["final_score"] = item["score"]

            # ================= \u65b0\u589e：Keywords \u5173\u952e\u8bcd\u786c\u5339\u914d\u903b\u8f91 =================
            keywords = []
            if "keywords" in meta:
                kw_data = meta["keywords"]
                # \u5904\u7406\u6570\u636e\u5e93\u4e2d\u5b58\u50a8\u7684 JSON \u5b57\u7b26\u4e32\u6216\u539f\u751f\u5217\u8868
                if isinstance(kw_data, str):
                    try:
                        kw_list = json.loads(kw_data)
                        if isinstance(kw_list, list):
                            keywords = [str(k).lower() for k in kw_list]
                    except json.JSONDecodeError:
                        keywords = [k.strip().lower() for k in kw_data.split(',')]
                elif isinstance(kw_data, list):
                    keywords = [str(k).lower() for k in kw_data]

            keyword_set = set(keywords)
            # \u5982\u679c\u67e5\u8be2\u8bcd\u7684\u4efb\u4f55\u90e8\u5206\u547d\u4e2d\u4e86\u5143\u5668\u4ef6\u7684 keywords (\u8ba1\u7b97\u4ea4\u96c6)
            matched_keywords = query_words.intersection(keyword_set)
            
            if matched_keywords:
                # \u53ea\u8981\u547d\u4e2d\u4e00\u4e2a\u5173\u952e\u8bcd，\u7ed9\u4e88\u5de8\u5927\u52a0\u5206 (3.0 \u5206\u8db3\u4ee5\u78be\u538b\u666e\u901a\u7684\u5411\u91cf\u8ddd\u79bb\u5206\u6b67)
                item["final_score"] += 3.0 * len(matched_keywords)
                print(f"      [🎯 \u5173\u952e\u8bcd\u52a0\u5206] \u547d\u4e2d Keywords: {matched_keywords} -> \u63d0\u6743: {lib_id}")
            # ===================================================================

            # \u539f\u6709\u7684\u57fa\u4e8e lib_id \u7684\u6253\u5206\u903b\u8f91
            if lib_id_lower == query_clean:
                item["final_score"] += 10.0
            if len(lib_id) <= 2 and "_" not in lib_id:
                item["final_score"] += 2.0
            if "_" in lib_id and "_" not in query_clean:
                item["final_score"] -= 5.0

        # \u6309\u6700\u7ec8\u5f97\u5206\u964d\u5e8f\u6392\u5e8f
        candidates.sort(key=lambda x: x["final_score"], reverse=True)
        return candidates[0]

    def _parse_metadata(self, meta, score, query):
        pins_data = []
        if "pins_json" in meta:
            try:
                pins_data = json.loads(meta["pins_json"])
            except:
                pass
        return {
            "lib_id": meta["lib_id"],
            "source_library": meta.get("source_library", ""),
            "description": meta.get("description", ""),
            "raw_symbol_definition": meta.get("raw_symbol_definition", ""),
            "pins": pins_data,
            "match_score": score
        }

# ==========================================
# \u7b2c\u4e8c\u90e8\u5206：\u6267\u884c\u903b\u8f91 (main)
# ==========================================

def inspect_components(plan_file, output_file):
    if not os.path.exists(plan_file):
        print(f"❌ \u627e\u4e0d\u5230\u89c4\u5212\u6587\u4ef6: {plan_file}")
        return

    print(f"📂 \u8bfb\u53d6\u89c4\u5212\u6587\u4ef6: {plan_file} ...")
    try:
        with open(plan_file, 'r', encoding='utf-8') as f:
            plan = json.load(f)
    except Exception as e:
        print(f"❌ JSON \u8bfb\u53d6\u5931\u8d25: {e}")
        return

    print("🚀 \u521d\u59cb\u5316\u68c0\u7d22\u5668...")
    try:
        retriever = IntelligentRetriever()
    except Exception as e:
        print(f"❌ \u521d\u59cb\u5316\u5931\u8d25: {e}")
        return

    print(f"\n🔍 --- \u5f00\u59cb\u68c0\u7d22 ---")
    retrieved_data = {}
    components = plan.get('components', [])

    for idx, comp in enumerate(components):
        uid = comp.get('uid', 'Unknown')
        search_query = comp.get('search_query', '')
        planned_params = comp.get('parameters', {})

        print(f"[{idx + 1}/{len(components)}] {uid} ('{search_query}')...")

        result_payload = retriever.search_component(search_query, expected_query=search_query, validation_threshold=0.4)

        if result_payload["status"] == "success":
            result = result_payload["data"]
            print(f"      ✅ \u91c7\u7eb3: {result['lib_id']}")
            comp_info = {
                "uid": uid,
                "planned_value": planned_params.get("value", ""),
                "lib_id": result['lib_id'],
                "source_library": result.get('source_library', 'Project_Lib'),
                "pins": result.get('pins', []),
                "raw_symbol_definition": result.get('raw_symbol_definition', ''),
                "description": result.get('description', '')
            }
            retrieved_data[uid] = comp_info
            
        elif result_payload["status"] == "validation_failed":
            print(f"      🛑 \u62e6\u622a: \u51c6\u5907\u5c06\u9519\u8bef\u4fe1\u606f\u8fd4\u56de\u7ed9\u5927\u6a21\u578b\u6362\u8bcd\u68c0\u7d22...")
            retrieved_data[uid] = None
            
        else:
             print(f"      ❌ \u672a\u627e\u5230\u4efb\u4f55\u5019\u9009\u5143\u4ef6")
             retrieved_data[uid] = None

    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(retrieved_data, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 50)
    print(f"💾 \u7ed3\u679c\u5df2\u4fdd\u5b58\u81f3: {output_file}")
    print("=" * 50)


if __name__ == "__main__":
    FIXED_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "experiment_results", "new_runs", "retrieval")

    print("\n📝 --- \u5408\u5e76\u7248\u68c0\u7d22\u811a\u672c ---")
    input_path = input("👉 \u8f93\u5165 Planner JSON \u8def\u5f84 (\u9ed8\u8ba4: planning_result.json): ").strip().replace('"', '').replace("'", "")

    if not input_path:
        input_path = "planning_result.json"

    if not os.path.exists(input_path):
        alt_path = os.path.join(PROJECT_ROOT, "experiment_results", "new_runs", "planning", input_path)
        if os.path.exists(alt_path):
            input_path = alt_path

    base_name = os.path.basename(input_path)
    output_filename = f"retrieved_{base_name}"
    final_output_path = os.path.join(FIXED_OUTPUT_DIR, output_filename)

    inspect_components(input_path, final_output_path)
