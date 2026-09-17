"""
Full Pipeline Runner
====================
Wraps the orchestrator flow (Plan → Retrieve → Simulate → Schematic)
into a batch-callable function for comparison experiments.

Each run produces:
- plan.json (planning output)
- retrieved.json (retrieval output)
- sim_v{1..N}.cir (SPICE netlists)
- ac_out_v{1..N}.txt or tran_out_v{1..N}.txt (simulation output)
- Final_Netlist.json (translated netlist)
- Schematic_Final.kicad_sch (final schematic)
- pipeline_result.json (aggregated metrics)
"""

import json
import os
import sys
import time
import traceback
from typing import Dict, Any, Optional
from pathlib import Path

# Ensure framework modules are on path.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_DIR = PROJECT_ROOT / "framework"
sys.path.insert(0, str(FRAMEWORK_DIR))

from core.netlist_engine import NetlistEngine
from core.spice_engine import SpiceEngine
from orchestrator import ExpertFactory

# Model availability tables (mirrors SpiceEngine for pre-simulation checking).
# Components whose lib_id appears here or matches generic types have valid SPICE models.
_SPICE_TIER2 = {
    "2N3904", "2N2222", "2N2219", "BC547", "2N3906",
    "1N4148", "1N4001", "1N4007", "LED",
    "IRF540",
    "1N4728A", "1N4729A", "1N4730A", "1N4731A", "1N4732A", "1N4733A",
    "1N4734A", "1N4735A", "1N4736A", "1N4737A", "1N4738A", "1N4739A",
    "1N4740A", "1N4741A", "1N4742A", "1N4743A", "1N4744A", "1N4745A",
    "1N4746A", "1N4747A", "1N4748A", "1N4749A", "1N4750A", "1N4751A",
    "1N4733",
    "Speaker", "Microphone",
}
_SPICE_TIER3 = {"LM2904", "LM358", "NE555", "NE555D", "TL431"}
_GENERIC_WITH_MODEL = {"R", "C", "L", "D", "Q_NPN", "Q_PNP", "VCC", "GND",
                       "Resistor", "Capacitor", "Inductor", "LED"}

def _component_has_spice_model(lib_id: str) -> bool:
    """Check whether a retrieved component has a corresponding SPICE model."""
    if not lib_id:
        return False
    lid = lib_id.strip()
    if lid in _SPICE_TIER2 or lid in _SPICE_TIER3 or lid in _GENERIC_WITH_MODEL:
        return True
    # Check substring: e.g. "LM7805_TO220" contains "LM78" which is not in our table,
    # but "LM7805" is. So we check if any known model is a prefix/suffix.
    lid_upper = lid.upper()
    for known in _SPICE_TIER2 | _SPICE_TIER3:
        if known.upper() in lid_upper or lid_upper in known.upper():
            return True
    return False


class PipelineRunner:
    """
    Runs the complete EDA pipeline for a single test case.

    Pipeline: Plan → Retrieve → SPICE Simulation → Schematic Generation
    """

    def __init__(self, plan_method, retrieval_method):
        """
        Args:
            plan_method: Plan method instance with generate_plan(user_requirement) -> Dict
            retrieval_method: Retrieval method instance with search_component(query) -> Dict
        """
        self.plan_method = plan_method
        self.retrieval_method = retrieval_method

    def run(self, user_requirement: str, test_case_id: str, base_workspace: Optional[str] = None) -> Dict[str, Any]:
        """
        Run the complete pipeline for a single test case.

        Returns a dict with results at every layer:
        {
            'plan': {...},
            'retrieval': {...},
            'simulation': {...},
            'schematic': {...},
            'success': bool,
            'error': str or None,
        }
        """
        if base_workspace is None:
            base_workspace = str(PROJECT_ROOT / "experiment_results" / "pipeline_workspaces" / "new_runs")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_id = "".join(c if c.isalnum() else "_" for c in test_case_id)
        workspace = os.path.abspath(os.path.join(base_workspace, f"{safe_id}_{timestamp}"))
        os.makedirs(workspace, exist_ok=True)

        result = {
            'test_case_id': test_case_id,
            'workspace': workspace,
            'plan': {'success': False, 'data': None, 'error': None},
            'retrieval': {'success': False, 'data': None, 'error': None},
            'simulation': {'passed': False, 'iterations': 0, 'first_pass': False, 'error': None},
            'schematic': {'generated': False, 'file_path': None, 'error': None},
            'success': False,
            'error': None,
        }

        try:
            # ============================================================
            # Step 1: Plan
            # ============================================================
            print(f"\n{'='*60}")
            print(f"[Pipeline] Step 1: Planning for '{test_case_id}'")
            print(f"{'='*60}")

            plan_data = self.plan_method.generate_plan(user_requirement)

            if plan_data is None or "components" not in plan_data:
                result['plan']['error'] = "Plan generation failed or missing components"
                return result

            result['plan']['success'] = True
            result['plan']['data'] = plan_data

            plan_path = os.path.join(workspace, "planning.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan_data, f, indent=2, ensure_ascii=False)
            print(f"   Plan generated: {len(plan_data.get('components', []))} components")

            # ============================================================
            # Step 2: Retrieve
            # ============================================================
            print(f"\n[Pipeline] Step 2: Retrieval for '{test_case_id}'")

            retrieved_data = self._run_retrieval(plan_data)

            if retrieved_data is None:
                result['retrieval']['error'] = "Retrieval failed"
                return result

            result['retrieval']['success'] = True
            result['retrieval']['data'] = retrieved_data

            # Compute model-match map: which retrieved components have SPICE models
            model_match = {}
            for uid, info in retrieved_data.items():
                if info and info.get("lib_id"):
                    model_match[uid] = _component_has_spice_model(info["lib_id"])
                else:
                    model_match[uid] = False
            result['retrieval']['model_match'] = model_match

            retrieved_path = os.path.join(workspace, "retrieved.json")
            with open(retrieved_path, "w", encoding="utf-8") as f:
                json.dump(retrieved_data, f, indent=2, ensure_ascii=False)

            valid_count = sum(1 for v in retrieved_data.values() if v is not None)
            model_ok = sum(1 for v in model_match.values() if v)
            print(f"   Retrieval done: {valid_count}/{len(retrieved_data)} found, "
                  f"{model_ok}/{len(retrieved_data)} with SPICE models")

            # ============================================================
            # Step 3: SPICE Simulation (iterative)
            # ============================================================
            print(f"\n[Pipeline] Step 3: SPICE Simulation for '{test_case_id}'")

            sim_result, best_spice_code = self._run_simulation(plan_data, retrieved_path, workspace)
            result['simulation'] = sim_result

            if not sim_result['passed']:
                print(f"   Simulation failed after {sim_result['iterations']} iterations")
                return result

            # ============================================================
            # Step 3.5: Translate SPICE to JSON (needed for schematic)
            # ============================================================
            print(f"\n[Pipeline] Step 3.5: Translating SPICE to JSON for '{test_case_id}'")
            json_path = os.path.join(workspace, "Final_Netlist.json")
            try:
                netlist_engine = NetlistEngine()
                netlist_engine.translate_to_json(best_spice_code, retrieved_path, json_path)
                print(f"   Netlist translated: {json_path}")
            except Exception as e:
                result['schematic']['error'] = f"SPICE translation failed: {e}"
                print(f"   Translation failed: {e}")
                return result

            # ============================================================
            # Step 4: Schematic Generation
            # ============================================================
            print(f"\n[Pipeline] Step 4: Schematic Generation for '{test_case_id}'")

            sch_result = self._run_schematic(workspace)
            result['schematic'] = sch_result

            if sch_result['generated']:
                result['success'] = True
                print(f"   Schematic generated: {sch_result['file_path']}")

        except Exception as e:
            result['error'] = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            print(f"   Pipeline error: {result['error']}")

        # Save pipeline result
        result_path = os.path.join(workspace, "pipeline_result.json")
        # Remove non-serializable data for saving
        save_result = {k: v for k, v in result.items() if k != 'plan'}
        save_result['plan'] = {
            'success': result['plan']['success'],
            'num_components': len(result['plan'].get('data', {}).get('components', [])) if result['plan'].get('data') else 0,
            'circuit_type': result['plan'].get('data', {}).get('circuit_type', 'unknown') if result['plan'].get('data') else 'unknown',
        }
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(save_result, f, indent=2, ensure_ascii=False)

        return result

    def _run_retrieval(self, plan_data: Dict) -> Optional[Dict]:
        """Run retrieval for all components in the plan."""
        components = plan_data.get('components', [])
        retrieved_data = {}

        for comp in components:
            uid = comp.get('uid', 'Unknown')
            search_query = comp.get('search_query', '')
            planned_params = comp.get('parameters', {})

            if not search_query:
                retrieved_data[uid] = None
                continue

            try:
                result = self.retrieval_method.search_component(search_query)

                if result and result.get("status") == "success":
                    data = result["data"]
                    retrieved_data[uid] = {
                        "uid": uid,
                        "planned_value": planned_params.get("value", ""),
                        "lib_id": data.get('lib_id', 'Unknown'),
                        "source_library": data.get('source_library', 'Project_Lib'),
                        "pins": data.get('pins', []),
                        "raw_symbol_definition": data.get('raw_symbol_definition', ''),
                        "description": data.get('description', ''),
                        "match_score": data.get('match_score', 0.0),
                    }
                else:
                    retrieved_data[uid] = None
            except Exception as e:
                print(f"   [Retrieval Error] {uid}: {e}")
                retrieved_data[uid] = None

        return retrieved_data

    def _run_simulation(self, plan_data: Dict, retrieved_path: str, workspace: str) -> tuple:
        """Run iterative SPICE simulation. Returns (result_dict, best_spice_code)."""
        result = {
            'passed': False,
            'iterations': 0,
            'first_pass': False,
            'error': None,
            'actual_metrics': {},  # Store parsed simulation metrics for deviation calculation
        }
        best_spice_code = None
        previous_spice = None

        try:
            netlist_engine = NetlistEngine()
            spice_engine = SpiceEngine()

            circuit_type = plan_data.get("circuit_type", "filter")
            expert = ExpertFactory.get_expert(circuit_type)

            MAX_ITERATIONS = 8
            current_feedback = None
            best_spice_code = None

            for iteration in range(1, MAX_ITERATIONS + 1):
                result['iterations'] = iteration

                # Generate SPICE netlist
                try:
                    spice_code = netlist_engine.generate_spice(
                        plan_data, expert, iteration, best_spice_code, current_feedback,
                        retrieved_path=retrieved_path
                    )
                except Exception as e:
                    result['error'] = f"Netlist generation failed at iter {iteration}: {e}"
                    break

                # Detect stale iteration (same SPICE code = no progress)
                if previous_spice and spice_code.strip() == previous_spice.strip():
                    result['error'] = f"No change in SPICE code at iteration {iteration} — same code as before"
                    print(f"   Stale iteration detected — aborting simulation loop")
                    break

                # Evaluate with Ngspice
                try:
                    passed, feedback, actual_metrics = spice_engine.evaluate(
                        spice_code, plan_data, expert, workspace, iteration,
                        use_hard_threshold=True
                    )
                except Exception as e:
                    result['error'] = f"Simulation evaluation failed at iter {iteration}: {e}"
                    break

                previous_spice = spice_code
                best_spice_code = spice_code

                if passed:
                    result['passed'] = True
                    result['actual_metrics'] = actual_metrics
                    if iteration == 1:
                        result['first_pass'] = True
                    print(f"   Simulation PASSED at iteration {iteration}")
                    break
                else:
                    current_feedback = feedback
                    result['actual_metrics'] = actual_metrics  # Store even failed metrics
                    if iteration == MAX_ITERATIONS:
                        result['error'] = f"Max iterations ({MAX_ITERATIONS}) reached without convergence"
                        print(f"   Simulation FAILED after {MAX_ITERATIONS} iterations")

        except Exception as e:
            result['error'] = f"Simulation error: {e}"

        return result, best_spice_code

    def _run_schematic(self, workspace: str) -> Dict:
        """Generate KiCad schematic from simulation results."""
        result = {
            'generated': False,
            'file_path': None,
            'error': None,
        }

        try:
            from generate_schematic import SchematicGenerator

            json_path = os.path.join(workspace, "Final_Netlist.json")
            updated_retrieved_path = json_path.replace('.json', '_updated_retrieved.json')

            if os.path.exists(updated_retrieved_path):
                final_retrieved_path = updated_retrieved_path
            else:
                retrieved_path = os.path.join(workspace, "retrieved.json")
                final_retrieved_path = retrieved_path

            # Need to generate Final_Netlist.json first via translate_to_json
            # This is handled inside the simulation loop via the netlist engine
            # We check if it exists, and if not, we can't generate schematic
            if not os.path.exists(json_path):
                result['error'] = "Final_Netlist.json not found - simulation may have failed to produce output"
                return result

            sch_path = os.path.join(workspace, "Schematic_Final.kicad_sch")
            sch_gen = SchematicGenerator()
            sch_gen.load_data(final_retrieved_path, json_path)
            sch_gen.process_and_layout()
            sch_gen.route_connections()
            sch_gen.generate_kicad_file(sch_path)

            if os.path.exists(sch_path):
                result['generated'] = True
                result['file_path'] = sch_path
                print(f"   Schematic saved: {sch_path}")
            else:
                result['error'] = "Schematic file was not created"

        except Exception as e:
            result['error'] = f"Schematic generation error: {e}\n{traceback.format_exc()}"

        return result
