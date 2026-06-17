import os
import json
import time
import csv
import re
import random
import traceback
import sys
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / "framework"))

from circuit_planner_v import CircuitPlannerFinal
from retriever_final_merged import inspect_components
import core.netlist_engine as netlist_mod
from core.netlist_engine import NetlistEngine
from core.spice_engine import SpiceEngine
from orchestrator import ExpertFactory
from experts.base_expert import CircuitExpert
from token_tracker import TokenTracker


def load_test_cases_v3(filepath: str) -> List[Dict]:
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

# =====================================================================
# 1. 退化版基础专家 (用于 Group 1: w/o Domain Expert)
# =====================================================================
class GenericFallbackExpert(CircuitExpert):
    """剔除了所有领域物理公式和拓扑约束的基础专家"""
    @property
    def circuit_type(self) -> str: return "generic"

    def get_circuit_description(self) -> str: return "通用电路"

    def get_netlist_prompts(self, elaborated_req, uid_hint, iteration, previous_spice, feedback):
        if iteration == 1:
            sys_prompt = f"你是一个电路设计工程师。请根据用户需求生成SPICE网表。\n【必须使用的元器件UID】：{uid_hint}\n【输出要求】：只输出SPICE代码，不要写其他多余文字。"
            user_prompt = f"需求：{elaborated_req}"
        else:
            sys_prompt = f"你是一个SPICE电路优化专家。请根据反馈修改网表。\n【必须使用的元器件UID】：{uid_hint}\n只输出SPICE代码。"
            user_prompt = f"需求：{elaborated_req}\n上一轮代码：\n{previous_spice}\n仿真反馈：{feedback}\n请修改并输出SPICE代码："
        return sys_prompt, user_prompt

    def clean_spice_code(self, spice_code: str) -> str:
        return spice_code  # 不做任何清洗保护

    def get_simulation_config(self):
        # 默认给一个 AC 分析，实际上基础专家不知道该用什么分析
        return {'analysis_type': 'ac', 'frequency_range': (1, 1e6), 'output_node': 'OUT', 'description': '通用分析'}

    def parse_simulation_data(self, x_data, y_data, config):
        if not y_data: return {'status': 'error'}
        return {'max_value': max(y_data), 'status': 'ok'}

    def get_judgment_prompts(self, requirement, metrics_str):
        sys_prompt = "你是裁判，判断以下电路仿真是否满足需求。\n输出JSON格式：{\"passed\": true/false, \"reason\": \"...\", \"feedback\": \"...\"}"
        user_prompt = f"需求: {requirement}\n仿真数据: {metrics_str}\n请判决："
        return sys_prompt, user_prompt

    def hard_threshold_judge(self, requirement: str, metrics: Dict[str, Any]) -> Tuple[bool, str]:
        """
        硬阈值判决（不使用 LLM）

        对于通用专家，我们只能做最简单的判断：如果有有效数据就根据数值判断
        """
        # 尝试提取一个数值进行判断
        if not metrics:
            return False, "无仿真数据"

        # 获取 max_value 作为参考
        max_val = metrics.get('max_value')
        if max_val is None:
            return False, "无法提取有效指标"

        # 通用判断：有输出就算通过（非常宽松的阈值）
        if max_val > 0:
            return True, f"检测到输出信号 {max_val}"
        else:
            return False, "无输出信号"

# =====================================================================
# 2. 移除拓扑护盾的 NetlistEngine (用于 Group 2: w/o Topology Shield)
# =====================================================================
class NoShieldNetlistEngine(NetlistEngine):
    def generate_spice(self, plan_data, expert, iteration=1, previous_spice=None, feedback=None, retrieved_path=None, temperature=0.1):
        """
        完全移除所有护盾的版本：
        1. 不调用 expert.clean_spice_code()
        2. 不执行全局护盾（重复元件名清洗）
        目的是让LLM生成的原始SPICE直接送入Ngspice，测试拓扑幻觉的致命影响
        """
        print(f"   [G2_NoShield] 跳过专家清洗和全局护盾")

        elaborated_req = plan_data.get("elaborated_requirement", "")
        uid_hint = "、".join([comp.get("uid") for comp in plan_data.get("components", [])])
        system_prompt, user_prompt = expert.get_netlist_prompts(elaborated_req, uid_hint, iteration, previous_spice, feedback)

        kwargs = {
            "model": netlist_mod.MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
        }
        if netlist_mod.THINKING_ENABLED:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        elif netlist_mod.EXPLICIT_DISABLE_THINKING:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = self.client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content
        match = re.search(r'```spice\s*(.*?)\s*```', raw, flags=re.DOTALL | re.IGNORECASE)
        spice_code = match.group(1).strip() if match else raw.replace("```", "").strip()

        # 致命修改1：不调用专家清洗
        # spice_code = expert.clean_spice_code(spice_code)  # 已注释

        # 致命修改2：不执行全局护盾（重复元件名清洗）
        # 直接返回raw SPICE，让拓扑幻觉直接撞击Ngspice

        # 检测是否有重复元件名（用于诊断）
        lines = spice_code.split('\n')
        comp_names = {}
        duplicate_warnings = []
        for line in lines:
            line_strip = line.strip()
            if not line_strip or line_strip.startswith('*') or line_strip.startswith('.'):
                continue
            parts = line_strip.split()
            if parts:
                comp_name = parts[0].upper()
                if comp_name in comp_names:
                    duplicate_warnings.append(comp_name)
                else:
                    comp_names[comp_name] = True

        if duplicate_warnings:
            print(f"   [G2_NoShield] 检测到重复元件名: {set(duplicate_warnings)} (未清洗，直接送Ngspice)")

        return spice_code

# =====================================================================
# 3. 核心消融运行器
# =====================================================================
class AblationRunner:
    def __init__(self):
        self.workspace_base = os.environ.get("EDA_WORKSPACE_DIR", os.path.join(os.path.dirname(__file__), "ablation_workspace"))
        os.makedirs(self.workspace_base, exist_ok=True)
        self.planner = CircuitPlannerFinal()
        self._original_system_prompt = self.planner.system_prompt
        self.token_tracker = TokenTracker()
        self.token_tracker.wrap_client(self.planner.client)

    def _build_pool_prompt(self, golden_components: List[str]) -> str:
        """注入元器件池约束到 system prompt"""
        prompt = self._original_system_prompt
        if any(m in golden_components for m in ["LM2904", "LM358"]):
            prompt = prompt.replace(
                "**禁止规划运放（LM2904）**，禁止规划电位器，禁止规划多个二极管",
                "**允许使用运放（LM2904/LM358）作为控制核心**，禁止规划电位器，禁止规划多个二极管"
            )
        pool_str = ", ".join(golden_components)
        pool_section = (
            f"\n\n【元器件池约束 - 请在此池内规划所有元器件】\n"
            f"当前设计的推荐元器件类型: {pool_str}\n"
            f"请在此范围内规划所有必需的元器件，不要超出此池的范围。"
        )
        return prompt + pool_section

    def _compute_golden_recall(self, retrieved_data: Dict, golden_components: List[str]) -> float:
        """计算 golden recall：检索到的元件覆盖了多少 golden 类型"""
        if not golden_components or not retrieved_data:
            return 0.0
        covered = set()
        for uid, info in retrieved_data.items():
            if not info:
                continue
            lib_id = info.get("lib_id", "").lower()
            for gold in golden_components:
                if gold.lower() in lib_id or lib_id in gold.lower():
                    covered.add(gold)
                    break
        return len(covered) / len(golden_components) if golden_components else 0.0

    def _compute_model_match_rate(self, retrieved_data: Dict) -> float:
        """计算 model match rate：检索到的元件有多少有 SPICE 模型"""
        if not retrieved_data:
            return 0.0
        generic_with_model = {"R", "C", "L", "D", "Q_NPN", "Q_PNP", "VCC", "GND",
                              "Resistor", "Capacitor", "Inductor", "LED"}
        known_model_prefixes = ["1N", "2N", "BC5", "LED", "LM", "NE555", "IRF", "TL"]
        total = len(retrieved_data)
        matched = 0
        for uid, info in retrieved_data.items():
            if not info:
                continue
            lib_id = info.get("lib_id", "")
            if not lib_id:
                continue
            if lib_id in generic_with_model:
                matched += 1
            else:
                lib_upper = lib_id.upper()
                if any(lib_upper.startswith(p) for p in known_model_prefixes):
                    matched += 1
        return matched / total if total > 0 else 0.0

    def run_single_test(self, prompt: str, group_id: str, group_config: dict) -> dict:
        timestamp = time.strftime("%H%M%S")
        safe_prompt = "".join(c if c.isalnum() else "_" for c in prompt[:10])
        workspace = os.path.join(self.workspace_base, f"{group_id}_{safe_prompt}_{timestamp}")
        os.makedirs(workspace, exist_ok=True)
        
        plan_path = os.path.join(workspace, "planning.json")
        retrieved_path = os.path.join(workspace, "retrieved.json")

        result_metrics = {
            "group": group_id,
            "prompt": prompt,
            "success": False,
            "iterations_used": 0,
            "fatal_errors": 0,
            "error_msg": ""
        }

        try:
            print(f"\n[{group_id}] 开始规划: {prompt}")
            # 为了加快消融实验速度，Planner只生成 1 个候选
            plan_data = self.planner.generate_plan(prompt, num_candidates=1)
            if not plan_data:
                result_metrics["error_msg"] = "Planner 失败"
                return result_metrics
            
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan_data, f, indent=2, ensure_ascii=False)

            inspect_components(plan_path, retrieved_path)

            # 根据消融组装配组件
            netlist_engine = NoShieldNetlistEngine() if group_config["no_shield"] else NetlistEngine()
            spice_engine = SpiceEngine()
            
            circuit_type = plan_data.get("circuit_type", "filter")
            if group_config["no_expert"]:
                expert = GenericFallbackExpert()
            else:
                expert = ExpertFactory.get_expert(circuit_type)

            max_iters = 1 if group_config["no_iteration"] else 8
            best_spice_code = None
            current_feedback = None

            for iteration in range(1, max_iters + 1):
                result_metrics["iterations_used"] = iteration

                # 生成网表
                spice_code = netlist_engine.generate_spice(
                    plan_data, expert, iteration, best_spice_code, current_feedback, retrieved_path
                )
                best_spice_code = spice_code

                # -------------------------------------------------------------
                # G3 特殊处理：使用硬阈值判决（不使用 LLM）
                # -------------------------------------------------------------
                use_hard_threshold = group_config.get("no_metric", False)

                # 跑仿真评估
                passed, feedback = spice_engine.evaluate(
                    spice_code, plan_data, expert, workspace, iteration,
                    use_hard_threshold=use_hard_threshold
                )

                if "Ngspice 调用环境异常" in feedback or "[致命错误]" in feedback:
                    result_metrics["fatal_errors"] += 1

                if passed:
                    result_metrics["success"] = True
                    break
                else:
                    current_feedback = feedback

        except Exception as e:
            result_metrics["error_msg"] = str(e)
            traceback.print_exc()

        print(f"[{group_id}] 测试完毕. 成功: {result_metrics['success']}, 轮次: {result_metrics['iterations_used']}")
        return result_metrics

    def run_single_test_with_cache(self, prompt: str, group_id: str, group_config: dict,
                                     base_workspace: str, cached_plan: dict = None,
                                     cached_retrieved: dict = None,
                                     golden_components: List[str] = None,
                                     targets: Dict = None,
                                     test_case_id: str = None,
                                     seed: int = 42) -> dict:
        random.seed(seed)
        timestamp = time.strftime("%H%M%S")
        workspace = os.path.join(base_workspace, f"{group_id}_{timestamp}")
        os.makedirs(workspace, exist_ok=True)

        plan_path = os.path.join(workspace, "planning.json")
        retrieved_path = os.path.join(workspace, "retrieved.json")

        result_metrics = {
            "group": group_id,
            "test_case_id": test_case_id or "",
            "run": seed,
            "prompt": prompt,
            "success": False,
            "iterations_used": 0,
            "fatal_errors": 0,
            "error_msg": "",
            "target_deviation_pct": None,
            "first_pass_success": False,
            "total_tokens": 0,
            "power_consumption_mw": None,
            "model_match_rate": 0.0,
        }

        actual_metrics = {}

        try:
            # Token snapshot
            token_snap = self.token_tracker.snapshot()

            if cached_plan is not None and cached_retrieved is not None:
                with open(plan_path, "w", encoding="utf-8") as f:
                    json.dump(cached_plan, f, indent=2, ensure_ascii=False)
                with open(retrieved_path, "w", encoding="utf-8") as f:
                    json.dump(cached_retrieved, f, indent=2, ensure_ascii=False)
                plan_data = cached_plan
                print(f"[{group_id}] 已从缓存加载规划和检索结果")
            else:
                # G0: 注入元器件池 + 规划 + 检索
                print(f"\n[{group_id}] 开始规划: {prompt}")
                if golden_components:
                    self.planner.system_prompt = self._build_pool_prompt(golden_components)
                    print(f"   [元器件池] 已注入: {golden_components}")

                plan_data = self.planner.generate_plan(prompt, num_candidates=1)

                # 恢复原始 system_prompt
                self.planner.system_prompt = self._original_system_prompt

                if not plan_data:
                    result_metrics["error_msg"] = "Planner 失败"
                    return result_metrics

                with open(plan_path, "w", encoding="utf-8") as f:
                    json.dump(plan_data, f, indent=2, ensure_ascii=False)

                inspect_components(plan_path, retrieved_path)

            if not os.path.exists(retrieved_path):
                inspect_components(plan_path, retrieved_path)

            # 计算 model_match_rate（所有组一致，因为检索结果相同）
            if os.path.exists(retrieved_path):
                with open(retrieved_path, 'r', encoding='utf-8') as f:
                    retrieved_data = json.load(f)
                result_metrics["model_match_rate"] = self._compute_model_match_rate(retrieved_data)

            # 组装消融组件
            netlist_engine = NoShieldNetlistEngine() if group_config["no_shield"] else NetlistEngine()
            self.token_tracker.wrap_client(netlist_engine.client)
            spice_engine = SpiceEngine()
            self.token_tracker.wrap_client(spice_engine.client)

            circuit_type = plan_data.get("circuit_type", "filter")
            if group_config["no_expert"]:
                expert = GenericFallbackExpert()
            else:
                expert = ExpertFactory.get_expert(circuit_type)

            # 注入目标值
            if targets and hasattr(expert, 'set_targets'):
                expert.set_targets(targets)

            max_iters = 1 if group_config["no_iteration"] else 8
            netlist_temp = group_config.get("temperature", 0.1)
            best_spice_code = None
            current_feedback = None

            for iteration in range(1, max_iters + 1):
                result_metrics["iterations_used"] = iteration

                spice_code = netlist_engine.generate_spice(
                    plan_data, expert, iteration, best_spice_code, current_feedback, retrieved_path,
                    temperature=netlist_temp
                )
                best_spice_code = spice_code

                use_hard_threshold = group_config.get("no_metric", False)

                result = spice_engine.evaluate(
                    spice_code, plan_data, expert, workspace, iteration,
                    use_hard_threshold=use_hard_threshold
                )
                passed, feedback = result[0], result[1]
                if len(result) > 2 and isinstance(result[2], dict):
                    actual_metrics = result[2]
                print(f"   [DEBUG] evaluate returned: passed={passed}, type={type(passed).__name__}")

                if "Ngspice 调用环境异常" in feedback or "[致命错误]" in feedback:
                    result_metrics["fatal_errors"] += 1

                if passed:
                    result_metrics["success"] = True
                    break
                else:
                    current_feedback = feedback

            # 后处理指标
            if result_metrics["success"] and result_metrics["iterations_used"] == 1:
                result_metrics["first_pass_success"] = True

            result_metrics["total_tokens"] = self.token_tracker.delta_since(token_snap)

            if actual_metrics:
                result_metrics["power_consumption_mw"] = actual_metrics.get("power_consumption_mw")

                if targets:
                    metric_name = targets.get("metric")
                    target_value = targets.get("value")
                    if metric_name and target_value and target_value != 0:
                        actual = actual_metrics.get(metric_name)
                        if actual is not None:
                            result_metrics["target_deviation_pct"] = abs(actual - target_value) / target_value * 100

        except Exception as e:
            result_metrics["error_msg"] = str(e)
            traceback.print_exc()

        print(f"[{group_id}] 测试完毕. 成功: {result_metrics['success']}, 轮次: {result_metrics['iterations_used']}")
        return result_metrics

# =====================================================================
# 4. 实验主程序
# =====================================================================
class MarkdownLogger:
    """双路日志器：同时输出到控制台和 Markdown 文件"""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8-sig")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

if __name__ == "__main__":
    experiment_timestamp = time.strftime("%Y%m%d_%H%M%S")
    experiment_name = f"ablation_exp_{experiment_timestamp}"
    workspace_base = os.environ.get("EDA_WORKSPACE_DIR", os.path.join(os.path.dirname(__file__), "ablation_workspace", experiment_name))
    os.makedirs(workspace_base, exist_ok=True)

    print(f"📁 本次实验文件夹: {workspace_base}\n")

    md_report_path = os.path.join(workspace_base, f"ablation_report.md")
    sys.stdout = MarkdownLogger(md_report_path)

    print(f"# 智能体 EDA 仿真模块消融实验报告")
    print(f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"**实验目录**: {workspace_base}\n")
    print(f"**模型**: deepseek-ai/DeepSeek-V3.2\n")
    print(f"## 1. 实验运行过程日志\n```text")

    # 加载 test_cases_v3
    test_cases_path = os.path.join(os.path.dirname(__file__), "datasets", "test_cases_v3.json")
    TEST_CASES = load_test_cases_v3(test_cases_path)
    print(f"📋 加载了 {len(TEST_CASES)} 个测试用例\n")

    NUM_RUNS = 3
    SEEDS = [42, 123, 456]
    GROUPS_ORDER = ["G0_Ours", "G1_No_Expert", "G2_No_Shield", "G3_No_Metric", "G4_No_Iter"]

    GROUPS = {
        "G0_Ours":      {"no_expert": False, "no_shield": False, "no_metric": False, "no_iteration": False, "temperature": 0.3},
        "G1_No_Expert":  {"no_expert": True,  "no_shield": False, "no_metric": False, "no_iteration": False, "temperature": 0.3},
        "G2_No_Shield":  {"no_expert": False, "no_shield": True,  "no_metric": False, "no_iteration": False, "temperature": 0.5},
        "G3_No_Metric":  {"no_expert": False, "no_shield": False, "no_metric": True,  "no_iteration": False, "temperature": 0.3},
        "G4_No_Iter":    {"no_expert": False, "no_shield": False, "no_metric": False, "no_iteration": True,  "temperature": 0.3},
    }

    runner = AblationRunner()
    runner.workspace_base = workspace_base
    all_results = []

    total_tests = len(TEST_CASES) * len(GROUPS) * NUM_RUNS
    print(f"🚀 开始自动化消融实验 (共 {total_tests} 组测试, NUM_RUNS={NUM_RUNS})...")
    print("💡 G0 执行规划（含元器件池约束）+ 检索，G1-G4 复用\n")
    print("💡 温度: G0/G1/G3/G4=0.3, G2=0.5; G3 硬阈值收紧; NUM_RUNS=3\n")

    for run_idx in range(NUM_RUNS):
        seed = SEEDS[run_idx]
        random.seed(seed)
        print(f"\n{'#'*70}")
        print(f"### RUN {run_idx+1}/{NUM_RUNS} (seed={seed})")
        print(f"{'#'*70}")

        for tc_idx, tc in enumerate(TEST_CASES):
            tc_id = tc["id"]
            prompt = tc["user_requirement"]
            golden_components = tc.get("golden_components", [])
            targets = tc.get("targets")

            safe_id = "".join(c if c.isalnum() else "_" for c in tc_id)
            base_workspace = os.path.join(workspace_base, f"R{run_idx+1}_{safe_id}_{time.strftime('%H%M%S')}")
            os.makedirs(base_workspace, exist_ok=True)

            # G0: 规划 + 检索
            g0_config = GROUPS["G0_Ours"]
            print(f"\n" + "="*70)
            print(f"🔄 [R{run_idx+1}] [{tc_idx+1}/{len(TEST_CASES)}] G0 (规划+检索): {tc_id}")
            print("="*70)

            g0_res = runner.run_single_test_with_cache(
                prompt, "G0_Ours", g0_config, base_workspace,
                cached_plan=None, cached_retrieved=None,
                golden_components=golden_components, targets=targets,
                test_case_id=tc_id, seed=seed
            )
            all_results.append(g0_res)

            # 缓存 G0 结果
            g0_subdirs = [d for d in os.listdir(base_workspace) if d.startswith("G0_Ours_")]
            if not g0_subdirs:
                print(f"❌ 找不到 G0 工作目录，跳过后续组")
                continue
            g0_workspace = os.path.join(base_workspace, g0_subdirs[0])

            with open(os.path.join(g0_workspace, "planning.json"), 'r', encoding='utf-8') as f:
                cached_plan = json.load(f)
            with open(os.path.join(g0_workspace, "retrieved.json"), 'r', encoding='utf-8') as f:
                cached_retrieved = json.load(f)
            print(f"✅ 已缓存，后续组复用")

            # G1-G4
            for group_id in GROUPS_ORDER[1:]:
                config = GROUPS[group_id]
                print(f"\n[R{run_idx+1}] [{tc_idx+1}/{len(TEST_CASES)}] {group_id}: {tc_id}")
                res = runner.run_single_test_with_cache(
                    prompt, group_id, config, base_workspace,
                    cached_plan, cached_retrieved,
                    golden_components=golden_components, targets=targets,
                    test_case_id=tc_id, seed=seed
                )
                all_results.append(res)
                time.sleep(1)

    # === 保存 CSV ===
    csv_fieldnames = [
        "group", "test_case_id", "run", "prompt", "success", "iterations_used",
        "fatal_errors", "error_msg", "target_deviation_pct", "first_pass_success",
        "total_tokens", "power_consumption_mw", "model_match_rate"
    ]
    csv_path = os.path.join(runner.workspace_base, "ablation_results.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_results)

    import statistics
    print("```\n")
    print("## 2. 消融实验数据对比表 (NUM_RUNS={NUM_RUNS})\n")

    # === 2.1: 逐 case 明细 (取 3 轮平均) ===
    print("### 2.1 逐测试用例明细 (3轮平均)\n")
    header_cols = ["Test Case"] + GROUPS_ORDER
    print("| " + " | ".join(header_cols) + " |")
    print("| " + " | ".join([":---"] + [":---:"] * len(GROUPS_ORDER)) + " |")

    for tc in TEST_CASES:
        tc_id = tc["id"]
        row = f"| {tc_id} "
        for group_id in GROUPS_ORDER:
            matches = [r for r in all_results if r.get("test_case_id") == tc_id and r["group"] == group_id]
            if matches:
                succ_rate = sum(1 for r in matches if r["success"]) / len(matches)
                devs = [r["target_deviation_pct"] for r in matches if r["target_deviation_pct"] is not None]
                avg_dev = sum(devs)/len(devs) if devs else None
                avg_iters = sum(r["iterations_used"] for r in matches) / len(matches)
                s = "✅" if succ_rate >= 0.67 else ("🟡" if succ_rate >= 0.34 else "❌")
                d = f"{avg_dev:.1f}%" if avg_dev is not None else "—"
                row += f"| {s}({avg_iters:.0f}轮, {d}) "
            else:
                row += "| — "
        row += "|"
        print(row)

    print("\n")

    # === 2.2: 按 Group 汇总 (均值 ± 标准差) ===
    print("### 2.2 按实验组汇总 (Mean ± Std)\n")
    print("| Metric | " + " | ".join(GROUPS_ORDER) + " |")
    print("| :--- | " + " | ".join([":---:"] * len(GROUPS_ORDER)) + " |")

    def agg_stability(group_id, key, mode='rate'):
        vals = [r[key] for r in all_results if r["group"] == group_id and r.get(key) is not None]
        if not vals:
            return "—"
        mean = sum(vals) / len(vals)
        if mode == 'rate':
            mean_str = f"{mean*100:.1f}%"
        elif mode == 'mean':
            mean_str = f"{mean:.1f}"
        elif mode == 'int':
            mean_str = f"{int(mean)}"
        else:
            mean_str = f"{mean:.2f}"
        if len(vals) >= 2:
            std = statistics.stdev(vals)
            if mode == 'rate':
                std_str = f"{std*100:.1f}%"
            elif mode == 'int':
                std_str = f"{int(std)}"
            else:
                std_str = f"{std:.1f}"
            return f"{mean_str} ±{std_str}"
        return mean_str

    metrics_rows = [
        ("Success Rate", "success", "rate"),
        ("Target Deviation %", "target_deviation_pct", "mean"),
        ("First-Pass Rate", "first_pass_success", "rate"),
        ("Model Match Rate", "model_match_rate", "rate"),
        ("Avg Tokens", "total_tokens", "int"),
        ("Avg Iterations", "iterations_used", "mean"),
    ]

    for metric_name, key, mode in metrics_rows:
        row = f"| {metric_name} "
        for group_id in GROUPS_ORDER:
            row += f"| {agg_stability(group_id, key, mode)} "
        row += "|"
        print(row)

    # === 2.3: 稳定性分析 ===
    print(f"\n### 2.3 稳定性分析 (跨 {NUM_RUNS} 轮标准差)\n")
    print("| Group | Success Std | Deviation Std | Iterations Std | 稳定性评级 |")
    print("| :--- | :---: | :---: | :---: | :---: |")

    for group_id in GROUPS_ORDER:
        per_case_success_rates = []
        per_case_dev_means = []
        per_case_iter_stds = []
        for tc in TEST_CASES:
            tc_id = tc["id"]
            matches = [r for r in all_results if r["test_case_id"] == tc_id and r["group"] == group_id]
            if matches:
                succ = [1 if r["success"] else 0 for r in matches]
                per_case_success_rates.append(sum(succ)/len(succ))
                devs = [r["target_deviation_pct"] for r in matches if r["target_deviation_pct"] is not None]
                if devs:
                    per_case_dev_means.append(sum(devs)/len(devs))
                iters = [r["iterations_used"] for r in matches]
                if len(iters) >= 2:
                    per_case_iter_stds.append(statistics.stdev(iters))

        succ_std = statistics.stdev(per_case_success_rates) if len(per_case_success_rates) >= 2 else 0
        dev_std = statistics.stdev(per_case_dev_means) if len(per_case_dev_means) >= 2 else 0
        iter_std = sum(per_case_iter_stds)/len(per_case_iter_stds) if per_case_iter_stds else 0

        if succ_std < 0.1:
            stability = "🟢 高稳定"
        elif succ_std < 0.25:
            stability = "🟡 中等"
        else:
            stability = "🔴 低稳定"

        print(f"| {group_id} | {succ_std:.3f} | {dev_std:.1f} | {iter_std:.1f} | {stability} |")

    print(f"\n---")
    print(f"**详细CSV数据已保存至**: `{csv_path}`")
    print(f"**模型**: deepseek-ai/DeepSeek-V3.2 (SiliconFlow API)")
    print(f"**配置**: NUM_RUNS={NUM_RUNS}, G2温度=0.5, G3硬阈值收紧(±10%)")