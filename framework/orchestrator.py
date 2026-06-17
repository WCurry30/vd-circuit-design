import os
import json
import time

from circuit_planner_v import CircuitPlannerFinal
from retriever_final_merged import inspect_components
from generate_schematic import SchematicGenerator

# 导入新架构
from core.netlist_engine import NetlistEngine
from core.spice_engine import SpiceEngine
from experts.base_expert import CircuitExpert
from experts.filter_expert import FilterExpert
from experts.bjt_amplifier_expert import BjtAmplifierExpert
from experts.zener_regulator_expert import ZenerRegulatorExpert
from experts.opamp_amplifier_expert import OpAmpAmplifierExpert
from experts.led_constant_current_expert import LedConstantCurrentExpert


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class ExpertFactory:
    """
    专家工厂 - 根据 circuit_type 实例化对应的电路专家

    未来添加新电路类型只需：
    1. 在 experts/ 下创建新的专家类
    2. 在 _experts 字典中注册
    """

    _experts = {
        'filter': FilterExpert,
        'bjt_amplifier': BjtAmplifierExpert,
        'zener_regulator': ZenerRegulatorExpert,
        'opamp_amplifier': OpAmpAmplifierExpert,
        'led_constant_current': LedConstantCurrentExpert,
    }

    @classmethod
    def get_expert(cls, circuit_type: str) -> CircuitExpert:
        """
        根据电路类型获取对应的专家实例

        Args:
            circuit_type: 电路类型标识符

        Returns:
            CircuitExpert: 专家实例
        """
        expert_class = cls._experts.get(circuit_type, FilterExpert)  # 默认使用滤波器专家
        print(f"   🎯 加载专家模块: {expert_class.__name__}")
        return expert_class()

class EDAOrchestrator:
    def __init__(self, req_name="Auto_Run"):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_req = "".join(c if c.isalnum() else "_" for c in req_name[:10])
        workspace_root = os.environ.get(
            "EDA_WORKSPACE_DIR",
            os.path.join(PROJECT_ROOT, "experiment_results", "new_runs", "workspaces")
        )
        self.workspace = os.path.abspath(os.path.join(workspace_root, f"workspace_{safe_req}_{timestamp}"))
        os.makedirs(self.workspace, exist_ok=True)
        self.plan_path = os.path.join(self.workspace, "planning.json")
        self.retrieved_path = os.path.join(self.workspace, "retrieved.json")

    def run(self, user_requirement):
        print("="*60)
        print(f"🚀 启动全自动 EDA 工作流 (插件化专家架构)")
        print(f"📁 工作目录: {self.workspace}")
        print("="*60)

        print("\n[Step 1] 规划元器件...")
        planner = CircuitPlannerFinal()
        plan_data = planner.generate_plan(user_requirement, num_candidates=3)
        if not plan_data: return
        with open(self.plan_path, "w", encoding="utf-8") as f: json.dump(plan_data, f, indent=2, ensure_ascii=False)

        print("\n[Step 2] 检索物理元器件...")
        inspect_components(self.plan_path, self.retrieved_path)
        if not os.path.exists(self.retrieved_path): return

        # =========================================================
        # [Step 3] 核心创新：SPICE 仿真与参数迭代闭环（使用专家架构）
        # =========================================================
        print("\n[Step 3] 启动 SPICE 参数仿真与优化闭环...")

        # 实例化引擎和专家
        netlist_engine = NetlistEngine()
        spice_engine = SpiceEngine()

        # 从规划数据中获取电路类型，加载对应专家
        circuit_type = plan_data.get("circuit_type", "filter")
        expert = ExpertFactory.get_expert(circuit_type)

        MAX_ITERATIONS = 8  # 增加迭代次数，给它收敛的空间
        current_feedback = None
        best_spice_code = None

        for iteration in range(1, MAX_ITERATIONS + 1):
            print(f"\n--- 🔄 开始第 {iteration} 轮仿真迭代 ---")

            # 使用引擎 + 专家生成网表
            spice_code = netlist_engine.generate_spice(
                plan_data, expert, iteration, best_spice_code, current_feedback,
                retrieved_path=self.retrieved_path
            )

            # 使用引擎 + 专家评估
            passed, feedback, _metrics = spice_engine.evaluate(
                spice_code, plan_data, expert, self.workspace, iteration
            )

            # 无论成功失败，都记录下这一轮的代码，以便下一轮知道该改哪里
            best_spice_code = spice_code

            if passed:
                print(f"🏆 在第 {iteration} 轮通过物理仿真验证，参数已收敛！")
                break
            else:
                print(f"   {feedback}")
                current_feedback = feedback
                if iteration == MAX_ITERATIONS:
                    print("⚠️ 达到最大迭代次数，保留最后一轮网表。")

        # =========================================================
        # [Step 4] 翻译回 JSON 并调用画图引擎
        # =========================================================
        print("\n[Step 4] 仿真通过！正在映射回 KiCad 引脚并生成原理图...")
        json_path = os.path.join(self.workspace, "Final_Netlist.json")
        netlist_engine.translate_to_json(best_spice_code, self.retrieved_path, json_path)

        # 使用更新后的元件数据（包含仿真优化后的阻值）
        updated_retrieved_path = json_path.replace('.json', '_updated_retrieved.json')
        if os.path.exists(updated_retrieved_path):
            final_retrieved_path = updated_retrieved_path
            print(f"   📊 使用仿真优化后的元件数据: {final_retrieved_path}")
        else:
            final_retrieved_path = self.retrieved_path
            print(f"   ⚠️ 使用原始元件数据")

        sch_path = os.path.join(self.workspace, f"Schematic_Final.kicad_sch")
        try:
            sch_gen = SchematicGenerator()
            sch_gen.load_data(final_retrieved_path, json_path)
            sch_gen.process_and_layout()
            sch_gen.route_connections()
            sch_gen.generate_kicad_file(sch_path)
            print("\n" + "="*60)
            print("🎉 原理图生成大功告成！")
            print(f"👉 【最终 KiCad 8 原理图】: {sch_path}")
            print("="*60)
        except Exception as e:
            print(f"❌ 渲染引擎错误: {e}")

if __name__ == "__main__":
    req = input("🎙️ 请输入您的电路设计需求: ").strip()
    if not req: req = "设计一个截止频率为1kHz的二阶Sallen-Key低通滤波电路"
    orchestrator = EDAOrchestrator(req_name=req)
    orchestrator.run(req)
