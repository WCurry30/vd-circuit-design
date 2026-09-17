import os
import json
import time

from circuit_planner_v import CircuitPlannerFinal
from retriever_final_merged import inspect_components
from generate_schematic import SchematicGenerator

# \u5bfc\u5165\u65b0\u67b6\u6784
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
    \u4e13\u5bb6\u5de5\u5382 - \u6839\u636e circuit_type \u5b9e\u4f8b\u5316\u5bf9\u5e94\u7684\u7535\u8def\u4e13\u5bb6

    \u672a\u6765\u6dfb\u52a0\u65b0\u7535\u8def\u7c7b\u578b\u53ea\u9700：
    1. \u5728 experts/ \u4e0b\u521b\u5efa\u65b0\u7684\u4e13\u5bb6\u7c7b
    2. \u5728 _experts \u5b57\u5178\u4e2d\u6ce8\u518c
    """

    _experts = {
        'filter': FilterExpert,
        'bjt_amplifier': BjtAmplifierExpert,
        'zener_regulator': ZenerRegulatorExpert,
        'opamp_amplifier': OpAmpAmplifierExpert,
        'led_constant_current': LedConstantCurrentExpert,
        # 'audio_amplifier': AudioAmplifierExpert,
        # 'power_supply': PowerSupplyExpert,
        # 'oscillator': OscillatorExpert,
    }

    @classmethod
    def get_expert(cls, circuit_type: str) -> CircuitExpert:
        """
        \u6839\u636e\u7535\u8def\u7c7b\u578b\u83b7\u53d6\u5bf9\u5e94\u7684\u4e13\u5bb6\u5b9e\u4f8b

        Args:
            circuit_type: \u7535\u8def\u7c7b\u578b\u6807\u8bc6\u7b26

        Returns:
            CircuitExpert: \u4e13\u5bb6\u5b9e\u4f8b
        """
        expert_class = cls._experts.get(circuit_type, FilterExpert)  # \u9ed8\u8ba4\u4f7f\u7528\u6ee4\u6ce2\u5668\u4e13\u5bb6
        print(f"   🎯 \u52a0\u8f7d\u4e13\u5bb6\u6a21\u5757: {expert_class.__name__}")
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
        print(f"🚀 \u542f\u52a8\u5168\u81ea\u52a8 EDA \u5de5\u4f5c\u6d41 (\u63d2\u4ef6\u5316\u4e13\u5bb6\u67b6\u6784)")
        print(f"📁 \u5de5\u4f5c\u76ee\u5f55: {self.workspace}")
        print("="*60)

        print("\n[Step 1] \u89c4\u5212\u5143\u5668\u4ef6...")
        planner = CircuitPlannerFinal()
        plan_data = planner.generate_plan(user_requirement, num_candidates=3)
        if not plan_data: return
        with open(self.plan_path, "w", encoding="utf-8") as f: json.dump(plan_data, f, indent=2, ensure_ascii=False)

        print("\n[Step 2] \u68c0\u7d22\u7269\u7406\u5143\u5668\u4ef6...")
        inspect_components(self.plan_path, self.retrieved_path)
        if not os.path.exists(self.retrieved_path): return

        # =========================================================
        # [Step 3] \u6838\u5fc3\u521b\u65b0：SPICE \u4eff\u771f\u4e0e\u53c2\u6570\u8fed\u4ee3\u95ed\u73af（\u4f7f\u7528\u4e13\u5bb6\u67b6\u6784）
        # =========================================================
        print("\n[Step 3] \u542f\u52a8 SPICE \u53c2\u6570\u4eff\u771f\u4e0e\u4f18\u5316\u95ed\u73af...")

        # \u5b9e\u4f8b\u5316\u5f15\u64ce\u548c\u4e13\u5bb6
        netlist_engine = NetlistEngine()
        spice_engine = SpiceEngine()

        # \u4ece\u89c4\u5212\u6570\u636e\u4e2d\u83b7\u53d6\u7535\u8def\u7c7b\u578b，\u52a0\u8f7d\u5bf9\u5e94\u4e13\u5bb6
        circuit_type = plan_data.get("circuit_type", "filter")
        expert = ExpertFactory.get_expert(circuit_type)

        MAX_ITERATIONS = 8  # \u589e\u52a0\u8fed\u4ee3\u6b21\u6570，\u7ed9\u5b83\u6536\u655b\u7684\u7a7a\u95f4
        current_feedback = None
        best_spice_code = None

        for iteration in range(1, MAX_ITERATIONS + 1):
            print(f"\n--- 🔄 \u5f00\u59cb\u7b2c {iteration} \u8f6e\u4eff\u771f\u8fed\u4ee3 ---")

            # \u4f7f\u7528\u5f15\u64ce + \u4e13\u5bb6\u751f\u6210\u7f51\u8868
            spice_code = netlist_engine.generate_spice(
                plan_data, expert, iteration, best_spice_code, current_feedback,
                retrieved_path=self.retrieved_path
            )

            # \u4f7f\u7528\u5f15\u64ce + \u4e13\u5bb6\u8bc4\u4f30
            passed, feedback, _metrics = spice_engine.evaluate(
                spice_code, plan_data, expert, self.workspace, iteration
            )

            # \u65e0\u8bba\u6210\u529f\u5931\u8d25，\u90fd\u8bb0\u5f55\u4e0b\u8fd9\u4e00\u8f6e\u7684\u4ee3\u7801，\u4ee5\u4fbf\u4e0b\u4e00\u8f6e\u77e5\u9053\u8be5\u6539\u54ea\u91cc
            best_spice_code = spice_code

            if passed:
                print(f"🏆 \u5728\u7b2c {iteration} \u8f6e\u901a\u8fc7\u7269\u7406\u4eff\u771f\u9a8c\u8bc1，\u53c2\u6570\u5df2\u6536\u655b！")
                break
            else:
                print(f"   {feedback}")
                current_feedback = feedback
                if iteration == MAX_ITERATIONS:
                    print("⚠️ \u8fbe\u5230\u6700\u5927\u8fed\u4ee3\u6b21\u6570，\u4fdd\u7559\u6700\u540e\u4e00\u8f6e\u7f51\u8868。")

        # =========================================================
        # [Step 4] \u7ffb\u8bd1\u56de JSON \u5e76\u8c03\u7528\u753b\u56fe\u5f15\u64ce
        # =========================================================
        print("\n[Step 4] \u4eff\u771f\u901a\u8fc7！\u6b63\u5728\u6620\u5c04\u56de KiCad \u5f15\u811a\u5e76\u751f\u6210\u539f\u7406\u56fe...")
        json_path = os.path.join(self.workspace, "Final_Netlist.json")
        netlist_engine.translate_to_json(best_spice_code, self.retrieved_path, json_path)

        # \u4f7f\u7528\u66f4\u65b0\u540e\u7684\u5143\u4ef6\u6570\u636e（\u5305\u542b\u4eff\u771f\u4f18\u5316\u540e\u7684\u963b\u503c）
        updated_retrieved_path = json_path.replace('.json', '_updated_retrieved.json')
        if os.path.exists(updated_retrieved_path):
            final_retrieved_path = updated_retrieved_path
            print(f"   📊 \u4f7f\u7528\u4eff\u771f\u4f18\u5316\u540e\u7684\u5143\u4ef6\u6570\u636e: {final_retrieved_path}")
        else:
            final_retrieved_path = self.retrieved_path
            print(f"   ⚠️ \u4f7f\u7528\u539f\u59cb\u5143\u4ef6\u6570\u636e")

        sch_path = os.path.join(self.workspace, f"Schematic_Final.kicad_sch")
        try:
            sch_gen = SchematicGenerator()
            sch_gen.load_data(final_retrieved_path, json_path)
            sch_gen.process_and_layout()
            sch_gen.route_connections()
            sch_gen.generate_kicad_file(sch_path)
            print("\n" + "="*60)
            print("🎉 \u539f\u7406\u56fe\u751f\u6210\u5927\u529f\u544a\u6210！")
            print(f"👉 【\u6700\u7ec8 KiCad 8 \u539f\u7406\u56fe】: {sch_path}")
            print("="*60)
        except Exception as e:
            print(f"❌ \u6e32\u67d3\u5f15\u64ce\u9519\u8bef: {e}")

if __name__ == "__main__":
    req = input("🎙️ \u8bf7\u8f93\u5165\u60a8\u7684\u7535\u8def\u8bbe\u8ba1\u9700\u6c42: ").strip()
    if not req: req = "\u8bbe\u8ba1\u4e00\u4e2a\u622a\u6b62\u9891\u7387\u4e3a1kHz\u7684\u4e8c\u9636Sallen-Key\u4f4e\u901a\u6ee4\u6ce2\u7535\u8def"
    orchestrator = EDAOrchestrator(req_name=req)
    orchestrator.run(req)
