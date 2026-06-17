import json
import os
import sys
import chromadb
from sentence_transformers import SentenceTransformer
import re
from pathlib import Path


FRAMEWORK_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FRAMEWORK_DIR.parent


# ==========================================
# 第一部分：内置的智能检索器类
# ==========================================
class IntelligentRetriever:
    def __init__(self, persist_directory=None, enable_exact_match=True):
        self.enable_exact_match = enable_exact_match
        if persist_directory is None:
            persist_directory = os.environ.get("EDA_CHROMA_DIR") or str(FRAMEWORK_DIR / "chroma_db")
        if not os.path.exists(persist_directory):
            raise FileNotFoundError(f"Vector database not found: {persist_directory}. Set EDA_CHROMA_DIR env var.")

        print(f"🔌 连接数据库: {persist_directory}...")
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_collection("electronic_components")

        print("⏳ 加载 Embedding 模型...")
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

       # ==========================================================
        # 🎯 【最高优先级】：精确锁定登记册 (直接硬查 lib_id，绕过向量搜索)
        # ==========================================================
        self.exact_match_registry = {
            # === 运算放大器系列 ===
            "opamp": "LM2904",
            "op-amp": "LM2904",
            "operational amplifier": "LM2904",
            "lm358": "LM2904",
            "lm2904": "LM2904",
            "ne5532": "LM2904",
            
            # === 微控制器系列 ===
            "attiny85": "ATtiny25V-10S",
            "mcuattiny85": "ATtiny25V-10S",
            "mcu attiny85": "ATtiny25V-10S",
            
            # === 🔌 新增：连接器/输入输出端子强制绑定 ===
            # 只要大模型的 search_query 包含左边的词，直接无脑提取右边的 lib_id
            "connector": "Conn_01x01",
            "header": "Conn_01x01",
            "pin": "Conn_01x01",
            "input": "Conn_01x01",
            "output": "Conn_01x01",
            "terminal": "Conn_01x01",

            # === 连接器系列 ===
            "dc jack": "Barrel_Jack",
            "dc power jack": "Barrel_Jack",

            # === 定时器系列 ===
            "ne555": "NE555D",

            # === 基础无源器件 ===
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
                print(f"      🎯 [绝对锁定模块] 命中规则 '{trigger_word}' -> 直接提取库元件: {target_lib_id}")
                meta = results['metadatas'][0]
                parsed_data = self._parse_metadata(meta, 1.0, raw_query)
                return {"status": "success", "data": parsed_data}
        except Exception as e:
            print(f"      ⚠️ [绝对锁定模块] 试图提取 {target_lib_id} 失败，将退回常规搜索。原因: {e}")
            
        return None

    def _optimize_query(self, raw_query):
        q = raw_query.lower().strip()
        print(f"      [调试] 分析: '{raw_query}'", end="")

        # =========================================================
        # 🔥 芯片家族智能映射 (你的专属规则)
        # =========================================================
        
        # 1. 拦截 78/79 系列稳压器 (如 78L12, 79L12, 7805, 7905 等)
        # 正则解释：匹配 78 或 79 开头，中间可能跟着一个字母(如L/M)，最后是两位数字
        # 重要：数据库中可能没有这些器件，但系统有 SPICE 模型
        # 返回特殊标记，让后续流程创建虚拟器件
        match_78xx = re.search(r'(7[89][a-z]?\d{2})', q)
        if match_78xx:
            original_model = match_78xx.group(1).upper()
            # 标准化型号名：LM7805, LM7812 等
            if not original_model.startswith('LM'):
                original_model = 'LM' + original_model
            print(f" -> 命中规则: 属于 78/79xx 稳压家族，使用虚拟器件 '{original_model}'")
            return f"__VIRTUAL_REGULATOR__:{original_model}"

        # 2. 【优先】拦截稳压二极管家族 (如 1N4733A, 1N4742A, 或基础词汇 zener)
        # 必须在普通二极管规则之前，否则会被 1n\d{4 正则先匹配
        match_zener = re.search(r'1n47\d{2}[a-z]?', q, re.IGNORECASE)
        if "zener" in q or match_zener:
            if match_zener:
                zener_model = match_zener.group(0).upper()
            else:
                # 默认使用 5.1V 稳压二极管
                zener_model = "1N4733A"
            print(f" -> 命中规则: 属于稳压二极管，使用虚拟器件 '{zener_model}'")
            return f"__VIRTUAL_ZENER__:{zener_model}"

        # 3. 拦截二极管家族 (如 1n4148, 1n4001, 1n4007, 或基础词汇 diode)
        # 正则解释：匹配 1n 后面跟着 4 位数字的型号
        if "diode" in q or re.search(r'1n\d{4}', q):
            # 排除发光二极管(LED)和稳压二极管(Zener)
            if "led" not in q and "zener" not in q:
                print(" -> 命中规则: 属于基础二极管，统一映射为 'D'")
                return "D" 

        if "resistor" in q or q == "r":
            print(" -> 命中规则: 强制转为 'Resistor'")
            return "Resistor"

        if "resistor" in q or q == "r":
            print(" -> 命中规则: 强制转为 'Resistor'")
            return "Resistor"
        if "capacitor" in q:
            if "polarized" in q or "electrolytic" in q:
                print(" -> 命中规则: 强制转为 'Capacitor'")
                return "Capacitor"
            print(" -> 命中规则: 强制转为 'Capacitor'")
            return "Capacitor"
        if "inductor" in q:
            print(" -> 命中规则: 强制转为 'L'")
            return "L"
        if "diode" in q and "led" not in q:
            print(" -> 命中规则: 强制转为 'D'")
            return "D"
        if "led" in q:
            print(" -> 命中规则: 强制转为 'Light emitting diode'")
            return "Light emitting diode"
        if "crystal" in q or "oscillator" in q:
            print(" -> 命中规则: 强制转为 'Crystal_Small'")
            return "Crystal_Small"
        if "switch" in q and "button" in q:
            print(" -> 命中规则: 强制转为 'SW_Push'")
            return "SW_Push"
        if "stm32" in q:
            print(" -> 命中规则: 强制转为 'STMicroelectronics'")
            return "STMicroelectronics"
        if "opamp" in q or "op-amp" in q or "operational amplifier" in q or "lm2904" in q:
            print(" -> 命中规则: 强制转为 'LM2904 Dual Operational Amplifiers'")
            return "LM2904 Dual Operational Amplifiers"
        if "regulator" in q or "ldo" in q or "1117" in q or "7805" in q:
            print(" -> 命中规则: 强制转为 'Regulator_Linear'")
            return "Regulator_Linear"
        if "mosfet" in q or "nmos" in q or "pmos" in q:
            print(" -> 命中规则: 强制转为 'GS66502B'")
            return "GS66502B"
        if "npn" in q or "pnp" in q or "bjt" in q:
            print(" -> 命中规则: 强制转为 '2N2219'")
            return "2N2219"
        if "connector" in q or "header" in q or "pin" in q or "input" in q or "output" in q:
            print(" -> 命中规则: 强制转为 'Conn_01x01' (单引脚信号端子)")
            return "Conn_01x01"  # 如果你库里单引脚叫别的名字，请替换成你库里的真实名字

        print(" -> 无规则，保持原样")
        return raw_query

    def search_component(self, query_text, expected_query=None, n_candidates=15, validation_threshold=0.4):
        # 1. 精确锁定（强制映射规则，保持不变）
        if self.enable_exact_match:
            exact_match_result = self._try_exact_match(query_text)
            if exact_match_result:
                return exact_match_result

        # 2. 查询优化/强制转换（检查是否命中强制转换规则）
        optimized_query = self._optimize_query(query_text)
        is_forced_conversion = (optimized_query != query_text)

        # 2.5 【特殊处理】虚拟稳压器（78xx 系列不在数据库中）
        # 必须在 _optimize_query 之后检查，因为标记是由它返回的
        if optimized_query.startswith("__VIRTUAL_REGULATOR__:"):
            actual_model = optimized_query.split(":")[1]
            # 提取输出电压（如 LM7812 -> 12V）
            voltage_match = re.search(r'LM78(\d+)', actual_model)
            voltage = voltage_match.group(1) if voltage_match else "05"
            print(f"      🔧 [虚拟稳压器] 创建 {actual_model} ({voltage}V) 虚拟器件")

            # 生成符合 KiCad 格式的符号定义
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

            # 返回一个标准的 TO-220 封装稳压器虚拟器件
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

        # 2.6 【特殊处理】虚拟稳压二极管（1N47xx 系列不在数据库中）
        if optimized_query.startswith("__VIRTUAL_ZENER__:"):
            actual_model = optimized_query.split(":")[1]

            # 稳压值映射表
            zener_voltages = {
                '1N4728A': 3.3, '1N4729A': 3.6, '1N4730A': 3.9, '1N4731A': 4.3,
                '1N4732A': 4.7, '1N4733A': 5.1, '1N4734A': 5.6, '1N4735A': 6.2,
                '1N4736A': 6.8, '1N4737A': 7.5, '1N4738A': 8.2, '1N4739A': 9.1,
                '1N4740A': 10.0, '1N4741A': 11.0, '1N4742A': 12.0, '1N4743A': 13.0,
                '1N4744A': 15.0, '1N4745A': 16.0, '1N4746A': 18.0, '1N4747A': 20.0,
                '1N4748A': 22.0, '1N4749A': 24.0, '1N4750A': 27.0, '1N4751A': 30.0,
                '1N4733': 5.1, '1N4742': 12.0,  # 无 A 后缀的兼容型号
            }
            voltage = zener_voltages.get(actual_model, 5.1)
            print(f"      🔧 [虚拟稳压二极管] 创建 {actual_model} ({voltage}V) 虚拟器件")

            # 生成符合 KiCad 格式的稳压二极管符号定义
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

        # 3. 白名单元器件直接进行向量检索（保持原有逻辑）
        whitelist = ["R", "C", "L", "D", "Speaker", "Microphone", "SW_Push", "Capacitor", "Resistor"]
        is_whitelist = query_text in whitelist or optimized_query in whitelist

        # ==================================================
        # 4. 【普通检索】首先尝试 lib_id 精确匹配
        # 只有非强制转换、非白名单的元器件才走这个流程
        # ==================================================
        if not is_forced_conversion and not is_whitelist:
            try:
                # 尝试多种形式的精确匹配
                match_attempts = [
                    query_text,                    # 原始查询
                    query_text.upper(),            # 大写
                    query_text.lower(),            # 小写
                    query_text.capitalize(),       # 首字母大写
                ]
                # 去重
                match_attempts = list(dict.fromkeys(match_attempts))

                for attempt in match_attempts:
                    direct_results = self.collection.get(
                        where={"lib_id": attempt},
                        include=["metadatas"]
                    )
                    if direct_results and direct_results['metadatas'] and len(direct_results['metadatas']) > 0:
                        print(f"      🎯 [lib_id精确匹配] 元件名 '{query_text}' -> 直接命中库元件: '{attempt}'")
                        meta = direct_results['metadatas'][0]
                        parsed_data = self._parse_metadata(meta, 1.0, query_text)
                        return {"status": "success", "data": parsed_data}

                print(f"      ℹ️ [lib_id精确匹配] 未找到 '{query_text}'，进入向量检索流程...")
            except Exception as e:
                print(f"      ⚠️ [lib_id精确匹配] 查询出错: {e}，继续向量检索...")

        # 5. 向量检索流程（强制转换、白名单、或 lib_id 精确匹配失败后执行）
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

        # 3. 强力重排 (包含新增的 Keywords 匹配)
        best_match = self._rerank_results(optimized_query, candidates)
        best_meta = best_match["meta"]
        retrieved_name = best_meta.get("lib_id", "")
        
        # 4. 【保留】：白名单免检
        whitelist = ["R", "C", "L", "D", "Speaker", "Microphone", "SW_Push", "Capacitor", "Resistor"]
        if retrieved_name in whitelist or optimized_query in whitelist:
            print(f"      ✅ 触发白名单豁免校验 -> 采纳: {retrieved_name}")
            parsed_data = self._parse_metadata(best_meta, best_match["score"], query_text)
            return {"status": "success", "data": parsed_data}

        # 5. 基于功能的相似度校验兜底
        retrieved_desc = best_meta.get("description", "")
        retrieved_func_text = f"{retrieved_name} {retrieved_desc}"
        expected_func_text = expected_query if expected_query else query_text

        v_expected = self.model.encode([expected_func_text])
        v_retrieved = self.model.encode([retrieved_func_text])
        similarity = self.model.similarity(v_expected, v_retrieved)[0][0].item()

        if similarity < validation_threshold:
            print(f"      ⚠️ 功能校验未通过!")
            print(f"      - 预期需求: '{expected_func_text}'")
            print(f"      - 实际捞取: '{retrieved_name}' (描述: {retrieved_desc})")
            return {
                "status": "validation_failed", 
                "reason": f"检索到的元件 '{retrieved_name}' 功能不匹配",
                "retrieved_name": retrieved_name,
                "data": None
            }
            
        print(f"      ✅ 功能校验通过 (相似度: {similarity:.2f})")
        parsed_data = self._parse_metadata(best_meta, best_match["score"], query_text)
        return {"status": "success", "data": parsed_data}

    def _rerank_results(self, query, candidates):
        """
        🔥 核心改进：引入 keywords 匹配打分机制
        """
        query_clean = query.strip().lower()
        # 将查询词进行拆分，方便与 keyword 进行交叉比对
        query_words = set(query_clean.split())
        query_words.add(query_clean) # 把完整短语也加进去

        for item in candidates:
            meta = item["meta"]
            lib_id = meta.get("lib_id", "")
            lib_id_lower = lib_id.lower()
            item["final_score"] = item["score"]

            # ================= 新增：Keywords 关键词硬匹配逻辑 =================
            keywords = []
            if "keywords" in meta:
                kw_data = meta["keywords"]
                # 处理数据库中存储的 JSON 字符串或原生列表
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
            # 如果查询词的任何部分命中了元器件的 keywords (计算交集)
            matched_keywords = query_words.intersection(keyword_set)
            
            if matched_keywords:
                # 只要命中一个关键词，给予巨大加分 (3.0 分足以碾压普通的向量距离分歧)
                item["final_score"] += 3.0 * len(matched_keywords)
                print(f"      [🎯 关键词加分] 命中 Keywords: {matched_keywords} -> 提权: {lib_id}")
            # ===================================================================

            # 原有的基于 lib_id 的打分逻辑
            if lib_id_lower == query_clean:
                item["final_score"] += 10.0
            if len(lib_id) <= 2 and "_" not in lib_id:
                item["final_score"] += 2.0
            if "_" in lib_id and "_" not in query_clean:
                item["final_score"] -= 5.0

        # 按最终得分降序排序
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
# 第二部分：执行逻辑 (main)
# ==========================================

def inspect_components(plan_file, output_file):
    if not os.path.exists(plan_file):
        print(f"❌ 找不到规划文件: {plan_file}")
        return

    print(f"📂 读取规划文件: {plan_file} ...")
    try:
        with open(plan_file, 'r', encoding='utf-8') as f:
            plan = json.load(f)
    except Exception as e:
        print(f"❌ JSON 读取失败: {e}")
        return

    print("🚀 初始化检索器...")
    try:
        retriever = IntelligentRetriever()
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return

    print(f"\n🔍 --- 开始检索 ---")
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
            print(f"      ✅ 采纳: {result['lib_id']}")
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
            print(f"      🛑 拦截: 准备将错误信息返回给大模型换词检索...")
            retrieved_data[uid] = None
            
        else:
             print(f"      ❌ 未找到任何候选元件")
             retrieved_data[uid] = None

    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(retrieved_data, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 50)
    print(f"💾 结果已保存至: {output_file}")
    print("=" * 50)


if __name__ == "__main__":
    FIXED_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "experiment_results", "new_runs", "retrieval")

    print("\n📝 --- 合并版检索脚本 ---")
    input_path = input("👉 输入 Planner JSON 路径 (默认: planning_result.json): ").strip().replace('"', '').replace("'", "")

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
