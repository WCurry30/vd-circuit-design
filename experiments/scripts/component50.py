"""Component study: paired planning candidates and deterministic retrieval ablations."""
import argparse
import ast
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def parse_plan(planner, raw):
    if not raw:
        return None
    cleaned = planner._clean_and_repair_json(raw)
    try:
        plan = json.loads(cleaned)
    except (ValueError, TypeError):
        try:
            plan = ast.literal_eval(cleaned)
        except (ValueError, SyntaxError):
            return None
    if not isinstance(plan, dict) or not isinstance(plan.get('components'), list):
        return None
    if not plan['components'] or any(not isinstance(c, dict) or not isinstance(c.get('search_query'), str)
                                     or not c['search_query'].strip() for c in plan['components']):
        return None
    return plan


def score_candidate(planner, summary, plan):
    # Same semantic and lexical score as CircuitPlannerFinal.generate_plan.
    semantic = planner.semantic_prm_score(summary, plan['cleaned'])
    text = str(plan['data']['components']).lower()
    bonus = .15 if 'lm2904' in text else .02 if 'amplifier' in text or 'opamp' in text else 0
    bonus += .02 if 'capacitor' in text or 'cap' in text else 0
    bonus += .02 if 'resistor' in text or 'res' in text else 0
    bonus += .03 if 'speaker' in text or 'mic' in text else 0
    return semantic + bonus


def canonical(label):
    return label.rsplit(':', 1)[-1].strip().lower()


def covered(gold, bindings):
    ids = {canonical(b['lib_id']) for b in bindings}
    if not gold.startswith('@'):
        return canonical(gold) in ids
    rules = {
        '@resistor': r'^(r|r_small|r_us)$', '@capacitor': r'^c($|_)',
        '@ground': r'^(gnd|gn[dap]a|gn[dap]d)$', '@power': r'^(vcc|vdd|vss|vee|\+\d.*v|\-\d.*v)$',
        '@opamp': r'^(lm2904|lm358|lm324|tl07[124]|ne5532|opamp).*',
        '@npn': r'^(2n2222a?|2n3904|bc547.*|q_npn.*|npn)$',
        '@nmos': r'^(2n700[02]|bss138.*|irf.*|q_nmos.*|nmos|eda_nmos)$',
        '@zener': r'^(1n47\d\d[a]?|d_zener.*|zener)$',
        '@connector': r'^(conn_|connector|screw_terminal).*',
        '@microphone': r'^(microphone|mic).*', '@led': r'^led($|_)',
    }
    return any(re.match(rules[gold], label) for label in ids)


class NoDirectLookup:
    """Disable the second lib_id exact path while retaining vector retrieval."""
    def __init__(self, collection):
        self.collection = collection
    def get(self, **kwargs):
        if 'lib_id' in (kwargs.get('where') or {}):
            return {'ids': [], 'metadatas': []}
        return self.collection.get(**kwargs)
    def __getattr__(self, name):
        return getattr(self.collection, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--env', type=Path, required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--preflight', action='store_true')
    args = ap.parse_args()
    root = args.root.resolve()
    sys.path[:0] = [str(root / 'framework'), str(root / 'support')]
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='2', TOKENIZERS_PARALLELISM='false')
    from alignment_config import MODELS, provider_blocks
    p = provider_blocks(args.env)[MODELS[args.model]]
    for cached in (root/'results'/args.model).glob('*/full/reused_provider.json'):
        prior=json.loads(cached.read_text())
        if prior['requested_model'] != p['MODEL'] or prior['endpoint_sha256'] != hashlib.sha256(p['URL'].encode()).hexdigest():
            raise RuntimeError('reused provider configuration differs: '+str(cached))
    os.environ.update(EDA_API_KEY=p['KEY'], EDA_BASE_URL=p['URL'], EDA_MODEL_NAME=p['MODEL'],
                      EDA_DISABLE_THINKING='1' if args.model in {'v4','qwen36'} else '0')
    from alignment_runner import ResponseLedger
    # Preserve requested and returned identifiers; provider aliases are reported, not rewritten.
    ledger = ResponseLedger(disable_qwen_thinking=args.model == 'qwen36')
    ledger.install()
    from circuit_planner_v import CircuitPlannerFinal
    from retriever_final_merged import IntelligentRetriever
    import torch
    planner = CircuitPlannerFinal()
    if planner.prm_model is None:
        raise RuntimeError('required ranking encoder unavailable')
    retriever = IntelligentRetriever(str(root / 'framework/chroma_db'))
    if torch.cuda.is_available():
        planner.prm_model.to('cuda'); retriever.model.to('cuda')
    if retriever.collection.count() == 0:
        raise RuntimeError('empty component catalog')
    planner.system_prompt = (root / 'planning_system.txt').read_text()
    if args.preflight:
        result = retriever.search_component('Resistor', expected_query='Resistor')
        assert result['status'] == 'success', result
        print(json.dumps({'preflight':'passed','device':str(planner.prm_model.device),
                          'catalog_count':retriever.collection.count()}))
        return
    tasks = json.loads((root / 'tasks.json').read_text())
    output = root / 'results' / args.model
    status = {'model': args.model, 'status': 'running', 'pid': os.getpid(), 'completed': 0, 'total': len(tasks)*4}
    save(output / 'status.json', status)
    try:
        for index, task in enumerate(tasks):
            unit = output / task['id']
            candidates_by_arm = {}
            for arm in ('full','no_elaboration'):
                path = unit / arm / 'candidates.json'
                if path.exists():
                    candidate_data = json.loads(path.read_text())
                else:
                    seed = task['seed']
                    with ledger.scope(unit / arm / 'calls'):
                        summary = (planner._elaborate_requirement(task['user_requirement'], seed=seed)
                                   if arm == 'full' else task['user_requirement'])
                        prompt = ('Original requirement (binding):\n' + task['user_requirement']
                                  + '\nComponent-role summary (advisory):\n' + summary)
                        candidates = []
                        for i in range(3):
                            temperature = .1 + i * .1
                            raw = planner._generate_candidate(prompt, temperature, seed=seed+i+1)
                            plan = parse_plan(planner, raw)
                            item = {'index':i,'data':plan,'raw':raw}
                            if plan:
                                item['cleaned'] = planner._clean_and_repair_json(raw)
                                item['score'] = score_candidate(planner, summary, item)
                            candidates.append(item)
                    candidate_data = {'summary':summary,'candidates':candidates}
                    save(path, candidate_data)
                candidates_by_arm[arm] = candidate_data
            for arm in ('full','no_elaboration','no_rank','no_exact_match'):
                result_path = unit / arm / 'record.json'
                if result_path.exists():
                    status['completed'] += 1
                    continue
                data = candidates_by_arm['no_elaboration' if arm == 'no_elaboration' else 'full']
                valid = [c for c in data['candidates'] if c['data']]
                selected = (next((c for c in data['candidates'] if c['index']==0), None) if arm=='no_rank'
                            else max(valid,key=lambda c:c['score']) if valid else None)
                plan = selected['data'] if selected else None
                retrieval_path = unit / arm / 'retrieved.json'
                retrieved = []
                if plan:
                    original = retriever.collection
                    retriever.enable_exact_match = arm != 'no_exact_match'
                    if arm == 'no_exact_match': retriever.collection = NoDirectLookup(original)
                    try:
                        for c in plan['components']:
                            query = c['search_query']
                            retrieved.append({'query':query, 'result':retriever.search_component(query,expected_query=query)})
                    finally:
                        retriever.collection = original; retriever.enable_exact_match = True
                save(retrieval_path, retrieved)
                bindings = [r['result']['data'] for r in retrieved if r['result']['status']=='success']
                matched = [g for g in task['golden_components'] if covered(g,bindings)]
                save(result_path, {'model':args.model,'task':task['id'],'stratum':task['stratum'],'arm':arm,
                     'format_parse':bool(plan),'selected_index':selected['index'] if selected else None,
                     'component_recall':len(matched)/len(task['golden_components']),
                     'retrieval_hit_rate':len(bindings)/len(retrieved) if retrieved else 0,
                     'matched':matched,'golden_components':task['golden_components'],
                     'planned_components':len(retrieved),'retrieved_components':len(bindings),
                     'candidate_source':'no_elaboration' if arm=='no_elaboration' else 'full'})
                status['completed'] += 1
                save(output / 'status.json',status)
        status['status']='completed'
    except BaseException as error:
        status.update(status='needs_attention',error_type=type(error).__name__,error=str(error)[:300])
        raise
    finally:
        status['updated_unix']=time.time();save(output/'status.json',status)


if __name__ == '__main__':
    main()
